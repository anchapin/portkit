"""
Packaging validation report generation.
"""

from typing import Any, Dict, List

from .validator import ValidationResult, ValidationSeverity


def generate_validation_report(result: ValidationResult) -> str:
    """Generate human-readable validation report."""
    lines = []
    lines.append("=" * 80)
    lines.append("Bedrock .mcaddon Validation Report")
    lines.append("=" * 80)
    lines.append("")

    status = "PASS" if result.is_valid else "FAIL"
    lines.append(f"Overall Status: {status} (Score: {result.overall_score}/100)")
    lines.append("")

    for severity in [
        ValidationSeverity.CRITICAL,
        ValidationSeverity.ERROR,
        ValidationSeverity.WARNING,
        ValidationSeverity.INFO,
    ]:
        issues = result.get_issues_by_severity(severity)
        if issues:
            lines.append(f"{severity.value.upper()} ({len(issues)}):")
            for issue in issues:
                location = f" [{issue.file_path}]" if issue.file_path else ""
                lines.append(f"  - {issue.message}{location}")
                if issue.suggestion:
                    lines.append(f"    Suggestion: {issue.suggestion}")
            lines.append("")

    lines.append("Package Statistics:")
    lines.append(f"  Total Files: {result.stats.get('total_files', 0)}")
    lines.append(f"  Behavior Packs: {len(result.stats.get('behavior_packs', []))}")
    lines.append(f"  Resource Packs: {len(result.stats.get('resource_packs', []))}")
    lines.append("")

    lines.append("Compatibility:")
    comp = result.compatibility
    lines.append(f"  Minimum Version: {'.'.join(map(str, comp.get('min_version', [1, 16, 0])))}")
    lines.append(f"  Experimental Features: {len(comp.get('experimental_features', []))}")
    lines.append("")

    return "\n".join(lines)
