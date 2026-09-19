"""
QA Validator tool wrappers — Input models and typed BaseTool subclasses.

Extracted from __init__.py to resolve the monolith pattern (issue #1740).
"""

from typing import ClassVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field


class _BaseQATool(BaseTool):
    """Common scaffolding for QA Validator typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class _ValidateConversionQualityInput(BaseModel):
    """Args for :class:`_ValidateConversionQualityTool`."""

    model_config = ConfigDict(extra="forbid")
    quality_data: str = Field(
        min_length=1,
        description=(
            "JSON string with mcaddon_path or conversion data describing the "
            "Java→Bedrock conversion to validate."
        ),
    )


class _ValidateMcaddonInput(BaseModel):
    """Args for :class:`_ValidateMcaddonTool`."""

    model_config = ConfigDict(extra="forbid")
    mcaddon_path: str = Field(
        min_length=1,
        description="Filesystem path to the .mcaddon archive to validate.",
    )


class _RunFunctionalTestsInput(BaseModel):
    """Args for :class:`_RunFunctionalTestsTool`."""

    model_config = ConfigDict(extra="forbid")
    test_data: str = Field(
        min_length=1,
        description="JSON string describing the functional test scenarios to run.",
    )


class _AnalyzeBedrockCompatibilityInput(BaseModel):
    """Args for :class:`_AnalyzeBedrockCompatibilityTool`."""

    model_config = ConfigDict(extra="forbid")
    compatibility_data: str = Field(
        min_length=1,
        description="JSON string describing the conversion artifacts to analyze.",
    )


class _AssessPerformanceMetricsInput(BaseModel):
    """Args for :class:`_AssessPerformanceMetricsTool`."""

    model_config = ConfigDict(extra="forbid")
    performance_data: str = Field(
        min_length=1,
        description="JSON string describing the conversion artifacts to measure.",
    )


class _GenerateQaReportInput(BaseModel):
    """Args for :class:`_GenerateQaReportTool`."""

    model_config = ConfigDict(extra="forbid")
    report_data: str = Field(
        min_length=1,
        description="JSON string with validation results to assemble into a QA report.",
    )


class _ValidateConversionQualityTool(_BaseQATool):
    name: str = "validate_conversion_quality_tool"
    description: str = (
        "Validate overall conversion quality. "
        "Args: quality_data (str, required) — JSON with mcaddon_path or "
        "conversion data."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateConversionQualityInput

    def _run(self, quality_data: str) -> str:
        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        return agent.validate_conversion_quality(quality_data)


class _ValidateMcaddonTool(_BaseQATool):
    name: str = "validate_mcaddon_tool"
    description: str = (
        "Validate a .mcaddon file and generate a comprehensive QA report. "
        "Returns overall_score (0-100), status (pass/partial/fail), per-category "
        "validations, issues, and recommendations. "
        "Args: mcaddon_path (str, required) — filesystem path to .mcaddon."
    )
    args_schema: ClassVar[type[BaseModel]] = _ValidateMcaddonInput

    def _run(self, mcaddon_path: str) -> str:
        import json

        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        result = agent.validate_mcaddon(mcaddon_path)
        result["success"] = result["status"] != "error"
        return json.dumps(result, indent=2)


class _RunFunctionalTestsTool(_BaseQATool):
    name: str = "run_functional_tests_tool"
    description: str = (
        "Run functional tests on the converted addon. "
        "Args: test_data (str, required) — JSON describing the test scenarios."
    )
    args_schema: ClassVar[type[BaseModel]] = _RunFunctionalTestsInput

    def _run(self, test_data: str) -> str:
        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        return agent.run_functional_tests(test_data)


class _AnalyzeBedrockCompatibilityTool(_BaseQATool):
    name: str = "analyze_bedrock_compatibility_tool"
    description: str = (
        "Analyze Bedrock compatibility of the conversion. "
        "Args: compatibility_data (str, required) — JSON of conversion artifacts."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeBedrockCompatibilityInput

    def _run(self, compatibility_data: str) -> str:
        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        return agent.analyze_bedrock_compatibility(compatibility_data)


class _AssessPerformanceMetricsTool(_BaseQATool):
    name: str = "assess_performance_metrics_tool"
    description: str = (
        "Assess performance metrics of the converted addon. "
        "Args: performance_data (str, required) — JSON of conversion artifacts."
    )
    args_schema: ClassVar[type[BaseModel]] = _AssessPerformanceMetricsInput

    def _run(self, performance_data: str) -> str:
        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        return agent.assess_performance_metrics(performance_data)


class _GenerateQaReportTool(_BaseQATool):
    name: str = "generate_qa_report_tool"
    description: str = (
        "Generate a comprehensive QA report. "
        "Args: report_data (str, required) — JSON of validation results."
    )
    args_schema: ClassVar[type[BaseModel]] = _GenerateQaReportInput

    def _run(self, report_data: str) -> str:
        from agents.qa import QAValidatorAgent

        agent = QAValidatorAgent.get_instance()
        return agent.generate_qa_report(report_data)


def _attach_tool_instances(agent_cls: type) -> None:
    """Attach module-level tool instances as class attributes on QAValidatorAgent."""
    agent_cls.validate_conversion_quality_tool = _ValidateConversionQualityTool()
    agent_cls.validate_mcaddon_tool = _ValidateMcaddonTool()
    agent_cls.run_functional_tests_tool = _RunFunctionalTestsTool()
    agent_cls.analyze_bedrock_compatibility_tool = _AnalyzeBedrockCompatibilityTool()
    agent_cls.assess_performance_metrics_tool = _AssessPerformanceMetricsTool()
    agent_cls.generate_qa_report_tool = _GenerateQaReportTool()
