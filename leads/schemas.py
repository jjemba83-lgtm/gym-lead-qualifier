from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class IntentType(str, Enum):
    WEIGHT_LOSS = "weight_loss"
    STRESS_RELIEF = "stress_relief_mental_health"
    BOXING_TECHNIQUE = "learn_boxing_technique"
    GENERAL_FITNESS = "general_fitness"
    SOCIAL_COMMUNITY = "social_community"
    JUST_FREE_CLASS = "just_wants_free_class"

class OutcomeType(str, Enum):
    AGREED_FREE_CLASS = "agreed_to_free_class"
    NOT_INTERESTED = "not_interested"
    CONTINUE = "continue"
    # FOLLOW_UP_NEEDED = "follow_up_needed"

class IntentData(BaseModel):
    primary_intent: Optional[IntentType] = Field(
        default=None,
        description="The primary intent detected from the conversation"
    )
    confidence: Optional[float] = Field(..., ge=0, le=1)
    reasoning: Optional[str] = None
    best_time_to_visit: Optional[str] = None # e.g., "mornings", "evenings"
    # secondary_intents: List[IntentType] = []
    # key_phrases: List[str] = []
    # metadata: Dict[str, Any] = {}

class salesBotTurn(BaseModel):
    response: str = Field(..., description="The chatbot's response message")
    intent_data: Optional[IntentData] = None

#only response required from the content anlaysis LLM.
class OutcomeData(BaseModel):
    final_outcome: OutcomeType = Field(
        default=None,
        description="The final outcome of the conversation"
    )
    should_end: bool = False
    reasoning: Optional[str] = None
    # next_steps: List[str] = []
    # follow_up_timing: Optional[str] = None # e.g., "1_week", "immediate"
    # metadata: Dict[str, Any] = {}
    # confidence: float = Field(..., ge=0, le=1)


