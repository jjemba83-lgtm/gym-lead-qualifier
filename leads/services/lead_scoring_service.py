"""
Lead scoring service for identifying hot leads based on conversation patterns.
"""
import logging
import json
from datetime import timedelta
from typing import Dict, Optional
from leads.models import Conversation, Message

logger = logging.getLogger(__name__)


def calculate_lead_score(conversation: Conversation) -> Dict:
    """
    Calculate lead score based on multiple factors including intent detection.
    
    Returns dict with:
    - score: 0.0 to 1.0
    - factors: list of scoring factors
    - is_hot: boolean (score >= 0.7)
    - intent: detected intent data if available
    - recommendations: list of follow-up actions
    """
    score = 0.4  # Base score for any engaged lead
    factors = []
    recommendations = []
    
    # 1. Intent Detection (highest weight - up to 0.35 points)
    intent_data = extract_intent_from_conversation(conversation)
    if intent_data:
        confidence = intent_data.get('confidence_level', 0)
        detected_intent = intent_data.get('detected_intent', '')
        
        if confidence > 0.8:
            score += 0.25
            factors.append(f"Clear intent: {detected_intent}")
            
            # High-value intents get bonus
            high_value_intents = ['weight_loss', 'stress_relief_mental_health', 'learn_boxing_technique']
            if detected_intent in high_value_intents:
                score += 0.1
                factors.append("High-value goal")
                recommendations.append("Premium package opportunity")
        elif confidence > 0.6:
            score += 0.15
            factors.append(f"Moderate intent: {detected_intent}")
        elif confidence > 0.4:
            score += 0.05
            factors.append("Unclear intent")
    
    # 2. Response Time (up to 0.2 points)
    first_reply = conversation.messages.filter(role='prospect').first()
    if first_reply:
        time_to_respond = (first_reply.created_at - conversation.created_at).total_seconds()
        
        if time_to_respond < 300:  # Under 5 minutes
            score += 0.2
            factors.append("Very fast response (<5 min)")
            recommendations.append("Call immediately - high engagement")
        elif time_to_respond < 900:  # Under 15 minutes
            score += 0.15
            factors.append("Fast response (<15 min)")
            recommendations.append("Priority follow-up")
        elif time_to_respond < 3600:  # Under 1 hour
            score += 0.1
            factors.append("Quick response (<1 hr)")
        elif time_to_respond < 86400:  # Under 24 hours
            score += 0.05
            factors.append("Same-day response")
    
    # 3. Contact Information Completeness (up to 0.1 points)
    if conversation.prospect.phone:
        score += 0.1
        factors.append("Phone provided")
        recommendations.append("SMS follow-up available")
    
    # 4. Conversation Outcome (up to 0.15 points)
    if conversation.outcome == 'agreed_to_free_class':
        score += 0.15
        factors.append("Agreed to free class!")
        recommendations.append("Schedule ASAP - ready to convert")
    elif conversation.outcome == 'not_interested':
        score -= 0.2  # Penalize not interested
        factors.append("Not interested")
        recommendations.append("Add to nurture campaign")
    
    # 5. Engagement Level (up to 0.15 points)
    message_count = conversation.message_count()
    prospect_messages = conversation.messages.filter(role='prospect').count()
    
    if prospect_messages >= 3:
        score += 0.1
        factors.append(f"High engagement ({prospect_messages} messages)")
    elif prospect_messages >= 2:
        score += 0.05
        factors.append(f"Good engagement ({prospect_messages} messages)")
    
    # Check for long messages (shows investment)
    long_messages = conversation.messages.filter(role='prospect').filter(
        content__regex=r'.{100,}'  # Messages over 100 chars
    ).count()
    if long_messages > 0:
        score += 0.05
        factors.append("Detailed responses")
    
    # 6. Buying Signals in Content (up to 0.1 points)
    buying_signals = detect_buying_signals(conversation)
    if buying_signals:
        score += 0.1
        factors.extend(buying_signals['factors'])
        if 'schedule' in buying_signals.get('keywords', []):
            recommendations.append("Ready to schedule - mention available times")
    
    # 7. Time of Day Bonus (up to 0.05 points)
    # People who respond during business hours are often more serious
    if first_reply:
        reply_hour = first_reply.created_at.hour
        if 9 <= reply_hour <= 17:  # Business hours
            score += 0.05
            factors.append("Business hours response")
    
    # Cap score at 1.0
    final_score = min(score, 1.0)
    
    # Determine if hot lead
    is_hot = final_score >= 0.7
    
    # Generate score interpretation
    if final_score >= 0.8:
        interpretation = "🔥 VERY HOT - Contact immediately!"
    elif final_score >= 0.7:
        interpretation = "🌟 HOT - Priority follow-up needed"
    elif final_score >= 0.6:
        interpretation = "♨️ WARM - Good potential"
    elif final_score >= 0.4:
        interpretation = "🌡️ LUKEWARM - Needs nurturing"
    else:
        interpretation = "❄️ COLD - Low priority"
    
    return {
        'score': final_score,
        'factors': factors,
        'is_hot': is_hot,
        'intent': intent_data,
        'recommendations': recommendations,
        'interpretation': interpretation,
        'reason': ', '.join(factors[:3]) if factors else 'Standard lead'
    }


def extract_intent_from_conversation(conversation: Conversation) -> Optional[Dict]:
    """
    Extract intent detection from conversation messages.
    Looks for the INTENT_DETECTION JSON in LLM messages.
    """
    try:
        # Look through recent LLM messages for intent detection
        llm_messages = conversation.messages.filter(
            role__in=['llm_generated', 'sent']
        ).order_by('-created_at')[:5]  # Check last 5 LLM messages
        
        for message in llm_messages:
            content = message.content
            
            # Look for INTENT_DETECTION marker
            if 'INTENT_DETECTION:' in content:
                # Extract JSON
                json_start = content.find('{', content.find('INTENT_DETECTION:'))
                json_end = content.rfind('}') + 1
                
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    intent_data = json.loads(json_str)
                    
                    logger.info(f"Found intent for conversation {conversation.id}: "
                              f"{intent_data.get('detected_intent')} "
                              f"(confidence: {intent_data.get('confidence_level')})")
                    return intent_data
        
        # If no explicit intent detection, try to infer from conversation outcome
        if conversation.outcome == 'agreed_to_free_class':
            return {
                'detected_intent': 'wants_free_class',
                'confidence_level': 0.9,
                'reasoning': 'Agreed to free class',
                'best_time_to_visit': None
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting intent from conversation {conversation.id}: {e}")
        return None


def detect_buying_signals(conversation: Conversation) -> Optional[Dict]:
    """
    Detect buying signals in prospect messages.
    """
    buying_keywords = {
        'schedule': ['when', 'what time', 'schedule', 'book', 'sign up', 'available'],
        'price': ['cost', 'price', 'how much', 'fee', 'payment', 'afford'],
        'commitment': ['ready', 'start', 'begin', 'join', 'lets do', "let's do", 'sounds good'],
        'urgency': ['today', 'tomorrow', 'this week', 'soon', 'asap', 'right away'],
        'comparison': ['better than', 'compared to', 'vs', 'other gyms', 'why you']
    }
    
    factors = []
    detected_keywords = []
    
    # Check recent prospect messages
    recent_messages = conversation.messages.filter(role='prospect').order_by('-created_at')[:3]
    
    for message in recent_messages:
        content_lower = message.content.lower()
        
        for signal_type, keywords in buying_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    if signal_type not in detected_keywords:
                        detected_keywords.append(signal_type)
                        
                        if signal_type == 'schedule':
                            factors.append("Asking about scheduling")
                        elif signal_type == 'price':
                            factors.append("Price conscious (address value)")
                        elif signal_type == 'commitment':
                            factors.append("Shows commitment")
                        elif signal_type == 'urgency':
                            factors.append("Urgent timeline")
                        elif signal_type == 'comparison':
                            factors.append("Comparing options")
                    break
    
    if factors:
        return {
            'factors': factors,
            'keywords': detected_keywords
        }
    
    return None


def get_lead_score_emoji(score: float) -> str:
    """
    Get visual representation of lead score.
    """
    if score >= 0.8:
        return "🔥🔥🔥"
    elif score >= 0.7:
        return "🔥🔥"
    elif score >= 0.6:
        return "🔥"
    elif score >= 0.5:
        return "♨️"
    elif score >= 0.4:
        return "🌡️"
    else:
        return "❄️"


def save_lead_score(conversation: Conversation, score_data: Dict) -> None:
    """
    Save lead score to database (for future LeadScore model).
    For now, logs the score.
    """
    logger.info(
        f"Lead Score for {conversation.prospect.first_name}: "
        f"{score_data['score']:.0%} - {score_data['interpretation']}"
    )
    
    # TODO: When LeadScore model is added:
    # LeadScore.objects.update_or_create(
    #     conversation=conversation,
    #     defaults={
    #         'score': score_data['score'],
    #         'factors': score_data['factors'],
    #         'is_hot': score_data['is_hot'],
    #         'intent_data': score_data.get('intent'),
    #         'calculated_at': timezone.now()
    #     }
    # )
