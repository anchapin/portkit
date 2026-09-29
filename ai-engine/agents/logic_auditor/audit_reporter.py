"""audit_reporter - Audit report data structures, scoring, and convenience entry points.

Seam: AuditFinding/AuditReport dataclasses, _generate_audit_report scoring
math (severity weights: HIGH=15, MEDIUM=5, LOW=1, capped at 50), and the
audit_conversion/deep_audit_conversion convenience functions.
Lifted from lines 42-82, 528-552, 672-683, 832-847 of the original
logic_auditor_agent.py.

Test coverage for audit scoring should be verified after split.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .pattern_detector import Severity


@dataclass
class AuditFinding:
    check_type: str
    severity: Severity
    description: str
    java_snippet: str
    bedrock_snippet: str
    expected_behavior: str = ""
    actual_behavior: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_type": self.check_type,
            "severity": self.severity.value,
            "description": self.description,
            "java_snippet": self.java_snippet,
            "bedrock_snippet": self.bedrock_snippet,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
        }


@dataclass
class AuditReport:
    findings: List[AuditFinding] = field(default_factory=list)
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0
    blocked: bool = False
    confidence_impact: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "high_severity_count": self.high_severity_count,
            "medium_severity_count": self.medium_severity_count,
            "low_severity_count": self.low_severity_count,
            "blocked": self.blocked,
            "confidence_impact": self.confidence_impact,
            "total_findings": len(self.findings),
        }


def generate_audit_report(
    findings: List[AuditFinding], semantic_types: List[Any] | None = None
) -> AuditReport:
    """Generate an audit report from findings.

    Severity weights: HIGH=15, MEDIUM=5, LOW=1, total confidence_impact capped at 50.
    The report is ``blocked`` when at least one HIGH severity finding is present.
    """
    report = AuditReport()

    for finding in findings:
        report.findings.append(finding)
        if finding.severity == Severity.HIGH:
            report.high_severity_count += 1
        elif finding.severity == Severity.MEDIUM:
            report.medium_severity_count += 1
        else:
            report.low_severity_count += 1

    report.blocked = report.high_severity_count > 0

    confidence_impact = (
        report.high_severity_count * 15.0
        + report.medium_severity_count * 5.0
        + report.low_severity_count * 1.0
    )
    report.confidence_impact = min(confidence_impact, 50.0)

    return report
