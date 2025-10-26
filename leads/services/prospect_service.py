"""
Prospect service for managing prospects, conversations, and messages.
"""
import logging
from typing import Optional, Tuple, Dict, Any, Union
from django.utils import timezone
from ..models import Prospect, Conversation, Message, PendingResponse
from ..schemas import IntentData as CustomerIntent

logger = logging.getLogger(__name__)


def create_or_get_prospect(email: str, first_name: str, phone: str = None) -> Prospect:
    """
    Create a new prospect or return existing one.
    Uses get_or_create to handle uniqueness.
    """
    try:
        prospect, created = Prospect.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'phone': phone
            }
        )
        
        if created:
            logger.info(f"Created new prospect: {first_name} ({email})")
        else:
            logger.info(f"Found existing prospect: {first_name} ({email})")
            # Update first_name and phone if they changed
            if prospect.first_name != first_name or prospect.phone != phone:
                prospect.first_name = first_name
                prospect.phone = phone
                prospect.save()
                logger.info(f"Updated prospect info for {email}")
        
        return prospect
        
    except Exception as e:
        logger.error(f"Error creating/getting prospect: {e}")
        raise


def create_conversation(prospect: Prospect, thread_subject: str) -> Conversation:
    """
    Create a new conversation or return existing one.
    Thread subject + prospect email ensures uniqueness.
    """
    try:
        conversation, created = Conversation.objects.get_or_create(
            prospect=prospect,
            thread_subject=thread_subject,
            defaults={
                'status': 'active',
                'last_message_at': timezone.now()
            }
        )
        
        if created:
            logger.info(f"Created new conversation for {prospect.first_name}")
        else:
            logger.info(f"Found existing conversation for {prospect.first_name}")
            # If conversation was cold/complete, reopen it
            if conversation.status in ['cold', 'complete']:
                conversation.status = 'active'
                conversation.outcome = None
                conversation.last_message_at = timezone.now()
                conversation.save()
                logger.info(f"Reopened conversation for {prospect.first_name}")
        
        return conversation
        
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise


def log_message(conversation: Conversation, role: str, content: str) -> Message:
    """
    Create a new message in the conversation.
    Updates conversation last_message_at.
    """
    try:
        message = Message.objects.create(
            conversation=conversation,
            role=role,
            content=content
        )
        
        # Update conversation timestamp
        conversation.last_message_at = timezone.now()
        conversation.save()
        
        logger.info(f"Logged {role} message for conversation {conversation.id}")
        return message
        
    except Exception as e:
        logger.error(f"Error logging message: {e}")
        raise

def update_conversation_intent(
    conversation_id: int,
    intent_data: Dict[str, Any]
) -> Conversation:
    """
    Update conversation with LLM-detected intent using Pydantic validation.
    """
    try:
        # Use Pydantic's parse_obj to accept dicts, mapping-likes, or
        # already-instantiated Pydantic models. This centralizes parsing
        # and simplifies error handling compared to manual isinstance checks.
        try:
            validated_intent = CustomerIntent.parse_obj(intent_data)
        except Exception as exc:
            logger.error("Failed to parse intent_data into CustomerIntent: %s", exc)
            raise
        
        conversation = Conversation.objects.get(id=conversation_id)
        
        # Store full LLM analysis (use Pydantic's json() method)
        conversation.llm_determined_intent = validated_intent.json()

        # Store simplified version for quick filtering (guard missing intent)
        conversation.intent = (
            validated_intent.primary_intent.value
            if validated_intent.primary_intent is not None
            else None
        )
        
        conversation.save()
        
        # Log safely even if primary_intent is None
        primary_label = (
            validated_intent.primary_intent.value
            if validated_intent.primary_intent is not None
            else "(none)"
        )
        logger.info(
            "Updated intent for conversation %s: %s (confidence: %.2f)",
            conversation_id,
            primary_label,
            validated_intent.confidence if validated_intent.confidence is not None else 0.0,
        )
        
        return conversation
        
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error updating conversation intent: {e}")
        raise

def update_conversation_status(
    conversation_id: int,
    status: str = None,
    outcome: str = None
) -> Conversation:
    """
    Update conversation status and/or outcome.
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        
        if status:
            conversation.status = status
        if outcome:
            conversation.outcome = outcome
        
        conversation.save()
        logger.info(f"Updated conversation {conversation_id}: status={status}, outcome={outcome}")
        
        return conversation
        
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error updating conversation status: {e}")
        raise


def create_pending_response(
    conversation: Conversation,
    llm_content: str,
    llm_provider: str = 'grok'
) -> PendingResponse:
    """
    Create a new pending response for human approval.
    """
    try:
        pending = PendingResponse.objects.create(
            conversation=conversation,
            llm_content=llm_content,
            llm_provider=llm_provider,
            status='pending'
        )
        
        logger.info(f"Created pending response for conversation {conversation.id}")
        return pending
        
    except Exception as e:
        logger.error(f"Error creating pending response: {e}")
        raise


def approve_response(pending_id: int, edited_content: str = None) -> Tuple[bool, str]:
    """
    Approve a pending response and mark it for sending.
    If edited_content provided, use that instead of original.
    Returns (success, message).
    """
    try:
        pending = PendingResponse.objects.get(id=pending_id)
        
        if edited_content:
            pending.edited_content = edited_content
            pending.status = 'edited'
        else:
            pending.status = 'approved'
        
        pending.actioned_at = timezone.now()
        pending.save()
        
        logger.info(f"Approved pending response {pending_id}")
        return True, "Response approved"
        
    except PendingResponse.DoesNotExist:
        logger.error(f"Pending response {pending_id} not found")
        return False, "Pending response not found"
    except Exception as e:
        logger.error(f"Error approving response: {e}")
        return False, str(e)


def reject_response(pending_id: int) -> Tuple[bool, str]:
    """
    Reject a pending response.
    Returns (success, message).
    """
    try:
        pending = PendingResponse.objects.get(id=pending_id)
        pending.status = 'rejected'
        pending.actioned_at = timezone.now()
        pending.save()
        
        logger.info(f"Rejected pending response {pending_id}")
        return True, "Response rejected"
        
    except PendingResponse.DoesNotExist:
        logger.error(f"Pending response {pending_id} not found")
        return False, "Pending response not found"
    except Exception as e:
        logger.error(f"Error rejecting response: {e}")
        return False, str(e)


def get_conversation_by_thread(prospect_email: str, thread_subject: str) -> Optional[Conversation]:
    """
    Find conversation by prospect email and thread subject.
    """
    try:
        prospect = Prospect.objects.get(email=prospect_email)
        conversation = Conversation.objects.get(
            prospect=prospect,
            thread_subject=thread_subject
        )
        return conversation
    except (Prospect.DoesNotExist, Conversation.DoesNotExist):
        return None
