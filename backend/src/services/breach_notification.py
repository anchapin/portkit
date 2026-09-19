"""
Data Breach Notification Service for portkit.

Implements GDPR Article 33 / Article 34 breach detection, structured logging,
and notification triggering. The 72-hour notification to the competent
supervisory authority is a LEGAL obligation; this service facilitates it by
recording the breach, computing the authority-notification deadline, alerting
the internal security contact, and surfacing all Article 33 required fields.
The actual notification to the supervisory authority remains a human /
operational step triggered by the alert this service raises.

Design notes:
- Async-first (AGENTS.md).
- Pydantic V2 models.
- No global state: the notification sender is injected (Protocol) so it can be
  mocked in tests and swapped for a real email/PagerDuty/Slack transport in
  production without changing this module.
- Field names intentionally mirror the reference test contract in
  tests/test_compliance_comprehensive.py::TestDataBreachNotification.

Issue: #1671 - Add Data Breach Notification Procedure to Code.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# GDPR Article 33(1): notify the supervisory authority without undue delay and,
# where feasible, not later than 72 hours after having become aware of it.
AUTHORITY_NOTIFICATION_DEADLINE_HOURS: int = 72

# Security / privacy contacts (see SECURITY.md). The domain was updated to
# portkit.ai in #1833.
DEFAULT_SECURITY_CONTACT: str = os.getenv("BREACH_SECURITY_CONTACT", "security@portkit.ai")
DEFAULT_PRIVACY_CONTACT: str = os.getenv("BREACH_PRIVACY_CONTACT", "privacy@portkit.ai")


class BreachSeverity(str, Enum):
    """Severity classification for a personal-data breach."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BreachEvent(BaseModel):
    """A detected personal-data breach (GDPR Art. 33).

    Captures everything needed to assess the breach, notify the supervisory
    authority, and (where required) communicate to affected data subjects.
    """

    model_config = ConfigDict(from_attributes=True)

    event_id: str = Field(default_factory=lambda: f"breach_{uuid.uuid4().hex[:12]}")
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: BreachSeverity = BreachSeverity.HIGH
    scope: str = Field(description="Systems / services affected by the breach.")
    affected_users: int = Field(
        default=0, ge=0, description="Approximate number of data subjects affected."
    )
    affected_data_types: list[str] = Field(
        default_factory=list,
        description="Categories of personal data affected (e.g. email, password hash).",
    )
    description: str = Field(description="Nature of the breach and how it was detected.")
    source: str = Field(description="What raised the breach (e.g. unauthorized_access).")
    likely_consequences: str | None = Field(
        default=None, description="Likely consequences of the breach (Art. 33(3)(c))."
    )
    measures_taken: str | None = Field(
        default=None, description="Measures taken or proposed (Art. 33(3)(d))."
    )
    detected_by: str | None = None


class BreachNotification(BaseModel):
    """A breach notification message (internal security contact or data subject).

    Field names mirror the reference test contract so the same payload shape is
    usable both in code and in the compliance test suite.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: str | None = None
    recipient: str
    breach_description: str
    data_affected: list[str]
    actions_taken: str
    notification_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    contact_info: str = DEFAULT_SECURITY_CONTACT
    event_id: str | None = None
    authority_notification_deadline: datetime | None = None
    is_to_authority: bool = False


class BreachLogEntry(BaseModel):
    """Append-only record of a breach + its notifications, kept on the service."""

    model_config = ConfigDict(from_attributes=True)

    event: BreachEvent
    authority_deadline: datetime
    notifications_sent: list[BreachNotification] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationSender(Protocol):
    """Transport-agnostic sender for breach notifications (mockable in tests)."""

    async def send(self, notification: BreachNotification) -> bool:
        """Deliver a notification. Return True on success, False on failure."""
        ...


class LoggingNotificationSender:
    """Default sender that logs the notification. Used when no transport is wired.

    This is intentionally side-effect-light: it records the notification to the
    structured log so on-call can act. Production deployments inject a real
    transport (email / PagerDuty / Slack) via the service constructor.
    """

    async def send(self, notification: BreachNotification) -> bool:
        target = "supervisory authority" if notification.is_to_authority else notification.recipient
        logger.critical(
            "DATA BREACH NOTIFICATION (event=%s, to=%s): %s",
            notification.event_id,
            target,
            notification.breach_description,
            extra={
                "breach_event_id": notification.event_id,
                "notification_recipient": notification.recipient,
                "is_authority_notification": notification.is_to_authority,
                "data_affected": notification.data_affected,
            },
        )
        return True


def authority_notification_deadline(detected_at: datetime) -> datetime:
    """Return the GDPR Art. 33 supervisory-authority notification deadline."""
    aware = detected_at if detected_at.tzinfo else detected_at.replace(tzinfo=timezone.utc)
    return aware + timedelta(hours=AUTHORITY_NOTIFICATION_DEADLINE_HOURS)


def is_within_authority_window(detected_at: datetime, now: datetime | None = None) -> bool:
    """Whether we are still inside the 72-hour authority-notification window."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now <= authority_notification_deadline(detected_at)


class BreachNotificationService:
    """Detects breaches, logs them, and triggers notifications.

    Instantiate once (e.g. via a FastAPI dependency) and inject a sender. The
    in-memory breach log is an audit trail for tests and operational tooling;
    production deployments may also persist BreachLogEntry to the database or a
    SIEM.
    """

    def __init__(
        self,
        sender: NotificationSender | None = None,
        security_contact: str = DEFAULT_SECURITY_CONTACT,
        privacy_contact: str = DEFAULT_PRIVACY_CONTACT,
    ) -> None:
        self._sender: NotificationSender = sender or LoggingNotificationSender()
        self.security_contact = security_contact
        self.privacy_contact = privacy_contact
        self._breach_log: list[BreachLogEntry] = []

    @property
    def breach_log(self) -> list[BreachLogEntry]:
        """Append-only record of recorded breaches and dispatched notifications."""
        return list(self._breach_log)

    def log_breach_event(self, event: BreachEvent) -> BreachLogEntry:
        """Record a breach event with structured logging and return the log entry.

        This is the single source of truth that a breach occurred. It always
        logs at CRITICAL severity so SIEM / alerting pipelines pick it up.
        """
        deadline = authority_notification_deadline(event.detected_at)
        logger.critical(
            "DATA BREACH DETECTED (id=%s severity=%s scope=%s affected_users=%s)",
            event.event_id,
            event.severity.value,
            event.scope,
            event.affected_users,
            extra={
                "breach_event_id": event.event_id,
                "breach_severity": event.severity.value,
                "breach_scope": event.scope,
                "affected_users": event.affected_users,
                "affected_data_types": event.affected_data_types,
                "breach_source": event.source,
                "authority_notification_deadline": deadline.isoformat(),
            },
        )
        entry = BreachLogEntry(event=event, authority_deadline=deadline)
        self._breach_log.append(entry)
        return entry

    async def detect_breach(
        self,
        *,
        severity: BreachSeverity,
        scope: str,
        affected_users: int,
        affected_data_types: list[str],
        description: str,
        source: str,
        detected_by: str | None = None,
        likely_consequences: str | None = None,
        measures_taken: str | None = None,
    ) -> BreachLogEntry:
        """Create, log, and alert on a newly detected breach.

        Triggers the internal security/privacy notification immediately. The
        authority notification itself is a human step; this raises the alert
        and records the 72-hour deadline so on-call can act within the law.
        """
        event = BreachEvent(
            severity=severity,
            scope=scope,
            affected_users=affected_users,
            affected_data_types=affected_data_types,
            description=description,
            source=source,
            detected_by=detected_by,
            likely_consequences=likely_consequences,
            measures_taken=measures_taken,
        )
        entry = self.log_breach_event(event)

        # Alert the internal security contact immediately. This is the trigger
        # for the 72-hour authority-notification workflow (see runbook).
        alert = BreachNotification(
            recipient=self.security_contact,
            user_id=None,
            breach_description=description,
            data_affected=affected_data_types,
            actions_taken=measures_taken or "Investigation in progress",
            notification_date=datetime.now(timezone.utc),
            contact_info=self.privacy_contact,
            event_id=event.event_id,
            authority_notification_deadline=entry.authority_deadline,
            is_to_authority=False,
        )
        try:
            await self._sender.send(alert)
            entry.notifications_sent.append(alert)
        except Exception:  # pragma: no cover - defensive: never swallow detection
            logger.exception("Failed to dispatch breach alert for event %s", event.event_id)

        return entry

    async def send_breach_notification(
        self,
        event: BreachEvent,
        *,
        recipient: str,
        user_id: str | None = None,
        is_to_authority: bool = False,
        actions_taken: str | None = None,
    ) -> BreachNotification:
        """Send a notification about a recorded breach to a recipient.

        Use ``is_to_authority=True`` when notifying the supervisory authority
        (Art. 33) and leave it False when notifying affected data subjects
        (Art. 34, high-risk breaches).
        """
        deadline = authority_notification_deadline(event.detected_at)
        notification = BreachNotification(
            recipient=recipient,
            user_id=user_id,
            breach_description=event.description,
            data_affected=event.affected_data_types,
            actions_taken=actions_taken or event.measures_taken or "See incident record",
            notification_date=datetime.now(timezone.utc),
            contact_info=self.privacy_contact if is_to_authority else self.security_contact,
            event_id=event.event_id,
            authority_notification_deadline=deadline,
            is_to_authority=is_to_authority,
        )
        await self._sender.send(notification)

        # Append to the matching breach log entry if present.
        for entry in self._breach_log:
            if entry.event.event_id == event.event_id:
                entry.notifications_sent.append(notification)
                break

        return notification


def get_breach_notification_service() -> BreachNotificationService:
    """Factory / FastAPI dependency provider.

    Production wiring should override this to inject a real transport (email,
    PagerDuty, etc.). Kept as a function to satisfy the project's
    ``Depends(get_...)`` convention without introducing global state.
    """
    return BreachNotificationService()
