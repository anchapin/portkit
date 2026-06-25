# Security Incident Response Runbook — Personal Data Breach

This runbook defines the operational procedure for responding to a **personal
data breach** at portkit, satisfying **GDPR Article 33** (notification to the
supervisory authority within **72 hours**) and **Article 34** (communication to
affected data subjects when the breach is likely to result in a high risk to
their rights and freedoms).

> **The 72-hour clock is a legal obligation.** It starts the moment portkit
> becomes *aware* of the breach — not when the breach began. Treat every alert
> from `BreachNotificationService` as the start of that clock.

---

## 1. Code entry points

| Concern | Location |
| --- | --- |
| Breach detection + logging + alert trigger | `backend/src/services/breach_notification.py` (`BreachNotificationService`) |
| Authority-notification deadline math (72h) | `authority_notification_deadline()`, `is_within_authority_window()` |
| Notification email/copy template (Art. 33 fields) | `backend/src/services/templates/breach_notification_template.py` |
| Factory / DI provider | `get_breach_notification_service()` |
| Contacts | `security@portkit.ai`, `privacy@portkit.ai` (see `SECURITY.md`) |

`detect_breach(...)` is the call a detector (IDS, WAF, audit job, on-call human)
makes the instant a breach is suspected. It:
1. logs the breach at `CRITICAL` severity (SIEM picks it up),
2. records it in the in-memory breach log with the computed 72-hour deadline,
3. fires an alert to `security@portkit.ai` via the injected sender.

The authority notification itself is a **human / operational step** triggered by
that alert — automated systems do not file regulator reports.

---

## 2. Procedure

### Step 1 — Detection
A breach is "detected" when any of the following raise:
- a security signal (IDS/WAF, ClamAV, anomaly alert) that exposes personal data,
- an engineer or user report of unauthorized access / disclosure / loss,
- `BreachNotificationService.detect_breach(...)` being invoked from code.

```python
from services.breach_notification import BreachNotificationService, BreachSeverity

svc = get_breach_notification_service()
await svc.detect_breach(
    severity=BreachSeverity.CRITICAL,
    scope="auth-service",
    affected_users=1000,                 # best estimate, refine later
    affected_data_types=["email", "hashed_password"],
    description="Unauthorized access to auth DB; credentials possibly exfiltrated",
    source="unauthorized_access",
    likely_consequences="Credential-stuffing and phishing risk",
    measures_taken="Revoked sessions, rotated secrets, blocked source IP",
)
```

### Step 2 — Assessment (within ~24 h)
The on-call + DPO confirm:
- **Nature** of the breach and root cause.
- **Categories and approximate numbers** of data subjects and records
  (Art. 33(3)(a)). Update `affected_users` / `affected_data_types`.
- **Likely consequences** (Art. 33(3)(c)).
- **Measures taken or proposed** (Art. 33(3)(d)).
- Whether the breach is **high-risk** to data subjects (triggers Art. 34).

Record the updated assessment on the breach log entry.

### Step 3 — Notify the supervisory authority (within 72 h of awareness)
Render the Article 33 notification and dispatch it to the competent supervisory
authority. The deadline is computed by `authority_notification_deadline()` and
is carried on every `BreachNotification`.

```python
from services.templates.breach_notification_template import render_breach_notification_email

rendered = render_breach_notification_email(
    event, contact_info="privacy@portkit.ai", is_authority_notification=True
)
# rendered["subject"], rendered["body"] -> send to the competent DPA.
```

The notification **must** contain Art. 33(3)(a)–(d):
1. nature of the breach + categories/approximate number of data subjects & records,
2. DPO / contact point (`privacy@portkit.ai`),
3. likely consequences,
4. measures taken or proposed.

If portkit is **not** required to notify (e.g. the breach is unlikely to result
in a risk to data subjects), **document the justification** on the breach log
— the DPA can demand it.

### Step 4 — Notify affected data subjects (Art. 34, without undue delay)
If the breach is **likely to result in a high risk** to data subjects, notify
them directly, in clear plain language, of:
- the nature of the breach,
- the DPO / contact point,
- likely consequences,
- measures taken (including what they can do to protect themselves).

```python
# Per-subject copy (is_to_authority=False)
await svc.send_breach_notification(
    event, recipient="user@example.com", user_id="user123", is_to_authority=False,
    actions_taken="Force-reset your password; we have invalidated all sessions.",
)
```

Exceptions to Art. 34 (still document them): appropriate technical
protection (e.g. strong encryption rendered data unintelligible), or subsequent
measures making the high risk no longer likely.

### Step 5 — Containment & eradication
Revoke sessions, rotate secrets/keys, patch the vector, restore from clean
backups, re-deploy. Validate eradication before Step 6.

### Step 6 — Post-incident review
Within **10 business days**, hold a blameless retrospective covering:
- timeline (detection → awareness → authority notice → subject notice → close),
- root cause and why it was not prevented,
- what we changed (code, alerting, runbook, policy),
- whether the 72-hour obligation was met; if not, why.

File the review against the breach `event_id`.

---

## 3. Timeline summary

| T (from awareness) | Action |
| --- | --- |
| T+0 | `detect_breach()` — breach logged, `security@` alerted |
| T+24 h | Assessment complete; numbers/consequences/measures confirmed |
| T ≤ 72 h | Supervisory authority notified (Art. 33) — **hard legal deadline** |
| Without undue delay | High-risk data subjects notified (Art. 34) |
| T+10 business days | Post-incident review |

---

## 4. Contacts
- Security: `security@portkit.ai`
- Privacy / DPO: `privacy@portkit.ai`
- Reporting a vulnerability: see [`../SECURITY.md`](../SECURITY.md)

## 5. Related documentation
- [`../data-retention.md`](../data-retention.md) — data retention policy
- [`../SECURITY.md`](../SECURITY.md) — security policy & vulnerability reporting
- `tests/test_compliance_comprehensive.py::TestDataBreachNotification` — compliance test contract
- `backend/src/tests/unit/test_breach_notification.py` — service unit tests
