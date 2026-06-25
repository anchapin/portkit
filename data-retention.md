# Data Retention Policy and GDPR Compliance

**Issue**: [#1207](https://github.com/anchapin/portkit/issues/1207)  
**Milestone**: M5 (Pre-beta)  
**Last Updated**: 2026-05-03

---

## 1. Overview

This document outlines the data retention policies for PortKit's mod conversion service, with specific focus on GDPR compliance and user rights under EU data protection regulations.

### 1.1 Scope

This policy applies to:
- All uploaded JAR/ZIP mod files (input files)
- All generated output files (.mcaddon, .zip)
- Associated metadata and conversion records
- User-provided feedback and ratings

### 1.2 Data Controller

**PortKit** ("we", "our", or "us") acts as the data controller for all personal data processed in connection with this service.

**Contact**: privacy@portkit.ai

---

## 2. GDPR Compliance Statement

PortKit is committed to complying with the **General Data Protection Regulation (GDPR)** (EU) 2016/679 for all users, with particular attention to:

| GDPR Article | Requirement | Implementation |
|-------------|-------------|----------------|
| **Art. 5** | Principles of processing | Data minimization, purpose limitation |
| **Art. 15** | Right of access | User data export endpoint |
| **Art. 16** | Right to rectification | Profile update capabilities |
| **Art. 17** | Right to erasure ("right to be forgotten") | Automated + manual deletion |
| **Art. 20** | Right to data portability | JSON export format |
| **Art. 32** | Security of processing | Encryption, access controls |

---

## 3. Data Retention Periods

### 3.1 Input Files (.jar, .zip)

| File Type | Retention Period | Deletion Trigger |
|-----------|-----------------|------------------|
| Uploaded mod files | **24 hours maximum** | Automatic deletion after conversion OR 24h expiry |
| Orphaned files (no active job) | **1 hour** | Hourly cleanup task |

**Implementation**: `services.celery_tasks.delete_input_file()` - called immediately after conversion completes

### 3.2 Output Files (.mcaddon, .zip)

| File Type | Retention Period | Deletion Trigger |
|-----------|-----------------|------------------|
| Converted output files | **7 days** | Automatic purge after retention period |

**Implementation**: `services.celery_tasks.purge_orphaned_files()` - daily cleanup at 7-day cutoff

### 3.3 Conversion Records & Metadata

| Record Type | Retention Period | Notes |
|-------------|-----------------|-------|
| Job metadata (status, timestamps) | **90 days** | For analytics and debugging |
| Audit logs | **1 year** | Security and compliance |
| Conversion feedback | **Indefinite** | Used for AI model improvement unless user requests deletion |

### 3.4 User Account Data

| Data Type | Retention Period | Deletion Trigger |
|-----------|-----------------|------------------|
| Beta signup email | Until account deletion | User-initiated |
| API keys | Until account deletion | User-initiated |
| Rate limit counters | **24 hours** | Rolling window |

---

## 4. Right to Erasure ("Right to Be Forgotten")

### 4.1 GDPR Article 17 Compliance

Users have the right to request deletion of their personal data. We implement this through:

#### 4.1.1 Automated Deletion

- **Input files**: Automatically deleted within 24 hours of upload or immediately after conversion
- **Output files**: Automatically purged after 7 days
- **Inactive accounts**: Data deleted after 365 days of inactivity

#### 4.1.2 Manual Deletion Requests

Users may submit deletion requests via:
- **Email**: privacy@portkit.ai
- **GitHub Issue**: [New Issue](https://github.com/anchapin/portkit/issues/new/choose)

For EU users, we will respond to erasure requests within **30 days** per GDPR Art. 17(3).

### 4.2 Data That Cannot Be Deleted

The following may be retained despite an erasure request due to legal/operational necessity:

- **Audit logs** containing file deletion events (retained for 1 year for compliance)
- **Aggregated/anonymized analytics** (no longer personally identifiable)
- **Legal obligations** requiring data retention (e.g., tax records)

### 4.3 Deletion Request Process

```
User Request → Verify Identity → Process Deletion → Confirm Completion
     ↓              ↓                ↓                ↓
  Contact us    Email/Issue    Max 30 days      Email confirmation
```

---

## 5. JAR File Lifecycle

### 5.1 Upload Phase

```
User Upload → Malware Scan → ClamAV → Store in temp_uploads/{job_id}/{file_id}.jar
                                    ↓
                              Store metadata in DB
```

### 5.2 Processing Phase

```
AI Engine Processing → Conversion → Output Generated → Input File Scheduled for Deletion
                                            ↓
                               User Notified (WebSocket/Email)
```

### 5.3 Deletion Phase

```
Scheduled Task (Celery) → Verify No Active Job → os.remove() → Audit Log Entry
                                        ↓
                              Log: job_id, filename, deleted_by="system"
```

### 5.4 Orphaned File Cleanup

Hourly cron job `purge_orphaned_files()` identifies and deletes:
- Files older than 24 hours with no associated active job
- Output files older than 7 days with no associated active job

---

## 6. Data Minimization & Purpose Limitation

### 6.1 Data We Collect

| Data Type | Purpose | Legal Basis |
|-----------|---------|-------------|
| Email (optional) | Beta access, support | Consent |
| Mod files | AI conversion service | Contract performance |
| Feedback/Ratings | AI model improvement | Legitimate interest |
| IP addresses | Security, rate limiting | Legitimate interest |

### 6.2 Data We Do NOT Collect

- Minecraft account credentials
- Personal identification beyond what is voluntarily provided
- Third-party data not directly related to the conversion service

---

## 7. Security Measures

### 7.1 Technical Safeguards

- **Encryption at rest**: AES-256 for stored files
- **Encryption in transit**: TLS 1.2+ for all uploads/downloads
- **Access controls**: Role-based access control (RBAC) for internal systems
- **Malware scanning**: ClamAV scan on all uploaded files

### 7.2 Organizational Safeguards

- **Access logging**: All data access logged with timestamp, user ID, action
- **Audit reviews**: Quarterly access pattern reviews
- **Staff training**: GDPR awareness training for all personnel

---

## 8. Data Subject Rights

### 8.1 How to Exercise Your Rights

| Right | Method | Response Time |
|-------|--------|---------------|
| Access (Art. 15) | Email/Issue | 30 days |
| Rectification (Art. 16) | Profile settings | 30 days |
| Erasure (Art. 17) | Email/Issue | 30 days |
| Portability (Art. 20) | Email/Issue | 30 days |

### 8.2 Contact Information

**Data Protection Inquiries**:  
📧 privacy@portkit.ai

**GitHub Issues**:  
[Open a new issue](https://github.com/anchapin/portkit/issues/new/choose) with the label `data-privacy`

---

## 9. Policy Updates

This policy is reviewed **annually** or when significant changes occur to our data processing activities.

**Changelog**:
- 2026-05-03: Initial version (M5 pre-beta)

---

## 10. Related Documentation

- [Privacy Notice](./legal/PRIVACY.md) - Full privacy statement
- [Security Policy](./SECURITY.md) - Security practices
- [Security Incident Runbook](./runbooks/security-incident.md) - Incident response & data breach notification procedure (GDPR Art. 33/34)
