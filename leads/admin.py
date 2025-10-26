"""
Django admin configuration for lead management.
"""
from django.contrib import admin
from .models import Prospect, Conversation, Message, PendingResponse, SystemConfig, SystemPrompt, SystemPromptVersion
@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'email', 'phone', 'created_at']
    search_fields = ['first_name', 'email', 'phone']
    list_filter = ['created_at']
    readonly_fields = ['created_at']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['prospect', 'thread_subject', 'status', 'outcome', 'detected_intent', 'last_message_at', 'created_at']
    list_filter = ['status', 'outcome', 'created_at']
    search_fields = ['prospect__first_name', 'prospect__email', 'thread_subject']
    readonly_fields = ['created_at']
    raw_id_fields = ['prospect']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['content', 'conversation__prospect__first_name']
    readonly_fields = ['created_at']
    raw_id_fields = ['conversation']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(PendingResponse)
class PendingResponseAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'status', 'llm_provider', 'created_at', 'actioned_at']
    list_filter = ['status', 'llm_provider', 'created_at']
    search_fields = ['conversation__prospect__first_name', 'llm_content']
    readonly_fields = ['created_at', 'actioned_at']
    raw_id_fields = ['conversation']


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Prevent adding more than one SystemConfig
        return not SystemConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of SystemConfig
        return False


# your_app/admin.py
from django.contrib import admin
from .models import SystemPrompt, SystemPromptVersion # Make sure this import path is correct

# --- 1. Admin for the Parent Prompt Model (SystemPrompt) ---
@admin.register(SystemPrompt)
class SystemPromptAdmin(admin.ModelAdmin):
    """
    Manages the logical prompt group.
    """
    # Fields to display in the list view
    list_display = ('name', 'active_version', 'updated_at')
    
    # Fields that can be searched
    search_fields = ('name',)
    
    # Allows a quick filter on the right sidebar (optional, but helpful)
    list_filter = ('updated_at',)
    
    # Use autocomplete for the ForeignKey field. 
    # Requires a search_fields on the related SystemPromptVersionAdmin (see below).
    autocomplete_fields = ('active_version',)


# --- 2. Admin for the Version History Model (SystemPromptVersion) ---
@admin.register(SystemPromptVersion)
class SystemPromptVersionAdmin(admin.ModelAdmin):
    """
    Manages the historical prompt content.
    """
    # Fields to display in the list view
    list_display = ('prompt', 'version', 'created_by', 'created_at', 'notes')
    
    # Fields that can be searched (useful for finding a version by its content)
    search_fields = ('content', 'notes')
    
    # Fields for quick filtering
    list_filter = ('prompt', 'created_by')
    
    # Default ordering: group by prompt, then show newest versions first
    ordering = ('prompt__name', '-version')
    
    # Use autocomplete for the ForeignKey to the parent SystemPrompt
    autocomplete_fields = ('prompt',)