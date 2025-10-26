"""
Database models for the gym lead qualification system.
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import JSONField

# Get the custom User model defined in your settings
#User = get_user_model()


class SystemPrompt(models.Model):
    """
    Represents the logical prompt grouping (e.g., 'Summary Generator').
    It points to the specific version that is currently in use.
    """
    name = models.CharField(max_length=100, unique=True, help_text="A human-readable name for this prompt group.")
    
    # This ForeignKey points to the single, active version of the prompt content.
    # We use related_name='+' because we don't need a reverse relationship from PromptVersion back to Prompt.
    active_version = models.ForeignKey(
        'SystemPromptVersion',
        on_delete=models.PROTECT,  # Prevent deleting the active version
        null=True, 
        blank=True,
        related_name='+',
        help_text="The currently active version of the prompt content."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    # --- Convenience Method to Access Content ---
    @property
    def current_content(self):
        """Property to easily access the content of the active version."""
        if self.active_version:
            return self.active_version.content
        return ""

    # --- Convenience Method for Creating/Activating New Version ---
    def create_and_activate_new_version(self, new_content: str, created_by: 'User' = None, notes: str = None):
        """
        Creates a new version and atomically updates the active_version pointer.
        """
        
        # 1. Determine the next version number
        last_version = self.versions.order_by('-version').first()
        new_version_number = (last_version.version + 1) if last_version else 1
        
        with transaction.atomic():
            # 2. Create the new version record
            new_version = SystemPromptVersion.objects.create(
                prompt=self,
                content=new_content,
                version=new_version_number,
                created_by=created_by,
                notes=notes
            )
            
            # 3. Update the active pointer on the parent object
            self.active_version = new_version
            self.save(update_fields=['active_version', 'updated_at'])
            
        return new_version


class SystemPromptVersion(models.Model):
    """
    Represents a specific, historical, and immutable version of a prompt's content.
    """
    prompt = models.ForeignKey(
        SystemPrompt, 
        on_delete=models.CASCADE, 
        related_name='versions',
        help_text="The logical prompt set this version belongs to."
    )
    
    content = models.TextField(help_text="The complete text of the prompt for this version.")
    version = models.PositiveIntegerField(help_text="The sequential version number (e.g., 1, 2, 3).")
    
    # Audit Trail Fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The user who created this version."
    )
    notes = models.TextField(
        blank=True, 
        help_text="A brief explanation of why this version was created (e.g., 'Fixed tone', 'Added JSON output requirement')."
    )

    class Meta:
        unique_together = ('prompt', 'version')
        ordering = ['prompt', 'version']

    def __str__(self):
        return f"{self.prompt.name} (v{self.version})"


# --- Standardized choices for conversation outcomes and intents ---
OUTCOME_CHOICES = [
    ('agreed_to_free_class', 'Agreed to free class'),
    ('not_interested', 'Not interested'),
    ('reached_message_limit', 'Reached message limit'),
    ('continue', 'Continue conversation'),
]

INTENT_CHOICES = [
    ('weight_loss', 'Weight loss'),
    ('stress_relief_mental_health', 'Stress relief / mental health'),
    ('learn_boxing_technique', 'Learn boxing technique'),
    ('general_fitness', 'General fitness'),
    ('social_community', 'Social / community'),
    ('just_wants_free_class', 'Just wants free class'),
]

class Prospect(models.Model):
    """Represents a potential gym member."""
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} ({self.email})"


class Conversation(models.Model):
    """Tracks a conversation thread with a prospect."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cold', 'Cold'),
        ('complete', 'Complete'),
    ]

    llm_determined_outcome = JSONField(
        blank=True,
        null=True,
        help_text="Full LLM outcome determination as structured data"
    )
    
    llm_determined_intent = JSONField(
        blank=True,
        null=True,
        help_text="Full LLM intent determination as structured data"
    )

    outcome = models.CharField(
        max_length=50,
        choices=OUTCOME_CHOICES,
        blank=True,
        null=True,
        help_text="Simplified outcome for quick filtering"
    )
    
    intent = models.CharField(
        max_length=50,
        choices=INTENT_CHOICES,
        blank=True,
        null=True,
        help_text="Simplified intent for quick filtering"
    )
    
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='conversations')
    thread_subject = models.CharField(max_length=255, help_text="Email subject for threading")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_message_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at']
        unique_together = ['prospect', 'thread_subject']
        indexes = [
            models.Index(fields=['status', 'last_message_at']),
            models.Index(fields=['intent']),
            models.Index(fields=['outcome']),
        ]

    def __str__(self):
        return f"Conversation with {self.prospect.first_name} - {self.status}"

    def message_count(self):
        """Return count of messages in conversation."""
        return self.messages.count()


class Message(models.Model):
    """Individual message in a conversation."""
    ROLE_CHOICES = [
        ('prospect', 'Prospect'),
        ('llm_generated', 'LLM Generated'),
        ('sent', 'Sent'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class PendingResponse(models.Model):
    """LLM-generated response awaiting human approval."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('edited', 'Edited'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='pending_responses')
    llm_content = models.TextField(help_text="Original LLM-generated content")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    edited_content = models.TextField(blank=True, null=True, help_text="Content after human editing")
    llm_provider = models.CharField(max_length=20, default='grok', help_text="Which LLM generated this")
    created_at = models.DateTimeField(auto_now_add=True)
    actioned_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Pending Response for {self.conversation.prospect.first_name} - {self.status}"

    def get_final_content(self):
        """Return the content to be sent (edited if available, otherwise original)."""
        return self.edited_content if self.edited_content else self.llm_content


class SystemConfig(models.Model):
    """System-wide configuration settings (singleton)."""
    polling_interval_minutes = models.IntegerField(default=5)
    cold_lead_threshold_days = models.IntegerField(default=7)
    cold_lead_notifications_enabled = models.BooleanField(default=False)
    max_message_exchanges = models.IntegerField(default=10)
    llm_provider_primary = models.CharField(max_length=20, default='grok')
    llm_provider_fallback = models.CharField(max_length=20, default='openai')

    class Meta:
        verbose_name = 'System Configuration'
        verbose_name_plural = 'System Configuration'

    def __str__(self):
        return "System Configuration"

    def save(self, *args, **kwargs):
        """Ensure only one SystemConfig instance exists."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of SystemConfig."""
        pass

    @classmethod
    def load(cls):
        """Load the singleton SystemConfig instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
