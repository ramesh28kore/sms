"""
Django settings package.
- base.py: shared settings for all environments
- development.py: local overrides (DEBUG=True, console email)
- production.py: production overrides (HTTPS, whitenoise, security headers)
- testing.py: fast test settings (in-memory caches, synchronous tasks)
"""

