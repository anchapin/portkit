# Security Policy

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Security Advisories**: Use the [GitHub Security Advisory](https://github.com/anchapin/portkit/security/advisories/new) to report vulnerabilities privately.

2. **Email**: Contact us at **security@portkit.ai** for security reports, or **privacy@portkit.ai** for privacy / personal-data concerns (including suspected data breaches).

### What to Include

When reporting a security vulnerability, please include:

- Type of vulnerability (e.g., XSS, SQL injection, etc.)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact assessment of the vulnerability

## Disclosure Process

Once we receive a security vulnerability report:

1. **Acknowledgment**: We will acknowledge receipt of your report within 48 hours.

2. **Initial Assessment**: We will conduct an initial assessment to determine the severity and validity of the vulnerability.

3. **Regular Updates**: We will provide updates on the progress of addressing the vulnerability every 7 days.

4. **Resolution**: We will work on a fix and test the solution.

5. **Public Disclosure**: Once the vulnerability has been addressed, we will publicly disclose the details in the release notes.

## Supported Versions

We currently support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Security Best Practices

When contributing to portkit, please follow these security best practices:

- Never commit sensitive information (API keys, passwords, tokens) to the repository
- Use environment variables for configuration secrets
- Follow the principle of least privilege
- Keep dependencies up to date
- Run security checks before submitting PRs

## Data Breach Handling (GDPR Article 33 / 34)

If you become aware of a **personal data breach**, contact **privacy@portkit.ai**
immediately. The supervisory authority must be notified within **72 hours** of
awareness; affected data subjects must be notified without undue delay when the
breach is high-risk.

- **Procedure & timeline**: see the [Security Incident Runbook](./docs/runbooks/security-incident.md).
- **Code entry point**: `backend/src/services/breach_notification.py`
  (`BreachNotificationService.detect_breach()`).

## Security-Related Configuration

For deployment security configurations, see:
- [Security Configuration Guide](.github/security-config-guide.md)
- [Security Check Script](.github/security-check.sh)

## Credits

We appreciate the efforts of security researchers and contributors who help us keep portkit secure. With your permission, we will acknowledge your contribution in the security advisory.
