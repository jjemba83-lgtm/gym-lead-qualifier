# Gym Lead Qualifier - Setup Guide

Complete setup instructions for local development and production deployment.

---

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Git
- Gmail account with API access
- Grok API key
- OpenAI API key

---

## Quick Start (Local Development)

### 1. Clone or Extract Project

```bash
cd /path/to/gym_lead_qualifier
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your keys:

```
GROK_API_KEY=your_grok_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
DJANGO_SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///db.sqlite3
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Generate a Django secret key:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Gmail API Setup

#### a. Enable Gmail API
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable Gmail API:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click "Enable"

#### b. Create OAuth Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Desktop app"
4. Download the JSON file
5. Save it as `secrets/gmail_credentials.json` in your project

#### c. First-time Authentication
```bash
# Create secrets directory
mkdir -p secrets

# The first time you run poll_emails, it will open a browser for authentication
python manage.py poll_emails
```

This creates `secrets/gmail_token.json` for subsequent runs.

### 6. Initialize Database

```bash
# Run migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser
# Follow prompts to create username and password
```

### 7. Create System Configuration

```bash
python manage.py shell
```

In the Python shell:
```python
from leads.models import SystemConfig
SystemConfig.objects.create(
    polling_interval_minutes=5,
    cold_lead_threshold_days=7,
    cold_lead_notifications_enabled=False,
    max_message_exchanges=10,
    llm_provider_primary='grok',
    llm_provider_fallback='openai'
)
exit()
```

### 8. Run Development Server

```bash
python manage.py runserver
```

Visit: http://localhost:8000

**Default login:** Use the superuser credentials you created in step 6.

---

## Testing the System

### 1. Send a Test Email

Send an email to your Gmail account with:

**Subject:** `New Prospect Notification - Downtown LA`

**Body:**
```
Name: John Doe
Email: john.doe@example.com
Phone: 555-123-4567
```

### 2. Poll for New Emails

```bash
python manage.py poll_emails
```

Or click "Check Email Now" button in the dashboard.

### 3. Approve Response

1. Go to dashboard: http://localhost:8000/dashboard/
2. You'll see the pending response
3. Click to review
4. Approve, edit, or reject
5. On approval, response is sent via Gmail

### 4. Test Reply Flow

Reply to the sent email from your test email address. Run `poll_emails` again to fetch the reply and generate a new response.

---

## Management Commands

### Poll Emails (Run every 5 minutes)

```bash
python manage.py poll_emails
```

### Check Cold Leads (Run daily)

```bash
python manage.py check_cold_leads
```

### Access Django Admin

Visit: http://localhost:8000/admin/

Use superuser credentials to:
- View all prospects
- Inspect conversations
- Modify system configuration
- Review messages

---

## Production Deployment (Render + Supabase)

### 1. Create Supabase Database

1. Go to [Supabase](https://supabase.com/)
2. Create new project
3. Get connection string:
   - Go to Settings → Database
   - Copy "Connection string" (URI format)
   - Example: `postgresql://postgres:[password]@[host]:5432/postgres`

### 2. Prepare for Deployment

Update `.env` for production:

```
DEBUG=False
DATABASE_URL=postgresql://postgres:[password]@[host]:5432/postgres
ALLOWED_HOSTS=your-app.onrender.com
GROK_API_KEY=your_key
OPENAI_API_KEY=your_key
DJANGO_SECRET_KEY=your_production_secret_key
```

### 3. Deploy to Render

1. Create account on [Render](https://render.com/)
2. Connect your GitHub repository
3. Create new "Web Service"
4. Configuration:
   - **Build Command:** `pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput`
   - **Start Command:** `gunicorn config.wsgi:application`
   - **Environment:** Python 3
5. Add environment variables from your `.env` file

### 4. Create Admin User on Render

In Render dashboard → Shell:

```bash
python manage.py createsuperuser
```

### 5. Create System Configuration

In Render dashboard → Shell:

```bash
python manage.py shell
```

Then run the SystemConfig creation code from step 7 above.

### 6. Set Up Cron Jobs

In Render dashboard:

**Job 1: Poll Emails**
- Schedule: `*/5 * * * *` (every 5 minutes)
- Command: `python manage.py poll_emails`

**Job 2: Check Cold Leads**
- Schedule: `0 9 * * *` (daily at 9 AM)
- Command: `python manage.py check_cold_leads`

### 7. Gmail API for Production

Upload `secrets/gmail_credentials.json` and `secrets/gmail_token.json` to Render:

Option A: Use Render Disks (persistent storage)
Option B: Store credentials in environment variables as base64:

```bash
# Encode credentials
cat secrets/gmail_credentials.json | base64

# In Render environment variables:
GMAIL_CREDENTIALS_BASE64=<base64_string>
```

Update `email_service.py` to decode from env var.

---

## Troubleshooting

### Issue: Gmail API Authentication Failed

**Solution:** 
- Ensure `gmail_credentials.json` is in `secrets/` directory
- Run `python manage.py poll_emails` locally first to authenticate
- Check that Gmail API is enabled in Google Cloud Console

### Issue: No Emails Detected

**Solution:**
- Verify email subject line exactly matches: `"New Prospect Notification - [Location]"`
- Check email body format matches the test format
- Run with verbose logging: `python manage.py poll_emails --verbosity 2`

### Issue: LLM API Errors

**Solution:**
- Verify API keys are correct in `.env`
- Check API key has sufficient credits/quota
- Check `llm_service.py` logs for specific error messages

### Issue: Database Connection Error (Production)

**Solution:**
- Verify `DATABASE_URL` format is correct
- Ensure Supabase database is running
- Check IP whitelist in Supabase (set to allow all: `0.0.0.0/0`)

### Issue: Static Files Not Loading (Production)

**Solution:**
- Run `python manage.py collectstatic`
- Verify `STATIC_ROOT` in settings.py
- Check Whitenoise is in `MIDDLEWARE`

---

## File Upload: Gmail Credentials

Place your Gmail API credentials file here:

```
secrets/
└── gmail_credentials.json
```

**Format:**
```json
{
  "installed": {
    "client_id": "your-client-id.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "your-client-secret",
    "redirect_uris": ["http://localhost"]
  }
}
```

---

## Development Workflow

### Daily Development

1. Activate virtual environment
2. Run server: `python manage.py runserver`
3. Test with email polling: `python manage.py poll_emails`
4. View dashboard: http://localhost:8000/dashboard/

### Making Changes

1. **Models:** 
   - Edit `leads/models.py`
   - Run `python manage.py makemigrations`
   - Run `python manage.py migrate`

2. **Templates:**
   - Edit files in `leads/templates/`
   - Refresh browser (auto-reloads)

3. **Services/Views:**
   - Edit Python files
   - Restart dev server

### Testing Email Format

Create a test email template:

```
Subject: New Prospect Notification - Brooklyn

Name: Jane Smith
Email: jane@example.com
Phone: 555-987-6543
```

---

## Future: Twilio Integration

When ready to switch from Gmail to SMS:

1. Install Twilio SDK:
```bash
pip install twilio
```

2. Create `TwilioAdapter` in `messaging_adapter.py`
3. Update `SystemConfig` to toggle messaging provider
4. Minimal changes to views/models (already designed for modularity)

---

## Security Notes

### DO NOT Commit:
- `.env` file
- `secrets/` directory
- `db.sqlite3` (local database)
- `*.pyc` files
- `__pycache__/` directories

### Already in .gitignore:
All sensitive files are pre-configured in `.gitignore`

---

## Support & Resources

- **Django Documentation:** https://docs.djangoproject.com/
- **Gmail API Python:** https://developers.google.com/gmail/api/guides
- **Render Deployment:** https://render.com/docs
- **Supabase Docs:** https://supabase.com/docs

---

## Quick Command Reference

```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver

# Poll emails manually
python manage.py poll_emails

# Check cold leads
python manage.py check_cold_leads

# Open Django shell
python manage.py shell

# Collect static files (production)
python manage.py collectstatic

# Run tests
python manage.py test
```

---

## Next Steps After Setup

1. ✅ Verify dashboard loads at http://localhost:8000
2. ✅ Send test email and poll for it
3. ✅ Approve a response and verify it sends
4. ✅ Test reply flow
5. ✅ Adjust prompts in `llm_service.py` if needed
6. ✅ Configure cold lead threshold in SystemConfig
7. ✅ Deploy to production when ready

---

**You're all set! Start the server and visit the dashboard to begin testing.**
