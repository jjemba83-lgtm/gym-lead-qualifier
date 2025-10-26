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
from ..models import Conversation, Message, SystemConfig, SystemPrompt

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

# llm_service.py

def get_latest_prompt_content(prompt_name: str) -> str:
    """
    Retrieves the content of the currently active version for a given prompt name.
    """
    try:
        # 1. Look up the SystemPrompt record by name, and eagerly load the active_version
        prompt_set = SystemPrompt.objects.select_related('active_version').get(name=prompt_name)
        
        # 2. Access the content using the custom property on the model
        return prompt_set.current_content
        
    except SystemPrompt.DoesNotExist:
        # Handle case where the logical prompt group doesn't exist
        return f"Error: Prompt set '{prompt_name}' not found."
    except AttributeError:
        # Handle case where the prompt is found but active_version is NULL
        return f"Error: Prompt set '{prompt_name}' found, but no active version is set."

#get prompts from database.
SALES_SYSTEM_PROMPT = get_latest_prompt_content('Sales System Prompt')
CONVERSATION_ASSESSMENT_PROMPT = get_latest_prompt_content('Conversation Assessment Prompt')
CLOSING_MESSAGE_PROMPTS = json.loads(get_latest_prompt_content('Closing Message Prompt'))  #this is a dictionary.


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