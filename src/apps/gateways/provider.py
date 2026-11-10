"""
OpenSMS provider interface and adapter.

Reviewed upstream contract (commit 810c20de0e512bd0e92094d550a6ddef58a6e286):
- POST /sms/ with Authorization: Bearer <key>, JSON: {number, text}
- Response: JSON {"stat": true|false}
- stat=true = gateway DISPATCH ACCEPTED (not delivery confirmation)
- stat=false = NOT success; API key/number/server error
- No idempotency, no delivery receipts, no health endpoint
- Android path: SmsManager.sendTextMessage without callbacks
- Ambiguous outcomes: timeout/crash after request = UNKNOWN_OUTCOME (no auto-retry)

This module contains:
1. SmsProviderInterface: abstract base
2. OpenSmsAdapter: wraps real OpenSMS HTTP call
3. DeterministicSimulator: for development/testing (never sends real SMS)

API keys NEVER appear in:
- Logs (this module's logger does not log phone numbers or message text)
- Browser JavaScript
- Source control
- Screenshots

Keys are read at call time from environment variables named by GatewayConfig.api_key_env_ref.
"""
import enum
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("apps.gateways")
# This logger does NOT log phone numbers, message text, or API keys.
# Any debug logging here must use safe identifiers only (e.g., attempt ID).


class SendOutcome(enum.Enum):
    """
    Outcome of one send attempt.
    Maps directly to DeliveryAttempt.outcome choices.
    """
    DISPATCH_ACCEPTED = "dispatch_accepted"      # stat=true in response body
    FAILED_PRE_SUBMIT = "failed_pre_submit"      # Definitely failed before any network call
    FAILED_POST_SUBMIT = "failed_post_submit"    # Responded clearly after request with failure
    UNKNOWN_OUTCOME = "unknown_outcome"          # May or may not have submitted


@dataclass
class SendRequest:
    """Input to the provider."""
    attempt_id: str                 # DeliveryAttempt.id (for log correlation only)
    destination: str                # E.164 normalized phone number
    message_text: str               # Rendered message text
    estimated_segments: int = 1
    is_simulation: bool = True      # Must be True for simulator; False for real


@dataclass
class SendResult:
    """Result from one provider call."""
    outcome: SendOutcome
    error_message: str = ""
    http_status_code: Optional[int] = None
    gateway_stat_value: Optional[bool] = None   # Raw stat from JSON response (if parseable)
    provider_response_body: str = ""            # Truncated, never logged with PII
    # Timing
    attempt_started_at: Optional[datetime] = None
    attempt_ended_at: Optional[datetime] = None


class SmsProviderInterface(ABC):
    """
    Abstract interface for SMS delivery providers.
    Implementations: OpenSmsAdapter and DeterministicSimulator.
    """

    @abstractmethod
    def send(self, request: SendRequest) -> SendResult:
        """
        Attempt to send one SMS.
        This method is called once per attempt. The caller commits the attempt record
        BEFORE calling this. Retries require a new attempt record.
        """
        ...

    @abstractmethod
    def check_connectivity(self) -> dict:
        """
        Non-sending connectivity check (does NOT send SMS).
        Returns a dict with 'reachable': bool and optional diagnostic info.
        Limitations are documented honestly.
        """
        ...


class OpenSmsAdapter(SmsProviderInterface):
    """
    Adapter for OpenSMS (https://github.com/daslearning-org/OpenSMS).
    Reviewed at commit 810c20de0e512bd0e92094d550a6ddef58a6e286.

    Limitations (do NOT invent):
    - No idempotency key
    - No delivery receipt
    - No bulk API
    - No confirmed health/status endpoint
    - Timeout after submission = UNKNOWN_OUTCOME, not retryable automatically
    - Android SmsManager does not provide carrier-acceptance callbacks
    """

    # OpenSMS does NOT provide a dedicated health endpoint.
    # We attempt a benign GET to / as a reachability check only.
    # A 404 or any HTTP response proves the server is up; connection error proves it's down.

    def __init__(self, host: str, port: int, api_key_env_ref: str):
        self.base_url = f"http://{host}:{port}"
        self._api_key_env_ref = api_key_env_ref
        # Connect timeout and read timeout are separate.
        # Read timeout must be generous (Android sending can take several seconds).
        # Retries are DISABLED; the caller decides retry eligibility.
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            follow_redirects=False,  # No unexpected redirects
            max_redirects=0,
        )

    def _get_api_key(self) -> str:
        key = os.environ.get(self._api_key_env_ref, "")
        if not key:
            raise ValueError(
                f"OpenSMS API key not found in environment variable '{self._api_key_env_ref}'. "
                "Configure the gateway before use."
            )
        return key

    def send(self, request: SendRequest) -> SendResult:
        """
        POST /sms/ to the OpenSMS device.
        Parse response body for 'stat'. HTTP 200 alone is NOT success.
        """
        if request.is_simulation:
            raise RuntimeError(
                "OpenSmsAdapter.send() called with is_simulation=True. "
                "Use DeterministicSimulator for simulated sends."
            )

        started_at = datetime.now(timezone.utc)
        result = SendResult(
            outcome=SendOutcome.UNKNOWN_OUTCOME,
            attempt_started_at=started_at,
        )

        try:
            api_key = self._get_api_key()
        except ValueError as exc:
            result.outcome = SendOutcome.FAILED_PRE_SUBMIT
            result.error_message = str(exc)
            result.attempt_ended_at = datetime.now(timezone.utc)
            return result

        try:
            response = self._client.post(
                f"{self.base_url}/sms/",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "number": request.destination,
                    "text": request.message_text,
                },
            )
            result.http_status_code = response.status_code
            result.attempt_ended_at = datetime.now(timezone.utc)

            # Parse response body for 'stat'
            try:
                body = response.json()
                stat = body.get("stat")
                result.gateway_stat_value = bool(stat) if stat is not None else None
            except Exception:
                # Malformed JSON response
                result.gateway_stat_value = None
                result.error_message = f"Malformed JSON response (HTTP {response.status_code})"
                result.outcome = SendOutcome.UNKNOWN_OUTCOME
                return result

            # Determine outcome
            if result.gateway_stat_value is True:
                # stat=true: dispatch accepted by gateway
                # Does NOT confirm handset delivery or carrier acceptance
                result.outcome = SendOutcome.DISPATCH_ACCEPTED
            elif result.gateway_stat_value is False:
                # stat=false: explicitly not accepted
                # We know the request was processed but rejected
                result.outcome = SendOutcome.FAILED_POST_SUBMIT
                result.error_message = f"Gateway returned stat=false (HTTP {response.status_code})"
            else:
                # stat key missing or null
                result.outcome = SendOutcome.UNKNOWN_OUTCOME
                result.error_message = f"Gateway response missing 'stat' (HTTP {response.status_code})"

            return result

        except httpx.ConnectError as exc:
            # Connection refused / host unreachable BEFORE sending
            result.outcome = SendOutcome.FAILED_PRE_SUBMIT
            result.error_message = f"Connection error: {type(exc).__name__}"
            result.attempt_ended_at = datetime.now(timezone.utc)
            return result

        except httpx.TimeoutException as exc:
            # Timeout: could be before OR after the request was delivered.
            # We cannot determine if the message was sent. → UNKNOWN_OUTCOME.
            result.outcome = SendOutcome.UNKNOWN_OUTCOME
            result.error_message = f"Timeout: {type(exc).__name__}. Message may or may not have been sent."
            result.attempt_ended_at = datetime.now(timezone.utc)
            return result

        except Exception as exc:
            # Any other unexpected error after the connection opened = UNKNOWN_OUTCOME
            # (conservative: we may have submitted but not seen the response)
            if result.http_status_code is not None:
                result.outcome = SendOutcome.UNKNOWN_OUTCOME
                result.error_message = f"Unexpected error after HTTP call: {type(exc).__name__}"
            else:
                # HTTP call had not been made yet
                result.outcome = SendOutcome.FAILED_PRE_SUBMIT
                result.error_message = f"Unexpected pre-submit error: {type(exc).__name__}"
            result.attempt_ended_at = datetime.now(timezone.utc)
            return result

    def check_connectivity(self) -> dict:
        """
        Non-sending connectivity check.
        Attempts a GET to /; interprets any HTTP response as 'reachable'.
        Does NOT send any SMS.
        Limitation: OpenSMS has no documented health endpoint. A 404 still proves the server is up.
        A cloud host cannot automatically reach a device on campus Wi-Fi without a tunnel.
        """
        try:
            response = self._client.get(
                f"{self.base_url}/",
                headers={"Accept": "application/json"},
            )
            return {
                "reachable": True,
                "http_status": response.status_code,
                "note": (
                    "OpenSMS has no dedicated health endpoint. "
                    "Any HTTP response indicates the server process is reachable. "
                    "This does not confirm SIM status or SMS permission."
                ),
            }
        except httpx.ConnectError:
            return {
                "reachable": False,
                "error": "Connection refused or host unreachable.",
                "note": (
                    "If the application is on a cloud server, it cannot reach a campus LAN device "
                    "without a configured secure tunnel."
                ),
            }
        except httpx.TimeoutException:
            return {
                "reachable": False,
                "error": "Connection timeout.",
            }
        except Exception as exc:
            return {
                "reachable": False,
                "error": f"{type(exc).__name__}",
            }

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass


class DeterministicSimulator(SmsProviderInterface):
    """
    Deterministic simulator for development and testing.
    NEVER sends real SMS. Records all calls to SimulatorLedger in the database.
    Uses a configurable scenario to produce predictable outcomes.

    Default scenario: all sends are DISPATCH_ACCEPTED.
    Special scenarios for testing:
    - 'fail_all': all sends return FAILED_PRE_SUBMIT
    - 'timeout_all': all sends return UNKNOWN_OUTCOME (simulated timeout)
    - 'stat_false': all sends return FAILED_POST_SUBMIT (stat=false)
    - 'mixed': alternates between success and failure

    Rows written to SimulatorLedger are NEVER promoted to live dispatch state.
    """

    def __init__(self, scenario: str = "accept_all", gateway_id: str | None = None):
        self.scenario = scenario
        self.gateway_id = gateway_id
        self._call_count = 0

    def send(self, request: SendRequest) -> SendResult:
        """
        Record a simulated send. Never sends real SMS.
        """
        self._call_count += 1
        started_at = datetime.now(timezone.utc)

        # Determine simulated outcome based on scenario
        outcome, stat, error = self._compute_outcome(self._call_count)

        # Persist to SimulatorLedger
        self._record_to_ledger(
            attempt_id=request.attempt_id,
            destination=request.destination,
            message_length=len(request.message_text),
            estimated_segments=request.estimated_segments,
            outcome=outcome,
        )

        ended_at = datetime.now(timezone.utc)
        return SendResult(
            outcome=outcome,
            http_status_code=200 if stat is not None else None,
            gateway_stat_value=stat,
            error_message=error,
            provider_response_body="[SIMULATED]",
            attempt_started_at=started_at,
            attempt_ended_at=ended_at,
        )

    def _compute_outcome(self, call_number: int):
        """Return (outcome, stat_value, error_message) for this scenario."""
        if self.scenario == "accept_all":
            return SendOutcome.DISPATCH_ACCEPTED, True, ""
        elif self.scenario == "fail_all":
            return SendOutcome.FAILED_PRE_SUBMIT, None, "Simulated connection failure."
        elif self.scenario == "timeout_all":
            return SendOutcome.UNKNOWN_OUTCOME, None, "Simulated timeout — message may or may not have been sent."
        elif self.scenario == "stat_false":
            return SendOutcome.FAILED_POST_SUBMIT, False, "Simulated stat=false response."
        elif self.scenario == "mixed":
            if call_number % 3 == 0:
                return SendOutcome.UNKNOWN_OUTCOME, None, "Simulated timeout."
            elif call_number % 3 == 1:
                return SendOutcome.DISPATCH_ACCEPTED, True, ""
            else:
                return SendOutcome.FAILED_POST_SUBMIT, False, "Simulated stat=false."
        else:
            return SendOutcome.DISPATCH_ACCEPTED, True, ""

    def _record_to_ledger(self, attempt_id, destination, message_length, estimated_segments, outcome):
        """Record to SimulatorLedger table (best-effort; never raises)."""
        try:
            SimulatorLedgerEntry.objects.create(
                attempt_id=attempt_id,
                gateway_id=self.gateway_id,
                scenario=self.scenario,
                destination_length=len(destination),  # Do NOT store the actual number
                message_length=message_length,
                estimated_segments=estimated_segments,
                simulated_outcome=outcome.value,
            )
        except Exception as exc:
            logger.warning("SimulatorLedger record failed: %s", type(exc).__name__)

    def check_connectivity(self) -> dict:
        return {
            "reachable": True,
            "note": "Simulator mode: no real gateway connectivity. This check is always 'reachable'.",
            "is_simulation": True,
        }


# Import here to avoid circular dependency
from apps.gateways.simulator_ledger import SimulatorLedgerEntry  # noqa: E402

