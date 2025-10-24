"""
Django settings for gym_lead_qualifier project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'leads',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # For static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/db.sqlite3')

# Parse DATABASE_URL manually for SQLite or PostgreSQL
if DATABASE_URL.startswith('sqlite'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
elif DATABASE_URL.startswith('postgres'):
    # Parse PostgreSQL URL: postgresql://user:password@host:port/dbname
    import re
    match = re.match(r'postgres(?:ql)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
    if match:
        user, password, host, port, dbname = match.groups()
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': dbname,
                'USER': user,
                'PASSWORD': password,
                'HOST': host,
                'PORT': port,
            }
        }
    else:
        # Fallback to SQLite if parsing fails
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    # Default to SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login URL
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# LLM API Keys
GROK_API_KEY = os.getenv('GROK_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Gmail API credentials path
GMAIL_CREDENTIALS_PATH = BASE_DIR / 'secrets' / 'gmail_credentials.json'
GMAIL_TOKEN_PATH = BASE_DIR / 'secrets' / 'gmail_token.json'

# Sales Team Notifications
SALES_TEAM_EMAIL = os.getenv('SALES_TEAM_EMAIL', 'stephen.l.roberts20@gmail.com')
# Future: Support multiple emails
# SALES_TEAM_EMAILS = os.getenv('SALES_TEAM_EMAILS', '').split(',')

# Business Hours Configuration
BUSINESS_HOURS_START = int(os.getenv('BUSINESS_HOURS_START', '9'))  # 9 AM
BUSINESS_HOURS_END = int(os.getenv('BUSINESS_HOURS_END', '20'))  # 8 PM
BUSINESS_TIMEZONE = os.getenv('BUSINESS_TIMEZONE', 'America/New_York')

# Message Delay Configuration
MESSAGE_DELAY_MIN = int(os.getenv('MESSAGE_DELAY_MIN', '5'))  # 5 minutes
MESSAGE_DELAY_MAX = int(os.getenv('MESSAGE_DELAY_MAX', '10'))  # 10 minutes

# Test Mode - bypasses delays and business hour restrictions
TEST_MODE = os.getenv('TEST_MODE', 'False') == 'True'

# Lead Scoring Thresholds
HOT_LEAD_SCORE_THRESHOLD = float(os.getenv('HOT_LEAD_SCORE_THRESHOLD', '0.7'))
WARM_LEAD_SCORE_THRESHOLD = float(os.getenv('WARM_LEAD_SCORE_THRESHOLD', '0.5'))

# WhatsApp Configuration (Phase 2)
WHATSAPP_PHONE_NUMBER = os.getenv('WHATSAPP_PHONE_NUMBER')
WHATSAPP_TEST_MODE = os.getenv('WHATSAPP_TEST_MODE', 'True') == 'True'

# Zapier Webhooks (Phase 3)
ZAPIER_CLUBREADY_WEBHOOK = os.getenv('ZAPIER_CLUBREADY_WEBHOOK')
ZAPIER_TEST_MODE = os.getenv('ZAPIER_TEST_MODE', 'True') == 'True'

# Twilio Configuration (Future)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_TEST_MODE = os.getenv('TWILIO_TEST_MODE', 'True') == 'True'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'leads': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
