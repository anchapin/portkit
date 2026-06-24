"""Shared BaseTool scaffolding for the Logic Translator tools subpackage."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, PrivateAttr

from agents.logic_translator.translator import LogicTranslatorAgent
from utils.logging_config import get_agent_logger

logger = get_agent_logger("logic_translator.tools")


class _BaseLogicTranslatorTool(BaseTool):
    """Common scaffolding for the Logic Translator typed tool wrappers.

    Holds an optional injected agent for tests; defers resolving the
    ``LogicTranslatorAgent`` singleton until the tool is actually invoked,
    so module import never triggers the agent's heavy ``__init__``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    _agent: Any = PrivateAttr(default=None)

    def __init__(self, agent: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._agent = agent

    def _get_agent(self) -> Any:
        """Return the injected agent or the module singleton (lazy)."""
        if self._agent is not None:
            return self._agent
        return LogicTranslatorAgent.get_instance()

    @staticmethod
    def _run_async(coro: Any) -> Any:
        """Drive an awaitable from a sync caller; refuse if a loop is running."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        coro.close()
        raise RuntimeError(
            "Sync invoke() called from inside a running event loop; use ainvoke() instead."
        )
