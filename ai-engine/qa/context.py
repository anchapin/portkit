from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


@dataclass
class RefinementHistory:
    iteration: int
    initial_score: float
    final_score: float
    issues_detected: List[Dict[str, Any]] = field(default_factory=list)
    translator_prompt_modifications: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class QAContext(BaseModel):
    job_id: str
    job_dir: Path
    source_java_path: Path
    output_bedrock_path: Path
    metadata: Dict[str, Any] = {}
    validation_results: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.now)
    current_agent: Optional[str] = None
    refinement_iteration: int = 0
    refinement_history: List[RefinementHistory] = []
    refinement_enabled: bool = True
    max_iterations: int = 3
    refinement_completed: bool = False
    strict_api: bool = Field(
        default=False, description="Enable strict API validation and context injection"
    )
