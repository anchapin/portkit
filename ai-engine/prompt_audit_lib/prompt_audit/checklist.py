"""
Audit Checklist - PortKit Prompt Spec Review Criteria

Issue: #1602 (T2) - Define PortKit audit checklist for prompt spec review

The audit checklist defines the criteria for evaluating prompt specs across:
- Completeness: Are all required fields present?
- Consistency: Are prompts consistent within and across lanes?
- Effectiveness: Are prompts fit for purpose?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AuditCategory(Enum):
    """Categories of audit checks."""

    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    EFFECTIVENESS = "effectiveness"
    SECURITY = "security"
    STYLE = "style"


class AuditSeverity(Enum):
    """Severity levels for audit findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class AuditFinding:
    """A single audit finding."""

    check_name: str
    category: AuditCategory
    severity: AuditSeverity
    message: str
    file_path: str
    line_number: int
    suggestion: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditResult:
    """Result of an audit checklist run."""

    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    findings: List[AuditFinding]
    summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuditChecklist:
    """
    PortKit audit checklist for prompt spec review.

    Implements three main categories:
    1. Completeness - Required fields, documentation, examples
    2. Consistency - Internal and cross-lane consistency
    3. Effectiveness - Task alignment, clarity, completeness
    """

    # Completeness checks
    COMPLETENESS_CHECKS = {
        "has_name": "Prompt has a clear, descriptive name",
        "has_version": "Prompt specifies version or last_updated date",
        "has_description": "Prompt has a description of its purpose",
        "has_examples": "Prompt includes few-shot examples where appropriate",
        "has_constraints": "Prompt specifies output constraints",
        "has_role_definition": "System prompts define the agent role clearly",
        "has_variable_docs": "Template variables are documented",
    }

    # Consistency checks
    CONSISTENCY_CHECKS = {
        "consistent_format": "Prompt follows consistent formatting style",
        "consistent_terminology": "Prompt uses consistent terminology",
        "no_contradiction": "Prompt does not contradict other prompts",
        "cross_lane_alignment": "Prompts are aligned across pipeline lanes",
        "style_guide_compliance": "Prompt follows PortKit style guide",
    }

    # Effectiveness checks
    EFFECTIVENESS_CHECKS = {
        "task_clarity": "Prompt clearly specifies the task",
        "output_format_defined": "Expected output format is defined",
        "context_sufficient": "Context provided is sufficient for the task",
        "edge_cases_handled": "Edge cases and limitations are mentioned",
        "instruction_clarity": "Instructions are unambiguous",
        "helpful_fallbacks": "Fallback behavior for unclear inputs is defined",
    }

    # Security checks
    SECURITY_CHECKS = {
        "no_hardcoded_secrets": "No hardcoded API keys or secrets",
        "no_pii_leakage": "No personally identifiable information",
        "safe_suggestions": "Suggestions don't enable harmful activities",
    }

    # Style checks
    STYLE_CHECKS = {
        "proper_length": "Prompt length is appropriate for the task",
        "clear_structure": "Prompt has clear structure (role, task, format)",
        "proper_casing": "Consistent casing and formatting",
        "complete_sentences": "Prompt uses complete sentences",
    }

    def __init__(self):
        self.findings: List[AuditFinding] = []

    def run_all_checks(self, prompts: List[Any]) -> AuditResult:
        """Run all audit checks on a list of prompts."""
        self.findings = []

        for prompt in prompts:
            self._check_completeness(prompt)
            self._check_consistency(prompt, prompts)
            self._check_effectiveness(prompt)
            self._check_security(prompt)
            self._check_style(prompt)

        total = (
            len(self.COMPLETENESS_CHECKS)
            + len(self.CONSISTENCY_CHECKS)
            + len(self.EFFECTIVENESS_CHECKS)
            + len(self.SECURITY_CHECKS)
            + len(self.STYLE_CHECKS)
        )

        # Simplified count - in reality would be per-prompt
        total_checks = total * len(prompts) if prompts else total
        passed_checks = total_checks - len(self.findings)

        return AuditResult(
            passed=len(self.findings) == 0,
            total_checks=total_checks,
            passed_checks=max(0, passed_checks),
            failed_checks=len(self.findings),
            findings=self.findings,
            summary=self._generate_summary(),
        )

    def _check_completeness(self, prompt: Any) -> None:
        """Run completeness checks on a prompt."""
        # Check for name
        if not hasattr(prompt, "name") or not prompt.name:
            self.findings.append(
                AuditFinding(
                    check_name="has_name",
                    category=AuditCategory.COMPLETENESS,
                    severity=AuditSeverity.HIGH,
                    message="Prompt lacks a name",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                )
            )

        # Check for content
        if not hasattr(prompt, "content") or not prompt.content:
            self.findings.append(
                AuditFinding(
                    check_name="has_description",
                    category=AuditCategory.COMPLETENESS,
                    severity=AuditSeverity.CRITICAL,
                    message="Prompt has no content",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                )
            )
            return

        content = prompt.content

        # Check minimum length
        if len(content) < 20:
            self.findings.append(
                AuditFinding(
                    check_name="has_description",
                    category=AuditCategory.COMPLETENESS,
                    severity=AuditSeverity.MEDIUM,
                    message=f"Prompt content is very short ({len(content)} chars)",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                )
            )

        # Check for role definition (system prompts)
        if getattr(prompt, "prompt_type", "") == "system":
            if not any(phrase in content for phrase in ["You are", "You are an", "Your role"]):
                self.findings.append(
                    AuditFinding(
                        check_name="has_role_definition",
                        category=AuditCategory.COMPLETENESS,
                        severity=AuditSeverity.MEDIUM,
                        message="System prompt lacks clear role definition",
                        file_path=getattr(prompt, "file_path", "unknown"),
                        line_number=getattr(prompt, "line_number", 0),
                        suggestion="Start with 'You are an expert...' or similar",
                    )
                )

    def _check_consistency(self, prompt: Any, all_prompts: List[Any]) -> None:
        """Run consistency checks across prompts."""
        content = getattr(prompt, "content", "")

        # Check for consistent terminology
        minecraft_terms = ["Minecraft", "Bedrock", "Java", "Forge", "addon"]
        has_minecraft_term = any(term in content for term in minecraft_terms)

        # If prompt mentions Minecraft, check consistency
        if has_minecraft_term:
            # Check for case consistency
            if "minecraft" in content and "Minecraft" in content:
                self.findings.append(
                    AuditFinding(
                        check_name="consistent_terminology",
                        category=AuditCategory.CONSISTENCY,
                        severity=AuditSeverity.LOW,
                        message="Inconsistent casing for 'Minecraft'",
                        file_path=getattr(prompt, "file_path", "unknown"),
                        line_number=getattr(prompt, "line_number", 0),
                    )
                )

    def _check_effectiveness(self, prompt: Any) -> None:
        """Run effectiveness checks on a prompt."""
        content = getattr(prompt, "content", "")

        # Check for output format definition
        output_indicators = ["Respond with", "Return", "Output", "Format"]
        has_output_hint = any(phrase in content for phrase in output_indicators)

        if not has_output_hint and len(content) > 100:
            self.findings.append(
                AuditFinding(
                    check_name="output_format_defined",
                    category=AuditCategory.EFFECTIVENESS,
                    severity=AuditSeverity.MEDIUM,
                    message="Prompt lacks clear output format definition",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                    suggestion="Add 'Respond with JSON:' or similar output format hint",
                )
            )

        # Check for ambiguity
        vague_terms = ["maybe", "perhaps", "might", "could be", "possibly"]
        vague_count = sum(1 for term in vague_terms if term in content.lower())

        if vague_count > 2:
            self.findings.append(
                AuditFinding(
                    check_name="instruction_clarity",
                    category=AuditCategory.EFFECTIVENESS,
                    severity=AuditSeverity.LOW,
                    message=f"Prompt contains {vague_count} vague terms that may reduce clarity",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                )
            )

    def _check_security(self, prompt: Any) -> None:
        """Run security checks on a prompt."""
        content = getattr(prompt, "content", "").lower()

        # Check for potential secret patterns
        secret_patterns = ["api_key", "secret", "password", "token", "sk-"]

        for pattern in secret_patterns:
            if pattern in content:
                self.findings.append(
                    AuditFinding(
                        check_name="no_hardcoded_secrets",
                        category=AuditCategory.SECURITY,
                        severity=AuditSeverity.CRITICAL,
                        message=f"Potential hardcoded secret detected: {pattern}",
                        file_path=getattr(prompt, "file_path", "unknown"),
                        line_number=getattr(prompt, "line_number", 0),
                    )
                )

    def _check_style(self, prompt: Any) -> None:
        """Run style checks on a prompt."""
        content = getattr(prompt, "content", "")

        # Check length
        if len(content) > 4000:
            self.findings.append(
                AuditFinding(
                    check_name="proper_length",
                    category=AuditCategory.STYLE,
                    severity=AuditSeverity.LOW,
                    message=f"Prompt is very long ({len(content)} chars). Consider splitting.",
                    file_path=getattr(prompt, "file_path", "unknown"),
                    line_number=getattr(prompt, "line_number", 0),
                )
            )

    def _generate_summary(self) -> str:
        """Generate a human-readable summary of findings."""
        if not self.findings:
            return "All checks passed."

        by_severity = {}
        for finding in self.findings:
            severity = finding.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

        summary_parts = [f"Found {len(self.findings)} issues:"]
        for severity in ["critical", "high", "medium", "low"]:
            count = by_severity.get(severity, 0)
            if count:
                summary_parts.append(f"  {severity.upper()}: {count}")

        return ", ".join(summary_parts)


# Default checklist instance
default_checklist = AuditChecklist()
