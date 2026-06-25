# DMCA / Copyright / IP Risk Policy

**Effective Date:** 2026-04-28
**Last Updated:** 2026-05-03
**Policy Owner:** PortKit

---

## 1. Purpose and Scope

This policy governs intellectual property risk management for PortKit's mod conversion service. It establishes procedures for:

- Detecting potentially infringing content before conversion
- Responding to DMCA takedown notices
- Handling user content that may violate third-party IP rights
- Protecting PortKit's legal standing as a service provider

This policy applies to all users of the PortKit conversion service, including beta testers and enterprise customers.

---

## 2. Background: Mod Licensing Risk

Minecraft Java Edition mods are copyrighted software. The majority use restrictive licenses:

| License Type | Description | Conversion Risk |
|--------------|-------------|-----------------|
| **ARR (All Rights Reserved)** | Explicit prohibition on redistribution, repackaging, or conversion | HIGH — conversion may be infringement |
| **GPL-incompatible** | Custom licenses that don't permit derivative works | HIGH — same as ARR |
| **Implicit copyright** | Mods without license files — "no license" ≠ "free to use" | MEDIUM — requires user to verify rights |
| **MIT / Apache / BSD** | Permissive licenses allowing derivative works | LOW — generally safe to convert |
| **GPL 3.0+** | Copyleft — derivatives must use same license | LOW — compatible with PortKit output |
| **CC0 / Unlicense** | Public domain — no restrictions | NONE — safe to convert |

When a user uploads someone else's mod and converts it, PortKit may be:

1. **Creating an unauthorized derivative work** (the Bedrock port)
2. **Facilitating copyright infringement** by enabling redistribution

This is the same legal risk that caused several mod conversion tools to shut down.

---

## 3. Mod License Detection

### 3.1 Automated License Scanning

Before any conversion proceeds, the system scans uploaded mods for license indicators:

**Files scanned (in order of priority):**
1. `LICENSE`, `LICENSE.md`, `LICENSE.txt` — explicit license files
2. `META-INF/MANIFEST.MF` — may contain license metadata
3. `pack.mcmeta` — Minecraft pack metadata
4. CurseForge/Modrinth metadata from API lookup

**Pattern detection:**
- License file content analysis using keyword matching
- Manifest attributes (`Bundle-Name`, `Implementation-Vendor`, etc.)
- API-based lookup via CurseForge or Modrinth mod ID

### 3.2 License Classification

| Classification | Indicators | Action |
|----------------|-------------|--------|
| **PERMISSIVE** | MIT, Apache 2.0, BSD, CC0, Unlicense, GPL 3.0+ | Proceed with conversion |
| **RESTRICTIVE** | "All Rights Reserved", "ARR", custom restrictive, EULA | Block conversion, show warning |
| **UNKNOWN** | No license detected | Prompt user to confirm rights |
| **NOT_ARR** | Modrinth/CurseForge API confirms non-ARR | Proceed with conversion |

### 3.3 User Warning Flow

```
User uploads mod
       ↓
License scan completes
       ↓
┌────────────────────────────────────┐
│ RESTRICTIVE LICENSE DETECTED       │
│                                    │
│ "This mod appears to use          │
│  All Rights Reserved licensing.    │
│  Do you have explicit permission  │
│  from the mod author to convert   │
│  it to Bedrock Edition?"          │
│                                    │
│ [ ] I have permission (verify)    │
│ [ ] Cancel conversion             │
└────────────────────────────────────┘
```

**If user cannot verify permission:** conversion is blocked. The mod is not processed.

**If user claims permission:** user must acknowledge a warranty checkbox before conversion proceeds.

---

## 4. Terms of Service — Conversion Authorization

By using PortKit, users represent and warrant that:

> **"I have the legal right to convert the mod I am uploading. I am either (a) the original mod author, (b) explicitly authorized by the mod author to convert their mod, or (c) converting a mod with a permissive license (MIT, Apache 2.0, BSD, CC0, GPL 3.0+, or Unlicense) that permits derivative works."**

Users agree to indemnify and hold harmless PortKit from any claims arising from unauthorized conversion.

---

## 5. DMCA Takedown Procedure

### 5.1 DMCA Agent Information

**Designated Agent:** Alex Chapin (PortKit Founder)
**Email:** dmca@portkit.ai
**Address:** Available upon formal written request

*Note: DMCA agent registration with US Copyright Office is required before beta launch. Estimated cost: $6/year.*

### 5.2 Takedown Notice Requirements

Valid DMCA notices must include:

1. **Identification of copyrighted work** — describe the original mod
2. **Identification of infringing material** — describe or link to the PortKit conversion
3. **Good faith belief** — statement that the use is not authorized
4. **Accuracy attestation** — "I swear, under penalty of perjury, that..."
5. **Contact information** — email, address, phone
6. **Signature** — physical or electronic

### 5.3 Internal Takedown Process

```
DMCA Notice Received (email to dmca@...)
       ↓
[ Hour 0-4 ]
Acknowledge receipt to sender
Log notice in DMCA tracking system
       ↓
[ Hour 4-8 ]
Verify notice validity (check all required elements)
Identify affected conversion/job
       ↓
[ Hour 8-24 ]
Remove or disable access to infringing content
Notify user that their content was removed
Document removal in audit log
       ↓
[ After removal ]
Send counter-notice option to affected user
Preserve notice for potential litigation
```

### 5.4 Response Timeline

| Action | Deadline |
|--------|----------|
| Acknowledge receipt | 4 hours |
| Remove/disable content | 24 hours |
| Notify affected user | 48 hours |

### 5.5 User Counter-Notice

If a user believes their content was wrongly removed, they may submit a counter-notice:

- Must include original infringement allegation details
- Must state a good faith belief the removal was a mistake
- Must consent to jurisdiction in the US
- PortKit has 10-14 days to reinstate content after valid counter-notice

---

## 6. Attribution in Converted Output

All converted `.mcaddon` files include original mod attribution in `manifest.json`:

```json
{
  "header": {
    "name": "Converted Mod Name",
    "uuid": "...",
    "version": [1, 0, 0],
    "description": "Converted from [Mod Name] by [Author] (Java Edition). Original license: MIT. Converted by PortKit."
  }
}
```

If the original license cannot be determined, the description reads:

```json
"description": "Converted from [Mod Name] by [Author]. Original license: Unknown. Converted by PortKit. If you are the copyright holder and believe this conversion is unauthorized, contact privacy@portkit.ai"
```

---

## 7. User Content Handling

### 7.1 Content Retention and IP

- **User retains all rights** to mods they upload
- PortKit does **not** claim ownership of user-uploaded content
- Converted outputs are considered derivative works — user's responsibility to ensure original mod permits conversion

### 7.2 Content Removal

PortKit reserves the right to remove content that:

- Violates third-party IP rights (confirmed DMCA)
- Contains malicious code or malware
- Violates Acceptable Use Policy

### 7.3 Suspension and Termination

Users who repeatedly submit DMCA-flagged content may have their account suspended or terminated.

---

## 8. Optional: Mod Ownership Verification (Stretch Goal)

For future implementation:

**CurseForge/Modrinth Integration:**
- Detect mod ID from uploaded file metadata
- Look up author and license via API
- Surface this information before conversion
- Allow mod authors to opt-out of PortKit conversions

**Verification Workflow:**
```
User uploads mod
       ↓
Detect CurseForge/Modrinth mod ID
       ↓
Query API for author + license
       ↓
┌───────────────────────────────┐
│ "This mod is [Name] by        │
│  [Author]. Licensed under     │
│  [License]. Proceed?"          │
└───────────────────────────────┘
```

---

## 9. Legal References

- **DMCA (Digital Millennium Copyright Act):** 17 U.S.C. § 512
- **US Copyright Office DMCA Agent Directory:** https://www.copyright.gov/dmca-directory/
- **Minecraft Mod Licensing:** Most popular CurseForge mods use ARR or custom restrictive licenses
- **Safe Harbor Provisions:** PortKit qualifies for DMCA safe harbor if we respond promptly to valid notices

---

## 10. Related Documents

- `docs/legal/PRIVACY.md` — Privacy policy and data handling
- `docs/legal/conversion-audit.md` — Approved test mods and license compliance
- `docs/beta-signup-page.md` — Beta program terms

---

## 11. Contact

For IP-related inquiries, contact:

- **General IP questions:** ip@portkit.ai
- **DMCA notices:** dmca@portkit.ai
- **Legal matters:** legal@portkit.ai