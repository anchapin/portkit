"""online_research_agent - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.online_research_agent`` (the old single-file module).

The actual implementation has been split into the ``online_research/``
subpackage at ``agents/online_research/``.

Issue #1730 — Stub file for backward compatibility.

For new code, import from submodules directly:
- ``from agents.online_research.agent import OnlineResearchAgent``
- ``from agents.online_research.models import SourceType, ResearchSource``
- ``from agents.online_research.url_analyzer import URLAnalyzer``
- ``from agents.online_research.clients import CurseForgeClient, ModrinthClient``
- ``from agents.online_research.multimodal import MultimodalAnalyzer``
- ``from agents.online_research.checklist import FeatureChecklistGenerator``

For backward compatibility, continue importing from:
``from agents.online_research_agent import OnlineResearchAgent, SourceType, ...``
"""

from __future__ import annotations

# Re-export the full public API from the subpackage for backward compatibility.
from agents.online_research import (
    CurseForgeClient,
    FeatureChecklistGenerator,
    FeatureChecklistItem,
    ModrinthClient,
    MultimodalAnalyzer,
    OnlineResearchAgent,
    ResearchSource,
    SourceType,
    URLAnalyzer,
    ValidationReport,
    YouTubeAnalyzer,
)

__all__ = [
    "CurseForgeClient",
    "FeatureChecklistGenerator",
    "FeatureChecklistItem",
    "ModrinthClient",
    "MultimodalAnalyzer",
    "OnlineResearchAgent",
    "ResearchSource",
    "SourceType",
    "URLAnalyzer",
    "ValidationReport",
    "YouTubeAnalyzer",
]
