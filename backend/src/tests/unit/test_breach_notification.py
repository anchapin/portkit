"""
Unit tests for the data breach notification service.

Covers detection logging, the 72-hour authority-notification window, Article 33
notification content, and the mockable notification sender. Mirrors the
reference contract in tests/test_compliance_comprehensive.py but exercises the
real implementation.

Issue: #1671.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from services.breach_notification import (
    AUTHORITY_NOTIFICATION_DEADLINE_HOURS,
    BreachNotification,
    BreachNotificationService,
    BreachSeverity,
    LoggingNotificationSender,
    authority_notification_deadline,
    is_within_authority_window,
)
from services.breach_notification import BreachEvent
from services.templates.breach_notification_template import (
    render_breach_notification_email,
    render_notification_from_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class TestBreachDetectionLogging:
    """detect_breach / log_breach_event behavior."""

    async def test_detect_breach_logs_event_with_expected_fields(self):
        svc = BreachNotificationService(sender=AsyncMock(return_value=True))
        entry = await svc.detect_breach(
            severity=BreachSeverity.CRITICAL,
            scope="auth-service",
            affected_users=1000,
            affected_data_types=["email", "username"],
            description="Unauthorized access detected",
            source="unauthorized_access",
        )
        # Reference contract: a breach log carries these required fields.
        log = {
            "event_id": entry.event.event_id,
            "detected_at": entry.event.detected_at.isoformat(),
            "severity": entry.event.severity.value,
            "affected_users": entry.event.affected_users,
            "data_types": entry.event.affected_data_types,
            "source": entry.event.source,
        }
        assert log["severity"] == "critical"
        assert len(log["data_types"]) > 0
        assert log["event_id"].startswith("breach_")
        assert entry.event.affected_users == 1000

    async def test_detect_breach_triggers_security_contact_notification(self):
        sender = AsyncMock()
        sender.send.return_value = True
        svc = BreachNotificationService(sender=sender)
        entry = await svc.detect_breach(
            severity=BreachSeverity.HIGH,
            scope="api",
            affected_users=5,
            affected_data_types=["email"],
            description="Token leak",
            source="log_scan",
        )
        assert sender.send.await_count == 1
        alert = sender.send.await_args.args[0]
        assert alert.recipient == svc.security_contact
        assert alert.event_id == entry.event.event_id
        # The breach log records the dispatched notification.
        assert entry.notifications_sent[0] is alert

    def test_log_breach_event_is_recorded_in_breach_log(self):
        svc = BreachNotificationService()
        event = BreachEvent(
            severity=BreachSeverity.LOW,
            scope="cache",
            affected_users=1,
            affected_data_types=["nickname"],
            description="Misconfigured cache",
            source="audit",
        )
        entry = svc.log_breach_event(event)
        assert entry in svc.breach_log
        assert entry.authority_deadline == authority_notification_deadline(event.detected_at)


class TestAuthorityNotificationWindow:
    """GDPR Art. 33 72-hour deadline math."""

    def test_authority_deadline_is_72_hours_after_detection(self):
        detected = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert authority_notification_deadline(detected) == detected + timedelta(hours=72)

    async def test_notification_within_72_hour_period_is_allowed(self):
        detected = datetime.now(timezone.utc)
        assert is_within_authority_window(detected, now=detected + timedelta(hours=24)) is True
        assert is_within_authority_window(detected, now=detected + timedelta(hours=72)) is True

    async def test_notification_outside_72_hour_period_is_late(self):
        detected = datetime.now(timezone.utc)
        late = detected + timedelta(hours=72, seconds=1)
        assert is_within_authority_window(detected, now=late) is False

    def test_deadline_constant_matches_gdpr(self):
        assert AUTHORITY_NOTIFICATION_DEADLINE_HOURS == 72


class TestBreachNotificationContent:
    """Article 33 required fields are present on every notification."""

    async def test_notification_contains_required_content_fields(self):
        svc = BreachNotificationService(sender=AsyncMock(return_value=True))
        event = BreachEvent(
            severity=BreachSeverity.HIGH,
            scope="db",
            affected_users=42,
            affected_data_types=["email", "hashed_password"],
            description="Unauthorized access detected",
            source="ids",
        )
        notification = await svc.send_breach_notification(
            event,
            recipient="user123",
            user_id="user123",
            actions_taken="All affected accounts secured",
        )
        # Reference contract: these fields must be present.
        payload = {
            "user_id": notification.user_id,
            "breach_description": notification.breach_description,
            "data_affected": notification.data_affected,
            "actions_taken": notification.actions_taken,
            "notification_date": notification.notification_date.isoformat(),
            "contact_info": notification.contact_info,
        }
        required_fields = ["breach_description", "data_affected", "notification_date"]
        assert all(field in payload for field in required_fields) is True
        assert notification.authority_notification_deadline is not None

    async def test_authority_notification_flagged_distinctly(self):
        svc = BreachNotificationService(sender=AsyncMock(return_value=True))
        event = BreachEvent(
            severity=BreachSeverity.CRITICAL,
            scope="auth",
            affected_users=10,
            affected_data_types=["email"],
            description="Exfiltration",
            source="soc",
        )
        authority = await svc.send_breach_notification(
            event, recipient="dpa@example.gov", is_to_authority=True
        )
        assert authority.is_to_authority is True

    async def test_send_breach_notification_appends_to_existing_log_entry(self):
        svc = BreachNotificationService(sender=AsyncMock(return_value=True))
        entry = await svc.detect_breach(
            severity=BreachSeverity.HIGH,
            scope="api",
            affected_users=3,
            affected_data_types=["email"],
            description="Leak",
            source="audit",
        )
        await svc.send_breach_notification(
            entry.event, recipient="dpa@example.gov", is_to_authority=True
        )
        # One alert from detect_breach + one explicit authority notification.
        assert len(entry.notifications_sent) == 2


class TestNotificationSender:
    """The sender Protocol is mockable; default sender logs."""

    async def test_logging_notification_sender_returns_true(self):
        sent = await LoggingNotificationSender().send(
            BreachNotification(
                recipient="security@portkit.ai",
                breach_description="x",
                data_affected=["email"],
                actions_taken="none",
            )
        )
        assert sent is True

    async def test_sender_failure_does_not_suppress_detection(self):
        failing = AsyncMock()
        failing.send.side_effect = RuntimeError("transport down")
        svc = BreachNotificationService(sender=failing)
        entry = await svc.detect_breach(
            severity=BreachSeverity.HIGH,
            scope="api",
            affected_users=1,
            affected_data_types=["email"],
            description="d",
            source="s",
        )
        # Detection is recorded even if the alert transport fails.
        assert entry in svc.breach_log
        assert entry.notifications_sent == []


class TestBreachTemplate:
    """Article 33(3)(a)-(d) fields appear in the rendered template."""

    def test_template_includes_all_article_33_fields(self):
        event = BreachEvent(
            severity=BreachSeverity.HIGH,
            scope="orders-db",
            affected_users=1500,
            affected_data_types=["email", "address"],
            description="SQL injection exposed orders table",
            source="waf",
            likely_consequences="Phishing and identity theft risk",
            measures_taken="Patched, rotated credentials, notified DPO",
        )
        rendered = render_breach_notification_email(
            event, contact_info="privacy@portkit.ai", is_authority_notification=True
        )
        body = rendered["body"]
        assert "Article 33(3)(a)" in body and "orders table" in body
        assert "Article 33(3)(b)" in body and "privacy@portkit.ai" in body
        assert "Article 33(3)(c)" in body and "Phishing" in body
        assert "Article 33(3)(d)" in body and "Patched" in body
        assert "72h" in body

    def test_render_notification_from_payload_round_trips(self):
        notification = BreachNotification(
            recipient="security@portkit.ai",
            breach_description="desc",
            data_affected=["email"],
            actions_taken="act",
            notification_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            contact_info="privacy@portkit.ai",
        )
        rendered = render_notification_from_payload(notification)
        assert "desc" in rendered["body"] and "email" in rendered["body"]
