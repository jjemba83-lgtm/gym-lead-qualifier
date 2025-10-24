"""
Email service for Gmail API integration.
Handles fetching new prospect notifications, replies, and sending responses.
"""
import logging
import base64
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/gmail.modify']


def get_gmail_service():
    """
    Authenticate and return Gmail API service.
    Uses credentials from secrets/ directory.
    """
    creds = None
    
    # Token file stores user's access and refresh tokens
    if settings.GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(settings.GMAIL_TOKEN_PATH), SCOPES)
    
    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not settings.GMAIL_CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {settings.GMAIL_CREDENTIALS_PATH}. "
                    "Please follow the setup guide to configure Gmail API."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(settings.GMAIL_CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(settings.GMAIL_TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    
    service = build('gmail', 'v1', credentials=creds)
    return service


def clean_reply_content(email_body: str) -> str:
    """
    Extract only the new reply content, removing quoted text from previous emails.
    Handles common email reply patterns.
    """
    # Common reply markers
    markers = [
        'On ',  # "On Mon, Oct 23, 2024 at 5:00 PM..."
        '-----Original Message-----',
        '________________________________',
        'From:',
        'Sent:',
        '> ',  # Quoted text starting with >
    ]
    
    lines = email_body.split('\n')
    clean_lines = []
    
    for line in lines:
        # Stop if we hit a reply marker
        if any(line.strip().startswith(marker) for marker in markers):
            break
        # Skip lines that are just ">" (quoted)
        if line.strip() and not line.strip().startswith('>'):
            clean_lines.append(line)
    
    # Join and clean up
    result = '\n'.join(clean_lines).strip()
    
    # If nothing left, return original (better to show everything than nothing)
    return result if result else email_body.strip()


def parse_prospect_data(email_body: str, subject: str) -> Dict[str, str]:
    """
    Parse prospect data from email body.
    Expected format:
        Name: John Doe
        Email: john.doe@example.com
        Phone: 555-123-4567
    """
    data = {}
    
    # Extract location from subject
    # Subject format: "New Prospect Notification - Downtown LA"
    location_match = re.search(r'New Prospect Notification - (.+)$', subject)
    if location_match:
        data['location'] = location_match.group(1).strip()
    
    # Parse body lines
    lines = email_body.strip().split('\n')
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key == 'name':
                # Extract first name
                data['first_name'] = value.split()[0] if value else ''
                data['full_name'] = value
            elif key == 'email':
                data['email'] = value
            elif key == 'phone':
                data['phone'] = value
    
    return data


def fetch_new_prospect_notifications() -> List[Dict]:
    """
    Fetch unread emails with subject "New Prospect Notification".
    Returns list of parsed prospect data with email IDs.
    """
    try:
        service = get_gmail_service()
        
        # Search for unread emails with the notification subject
        query = 'subject:"New Prospect Notification" -subject:Re is:unread'
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        prospects = []
        
        for msg in messages:
            try:
                # Get full message
                message = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                
                # Extract headers
                headers = message['payload']['headers']
                subject = next(h['value'] for h in headers if h['name'] == 'Subject')
                from_email = next(h['value'] for h in headers if h['name'] == 'From')
                
                # Extract body
                if 'parts' in message['payload']:
                    parts = message['payload']['parts']
                    body = parts[0]['body'].get('data', '')
                else:
                    body = message['payload']['body'].get('data', '')
                
                if body:
                    body_text = base64.urlsafe_b64decode(body).decode('utf-8')
                else:
                    body_text = ''
                
                # Parse prospect data
                prospect_data = parse_prospect_data(body_text, subject)
                prospect_data['email_id'] = msg['id']
                prospect_data['thread_subject'] = subject
                prospect_data['from_email'] = from_email
                
                prospects.append(prospect_data)
                
                # Mark as read
                service.users().messages().modify(
                    userId='me',
                    id=msg['id'],
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
                
                logger.info(f"Fetched new prospect notification: {prospect_data.get('email')}")
                
            except Exception as e:
                logger.error(f"Error processing message {msg['id']}: {e}")
                continue
        
        return prospects
        
    except Exception as e:
        logger.error(f"Error fetching prospect notifications: {e}")
        return []


def fetch_replies_to_conversations(active_conversations: List[Dict]) -> List[Dict]:
    """
    Fetch replies to active conversations.
    active_conversations: List of dicts with 'thread_subject' and 'prospect_email'.
    Returns list of dicts with 'thread_subject', 'prospect_email', 'reply_content', 'email_id'.
    """
    try:
        service = get_gmail_service()
        replies = []
        
        for conv in active_conversations:
            thread_subject = conv['thread_subject']
            prospect_email = conv['prospect_email']
            
            # Extract the core subject without "Re:" or "Fwd:" prefixes
            # Gmail adds these when replying
            core_subject = thread_subject.replace('Re: ', '').replace('RE: ', '').replace('Fwd: ', '').replace('FWD: ', '').strip()
            
            # Search for unread emails from this prospect with subject containing core subject
            # Use partial match to handle Re:, Fwd:, etc.
            query = f'from:{prospect_email} subject:"{core_subject}" is:unread'
            results = service.users().messages().list(userId='me', q=query).execute()
            messages = results.get('messages', [])
            
            for msg in messages:
                try:
                    # Get full message
                    message = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                    
                    # Extract body
                    if 'parts' in message['payload']:
                        parts = message['payload']['parts']
                        body = parts[0]['body'].get('data', '')
                    else:
                        body = message['payload']['body'].get('data', '')
                    
                    if body:
                        body_text = base64.urlsafe_b64decode(body).decode('utf-8')
                    else:
                        body_text = ''
                    
                    # Clean the reply to remove quoted conversation history
                    clean_content = clean_reply_content(body_text)
                    
                    replies.append({
                        'thread_subject': thread_subject,
                        'prospect_email': prospect_email,
                        'reply_content': clean_content,
                        'email_id': msg['id']
                    })
                    
                    # Mark as read
                    service.users().messages().modify(
                        userId='me',
                        id=msg['id'],
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                    
                    logger.info(f"Fetched reply from {prospect_email}")
                    
                except Exception as e:
                    logger.error(f"Error processing reply {msg['id']}: {e}")
                    continue
        
        return replies
        
    except Exception as e:
        logger.error(f"Error fetching replies: {e}")
        return []


def send_response(to_email: str, subject: str, message_content: str) -> bool:
    """
    Send email response via Gmail.
    Returns True if successful, False otherwise.
    """
    try:
        service = get_gmail_service()
        
        # Create message
        message = MIMEText(message_content)
        message['to'] = to_email
        message['subject'] = subject
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        # Send
        send_result = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        logger.info(f"Sent email to {to_email} (Message ID: {send_result['id']})")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False


def send_hot_lead_notification(conversation, lead_score: Dict) -> bool:
    """
    Send immediate notification for hot leads to sales team.
    Includes lead score, conversation summary, and action items.
    
    Args:
        conversation: Conversation model instance
        lead_score: Dict from calculate_lead_score with score, factors, recommendations
    
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Get sales team email
        sales_email = getattr(settings, 'SALES_TEAM_EMAIL', None)
        if not sales_email:
            logger.warning("SALES_TEAM_EMAIL not configured in settings")
            return False
        
        # Determine urgency level
        score = lead_score['score']
        if score >= 0.8:
            urgency = "🔥🔥🔥 URGENT"
            priority = "IMMEDIATE FOLLOW-UP REQUIRED"
        elif score >= 0.7:
            urgency = "🔥🔥 HIGH PRIORITY"
            priority = "Follow up within 2 hours"
        else:
            urgency = "🔥 WARM LEAD"
            priority = "Follow up today"
        
        # Build subject line
        subject = f"{urgency}: {conversation.prospect.first_name} - Score {score:.0%}"
        if conversation.outcome == 'agreed_to_free_class':
            subject += " - READY TO BOOK!"
        
        # Get recent conversation for context
        recent_messages = conversation.messages.order_by('-created_at')[:5]
        
        # Build email body (plain text for better compatibility)
        body = f"""HOT LEAD ALERT - {priority}
{'='*60}

PROSPECT INFORMATION:
Name: {conversation.prospect.first_name}
Email: {conversation.prospect.email}
Phone: {conversation.prospect.phone or 'Not provided'}

LEAD SCORE: {score:.0%} {lead_score.get('interpretation', '')}
{'='*60}

SCORING FACTORS:
"""
        
        # Add scoring factors
        for factor in lead_score.get('factors', [])[:5]:
            body += f"• {factor}\n"
        
        # Add intent if detected
        if lead_score.get('intent'):
            intent_data = lead_score['intent']
            body += f"\nDETECTED INTENT:\n"
            body += f"• Goal: {intent_data.get('detected_intent', 'Unknown')}\n"
            body += f"• Confidence: {intent_data.get('confidence_level', 0):.0%}\n"
            if intent_data.get('best_time_to_visit'):
                body += f"• Preferred time: {intent_data['best_time_to_visit']}\n"
        
        # Add recommendations
        if lead_score.get('recommendations'):
            body += f"\nRECOMMENDED ACTIONS:\n"
            for rec in lead_score['recommendations'][:3]:
                body += f"✓ {rec}\n"
        
        # Add conversation summary
        body += f"""
{'='*60}
RECENT CONVERSATION:
"""
        
        for msg in reversed(recent_messages):
            role = "Prospect" if msg.role == 'prospect' else "Bot"
            # Truncate long messages
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            body += f"\n{role}: {content}\n"
        
        # Add action footer
        body += f"""
{'='*60}
NEXT STEPS:
1. {'Call immediately' if conversation.prospect.phone else 'Email immediately'}
2. Schedule free class while interest is high
3. Mention their specific goal: {lead_score.get('intent', {}).get('detected_intent', 'fitness')}
4. Log interaction in ClubReady

Time is critical - leads cool down quickly!
{'='*60}

This is an automated notification from the Gym Lead Qualifier system.
Dashboard: http://localhost:8000/dashboard/conversation/{conversation.id}/
"""
        
        # Send the email
        success = send_response(
            to_email=sales_email,
            subject=subject,
            message_content=body
        )
        
        if success:
            logger.info(f"Hot lead notification sent for {conversation.prospect.first_name} "
                       f"(Score: {score:.0%})")
        else:
            logger.error(f"Failed to send hot lead notification for {conversation.prospect.first_name}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error sending hot lead notification: {e}")
        return False


def send_daily_lead_summary() -> bool:
    """
    Send daily summary of all leads to sales team.
    Future enhancement - not implemented yet.
    """
    # TODO: Implement daily summary
    # - Count of new leads
    # - Hot leads that weren't contacted
    # - Conversion metrics
    # - Top performing messages/approaches
    pass
