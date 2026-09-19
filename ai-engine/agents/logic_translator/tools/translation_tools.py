"""Core translation tools — method and class conversion."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.logic_translator.tools._base import _BaseLogicTranslatorTool


class TranslateJavaMethodInput(BaseModel):
    """Args for :class:`TranslateJavaMethodTool`."""

    model_config = ConfigDict(extra="forbid")
    method_name: str = Field(min_length=1, description="Java method name.")
    method_body: str = Field(default="", description="Java method body (optional).")
    feature_type: str = Field(
        default="unknown", description="Feature type for optional RAG context."
    )


class ConvertJavaClassInput(BaseModel):
    """Args for :class:`ConvertJavaClassTool`."""

    model_config = ConfigDict(extra="forbid")
    class_name: str = Field(min_length=1, description="Java class name.")
    methods: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of method dicts on the class."
    )
    feature_type: str = Field(
        default="unknown", description="Feature type for optional RAG context."
    )


class TranslateJavaMethodTool(_BaseLogicTranslatorTool):
    """Translate a Java method to JavaScript via the agent."""

    name: str = "translate_java_method_tool"
    description: str = (
        "Translate a Java method to JavaScript. Args: method_name (str, required), "
        "method_body (str, default ''), feature_type (str, default 'unknown')."
    )
    args_schema: ClassVar[type[BaseModel]] = TranslateJavaMethodInput

    async def _arun(  # type: ignore[override]
        self,
        method_name: str,
        method_body: str = "",
        feature_type: str = "unknown",
    ) -> str:
        agent = self._get_agent()
        payload = json.dumps(
            {
                "method_name": method_name,
                "method_body": method_body,
                "feature_type": feature_type,
            }
        )
        return agent.translate_java_method(payload)

    def _run(  # type: ignore[override]
        self,
        method_name: str,
        method_body: str = "",
        feature_type: str = "unknown",
    ) -> str:
        return self._run_async(
            self._arun(
                method_name=method_name,
                method_body=method_body,
                feature_type=feature_type,
            )
        )


class ConvertJavaClassTool(_BaseLogicTranslatorTool):
    """Convert a Java class declaration to JavaScript."""

    name: str = "convert_java_class_tool"
    description: str = (
        "Convert a Java class to JavaScript. Args: class_name (str, required), "
        "methods (list[dict], default []), feature_type (str, default 'unknown')."
    )
    args_schema: ClassVar[type[BaseModel]] = ConvertJavaClassInput

    async def _arun(  # type: ignore[override]
        self,
        class_name: str,
        methods: Optional[List[Dict[str, Any]]] = None,
        feature_type: str = "unknown",
    ) -> str:
        agent = self._get_agent()
        payload = json.dumps(
            {
                "class_name": class_name,
                "methods": methods or [],
                "feature_type": feature_type,
            }
        )
        return agent.convert_java_class(payload)

    def _run(  # type: ignore[override]
        self,
        class_name: str,
        methods: Optional[List[Dict[str, Any]]] = None,
        feature_type: str = "unknown",
    ) -> str:
        return self._run_async(
            self._arun(class_name=class_name, methods=methods, feature_type=feature_type)
        )


# Module-level singleton instances
_translate_java_method_tool_instance = TranslateJavaMethodTool()
_convert_java_class_tool_instance = ConvertJavaClassTool()
