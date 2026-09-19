"""RAG context tools — get and set RAG-augmented translation context."""

from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from agents.logic_translator.tools._base import _BaseLogicTranslatorTool


class GetRagContextInput(BaseModel):
    """Args for :class:`GetRagContextTool`."""

    model_config = ConfigDict(extra="forbid")
    java_feature: str = Field(
        min_length=1, description="Description of the Java feature to convert."
    )
    feature_type: str = Field(
        min_length=1, description="Feature type (block, item, entity, recipe, event)."
    )


class SetRagContextInput(BaseModel):
    """Args for :class:`SetRagContextTool`."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(description="True to enable RAG context, False to disable.")


class GetRagContextTool(_BaseLogicTranslatorTool):
    """Get RAG context for context-augmented translation."""

    name: str = "get_rag_context_tool"
    description: str = (
        "Retrieve RAG context for translating a Java feature. "
        "Args: java_feature (str, required), feature_type (str, required)."
    )
    args_schema: ClassVar[type[BaseModel]] = GetRagContextInput

    async def _arun(  # type: ignore[override]
        self, java_feature: str, feature_type: str
    ) -> str:
        agent = self._get_agent()
        context_str = agent._get_rag_context(java_feature, feature_type)
        if not context_str:
            return json.dumps(
                {
                    "success": True,
                    "context": "",
                    "message": "RAG context not available",
                    "rag_enabled": agent._rag_context_enabled,
                }
            )
        return json.dumps(
            {
                "success": True,
                "context": context_str,
                "rag_enabled": agent._rag_context_enabled,
            }
        )

    def _run(  # type: ignore[override]
        self, java_feature: str, feature_type: str
    ) -> str:
        return self._run_async(self._arun(java_feature=java_feature, feature_type=feature_type))


class SetRagContextTool(_BaseLogicTranslatorTool):
    """Enable or disable RAG context for translation."""

    name: str = "set_rag_context_tool"
    description: str = "Enable or disable RAG context. Args: enabled (bool)."
    args_schema: ClassVar[type[BaseModel]] = SetRagContextInput

    async def _arun(self, enabled: bool) -> str:  # type: ignore[override]
        agent = self._get_agent()
        agent.enable_rag_context(enabled)
        return json.dumps(
            {
                "success": True,
                "rag_enabled": agent._rag_context_enabled,
                "message": (
                    f"RAG context {'enabled' if agent._rag_context_enabled else 'disabled'}"
                ),
            }
        )

    def _run(self, enabled: bool) -> str:  # type: ignore[override]
        return self._run_async(self._arun(enabled=enabled))


# Module-level singleton instances (private names, re-exported as public in __init__)
_get_rag_context_tool_instance = GetRagContextTool()
_set_rag_context_tool_instance = SetRagContextTool()
