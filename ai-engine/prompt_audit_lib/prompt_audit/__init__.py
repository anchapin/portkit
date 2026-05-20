"""
PortKit Prompt Spec Audit - Iterative Agent-Driven Prompt Review

This module provides comprehensive prompt spec auditing across PortKit's
LangGraph pipeline lanes. It implements:

1. Prompt Spec Collection: Find all prompts across agent nodes
2. Audit Checklist: Completeness, consistency, effectiveness checks
3. Round 1 Audit: Single-file consistency checks
4. Round 2+ Audit: Cross-lane consistency (iterative until convergence)
5. Defect Taxonomy: Categorize and track issues found
6. CI Regression Gate: Prevent prompt drift

Related Issues: #1579, #1601, #1602, #1603, #1606, #1607, #1608
"""

from .collector import PromptCollector, PromptSpec
from .checklist import AuditChecklist, AuditResult, AuditCategory
from .round1 import Round1Auditor
from .round2 import Round2Auditor, ConvergenceChecker
from .defects import DefectTaxonomy, Defect, DefectSeverity, DefectType
from .ci_gate import CIGate, RegressionCheck

__all__ = [
    "PromptCollector",
    "PromptSpec",
    "AuditChecklist",
    "AuditResult",
    "AuditCategory",
    "Round1Auditor",
    "Round2Auditor",
    "ConvergenceChecker",
    "DefectTaxonomy",
    "Defect",
    "DefectSeverity",
    "DefectType",
    "CIGate",
    "RegressionCheck",
]