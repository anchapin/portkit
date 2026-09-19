"""
LogicAuditor subpackage — adversarial logic auditor for QA pipeline.

Split from agents/logic_auditor_agent.py (32K) per issue #1708.
Public API remains unchanged - callers import from agents.logic_auditor_agent
(backward-compat stub) or from agents.logic_auditor for new code.

Module structure:
- behavior_validator.py: LogicAuditorAgent coordinator + audit_conversion
- pattern_detector.py: Severity/SemanticType enums + classify_semantic_type
- semantic_diff.py: 5 Java<->Bedrock diff checkers (formula/probability/event/conditional/resource)
- complexity_analyzer.py: LLM-powered deep audit (LLMLogicAuditor)
- audit_reporter.py: AuditFinding/AuditReport dataclasses + scoring + deep_audit_conversion
"""

from .audit_reporter import (
    AuditFinding,
    AuditReport,
    generate_audit_report,
)
from .behavior_validator import (
    LogicAuditorAgent,
    TEMPERATURE_ZERO,
    audit_conversion,
)
from .complexity_analyzer import LLMLogicAuditor, deep_audit_conversion
from .pattern_detector import (
    SemanticType,
    Severity,
    classify_semantic_type,
)
from .semantic_diff import (
    ADVERSARIAL_CHECKS,
    ConditionalNegationChecker,
    EventHookMismatchChecker,
    FormulaDriftChecker,
    ProbabilityInversionChecker,
    ResourceIDMatchChecker,
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
