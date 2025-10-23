# Gym Lead Qualifier

Django application for managing AI-powered gym lead qualification with human approval workflow.

## Quick Start

1. **Read the Setup Guide**: See `SETUP_GUIDE.md` for complete instructions
2. **Review Project Structure**: See `PROJECT_STRUCTURE.md` for architecture details

## Key Features

- ✅ Gmail integration for prospect notifications
- ✅ AI-powered response generation (Grok + OpenAI fallback)
- ✅ Human approval workflow for all responses
- ✅ Conversation thread management
- ✅ Cold lead detection
- ✅ Django admin for data management
- ✅ Bootstrap 5 dashboard UI
- ✅ Multi-user authentication ready

## Technology Stack

- **Backend**: Django 5.1
- **Database**: SQLite (dev) / PostgreSQL (production)
- **AI**: Grok API (primary), OpenAI (fallback)
- **Email**: Gmail API
- **Frontend**: Bootstrap 5 + Django Templates

## Files Overview

### Documentation
- `SETUP_GUIDE.md` - Complete setup instructions
- `PROJECT_STRUCTURE.md` - Architecture and file structure
- `README.md` - This file

### Configuration
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variables template
- `config/settings.py` - Django settings

### Application
- `leads/` - Main Django app
  - `models.py` - Database models
  - `services/` - Business logic
  - `views/` - Dashboard and action views
  - `templates/` - HTML templates
  - `management/commands/` - Email polling and cold lead checks

## Next Steps

1. Follow `SETUP_GUIDE.md` for installation
2. Set up Gmail API credentials
3. Configure environment variables
4. Run migrations
5. Create superuser
6. Start development server
7. Send test email and poll

## Support

For issues or questions, refer to the comprehensive `SETUP_GUIDE.md`.

---

**Ready to deploy? Follow the Production Deployment section in SETUP_GUIDE.md**
