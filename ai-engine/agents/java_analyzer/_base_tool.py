"""Shared BaseTool scaffolding for the Java Analyzer typed tool wrappers."""

from __future__ import annotations


from langchain_core.tools import BaseTool
from pydantic import ConfigDict


class _BaseJavaAnalyzerTool(BaseTool):
    """Common scaffolding for Java Analyzer typed tool wrappers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
