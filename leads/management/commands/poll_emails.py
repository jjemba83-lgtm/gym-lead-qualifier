"""
Management command to poll Gmail for new prospects and replies.
Run this command every 5 minutes via cron or manually.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from leads.services import email_service, prospect_service
from leads.services.lead_scoring_service import calculate_lead_score
from leads.models import Conversation, SystemConfig
import logging
from leads.services.llm_service import LLMService

logger = logging.getLogger(__name__)
#instantiate the llm service
llm_service = LLMService()

# Standard opening template - no LLM needed!
STANDARD_OPENING_TEMPLATE = """Hi {first_name}! Thanks for reaching out about our boxing fitness gym. To help match you with the right class, I have a few quick questions:

1. What's your main fitness goal? (weight loss, stress relief, learn technique, general fitness, etc.)
2. How often do you currently exercise?
3. Any concerns about high-intensity training?

Looking forward to getting you started!"""


class Command(BaseCommand):
    help = 'Poll Gmail for new prospect notifications and replies'

    def handle(self, *args, **options):
        self.stdout.write("Starting email polling...")
        
        # Check for new prospect notifications
        self.stdout.write("Checking for new prospect notifications...")
        new_prospects = email_service.fetch_new_prospect_notifications()
        
        for prospect_data in new_prospects:
            try:
                with transaction.atomic():
                    # Create or get prospect
                    prospect = prospect_service.create_or_get_prospect(
                        email=prospect_data.get('email'),
                        first_name=prospect_data.get('first_name'),
                        phone=prospect_data.get('phone')
                    )
                    
                    # Create conversation
                    conversation = prospect_service.create_conversation(
                        prospect=prospect,
                        thread_subject=prospect_data.get('thread_subject')
                    )
                    
                    # Use template for initial response - NO LLM CALL!
                    response_text = STANDARD_OPENING_TEMPLATE.format(
                        first_name=prospect.first_name
                    )
                    
                    # Create pending response for approval
                    prospect_service.create_pending_response(
                        conversation=conversation,
                        llm_content=response_text,
                        llm_provider='template'  # Mark as template, not LLM
                    )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ Processed new prospect: {prospect.first_name} ({prospect.email})"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Error processing prospect {prospect_data.get('email')}: {str(e)}"
                ))
                logger.exception(f"Error processing prospect {prospect_data.get('email')}")
        
        if not new_prospects:
            self.stdout.write("No new prospect notifications found.")
        
        # Check for replies to active conversations
        self.stdout.write("\nChecking for replies to active conversations...")
        
        active_conversations = Conversation.objects.filter(status='active').select_related('prospect')
        conv_data = [
            {
                'thread_subject': conv.thread_subject,
                'prospect_email': conv.prospect.email,
                'conversation_id': conv.id
            }
            for conv in active_conversations
        ]
        
        replies = email_service.fetch_replies_to_conversations(conv_data)
        
        for reply_data in replies:
            try:
                with transaction.atomic():
                    # Find conversation
                    conversation = prospect_service.get_conversation_by_thread(
                        prospect_email=reply_data['prospect_email'],
                        thread_subject=reply_data['thread_subject']
                    )
                    
                    if not conversation:
                        self.stdout.write(self.style.WARNING(
                            f"⚠ Could not find conversation for {reply_data['prospect_email']}"
                        ))
                        continue
                    
                    # Log prospect's message
                    prospect_service.log_message(
                        conversation=conversation,
                        role='prospect',
                        content=reply_data['reply_content']
                    )
                    
                    # Check if conversation should end
                    should_end, outcome = llm_service.detect_conversation_outcome(
                        conversation.id,
                        reply_data['reply_content']
                    )
                    
                    if should_end and outcome:
                        # Calculate lead score before closing
                        lead_score = calculate_lead_score(conversation)
                        
                        # Generate closing message
                        self.stdout.write(f"Generating closing message for {conversation.prospect.first_name}...")
                        closing_message, provider = llm_service.generate_closing_message(
                            conversation.id,
                            outcome
                        )
                        
                        # Create pending response for the closing message
                        prospect_service.create_pending_response(
                            conversation=conversation,
                            llm_content=closing_message,
                            llm_provider=provider
                        )
                        
                        # Update conversation outcome (but keep active until closing is sent)
                        prospect_service.update_conversation_status(
                            conversation.id,
                            status='active',  # Keep active until closing is sent
                            outcome=outcome
                        )
                        
                        # Send hot lead notification if score is high
                        if lead_score['is_hot']:
                            self.stdout.write(self.style.SUCCESS(
                                f"🔥 HOT LEAD DETECTED: {conversation.prospect.first_name} "
                                f"(Score: {lead_score['score']:.0%})"
                            ))
                            
                            # Send hot lead email notification
                            if hasattr(settings, 'SALES_TEAM_EMAIL'):
                                try:
                                    email_service.send_hot_lead_notification(
                                        conversation=conversation,
                                        lead_score=lead_score
                                    )
                                    self.stdout.write(self.style.SUCCESS(
                                        f"✓ Hot lead notification sent to {settings.SALES_TEAM_EMAIL}"
                                    ))
                                except Exception as e:
                                    self.stdout.write(self.style.ERROR(
                                        f"✗ Failed to send hot lead notification: {str(e)}"
                                    ))
                        
                        self.stdout.write(self.style.SUCCESS(
                            f"✓ Conversation ready to close for {conversation.prospect.first_name}: {outcome}"
                        ))
                        continue
                    
                    # Check message limit
                    config = SystemConfig.load()
                    if conversation.message_count() >= config.max_message_exchanges * 2:  # *2 for back-and-forth
                        # Generate closing message for message limit
                        closing_message, provider = llm_service.generate_closing_message(
                            conversation.id,
                            'reached_message_limit'
                        )
                        
                        prospect_service.create_pending_response(
                            conversation=conversation,
                            llm_content=closing_message,
                            llm_provider=provider
                        )
                        
                        prospect_service.update_conversation_status(
                            conversation.id,
                            status='active',  # Keep active until closing is sent
                            outcome='reached_message_limit'
                        )
                        
                        self.stdout.write(self.style.WARNING(
                            f"⚠ Message limit reached for {conversation.prospect.first_name}"
                        ))
                        continue
                    
                    # Generate LLM response for ongoing conversation
                    self.stdout.write(f"Generating response for {conversation.prospect.first_name}...")
                    response_text, provider = llm_service.generate_response(conversation.id)
                    
                    
                    # Create pending response
                    prospect_service.create_pending_response(
                        conversation=conversation,
                        llm_content=response_text.response,
                        llm_provider=provider
                    )

                    #update intent
                    prospect_service.update_conversation_intent(
                        conversation.id,
                        response_text.intent_data
                    )
                    
                    # Calculate and log lead score for monitoring
                    lead_score = calculate_lead_score(conversation)
                    if lead_score['score'] >= 0.5:
                        self.stdout.write(
                            f"  Lead score: {lead_score['score']:.0%} - "
                            f"{', '.join(lead_score['factors'][:2])}"
                        )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ Processed reply from {conversation.prospect.first_name}"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Error processing reply: {str(e)}"
                ))
                logger.exception(f"Error processing reply from {reply_data.get('prospect_email')}")
        
        if not replies:
            self.stdout.write("No new replies found.")
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Polling complete! Processed {len(new_prospects)} new prospects and {len(replies)} replies."
        ))
