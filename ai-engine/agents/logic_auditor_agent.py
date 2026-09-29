"""logic_auditor_agent - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.logic_auditor_agent`` (the old single-file module).

The actual implementation has been split into the ``logic_auditor/``
subpackage under agents/logic_auditor/.

Issue #1708 — Stub file for backward compatibility.

For new code, import from submodules directly:
- ``from agents.logic_auditor import LogicAuditorAgent``
- ``from agents.logic_auditor.semantic_diff import FormulaDriftChecker``
- ``from agents.logic_auditor.audit_reporter import AuditFinding``
- ``from agents.logic_auditor.complexity_analyzer import LLMLogicAuditor``

For backward compatibility, import LogicAuditorAgent from:
``from agents.logic_auditor_agent import LogicAuditorAgent``
"""

from __future__ import annotations

# Re-export everything from the new subpackage for backward compatibility
from agents.logic_auditor import (
    ADVERSARIAL_CHECKS,
    AuditFinding,
    AuditReport,
    ConditionalNegationChecker,
    EventHookMismatchChecker,
    FormulaDriftChecker,
    LLMLogicAuditor,
    LogicAuditorAgent,
    ProbabilityInversionChecker,
    ResourceIDMatchChecker,
    SemanticType,
    Severity,
    TEMPERATURE_ZERO,
    audit_conversion,
    classify_semantic_type,
    deep_audit_conversion,
    generate_audit_report,
)

__all__ = [
    "ADVERSARIAL_CHECKS",
    "AuditFinding",
    "AuditReport",
    "ConditionalNegationChecker",
    "EventHookMismatchChecker",
    "FormulaDriftChecker",
    "LLMLogicAuditor",
    "LogicAuditorAgent",
    "ProbabilityInversionChecker",
    "ResourceIDMatchChecker",
    "SemanticType",
    "Severity",
    "TEMPERATURE_ZERO",
    "audit_conversion",
    "classify_semantic_type",
    "deep_audit_conversion",
    "generate_audit_report",
]
