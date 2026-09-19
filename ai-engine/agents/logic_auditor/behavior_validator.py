"""behavior_validator - LogicAuditorAgent coordinator and Bedrock reader.

Seam: LogicAuditorAgent (constructor, _classify_semantic_type, _run_checks_for_type,
_generate_audit_report, execute, _read_bedrock_code) and the
audit_conversion convenience function.
Lifted from lines 485-683 of the original logic_auditor_agent.py.
"""

from __future__ import annotations

import structlog
import time
from pathlib import Path
from typing import List

from qa.context import QAContext
from qa.validators import AgentOutput, validate_agent_output

from .audit_reporter import (
    AuditFinding,
    AuditReport,
    generate_audit_report,
)
from .pattern_detector import SemanticType, Severity, classify_semantic_type
from .semantic_diff import (
    ADVERSARIAL_CHECKS,
)

logger = structlog.get_logger(__name__)

TEMPERATURE_ZERO = 0.0


class LogicAuditorAgent:
    """
    Adversarial Logic Auditor Agent.

    Detects subtle functional discrepancies that pass syntax/schema checks
    but silently break gameplay behavior. Based on ASMR-Bench framework.
    """

    def __init__(self, temperature: float = TEMPERATURE_ZERO):
        self.temperature = temperature
        self.checks = ADVERSARIAL_CHECKS
        logger.info("LogicAuditorAgent initialized", checks=list(self.checks.keys()))

    def _classify_semantic_type(self, code: str) -> List[SemanticType]:
        """Classify which semantic types are present in the code."""
        return classify_semantic_type(code)

    def _run_checks_for_type(
        self, semantic_type: SemanticType, java_code: str, bedrock_code: str
    ) -> List[AuditFinding]:
        """Run checks for a specific semantic type."""
        checker = self.checks.get(semantic_type)
        if checker:
            return checker.check(java_code, bedrock_code)
        return []

    def _generate_audit_report(
        self, findings: List[AuditFinding], semantic_types: List[SemanticType]
    ) -> AuditReport:
        """Generate an audit report from findings."""
        return generate_audit_report(findings, semantic_types)

    def execute(self, context: QAContext) -> AgentOutput:
        """
        Execute the adversarial logic auditor on the given QA context.

        Args:
            context: QA context containing job information and paths

        Returns:
            AgentOutput with audit results
        """
        start_time = time.time()

        try:
            logger.info("LogicAuditorAgent executing", job_id=context.job_id)

            java_path = context.source_java_path
            bedrock_path = context.output_bedrock_path

            if not java_path.exists():
                return AgentOutput(
                    agent_name="logic_auditor",
                    success=False,
                    result={},
                    errors=[f"Java source not found: {java_path}"],
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            java_code = java_path.read_text(encoding="utf-8") if java_path.is_file() else ""
            bedrock_code = self._read_bedrock_code(bedrock_path)

            if not java_code and not bedrock_code:
                return AgentOutput(
                    agent_name="logic_auditor",
                    success=False,
                    result={},
                    errors=["No Java or Bedrock code found"],
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            semantic_types = self._classify_semantic_type(java_code)

            all_findings = []
            for sem_type in semantic_types:
                findings = self._run_checks_for_type(sem_type, java_code, bedrock_code)
                all_findings.extend(findings)

            if semantic_types == [SemanticType.UNKNOWN] or not semantic_types:
                for check_type, checker in self.checks.items():
                    findings = checker.check(java_code, bedrock_code)
                    all_findings.extend(findings)

            audit_report = self._generate_audit_report(all_findings, semantic_types)

            result = {
                "audit_report": audit_report.to_dict(),
                "semantic_types_detected": [st.value for st in semantic_types],
                "checks_run": len(semantic_types)
                if semantic_types != [SemanticType.UNKNOWN]
                else len(self.checks),
                "blocked": audit_report.blocked,
                "confidence_impact": audit_report.confidence_impact,
            }

            context.validation_results["logic_auditor"] = {
                "success": not audit_report.blocked,
                "report": audit_report.to_dict(),
                "findings_count": len(all_findings),
                "high_severity": audit_report.high_severity_count,
            }

            execution_time = int((time.time() - start_time) * 1000)

            output_data = {
                "agent_name": "logic_auditor",
                "success": not audit_report.blocked,
                "result": result,
                "errors": [f.description for f in all_findings if f.severity == Severity.HIGH],
                "execution_time_ms": execution_time,
            }

            validated = validate_agent_output(output_data)

            logger.info(
                "LogicAuditorAgent completed",
                job_id=context.job_id,
                findings=len(all_findings),
                blocked=audit_report.blocked,
            )

            return validated

        except Exception as e:
            logger.error("LogicAuditorAgent failed", job_id=context.job_id, error=str(e))
            return AgentOutput(
                agent_name="logic_auditor",
                success=False,
                result={},
                errors=[str(e)],
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def _read_bedrock_code(self, bedrock_path: Path) -> str:
        """Read all Bedrock code from path (file or directory)."""
        if bedrock_path.is_file():
            return bedrock_path.read_text(encoding="utf-8")
        elif bedrock_path.is_dir():
            code_parts = []
            for f in bedrock_path.rglob("*.ts"):
                code_parts.append(f.read_text(encoding="utf-8"))
            for f in bedrock_path.rglob("*.js"):
                code_parts.append(f.read_text(encoding="utf-8"))
            for f in bedrock_path.rglob("*.json"):
                if "manifest" not in f.name.lower():
                    code_parts.append(f.read_text(encoding="utf-8"))
            return "\n".join(code_parts)
        return ""


def audit_conversion(context: QAContext) -> AgentOutput:
    """
    Convenience function to run adversarial logic audit.

    Args:
        context: QA context

    Returns:
        AgentOutput with audit results
    """
    agent = LogicAuditorAgent()
    return agent.execute(context)
