"""Testing settings — fast, isolated, synchronous."""
from .base import *  # noqa: F401, F403

DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast password hashing in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Synchronous Celery tasks in tests (bypass broker)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable axes in tests
AXES_ENABLED = False

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SMS_MODE = "simulator"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Cache: use in-memory in tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

