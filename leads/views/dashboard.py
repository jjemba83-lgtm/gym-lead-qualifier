"""
Dashboard views for managing pending responses and conversations.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from ..models import PendingResponse, Conversation, Prospect, SystemConfig


@login_required
def dashboard(request):
    """Main dashboard view showing pending responses and stats."""
    # Get pending responses
    pending_responses = PendingResponse.objects.filter(
        status='pending'
    ).select_related('conversation__prospect').order_by('-created_at')
    
    # Get stats
    active_conversations = Conversation.objects.filter(status='active').count()
    cold_conversations = Conversation.objects.filter(status='cold').count()
    completed_conversations = Conversation.objects.filter(status='complete').count()
    
    # Get cold leads if notifications enabled
    config = SystemConfig.load()
    cold_leads = []
    if config.cold_lead_notifications_enabled:
        cold_leads = Conversation.objects.filter(
            status='cold'
        ).select_related('prospect').order_by('-last_message_at')[:5]
    
    context = {
        'pending_responses': pending_responses,
        'active_count': active_conversations,
        'cold_count': cold_conversations,
        'completed_count': completed_conversations,
        'cold_leads': cold_leads,
        'config': config,
    }
    
    return render(request, 'dashboard/index.html', context)


@login_required
def pending_detail(request, pending_id):
    """View a pending response for approval/editing."""
    pending = get_object_or_404(
        PendingResponse.objects.select_related('conversation__prospect'),
        id=pending_id
    )
    
    # Get conversation messages (for context)
    messages = pending.conversation.messages.all().order_by('created_at')
    
    context = {
        'pending': pending,
        'conversation': pending.conversation,
        'messages': messages,
    }
    
    return render(request, 'dashboard/pending_detail.html', context)


@login_required
def conversations_list(request):
    """List all conversations with filtering."""
    status_filter = request.GET.get('status', 'all')
    
    conversations = Conversation.objects.select_related('prospect')
    
    if status_filter != 'all':
        conversations = conversations.filter(status=status_filter)
    
    conversations = conversations.order_by('-last_message_at')
    
    context = {
        'conversations': conversations,
        'status_filter': status_filter,
    }
    
    return render(request, 'dashboard/conversations.html', context)


@login_required
def conversation_detail(request, conversation_id):
    """View full conversation details including contact info."""
    conversation = get_object_or_404(
        Conversation.objects.select_related('prospect'),
        id=conversation_id
    )
    
    messages = conversation.messages.all().order_by('created_at')
    pending_responses = conversation.pending_responses.all().order_by('-created_at')
    
    context = {
        'conversation': conversation,
        'messages': messages,
        'pending_responses': pending_responses,
    }
    
    return render(request, 'dashboard/conversation_detail.html', context)
