"""
SimulatorLedgerEntry — records every simulated send attempt.
Stored in a separate table from live delivery attempts.
Cannot be promoted to live namespace.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class SimulatorLedgerEntry(models.Model):
    """
    Records one simulated send in the simulator ledger.
    Does NOT store phone numbers or message text (only lengths).
    Cannot be promoted to or confused with live delivery attempts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt_id = models.CharField(
        _("delivery attempt ID"), max_length=64,
        help_text="ID of the DeliveryAttempt row this simulation corresponds to.",
    )
    gateway_id = models.CharField(_("gateway ID"), max_length=64, blank=True, null=True)
    scenario = models.CharField(_("scenario"), max_length=64, default="accept_all")
    # Store only lengths, never actual phone or message content
    destination_length = models.PositiveSmallIntegerField(_("destination length"))
    message_length = models.PositiveIntegerField(_("message length"))
    estimated_segments = models.PositiveSmallIntegerField(_("estimated segments"), default=1)
    simulated_outcome = models.CharField(_("simulated outcome"), max_length=32)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gateways_simulator_ledger"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"SimLedger {self.attempt_id}: {self.simulated_outcome}"

