"""
Database models for the gym lead qualification system.
"""
from django.db import models
from django.utils import timezone
from enum import Enum

class Intent(str, Enum):
    """Possible fitness intents/goals."""
    WEIGHT_LOSS = "weight_loss"
    STRESS_RELIEF = "stress_relief_mental_health"
    BOXING_TECHNIQUE = "learn_boxing_technique"
    GENERAL_FITNESS = "general_fitness"
    SOCIAL_COMMUNITY = "social_community"
    JUST_FREE_CLASS = "just_wants_free_class"


# Then add this field to your Conversation model:
# detected_intent = models.CharField(
#     max_length=50,
#     choices=[(tag.value, tag.name) for tag in Intent],
#     blank=True,
#     null=True,
#     help_text="Intent detected by sales LLM"
# )

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

    OUTCOME_CHOICES = [
        ('agreed_to_free_class', 'Agreed to Free Class'),
        ('not_interested', 'Not Interested'),
        ('reached_message_limit', 'Reached Message Limit'),
    ]
    

    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='conversations')
    thread_subject = models.CharField(max_length=255, help_text="Email subject for threading")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES, blank=True, null=True)
    detected_intent = models.CharField(
        max_length=50,
        choices=[(tag.value, tag.name) for tag in Intent],
        blank=True,
        null=True,
        help_text="Intent detected by sales LLM"
    )
    last_message_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ['-last_message_at']
        unique_together = ['prospect', 'thread_subject']

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
