"""Production settings — HTTPS required, strict security headers."""
from decouple import Csv, config

from .base import *  # noqa: F401, F403
from .base import LOGGING

DEBUG = False

# Behind a TLS-terminating proxy (Vercel, nginx). Trust X-Forwarded-Proto so
# SECURE_SSL_REDIRECT does not loop and request.is_secure() is correct.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True

# Email
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=25, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

# Logging: more verbose in production
import logging
LOGGING["root"]["level"] = "INFO"

# ---------------------------------------------------------------------------
# Serverless (Vercel) adjustments — active when the VERCEL env var is set
# ---------------------------------------------------------------------------
if config("VERCEL", default="", cast=str):
    # No build step runs collectstatic on Vercel; serve via staticfiles finders.
    WHITENOISE_USE_FINDERS = True
    STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
    # Read-only filesystem: media uploads go to /tmp (ephemeral).
    MEDIA_ROOT = "/tmp/media"
    # Hosted Postgres (Neon/Vercel Postgres) requires TLS.
    DATABASES["default"]["OPTIONS"]["sslmode"] = config(  # noqa: F405
        "POSTGRES_SSLMODE", default="require"
    )
    # Vercel Postgres integration exposes POSTGRES_DATABASE instead of POSTGRES_DB.
    if not config("POSTGRES_DB", default=""):
        DATABASES["default"]["NAME"] = config(  # noqa: F405
            "POSTGRES_DATABASE", default="verceldb"
        )
    # Allow skipping Redis: locmem cache is enough (sessions are DB-backed).
    if REDIS_URL.startswith("locmem"):  # noqa: F405
        CACHES["default"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}

