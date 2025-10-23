"""
Action views for approving, editing, rejecting responses and managing conversations.
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.management import call_command
from io import StringIO
from ..models import PendingResponse, Conversation
from ..services import email_service, prospect_service


@login_required
@require_POST
def check_email_now(request):
    """Manually trigger email polling."""
    try:
        # Capture command output
        out = StringIO()
        call_command('poll_emails', stdout=out)
        output = out.getvalue()
        
        # Count new items (simple parsing)
        new_prospects = output.count('✓ Processed new prospect:')
        new_replies = output.count('✓ Processed reply from')
        
        return JsonResponse({
            'success': True,
            'new_prospects': new_prospects,
            'new_replies': new_replies,
            'message': f'Found {new_prospects} new prospects and {new_replies} replies'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required
@require_POST
def approve_response(request, pending_id):
    """Approve and send a pending response."""
    pending = get_object_or_404(PendingResponse, id=pending_id)
    
    try:
        # Mark as approved
        success, msg = prospect_service.approve_response(pending_id)
        
        if not success:
            messages.error(request, f"Error approving response: {msg}")
            return redirect('pending_detail', pending_id=pending_id)
        
        # Send email
        sent = email_service.send_response(
            to_email=pending.conversation.prospect.email,
            subject=pending.conversation.thread_subject,
            message_content=pending.get_final_content()
        )
        
        if sent:
            # Log as sent message
            prospect_service.log_message(
                conversation=pending.conversation,
                role='sent',
                content=pending.get_final_content()
            )
            messages.success(request, "Response approved and sent successfully!")
        else:
            messages.error(request, "Response approved but failed to send email.")
        
        return redirect('dashboard')
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('pending_detail', pending_id=pending_id)


@login_required
@require_POST
def edit_response(request, pending_id):
    """Edit and send a pending response."""
    pending = get_object_or_404(PendingResponse, id=pending_id)
    
    try:
        edited_content = request.POST.get('edited_content', '').strip()
        
        if not edited_content:
            messages.error(request, "Cannot send empty response.")
            return redirect('pending_detail', pending_id=pending_id)
        
        # Approve with edited content
        success, msg = prospect_service.approve_response(pending_id, edited_content=edited_content)
        
        if not success:
            messages.error(request, f"Error saving edited response: {msg}")
            return redirect('pending_detail', pending_id=pending_id)
        
        # Send email
        sent = email_service.send_response(
            to_email=pending.conversation.prospect.email,
            subject=pending.conversation.thread_subject,
            message_content=edited_content
        )
        
        if sent:
            # Log as sent message
            prospect_service.log_message(
                conversation=pending.conversation,
                role='sent',
                content=edited_content
            )
            messages.success(request, "Edited response sent successfully!")
        else:
            messages.error(request, "Response saved but failed to send email.")
        
        return redirect('dashboard')
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('pending_detail', pending_id=pending_id)


@login_required
@require_POST
def reject_response(request, pending_id):
    """Reject a pending response."""
    try:
        success, msg = prospect_service.reject_response(pending_id)
        
        if success:
            messages.info(request, "Response rejected.")
        else:
            messages.error(request, f"Error rejecting response: {msg}")
        
        return redirect('dashboard')
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('dashboard')


@login_required
@require_POST
def mark_complete(request, conversation_id):
    """Manually mark a conversation as complete."""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    try:
        outcome = request.POST.get('outcome')
        
        prospect_service.update_conversation_status(
            conversation_id=conversation_id,
            status='complete',
            outcome=outcome
        )
        
        messages.success(request, f"Conversation marked as complete: {outcome}")
        return redirect('conversation_detail', conversation_id=conversation_id)
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('conversation_detail', conversation_id=conversation_id)
