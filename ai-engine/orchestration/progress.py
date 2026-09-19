"""Framework-agnostic conversion progress tracking (issue #1201).

Used by the LangGraph pipeline to report progress through node entry/exit
hooks. Replaces ``crew.conversion_crew.PortkitConversionCrew.PipelineStage``
and ``PipelineProgress`` (which were nested classes coupled to the legacy multi-agent framework).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Stages in the conversion pipeline (mirrors ConversionPipeline graph nodes)."""

    INITIALIZE = 0
    ANALYZE_JAVA = 1
    PLAN_STRATEGY = 2
    TRANSLATE_BLOCK = 3
    CONVERT_ENTITIES = 4
    CONVERT_RECIPES = 5
    CONVERT_ASSETS = 6
    GENERATE_BEDROCK = 7
    VALIDATE_OUTPUT = 8
    FINALIZE = 9


_TOTAL_STAGES = len(PipelineStage)


@dataclass
class PipelineProgress:
    """Track progress through the conversion pipeline."""

    stage: str
    stage_number: int
    total_stages: int
    status: Literal["pending", "in_progress", "completed", "failed"]
    message: str
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


def log_pipeline_progress(
    stage: PipelineStage,
    status: Literal["pending", "in_progress", "completed", "failed"],
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, str, int, str], Awaitable[None]]] = None,
) -> PipelineProgress:
    """Log a pipeline-progress event and optionally fan it out to a callback."""

    progress = PipelineProgress(
        stage=stage.name,
        stage_number=stage.value,
        total_stages=_TOTAL_STAGES,
        status=status,
        message=message,
        details=details or {},
    )

    logger.info(
        f"[LangGraph Pipeline] Stage {stage.value}/{_TOTAL_STAGES} - {stage.name}: "
        f"{status} - {message}"
    )

    if progress_callback is not None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pct = int((stage.value / _TOTAL_STAGES) * 100)
                loop.create_task(progress_callback("LangGraphPipeline", status, pct, message))
        except Exception as e:  # pragma: no cover - best-effort progress reporting
            logger.warning(f"Failed to dispatch progress update: {e}")

    return progress


__all__ = ["PipelineStage", "PipelineProgress", "log_pipeline_progress"]
