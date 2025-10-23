"""
Management command to poll Gmail for new prospects and replies.
Run this command every 5 minutes via cron or manually.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from leads.services import email_service, prospect_service, llm_service
from leads.models import Conversation, SystemConfig


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
                    
                    # Generate initial LLM response
                    self.stdout.write(f"Generating response for {prospect.first_name}...")
                    response_text, provider = llm_service.generate_response(conversation.id)
                    
                    # Create pending response for approval
                    prospect_service.create_pending_response(
                        conversation=conversation,
                        llm_content=response_text,
                        llm_provider=provider
                    )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ Processed new prospect: {prospect.first_name} ({prospect.email})"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Error processing prospect {prospect_data.get('email')}: {str(e)}"
                ))
        
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
                        # Update conversation outcome
                        prospect_service.update_conversation_status(
                            conversation.id,
                            status='complete',
                            outcome=outcome
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f"✓ Conversation completed for {conversation.prospect.first_name}: {outcome}"
                        ))
                        continue
                    
                    # Check message limit
                    config = SystemConfig.load()
                    if conversation.message_count() >= config.max_message_exchanges * 2:  # *2 for back-and-forth
                        prospect_service.update_conversation_status(
                            conversation.id,
                            status='complete',
                            outcome='reached_message_limit'
                        )
                        self.stdout.write(self.style.WARNING(
                            f"⚠ Message limit reached for {conversation.prospect.first_name}"
                        ))
                        continue
                    
                    # Generate LLM response
                    self.stdout.write(f"Generating response for {conversation.prospect.first_name}...")
                    response_text, provider = llm_service.generate_response(conversation.id)
                    
                    # Create pending response
                    prospect_service.create_pending_response(
                        conversation=conversation,
                        llm_content=response_text,
                        llm_provider=provider
                    )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ Processed reply from {conversation.prospect.first_name}"
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Error processing reply: {str(e)}"
                ))
        
        if not replies:
            self.stdout.write("No new replies found.")
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Polling complete! Processed {len(new_prospects)} new prospects and {len(replies)} replies."
        ))
