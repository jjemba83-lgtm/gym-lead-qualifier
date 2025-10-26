"""
LLM service for generating responses using Grok (primary) or OpenAI (fallback).
Uses the exact prompts from the original simulator.py file.

IMPORTANT: Intent detection is handled by the sales LLM during conversation,
not through separate API calls. The sales prompt includes instructions for
INTENT_DETECTION JSON when explicitly requested.
"""
import logging
import json
import instructor
from typing import Optional, Tuple
from django.conf import settings
from openai import OpenAI
from ..models import Conversation, Message, SystemConfig, SystemPrompt
from ..schemas import salesBotTurn, OutcomeData

logger = logging.getLogger(__name__)

# Initialize clients lazily to avoid initialization errors
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
# The closing messages prompt is stored as JSON in the DB (a dict of outcomes -> prompt).
# Guard against missing or malformed prompt content so import-time json.loads doesn't
# raise and crash command calls or view handlers that import this module.
raw_closing = get_latest_prompt_content('Closing Message Prompt')
try:
    CLOSING_MESSAGE_PROMPTS = json.loads(raw_closing)
except Exception as exc:
    logger.warning("Could not parse Closing Message Prompt as JSON; using fallback empty dict: %s", exc)
    CLOSING_MESSAGE_PROMPTS = {}

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

class LLMService:
    def __init__(self):
        config = settings.LLM_PROVIDER_CONFIG
        self.provider = config.get("provider")
        self.model_name = config.get("model")
        
        # 1. Select the base client
        if self.provider == "openai":
            base_client = OpenAI(
                api_key=settings.OPENAI_API_KEY
            )
            
        elif self.provider == "openrouter": # <-- ADDED THIS
            base_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )

        elif self.provider == "ollama": # <-- RENAMED THIS (was 'google')
            base_client = OpenAI(
                base_url="http://localhost:11434/v1", # Example for local Ollama
                api_key="ollama" # Ollama's required key
            )
            
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        # 2. Patch the client with instructor
        # This gives you a single, unified `client` interface
        self.client = instructor.patch(base_client)


    def generate_response(self, conversation_id: int) -> Tuple[str, str]:
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
            response_text= self.client.chat.completions.create(
                model = self.model_name,
                messages=messages,
                temperature=0.3,
                response_model = salesBotTurn,
                max_tokens=200
            )
            
            logger.info(f"Generated response for conversation {conversation_id} using {self.provider}")
            return response_text, self.provider
            
        except Conversation.DoesNotExist:
            logger.error(f"Conversation {conversation_id} not found")
            raise
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise


    def generate_closing_message(self, conversation_id: int, outcome: str) -> Tuple[str, str]:
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
            closing_text =  self.client.chat.completions.create(
                model=self.model_name,
                messages = messages,
                temperature=0.2,  # Lower temperature for more consistent closings
                max_tokens=100
            )
            
            logger.info(f"Generated closing message for conversation {conversation_id} ({outcome})")
            return closing_text.choices[0].message.content , self.provider
            
        except Conversation.DoesNotExist:
            logger.error(f"Conversation {conversation_id} not found")
            raise
        except Exception as e:
            logger.error(f"Error generating closing message: {e}")
            raise


    def detect_conversation_outcome(self, conversation_id: int, prospect_response: str) -> Tuple[bool, Optional[str]]:
        """
        Use LLM to assess if conversation should end and what the outcome is.
        Returns (should_end, outcome) where outcome is one of:
        - 'agreed_to_free_class'
        - 'not_interested'
        - None (continue conversation)

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
            
            response_text =  self.client.chat.completions.create(
                model = self.model_name,
                messages= assessment_messages,
                response_model = OutcomeData,
                temperature=0.1,
                max_tokens=150
            )
            
            # The LLM client / response_model can return fields as:
            # - raw python primitives (bool / str / None)
            # - Enum instances (with a .value attribute)
            # - Pydantic model fields that wrap enums or primitives
            # To be robust, check for a `.value` attribute and fall back
            # to the raw value when it's not present.
            raw_should_end = getattr(response_text, 'should_end', None)
            should_end = getattr(raw_should_end, 'value', raw_should_end)
            # ensure boolean
            should_end = bool(should_end)

            raw_final = getattr(response_text, 'final_outcome', None)
            if raw_final is None:
                outcome_str = None
            else:
                outcome_str = getattr(raw_final, 'value', raw_final)
            
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
