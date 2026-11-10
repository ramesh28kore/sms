"""Vercel serverless entry point for the Django WSGI app.

Adds src/ to sys.path so `config` and `apps` packages resolve,
then exposes the WSGI application as `app` for @vercel/python.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application as app  # noqa: E402
