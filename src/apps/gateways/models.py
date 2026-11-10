"""
Gateways models: GatewayConfig, GatewayRuntime, GatewayBudgetDay, SimulationRun.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class GatewayConfig(models.Model):
    """
    One registered SMS gateway (OpenSMS device or simulator).
    API key stored via env var reference, never in plain settings.
    Allowlisted hosts only (LAN addresses are legitimate).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=128, unique=True)
    # Allowlisted host (LAN IP or hostname; must be administrator-confirmed)
    host = models.CharField(
        _("host"), max_length=253,
        help_text="LAN IP or hostname of the OpenSMS device. Must be allowlisted.",
    )
    port = models.PositiveIntegerField(_("port"), default=9292)
    # API key is stored in an env var; this field names which env var to read.
    api_key_env_ref = models.CharField(
        _("API key env variable name"), max_length=128, default="OPENSMS_SECRET",
        help_text="Name of the environment variable holding the actual API key. Never store the key here.",
    )
    is_simulator = models.BooleanField(
        _("is simulator"), default=True,
        help_text="True = use deterministic simulator; False = real OpenSMS HTTP call.",
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_paused = models.BooleanField(_("paused"), default=False)
    pause_reason = models.CharField(_("pause reason"), max_length=512, blank=True)
    paused_at = models.DateTimeField(_("paused at"), null=True, blank=True)
    # Daily segment budget
    daily_segment_limit = models.PositiveIntegerField(
        _("daily segment limit"), default=500,
        help_text="Maximum SMS segments per day. 0 = no limit (not recommended).",
    )
    # Device capability (informs segment estimator)
    supports_unicode = models.BooleanField(
        _("supports Unicode SMS"), default=True,
        help_text="Unconfirmed for modem targets. Android: typically yes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gateways_config"
        ordering = ["name"]

    def __str__(self):
        mode = "SIM" if self.is_simulator else "LIVE"
        return f"{self.name} [{mode}]"


class GatewayBudgetDay(models.Model):
    """
    Per-gateway per-local-date segment budget tracking.
    Atomic shared budget enforced at the database level.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey(GatewayConfig, on_delete=models.CASCADE, related_name="budget_days")
    budget_date = models.DateField(_("date"))
    limit = models.PositiveIntegerField(_("segment limit"))
    reserved = models.PositiveIntegerField(_("reserved segments"), default=0)
    consumed = models.PositiveIntegerField(_("consumed segments"), default=0)

    class Meta:
        db_table = "gateways_budget_day"
        unique_together = [("gateway", "budget_date")]

    def __str__(self):
        return f"{self.gateway} on {self.budget_date}: {self.consumed}/{self.limit}"

    @property
    def available(self) -> int:
        return max(0, self.limit - self.reserved - self.consumed)


class SimulationRun(models.Model):
    """
    Tracks a simulator session. Rows cannot be promoted to live namespace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(_("namespace"), max_length=64, unique=True)
    scenario_seed = models.CharField(_("scenario seed"), max_length=256, blank=True)
    description = models.CharField(_("description"), max_length=512, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        db_table = "gateways_simulation_run"

    def __str__(self):
        return f"SimRun {self.namespace}"


from .simulator_ledger import SimulatorLedgerEntry  # noqa: F401


