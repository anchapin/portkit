"""Validation tools — JavaScript syntax validation."""

from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from agents.logic_translator.tools._base import _BaseLogicTranslatorTool


class ValidateJavascriptSyntaxInput(BaseModel):
    """Args for :class:`ValidateJavascriptSyntaxTool`."""

    model_config = ConfigDict(extra="forbid")
    javascript_code: str = Field(default="", description="JavaScript source to validate.")


class ValidateJavascriptSyntaxTool(_BaseLogicTranslatorTool):
    """Validate JavaScript syntax."""

    name: str = "validate_javascript_syntax_tool"
    description: str = "Validate JavaScript source. Args: javascript_code (str, default '')."
    args_schema: ClassVar[type[BaseModel]] = ValidateJavascriptSyntaxInput

    async def _arun(  # type: ignore[override]
        self, javascript_code: str = ""
    ) -> str:
        agent = self._get_agent()
        return agent.validate_javascript_syntax(json.dumps({"javascript_code": javascript_code}))

    def _run(  # type: ignore[override]
        self, javascript_code: str = ""
    ) -> str:
        return self._run_async(self._arun(javascript_code=javascript_code))


# Module-level singleton instance
_validate_javascript_syntax_tool_instance = ValidateJavascriptSyntaxTool()
