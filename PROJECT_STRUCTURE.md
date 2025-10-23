# Gym Lead Qualifier - Project Structure

```
gym_lead_qualifier/
│
├── manage.py                          # Django management script
├── requirements.txt                   # Python dependencies
├── .env.example                       # Example environment variables
├── .gitignore                        # Git ignore file
├── PROJECT_STRUCTURE.md              # This file
├── SETUP_GUIDE.md                    # Complete setup instructions
│
├── config/                           # Django project settings
│   ├── __init__.py
│   ├── settings.py                   # Main settings
│   ├── urls.py                       # Root URL configuration
│   ├── wsgi.py                       # WSGI configuration for deployment
│   └── asgi.py                       # ASGI configuration
│
├── leads/                            # Main Django app
│   ├── __init__.py
│   ├── admin.py                      # Django admin configuration
│   ├── apps.py                       # App configuration
│   ├── models.py                     # Database models
│   ├── urls.py                       # App URL patterns
│   ├── views/                        # View modules
│   │   ├── __init__.py
│   │   ├── dashboard.py              # Dashboard views
│   │   └── actions.py                # Action views (approve, reject, etc.)
│   ├── services/                     # Business logic layer
│   │   ├── __init__.py
│   │   ├── email_service.py          # Gmail integration
│   │   ├── llm_service.py            # Grok/OpenAI integration
│   │   ├── prospect_service.py       # Prospect management
│   │   └── cold_lead_service.py      # Cold lead detection
│   ├── management/                   # Django management commands
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── poll_emails.py        # Email polling command
│   │       └── check_cold_leads.py   # Cold lead check command
│   ├── migrations/                   # Database migrations
│   │   └── __init__.py
│   └── templates/                    # Django templates
│       ├── base.html                 # Base template
│       ├── dashboard/
│       │   ├── index.html            # Main dashboard
│       │   ├── pending_detail.html   # Response approval page
│       │   ├── conversations.html    # Conversation list
│       │   └── conversation_detail.html  # Full conversation view
│       └── partials/
│           ├── conversation_card.html
│           └── message_thread.html
│
├── secrets/                          # API credentials (gitignored)
│   └── gmail_credentials.json        # Gmail API credentials
│
└── staticfiles/                      # Static files (CSS, JS - collected in production)
```

## Key Files Description

### Configuration Files
- **requirements.txt**: All Python package dependencies
- **.env**: Environment variables (API keys, database URL)
- **config/settings.py**: Django settings including database, apps, middleware

### Models (leads/models.py)
- **Prospect**: Email, first name, phone
- **Conversation**: Thread tracking, status, outcome
- **Message**: Individual messages in conversations
- **PendingResponse**: LLM-generated responses awaiting approval
- **SystemConfig**: System-wide configuration settings

### Services (leads/services/)
- **email_service.py**: Gmail API integration for sending/receiving
- **llm_service.py**: Grok and OpenAI API calls with fallback
- **prospect_service.py**: Prospect and conversation management
- **cold_lead_service.py**: Detect and mark cold leads

### Views (leads/views/)
- **dashboard.py**: Main dashboard, pending queue, conversation lists
- **actions.py**: Approve, edit, reject responses; manual actions

### Management Commands (leads/management/commands/)
- **poll_emails.py**: Run every 5 minutes to check for new emails
- **check_cold_leads.py**: Run daily to detect cold leads

### Templates (leads/templates/)
- Django templates using Bootstrap 5 for UI
- Base template with navbar and common styling
- Dashboard pages for viewing and managing conversations

## Database Schema

### Prospect
- id (PK)
- email (unique, indexed)
- first_name
- phone
- created_at

### Conversation
- id (PK)
- prospect_id (FK)
- thread_subject (for email threading)
- status (active/cold/complete)
- outcome (agreed_to_free_class/not_interested/reached_message_limit)
- last_message_at
- created_at
- Unique constraint: (prospect, thread_subject)

### Message
- id (PK)
- conversation_id (FK)
- role (prospect/llm_generated/sent)
- content (text)
- created_at

### PendingResponse
- id (PK)
- conversation_id (FK)
- llm_content (text)
- status (pending/approved/rejected/edited)
- edited_content (nullable)
- created_at
- actioned_at

### SystemConfig
- id (PK)
- polling_interval_minutes (default: 5)
- cold_lead_threshold_days (default: 7)
- cold_lead_notifications_enabled (default: False)
- max_message_exchanges (default: 10)
- llm_provider_primary (default: 'grok')
- llm_provider_fallback (default: 'openai')

## URLs Structure

```
/                                     → Redirect to dashboard
/dashboard/                          → Main dashboard
/dashboard/pending/<id>/             → Approve/edit pending response
/dashboard/conversations/            → All conversations list
/dashboard/conversation/<id>/        → Conversation detail
/actions/check-email/                → Manual email check (POST)
/actions/approve/<id>/               → Approve response (POST)
/actions/edit/<id>/                  → Edit and send response (POST)
/actions/reject/<id>/                → Reject response (POST)
/actions/mark-complete/<id>/         → Mark conversation complete (POST)
/admin/                              → Django admin
```

## Data Flow

1. **Email Polling** (every 5 min via cron)
   - poll_emails.py runs
   - Fetches new "New Prospect Notification" emails
   - Creates Prospect + Conversation
   - Generates LLM response → PendingResponse

2. **Human Approval** (dashboard)
   - User views pending responses
   - Approves/edits/rejects
   - On approve: sends via Gmail, marks as sent

3. **Reply Handling** (polling)
   - Fetches replies to existing conversations
   - Logs Message with role='prospect'
   - Generates LLM response → PendingResponse

4. **Cold Lead Detection** (daily cron)
   - check_cold_leads.py runs
   - Marks conversations with no response in 7 days as 'cold'
   - Displays in dashboard

## Environment Variables

```
GROK_API_KEY=your_grok_key
OPENAI_API_KEY=your_openai_key
DJANGO_SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///db.sqlite3  # or postgres://...
DEBUG=True  # False in production
ALLOWED_HOSTS=localhost,127.0.0.1  # Add your domain in production
```

## Development vs Production

### Development (Local)
- SQLite database
- DEBUG=True
- Run polling manually: `python manage.py poll_emails`
- Django dev server: `python manage.py runserver`

### Production (Render)
- PostgreSQL (Supabase)
- DEBUG=False
- Render Cron Jobs for polling
- Gunicorn WSGI server
- Whitenoise for static files
