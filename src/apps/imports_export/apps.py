"""AppConfig for imports_export."""
from django.apps import AppConfig


class ImportsExportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.imports_export"
    verbose_name = "Imports & Exports"

