"""
Breach notification message templates (GDPR Article 33 / Article 34).

Renders the structured :class:`~services.breach_notification.BreachEvent` into
human-readable email/Slack payloads that include every field Article 33(3)
requires supervisory-authority notifications to contain:

    (a) the nature of the breach including, where possible, the categories and
        approximate number of data subjects and of personal data records
        concerned;
    (b) the name and contact details of the data protection officer or other
        contact point where more information can be obtained;
    (c) the likely consequences of the personal data breach;
    (d) the measures taken or proposed to be taken by the controller to address
        the personal data breach, including, where appropriate, measures to
        mitigate its possible adverse effects.

Issue: #1671.
"""

from __future__ import annotations

from typing import Any

from services.breach_notification import (
    AUTHORITY_NOTIFICATION_DEADLINE_HOURS,
    BreachEvent,
    BreachNotification,
    authority_notification_deadline,
)


def render_breach_notification_email(
    event: BreachEvent,
    *,
    contact_info: str,
    is_authority_notification: bool = True,
) -> dict[str, Any]:
    """Render a breach notification into an email ``{subject, body}`` payload.

    Args:
        event: The recorded breach event.
        contact_info: Contact point for more information (DPO / security).
        is_authority_notification: When True the copy is addressed to the
            supervisory authority and emphasizes the 72-hour obligation.

    Returns:
        A dict with ``subject`` and ``body`` (plain text) keys.
    """
    deadline = authority_notification_deadline(event.detected_at)
    audience = "Supervisory Authority" if is_authority_notification else "Affected Data Subject"
    subject = (
        f"[{event.severity.value.upper()}] Personal Data Breach Notification "
        f"({event.event_id}) — {audience}"
    )

    data_types = ", ".join(event.affected_data_types) or "unknown"
    body = (
        f"Personal Data Breach Notification — {audience}\n"
        f"{'=' * 60}\n\n"
        f"Event ID: {event.event_id}\n"
        f"Detected at (UTC): {event.detected_at.isoformat()}\n"
        f"Severity: {event.severity.value}\n"
        f"Scope (systems affected): {event.scope}\n\n"
        f"Article 33(3)(a) — Nature of the breach:\n"
        f"  {event.description}\n"
        f"  Categories of personal data concerned: {data_types}\n"
        f"  Approximate number of data subjects: {event.affected_users}\n\n"
        f"Article 33(3)(b) — Contact point for more information:\n"
        f"  {contact_info}\n\n"
        f"Article 33(3)(c) — Likely consequences:\n"
        f"  {event.likely_consequences or 'Assessment in progress'}\n\n"
        f"Article 33(3)(d) — Measures taken or proposed:\n"
        f"  {event.measures_taken or 'Containment and investigation in progress'}\n\n"
        f"Authority notification deadline (72h): {deadline.isoformat()}\n"
        f"Source of detection: {event.source}\n"
    )

    if is_authority_notification:
        body += (
            f"\nThis notification is provided under GDPR Article 33, within "
            f"{AUTHORITY_NOTIFICATION_DEADLINE_HOURS} hours of becoming aware of "
            f"the breach.\n"
        )

    return {"subject": subject, "body": body}


def render_notification_from_payload(notification: BreachNotification) -> dict[str, Any]:
    """Render an already-built :class:`BreachNotification` into an email payload.

    Useful when the notification has been customized (e.g. per-data-subject
    copy under Article 34) before rendering.
    """
    deadline = notification.authority_notification_deadline
    audience = "Supervisory Authority" if notification.is_to_authority else "Affected Data Subject"
    subject = f"Personal Data Breach Notification — {audience}" + (
        f" (event {notification.event_id})" if notification.event_id else ""
    )
    data_types = ", ".join(notification.data_affected) or "unknown"
    body = (
        f"Personal Data Breach Notification — {audience}\n"
        f"{'=' * 60}\n\n"
        f"Breach description: {notification.breach_description}\n"
        f"Data affected: {data_types}\n"
        f"Actions taken: {notification.actions_taken}\n"
        f"Notification date: {notification.notification_date.isoformat()}\n"
        f"Contact: {notification.contact_info}\n"
    )
    if deadline is not None:
        body += f"Authority notification deadline (72h): {deadline.isoformat()}\n"
    return {"subject": subject, "body": body}
