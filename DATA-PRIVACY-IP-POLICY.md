# Data Privacy and IP Handling Policy

**Effective Date:** 2026-04-28
**Last Updated:** 2026-05-16
**Policy Owner:** PortKit
**Version:** 1.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [Data Retention](#2-data-retention)
3. [AI Training and Model Improvement](#3-ai-training-and-model-improvement)
4. [Commercial IP Protection](#4-commercial-ip-protection)
5. [Security Measures](#5-security-measures)
6. [GDPR Compliance](#6-gdpr-compliance)
7. [Enterprise Options](#7-enterprise-options)
8. [User Rights](#8-user-rights)
9. [Policy Updates](#9-policy-updates)
10. [Contact Information](#10-contact-information)

---

## 1. Overview

This policy governs how PortKit handles user data, intellectual property, and security for our mod conversion service. We recognize that commercial developers entrust us with valuable intellectual property, and we take that responsibility seriously.

### 1.1 Scope

This policy applies to:
- All users of the PortKit conversion service (including beta testers)
- Uploaded mod files (`.jar`, `.zip`)
- Generated output files (`.mcaddon`, `.zip`)
- Associated metadata and conversion records
- User-provided feedback and ratings

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Data Minimization** | We collect only what is necessary to provide the service |
| **User Control** | You retain ownership of your mods and can request deletion |
| **Transparency** | Clear disclosure of how we handle your data |
| **Security First** | Enterprise-grade security for all user files |
| **Legal Compliance** | GDPR compliant, DMCA compliant, IP-aware |

---

## 2. Data Retention

### 2.1 File Retention Schedule

| File Type | Retention Period | Deletion Trigger |
|-----------|-----------------|------------------|
| **Input files** (uploaded `.jar`, `.zip`) | **24 hours maximum** | Automatic deletion after conversion OR 24h expiry, whichever comes first |
| **Orphaned files** (no active job) | **1 hour** | Hourly cleanup task |
| **Output files** (`.mcaddon`, `.zip`) | **7 days** | Automatic purge after retention period |
| **Conversion metadata** (job IDs, timestamps) | **90 days** | Analytics and debugging |
| **Audit logs** | **1 year** | Security and compliance |
| **Feedback/Ratings** | **Indefinite** | Unless user requests deletion |

### 2.2 Deletion Process

```
Upload → Conversion Complete → Input File Scheduled for Deletion → Automatic Removal
                                                              ↓
                                                    Audit Log Entry Created
```

**Implementation:**
- Input files are deleted immediately after conversion completes (typically within minutes)
- Orphaned uploads (not associated with a job) are purged hourly
- Output files are automatically purged after 7 days
- All deletion events are logged for audit compliance

### 2.3 What Gets Deleted

You can verify our data handling by examining:
- **Audit logs**: All file deletion events are recorded with timestamp, job ID, and deletion reason
- **Job records**: Metadata retained for 90 days for operational purposes, then anonymized

### 2.4 Data That Cannot Be Deleted

Due to legal and operational requirements, the following may be retained despite a deletion request:

- **Audit logs** (1 year retention for compliance)
- **Aggregated/anonymized analytics** (no longer personally identifiable)
- **Legal obligations** requiring data retention

---

## 3. AI Training and Model Improvement

### 3.1 How We Use Your Data for AI Improvement

The data we collect is used to improve our AI conversion model. This includes:

| Data Type | Used for AI Training | Retention for Training |
|-----------|---------------------|------------------------|
| Uploaded mod files | No | Deleted within 24h |
| Converted output files | No | Deleted within 7 days |
| Feedback (ratings) | Yes | Indefinite unless deleted |
| Feedback (comments) | Yes | Indefinite unless deleted |

### 3.2 What We Do NOT Use for Training

**We do not train on:**
- Your proprietary mod source code
- Files from commercial/enterprise accounts (unless explicitly agreed)
- Any content flagged as confidential

### 3.3 Opt-Out Options

| Opt-Out Method | What It Covers |
|----------------|----------------|
| **Skip feedback** | Providing ratings/comments is entirely optional |
| **Request deletion** | Contact us to delete your feedback data |
| **Enterprise agreement** | Custom terms available for commercial users |

### 3.4 Training Data Governance

Our AI training process:

1. **Input files** are never used for model training
2. **Output files** are never used for model training
3. **Feedback** helps identify successful conversions but does not contain your source code
4. **No PII** is attached to training samples

---

## 4. Commercial IP Protection

### 4.1 User Ownership

**You retain full ownership of all intellectual property:**

- Mods you upload remain your property
- PortKit does not claim ownership of user-uploaded content
- Converted outputs are derivative works—**you** are responsible for ensuring the original mod permits conversion

### 4.2 License Detection

Before conversion, we scan for license indicators:

| License Type | Action |
|--------------|--------|
| **ARR (All Rights Reserved)** | Blocked—requires explicit permission |
| **GPL-incompatible** | Blocked—requires explicit permission |
| **Unknown/No license** | User prompted to confirm rights |
| **MIT/Apache/BSD/CC0/GPL 3.0+** | Proceed with conversion |

### 4.3 Enterprise NDA and DPA Options

For commercial users with additional IP requirements:

| Option | Description |
|--------|-------------|
| **NDA (Non-Disclosure Agreement)** | Protects your mod source code from disclosure |
| **DPA (Data Processing Agreement)** | Contractual data processing terms per GDPR Art. 28 |
| **Custom Terms** | Enterprise agreements available upon request |

**Contact:** enterprise@portkit.ai for NDA/DPA agreements.

### 4.4 DMCA Compliance

We respond to valid DMCA takedown notices within 24 hours:

1. **Acknowledge** receipt within 4 hours
2. **Verify** notice validity (all required elements)
3. **Remove** or disable access within 24 hours
4. **Notify** affected user within 48 hours

**DMCA Agent:** Alex Chapin (PortKit Founder)
**Email:** dmca@portkit.ai

---

## 5. Security Measures

### 5.1 File Scanning

**All uploaded files are scanned before processing:**

| Scanner | Purpose | Action on Detection |
|---------|---------|---------------------|
| **ClamAV** | Malware detection | Quarantine and reject |
| **File validation** | Format verification | Reject malformed files |
| **Size limits** | Resource protection | Reject oversized files |

### 5.2 Encryption

| State | Protection |
|-------|------------|
| **At rest** | AES-256 encryption for stored files |
| **In transit** | TLS 1.2+ for all uploads/downloads |
| **In processing** | Ephemeral compute, no persistent storage of raw input |

### 5.3 Access Controls

- **Role-based access control (RBAC)** for internal systems
- **No public access** to uploaded files
- **Access logging** for all data operations
- **Quarterly access reviews** for internal compliance

### 5.4 Security Process Flow

```
Upload → ClamAV Scan → Validation → Encryption at Rest → Processing
                              ↓
                    Reject if malicious
```

---

## 6. GDPR Compliance

PortKit complies with the General Data Protection Regulation (GDPR) for all users:

| GDPR Article | Requirement | Implementation |
|-------------|-------------|----------------|
| Art. 5 | Principles of processing | Data minimization, purpose limitation |
| Art. 15 | Right of access | Data export endpoint |
| Art. 16 | Right to rectification | Profile update capabilities |
| Art. 17 | Right to erasure | Automated + manual deletion |
| Art. 20 | Right to data portability | JSON export format |
| Art. 28 | Data Processing Agreement | Available for enterprise |
| Art. 32 | Security of processing | Encryption, access controls |

### 6.1 Lawful Basis for Processing

| Data Type | Purpose | Legal Basis |
|-----------|---------|-------------|
| Mod files | AI conversion service | Contract performance |
| Feedback/Ratings | AI model improvement | Legitimate interest |
| IP addresses | Security, rate limiting | Legitimate interest |
| Email (optional) | Beta access, support | Consent |

---

## 7. Enterprise Options

For commercial developers and enterprises with heightened IP requirements:

### 7.1 Available Enterprise Agreements

| Agreement | Purpose |
|-----------|---------|
| **NDA** | Mutual protection of confidential information |
| **DPA** | GDPR Art. 28 compliant data processing terms |
| **Custom SLA** | Guaranteed service levels |
| **Dedicated infrastructure** | Isolated processing environment |

### 7.2 Enterprise Features

- **No AI training** on enterprise account data (opt-out by default)
- **Extended retention** options available (30/60/90 days)
- **Audit reports** for compliance reporting
- **Dedicated support** channel
- **SLA guarantees** with uptime commitments

### 7.3 Getting Started with Enterprise

Contact **enterprise@portkit.ai** for:
- Pricing and availability
- Custom agreement drafting
- Proof of concept for your use case

---

## 8. User Rights

### 8.1 Your Rights Under This Policy

| Right | Description | How to Exercise |
|-------|-------------|-----------------|
| **Access** | Request a copy of your data | Email/Issue |
| **Rectification** | Correct inaccurate data | Profile settings |
| **Erasure** | Request deletion of your data | Email/Issue |
| **Portability** | Export your data in JSON format | Email/Issue |
| **Object** | Opt out of specific processing | Email/Issue |

### 8.2 Response Timeline

| Request Type | Response Time |
|--------------|---------------|
| General inquiries | 5 business days |
| Data access requests | 30 days |
| Deletion requests | 30 days |
| Enterprise agreements | 10 business days |

### 8.3 Deletion Request Process

```
Contact Us → Identity Verification → Request Processing → Confirmation
     ↓              ↓                    ↓                  ↓
  Email/Issue    Required           Max 30 days       Email confirmation
```

---

## 9. Policy Updates

We may update this policy to reflect changes in our practices or legal requirements.

**Changelog:**
- 2026-05-16: Consolidated policy (previously spread across multiple documents)
- 2026-05-03: Added NDA/DPA options for enterprise
- 2026-04-28: Initial release

**Notification:** Significant changes will be communicated via:
- Email to registered users
- Notice on the PortKit platform
- GitHub issue tracker

---

## 10. Contact Information

| Purpose | Contact |
|---------|---------|
| **General Privacy Questions** | privacy@portkit.ai |
| **Data Deletion Requests** | privacy@portkit.ai |
| **GDPR Inquiries** | privacy@portkit.ai |
| **Enterprise Agreements (NDA/DPA)** | enterprise@portkit.ai |
| **DMCA Notices** | dmca@portkit.ai |
| **IP Questions** | ip@portkit.ai |
| **Legal Matters** | legal@portkit.ai |

---

## Related Documentation

- [DMCA / Copyright / IP Risk Policy](../ip-policy.md)
- [Data Retention Policy and GDPR Compliance](../data-retention.md)
- [Privacy Notice: Training Data](./legal/PRIVACY.md)
- [Security Policy](../SECURITY.md)

---

*Last Updated: 2026-05-16*