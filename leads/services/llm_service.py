"""
LLM service for generating responses using Grok (primary) or OpenAI (fallback).
Uses the exact prompts from the original simulator.py file.

IMPORTANT: Intent detection is handled by the sales LLM during conversation,
not through separate API calls. The sales prompt includes instructions for
INTENT_DETECTION JSON when explicitly requested.
"""
import logging
import json
from typing import Optional, Tuple
from django.conf import settings
from openai import OpenAI
from ..models import Conversation, Message, SystemConfig

logger = logging.getLogger(__name__)

# Initialize clients lazily to avoid initialization errors
def get_grok_client():
    """Get or create Grok client."""
    if settings.GROK_API_KEY:
        return OpenAI(
            api_key=settings.GROK_API_KEY,
            base_url="https://api.x.ai/v1"
        )
    return None

def get_openai_client():
    """Get or create OpenAI client."""
    if settings.OPENAI_API_KEY:
        try:
            return OpenAI(api_key=settings.OPENAI_API_KEY)
        except Exception as e:
            import traceback
            print("FULL ERROR:")
            traceback.print_exc()
            raise
    return None


# Sales prompt from simulator.py (lines 182-271)
SALES_SYSTEM_PROMPT = """You are a friendly sales assistant for a group fitness boxing gym. A prospect filled out a web form - qualify them and get them to book a free class.

GYM INFO:
- 45-min classes: 5 rounds strength + 5 rounds boxing (10 rounds × 3 mins)
- Schedule: Weekday mornings/evenings, weekend mornings
- High energy with curated playlists
- Gloves/wraps provided for free class
- HIGH INTENSITY - not for complete beginners

YOUR GOALS:
1. Determine their fitness goal/intent
2. Get them to agree to a free class

URGENCY & MESSAGE MANAGEMENT:
- Keep the conversation moving toward booking
- Be direct and ask for the free class booking early in conversation
- If they show hesitation, address objections and offer the free class
- If they need more time, let them know a sales associate can follow up within 24 hours

IMPORTANT: DO NOT decide when the conversation ends - just respond naturally to each message.
The system will automatically end the conversation when appropriate.

STANDARDIZED OPENING (Use this for your FIRST message):
"Hi! Thanks for reaching out about our boxing fitness gym. To help match you with the right class, I have a few quick questions:

1. What's your main fitness goal? (weight loss, stress relief, learn technique, general fitness, etc.)
2. How often do you currently exercise?
3. Any concerns about high-intensity training?

Looking forward to getting you started!"

CONVERSATION RULES:
- Keep responses brief (2-3 sentences max)
- Be direct and ask for the free class booking when appropriate
- If they explicitly say not interested, acknowledge politely
- If they agree to free class, ask preferred time (morning/evening/weekend)
- You have their phone and email from the web form
- Respond naturally to each message - don't add extra commentary about "final messages" or "wrapping up"

⚠️ CRITICAL: You do NOT control when the conversation ends. Just respond naturally to each prospect message.
The conversation management system will handle ending detection automatically.

QUALIFICATION:
- Check if they exercise regularly (high intensity requirement)
- Listen carefully to their stated goal in response to question 1
- Use their exact words when possible for intent detection

INTENT DETECTION PRIORITY:
When determining their PRIMARY intent, pay attention to EMPHASIS not just first mention:
- What do they ask MULTIPLE questions about?
- What topic do they return to or elaborate on?
- What seems to matter MOST to them based on their questions?

Examples:
- If they mention "fitness" once but ask 3 questions about "class size", "meeting people", 
  or "group dynamics" → PRIMARY intent is social_community
  
- If they mention "general fitness" but repeatedly emphasize "technique", "proper form", 
  or "learning fundamentals" → PRIMARY intent is learn_boxing_technique
  
- If they mention multiple goals, pick the one they show MOST interest in through their 
  questions and follow-ups, not just what they said first

CRITICAL INSTRUCTIONS FOR INTENT DETECTION:
⚠️ NEVER, EVER include the INTENT_DETECTION JSON in your regular chat messages to the prospect!
⚠️ The INTENT_DETECTION should ONLY be provided when you receive the EXACT message: "Based on our conversation, please provide your INTENT_DETECTION assessment in the required JSON format."
⚠️ During ALL normal conversation with the prospect, respond naturally without ANY JSON formatting
⚠️ Do NOT include JSON just because you think the conversation is ending
⚠️ Do NOT include JSON after mentioning callbacks or follow-ups
⚠️ Keep your responses conversational and friendly - save the structured data for when explicitly requested
⚠️ If you're unsure, DON'T include JSON - only include it when you see the exact request phrase above

When (and ONLY when) you receive the explicit request "provide your INTENT_DETECTION assessment", provide assessment in EXACT format:

INTENT_DETECTION:
{
  "detected_intent": "ONE PRIMARY INTENT ONLY - choose the MAIN goal: weight_loss, stress_relief_mental_health, learn_boxing_technique, general_fitness, social_community, or just_wants_free_class",
  "confidence_level": 0.0-1.0,
  "reasoning": "brief explanation based on their stated goal AND what they emphasized through questions - if multiple goals mentioned, explain why you chose this as primary",
  "best_time_to_visit": "morning/evening/weekend or null"
}

Be warm and helpful, but move quickly to booking!"""


# Conversation assessment prompt from simulator.py (lines 340-408)
CONVERSATION_ASSESSMENT_PROMPT = """You are analyzing a sales conversation. Review the conversation and the prospect's latest response to determine if the conversation should end.

CONVERSATION HISTORY:
{conversation_history}

PROSPECT'S LATEST RESPONSE:
"{prospect_response}"

Determine if the prospect has shown INTEREST IN ATTENDING the free class:

SIGNS OF AGREEMENT/INTEREST (mark as "agreed_to_free_class"):
- Explicit agreement ("yes", "sure", "sounds good", "I'd like to", "let's do it", "I'm in", "sign me up")
- Discussing specific times or days ("weekend works", "Tuesday evening", "mornings are best", "I can do 6pm")
- Asking about scheduling ("what times?", "when do classes start?", "what days are available?", "when's the next class?")
- Expressing time preferences ("I'd prefer evening", "weekend morning would work", "I'm free Tuesday")
- Providing availability information ("I'm available weekdays", "mornings work for me")
- Asking logistical questions about attending ("where's it located?", "what should I bring?", "should I wear anything specific?", "do I need to arrive early?")
- Responding positively to booking offers ("that works", "sounds perfect", "let's try it")
- Any indication they're planning to attend or moving toward booking
- Discussing with sales rep about scheduling ("let me check my calendar", "what works for you?")

🚨 CRITICAL RULE: If the prospect is discussing WHEN, WHERE, or HOW to attend → they have AGREED!
Don't wait for magic words like "yes, book me now". In real sales, talking logistics = commitment.

EXAMPLES THAT ARE AGREEMENT:
✅ "Tuesday works for me" → AGREED (discussing when)
✅ "I can do mornings" → AGREED (stating availability)
✅ "What time is the next class?" → AGREED (asking about scheduling)
✅ "Should I bring anything?" → AGREED (logistics question)
✅ "Where's it located?" → AGREED (planning to attend)
✅ "That sounds good" after booking offer → AGREED (positive response)

SIGNS OF DECLINE (mark as "not_interested"):
- Explicit rejection ("no thanks", "not interested", "I'll pass", "not for me", "maybe later")
- Clear backing out after initial interest
- Strong hesitation with no forward movement ("I need to think about it", "let me get back to you")
- Saying they're just browsing/looking

OTHERWISE (mark as "continue"):
- Still asking questions about the gym/classes (not booking-related)
- Hasn't engaged with booking yet
- Needs more information before deciding
- General conversation without commitment signals
- Sales bot mentioned follow-up/callback but prospect hasn't explicitly declined

⚠️ IMPORTANT: Don't be too conservative! In real sales, discussing scheduling = commitment.
If they're talking about WHEN/WHERE/HOW to attend, mark as "agreed_to_free_class" immediately.
Don't require explicit "yes, I want to book" - that's unrealistic!

CRITICAL: Set "should_end" based on outcome:
- If outcome is "agreed_to_free_class" → should_end = TRUE
- If outcome is "not_interested" → should_end = TRUE
- If outcome is "continue" → should_end = FALSE

Return ONLY valid JSON in this exact format:
{{
  "should_end": true or false,
  "outcome": "agreed_to_free_class" or "not_interested" or "continue",
  "reasoning": "brief explanation of your decision"
}}"""


# New closing message prompts
CLOSING_MESSAGE_PROMPTS = {
    'agreed_to_free_class': """You're wrapping up a conversation with someone who has agreed to try a free class.
Write a brief, warm closing message (2-3 sentences max) that:
1. Confirms their interest in the free class
2. Mentions that a team member will contact them within 24 hours to schedule
3. Thanks them warmly

Keep it natural and friendly. Don't use formal language or marketing speak.
Example tone: "Awesome, {name}! I'm excited you want to try a class. Someone from our team will reach out within 24 hours to get you scheduled. Looking forward to seeing you in the gym!"

DO NOT include any JSON or structured data in your response.""",
    
    'not_interested': """You're wrapping up a conversation with someone who is not interested.
Write a brief, respectful closing message (1-2 sentences max) that:
1. Thanks them for their time
2. Leaves the door open for the future

Keep it gracious and brief. No hard sell.
Example tone: "No problem at all! Thanks for taking the time to chat, and feel free to reach out if you change your mind."

DO NOT include any JSON or structured data in your response.""",
    
    'reached_message_limit': """You're wrapping up a conversation that has reached the message limit.
Write a brief, helpful closing message (2-3 sentences max) that:
1. Mentions that a specialist can answer any remaining questions
2. Provides next steps (team member will follow up)
3. Thanks them for their interest

Keep it professional and helpful.
Example tone: "I want to make sure all your questions get answered! A team member will follow up within 24 hours to discuss details and help you get started. Thanks for your interest!"

DO NOT include any JSON or structured data in your response.""",
}


def _call_llm(messages: list, provider: str = 'grok', temperature: float = 0.3, max_tokens: int = 120) -> Tuple[str, str]:
    """
    Call LLM API with the specified provider.
    Returns (response_text, provider_used).
    """
    config = SystemConfig.load()
    
    # Determine which client to use
    if provider == 'grok' and settings.GROK_API_KEY:
        client = get_grok_client()
        if client:
            model = "llama-3.3-70b-versatile"
            actual_provider = 'grok'
        else:
            # Fall back to OpenAI
            client = get_openai_client()
            model = "gpt-4o-mini"
            actual_provider = 'openai'
    else:
        client = get_openai_client()
        model = "gpt-4o-mini"
        actual_provider = 'openai'
    
    if not client:
        raise ValueError("No LLM client configured - check API keys in .env")
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        content = response.choices[0].message.content
        logger.info(f"LLM call successful using {actual_provider}")
        return content, actual_provider
        
    except Exception as e:
        logger.error(f"Error calling {actual_provider}: {e}")
        
        # Try fallback if primary failed
        if provider == 'grok' and settings.OPENAI_API_KEY:
            logger.info("Falling back to OpenAI")
            try:
                fallback_client = get_openai_client()
                if not fallback_client:
                    raise ValueError("Fallback OpenAI client not available")
                    
                response = fallback_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                content = response.choices[0].message.content
                logger.info("Fallback to OpenAI successful")
                return content, 'openai'
            except Exception as fallback_error:
                logger.error(f"Fallback to OpenAI also failed: {fallback_error}")
                raise
        else:
            raise


def build_conversation_context(conversation: Conversation) -> list:
    """
    Build conversation context for LLM using only prospect's first name.
    Returns list of message dicts for the LLM API.
    """
    messages = [{"role": "system", "content": SALES_SYSTEM_PROMPT}]
    
    # Add conversation history
    for msg in conversation.messages.all():
        if msg.role == 'prospect':
            messages.append({"role": "user", "content": msg.content})
        elif msg.role in ['llm_generated', 'sent']:
            messages.append({"role": "assistant", "content": msg.content})
    
    return messages


def generate_response(conversation_id: int) -> Tuple[str, str]:
    """
    Generate LLM response for a conversation.
    Returns (response_text, provider_used).
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        config = SystemConfig.load()
        
        # Build context
        messages = build_conversation_context(conversation)
        
        # Call LLM
        response_text, provider = _call_llm(
            messages,
            provider=config.llm_provider_primary,
            temperature=0.3,
            max_tokens=120
        )
        
        logger.info(f"Generated response for conversation {conversation_id} using {provider}")
        return response_text, provider
        
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise


def generate_closing_message(conversation_id: int, outcome: str) -> Tuple[str, str]:
    """
    Generate appropriate closing message based on conversation outcome.
    Returns (closing_message, provider_used).
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        config = SystemConfig.load()
        
        # Get the appropriate closing prompt
        closing_prompt = CLOSING_MESSAGE_PROMPTS.get(
            outcome, 
            CLOSING_MESSAGE_PROMPTS['reached_message_limit']
        )
        
        # Build minimal context - just recent messages and closing instruction
        recent_messages = conversation.messages.order_by('-created_at')[:3]
        
        messages = [
            {"role": "system", "content": closing_prompt},
        ]
        
        # Add recent context for personalization
        for msg in reversed(recent_messages):
            if msg.role == 'prospect':
                messages.append({"role": "user", "content": msg.content})
            elif msg.role in ['llm_generated', 'sent']:
                messages.append({"role": "assistant", "content": msg.content})
        
        # Add instruction with the person's name
        messages.append({
            "role": "user", 
            "content": f"Generate the closing message for {conversation.prospect.first_name}."
        })
        
        # Call LLM with lower temperature for consistency
        closing_text, provider = _call_llm(
            messages,
            provider=config.llm_provider_primary,
            temperature=0.2,  # Lower temperature for more consistent closings
            max_tokens=100
        )
        
        logger.info(f"Generated closing message for conversation {conversation_id} ({outcome})")
        return closing_text, provider
        
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error generating closing message: {e}")
        raise


def detect_conversation_outcome(conversation_id: int, prospect_response: str) -> Tuple[bool, Optional[str]]:
    """
    Use LLM to assess if conversation should end and what the outcome is.
    Returns (should_end, outcome) where outcome is one of:
    - 'agreed_to_free_class'
    - 'not_interested'
    - None (continue conversation)
    
    NOTE: This does NOT detect intent - that should come from the sales LLM's
    conversation flow when it includes INTENT_DETECTION JSON.
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        
        # Build conversation history (last 6 messages for context)
        messages = build_conversation_context(conversation)
        recent_history = messages[-7:]  # System + last 6 messages
        
        # Format for assessment prompt
        history_json = json.dumps(recent_history, indent=2)
        assessment_prompt = CONVERSATION_ASSESSMENT_PROMPT.format(
            conversation_history=history_json,
            prospect_response=prospect_response
        )
        
        # Call LLM for assessment
        assessment_messages = [
            {"role": "system", "content": "You are a conversation analyzer. Return only valid JSON."},
            {"role": "user", "content": assessment_prompt}
        ]
        
        response_text, _ = _call_llm(
            assessment_messages,
            provider='openai',  # Use OpenAI for assessment (more reliable)
            temperature=0.1,
            max_tokens=150
        )
        
        # Parse JSON response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        assessment = json.loads(response_text)
        
        should_end = assessment.get("should_end", False)
        outcome_str = assessment.get("outcome", "continue")
        
        # Map to outcome value
        outcome = None
        if outcome_str == "agreed_to_free_class":
            outcome = "agreed_to_free_class"
        elif outcome_str == "not_interested":
            outcome = "not_interested"
        
        logger.info(f"Conversation assessment: should_end={should_end}, outcome={outcome}")
        return should_end, outcome
        
    except Exception as e:
        logger.error(f"Error in conversation assessment: {e}")
        # Default to continue if assessment fails
        return False, None


# REMOVED: detect_intent() function
# Intent detection should come from the sales LLM's conversation flow,
# not a separate API call. The sales LLM should include INTENT_DETECTION
# in its response when it determines the prospect's intent.