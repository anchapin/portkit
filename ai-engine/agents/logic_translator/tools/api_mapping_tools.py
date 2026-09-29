"""API mapping tools — Java API mapping and event handler generation."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.logic_translator.tools._base import _BaseLogicTranslatorTool


class MapJavaApisInput(BaseModel):
    """Args for :class:`MapJavaApisTool`."""

    model_config = ConfigDict(extra="forbid")
    apis: List[str] = Field(default_factory=list, description="List of Java API call signatures.")


class GenerateEventHandlersInput(BaseModel):
    """Args for :class:`GenerateEventHandlersTool`.

    Mirrors the live ``LogicTranslatorAgent.generate_event_handlers`` schema.
    """

    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(default="unknown", description="Event type identifier.")
    handlers: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of handler descriptors."
    )


class MapJavaApisTool(_BaseLogicTranslatorTool):
    """Map Java APIs to JavaScript equivalents."""

    name: str = "map_java_apis_tool"
    description: str = "Map Java APIs to JavaScript. Args: apis (list[str], default [])."
    args_schema: ClassVar[type[BaseModel]] = MapJavaApisInput

    async def _arun(  # type: ignore[override]
        self, apis: Optional[List[str]] = None
    ) -> str:
        agent = self._get_agent()
        payload = json.dumps({"apis": apis or []})
        return agent.map_java_apis(payload)

    def _run(  # type: ignore[override]
        self, apis: Optional[List[str]] = None
    ) -> str:
        return self._run_async(self._arun(apis=apis))


class GenerateEventHandlersTool(_BaseLogicTranslatorTool):
    """Generate JavaScript event handlers from Java event metadata."""

    name: str = "generate_event_handlers_tool"
    description: str = (
        "Generate JavaScript event handlers. Args: event_type (str, default 'unknown'), "
        "handlers (list[dict], default [])."
    )
    args_schema: ClassVar[type[BaseModel]] = GenerateEventHandlersInput

    async def _arun(  # type: ignore[override]
        self,
        event_type: str = "unknown",
        handlers: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        agent = self._get_agent()
        payload = json.dumps({"event_type": event_type, "handlers": handlers or []})
        return agent.generate_event_handlers(payload)

    def _run(  # type: ignore[override]
        self,
        event_type: str = "unknown",
        handlers: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return self._run_async(self._arun(event_type=event_type, handlers=handlers))


# Module-level singleton instances
_map_java_apis_tool_instance = MapJavaApisTool()
_generate_event_handlers_tool_instance = GenerateEventHandlersTool()
