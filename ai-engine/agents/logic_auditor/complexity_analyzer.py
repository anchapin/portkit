"""complexity_analyzer - LLM-powered deep audit for subtle conversion bugs.

Seam: LLMLogicAuditor and deep_audit_conversion — the deeper, more expensive
LLM-driven pass that catches logic errors pattern-based checks might miss.
Lifted from lines 686-847 of the original logic_auditor_agent.py.
"""

from __future__ import annotations

import json
import structlog
from typing import Any, Dict, Optional


logger = structlog.get_logger(__name__)


class LLMLogicAuditor:
    """
    LLM-powered adversarial logic auditor for deeper analysis.

    Uses LLM to compare Java source intent with Bedrock output behavior
    for detecting subtle logic errors that pattern-based checks might miss.
    """

    _instance = None

    def __init__(self):
        self._llm = None
        self._initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        """Initialize LLM backend."""
        if self._initialized:
            return

        try:
            from utils.rate_limiter import get_llm_backend

            self._llm = get_llm_backend()
            logger.info("LLM initialized for logic auditing")
        except Exception as e:
            logger.warning(f"LLM not available: {e}")
            self._llm = None

        self._initialized = True

    def _call_llm(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Call LLM with prompt."""
        if not self._initialized:
            self.initialize()

        if self._llm is None:
            return None

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
            response = self._llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            return str(content) if content else None
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def deep_audit(
        self, java_source: str, bedrock_output: str, context: str = ""
    ) -> Dict[str, Any]:
        """
        Use LLM to perform deep adversarial audit.

        Args:
            java_source: Original Java source code
            bedrock_output: Generated Bedrock code
            context: Additional context about conversion

        Returns:
            Dict with LLM audit results
        """
        system_prompt = """You are an adversarial logic auditor specializing in detecting subtle bugs
in code conversions between Java Minecraft mods and Bedrock addons.

Your task is to find bugs that:
1. Pass syntax validation
2. Pass schema validation
3. But produce WRONG gameplay behavior

Common patterns to detect:
- Formula errors: `base * 1.5` → `base + 1.5` (multiplication becomes addition)
- Probability inversion: `random < 0.05` → `random > 0.05` (inverted spawn chance)
- Event hook mismatch: `BREAK_BLOCK` → `on_step_on` (wrong lifecycle hook)
- Conditional negation: `a && b` → `a || b` (AND becomes OR)
- Resource ID case: `minecraft:stone` → `minecraft:STONE` (case sensitivity)

Respond with JSON:
{
  "adversarial_findings": [
    {
      "check_type": "formula_drift|probability_inversion|event_hook_mismatch|conditional_negation|resource_id_match",
      "severity": "high|medium|low",
      "description": "What the bug is",
      "java_snippet": "The problematic Java line",
      "bedrock_snippet": "The converted Bedrock line",
      "expected_behavior": "What should happen",
      "actual_behavior": "What actually happens",
      "gameplay_impact": "Why this matters for players"
    }
  ],
  "overall_assessment": "Summary of conversion quality",
  "blocked": true/false,
  "confidence_impact": 0-50
}"""

        prompt = f"""Perform adversarial audit on this conversion:

=== Java Source ===
{java_source[:4000]}

=== Generated Bedrock Output ===
{bedrock_output[:4000]}

=== Context ===
{context or "Java to Bedrock mod conversion"}

Look for subtle bugs that pass validation but break gameplay.
Focus on: formulas, probability comparisons, event hooks, conditionals, resource IDs."""

        response = self._call_llm(prompt, system_prompt)

        if response is None:
            return {
                "success": False,
                "error": "LLM not available",
                "adversarial_findings": [],
            }

        try:
            analysis = json.loads(response)
            return {
                "success": True,
                "adversarial_findings": analysis.get("adversarial_findings", []),
                "overall_assessment": analysis.get("overall_assessment", ""),
                "blocked": analysis.get("blocked", False),
                "confidence_impact": analysis.get("confidence_impact", 0),
            }
        except json.JSONDecodeError:
            return {
                "success": True,
                "adversarial_findings": [],
                "raw_response": response[:500],
            }


def deep_audit_conversion(
    java_source: str, bedrock_output: str, context: str = ""
) -> Dict[str, Any]:
    """
    Convenience function to run LLM-powered deep audit.

    Args:
        java_source: Original Java source code
        bedrock_output: Generated Bedrock code
        context: Additional context

    Returns:
        Dict with deep audit results
    """
    auditor = LLMLogicAuditor.get_instance()
    return auditor.deep_audit(java_source, bedrock_output, context)
