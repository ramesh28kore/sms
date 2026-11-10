"""
Base Django settings for Avanthi Attendance & Parent Alerts.
Environment-specific files (development.py, production.py, testing.py) import this.
All secrets are read from environment variables. Never commit real secrets.
"""

import os
from pathlib import Path

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# src/ is the Django root (where manage.py lives).
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # == src/

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-in-production-avanthi-sms-2026")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "django_celery_beat",
    "django_htmx",
    "crispy_forms",
    "crispy_tailwind",
    "axes",
    "phonenumber_field",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.institution",
    "apps.academics",
    "apps.people",
    "apps.scheduling",
    "apps.attendance",
    "apps.notifications",
    "apps.gateways",
    "apps.imports_export",
    "apps.reporting",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.institution.context_processors.institute_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="avanthi_sms"),
        "USER": config("POSTGRES_USER", default="avanthi"),
        "PASSWORD": config("POSTGRES_PASSWORD", default=""),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "OPTIONS": {
            "connect_timeout": 10,
        },
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # Axes must be first for lockout to work
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# django-allauth configuration
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_EMAIL_VERIFICATION = "none"  # No self-service registration; admin creates users
ACCOUNT_SIGNUP_FORM_CLASS = None
ACCOUNT_ADAPTER = "apps.accounts.adapters.NoSignupAccountAdapter"
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
MFA_ADAPTER = "allauth.mfa.adapter.DefaultMFAAdapter"
MFA_TOTP_PERIOD = 30
MFA_TOTP_DIGITS = 6
# Recovery codes
MFA_RECOVERY_CODE_COUNT = 10

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# django-axes (brute-force protection)
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCKOUT_URL = "/accounts/locked/"
AXES_RESET_ON_SUCCESS = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 28800  # 8 hours
SESSION_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TIMEZONE = "UTC"  # Celery always uses UTC; app translates for display
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True  # Tasks re-queued on worker crash (app handles idempotency)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair dispatch; one task at a time per worker slot
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Task routing: gateway sends go to a dedicated queue with limited concurrency
CELERY_TASK_ROUTES = {
    "apps.gateways.tasks.*": {"queue": "gateway_sender"},
}
CELERY_TASK_DEFAULT_QUEUE = "default"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # Django always stores in UTC
USE_I18N = True
USE_TZ = True

INSTITUTE_TIMEZONE = config("INSTITUTE_TIMEZONE", default="Asia/Kolkata")
PHONE_REGION = config("PHONE_REGION", default="IN")

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static_src" / "dist"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ---------------------------------------------------------------------------
# SMS Gateway
# ---------------------------------------------------------------------------
SMS_MODE = config("SMS_MODE", default="simulator")  # 'simulator' or 'live'
OPENSMS_HOST = config("OPENSMS_HOST", default="")
OPENSMS_PORT = config("OPENSMS_PORT", default=9292, cast=int)
OPENSMS_API_KEY_REF = config("OPENSMS_API_KEY_REF", default="OPENSMS_SECRET")
# The actual key is read at runtime from the env var named by OPENSMS_API_KEY_REF.
# It is NEVER stored in settings or logs.

# ---------------------------------------------------------------------------
# File uploads
# ---------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = config("MAX_UPLOAD_MB", default=10, cast=int) * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Suppress phone numbers / message content from reaching log handlers.
        # Gateway adapter must NOT log phone numbers or message text at any level.
        "apps.gateways": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Crispy forms
# ---------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# ---------------------------------------------------------------------------
# HTMX
# ---------------------------------------------------------------------------
HTMX_USE_MULTI_SWAP = True

# ---------------------------------------------------------------------------
# Phonenumber field
# ---------------------------------------------------------------------------
PHONENUMBER_DEFAULT_REGION = PHONE_REGION
PHONENUMBER_DB_FORMAT = "E164"

