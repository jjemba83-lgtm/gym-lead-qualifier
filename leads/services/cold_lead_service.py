"""
Cold lead service for detecting and marking conversations that have gone cold.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from ..models import Conversation, SystemConfig

logger = logging.getLogger(__name__)


def check_cold_leads() -> list:
    """
    Check for conversations that have gone cold (no response within threshold).
    Mark them as 'cold' and return list of newly marked conversations.
    """
    try:
        config = SystemConfig.load()
        
        # Skip if cold lead notifications are disabled
        if not config.cold_lead_notifications_enabled:
            logger.info("Cold lead notifications are disabled")
            return []
        
        # Calculate cutoff time
        threshold_days = config.cold_lead_threshold_days
        cutoff_time = timezone.now() - timedelta(days=threshold_days)
        
        # Find active conversations with last message before cutoff
        # Only mark as cold if the last message was FROM the sales rep (sent)
        cold_conversations = []
        
        active_convs = Conversation.objects.filter(
            status='active',
            last_message_at__lt=cutoff_time
        )
        
        for conv in active_convs:
            # Check if last message was from sales rep
            last_message = conv.messages.last()
            if last_message and last_message.role == 'sent':
                # This conversation went cold (prospect didn't respond)
                conv.status = 'cold'
                conv.save()
                cold_conversations.append(conv)
                logger.info(f"Marked conversation {conv.id} as cold")
        
        logger.info(f"Found {len(cold_conversations)} cold leads")
        return cold_conversations
        
    except Exception as e:
        logger.error(f"Error checking cold leads: {e}")
        return []


def should_notify_cold_leads() -> bool:
    """
    Check if cold lead notifications are enabled.
    """
    try:
        config = SystemConfig.load()
        return config.cold_lead_notifications_enabled
    except Exception as e:
        logger.error(f"Error checking notification status: {e}")
        return False
