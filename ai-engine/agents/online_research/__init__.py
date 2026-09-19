"""online_research — Online Research Analysis agent subpackage.

Coordinator subpackage extracted from the monolithic
``agents/online_research_agent.py`` (29K) for single-responsibility design
(issue #1730). The public API is unchanged: existing code can continue to
import from ``agents.online_research_agent`` (the backward-compat stub
re-exports everything below) or, equivalently, from ``agents.online_research``.

Submodules:
- :mod:`.models` — ``SourceType`` enum + ``ResearchSource`` /
``FeatureChecklistItem`` / ``ValidationReport`` dataclasses
- :mod:`.url_analyzer` — URL source-type classification + identifier
extraction (``URLAnalyzer``)
- :mod:`.clients` — CurseForge/Modrinth API clients + YouTube analyzer
- :mod:`.multimodal` — Multimodal (image/video/text) feature extraction
- :mod:`.checklist` — Feature checklist generation
- :mod:`.agent` — ``OnlineResearchAgent`` coordinator + addon validation
- :mod:`.parsers` — Consolidated Modrinth/CurseForge descriptor-file
parsers (``ModrinthPackParser`` / ``CurseForgeManifestParser``) sharing
``parsers.base.ModPortalParserBase``

This ``__init__`` is intentionally THIN (re-exports only); all logic lives in
the submodules to avoid the monolith-``__init__`` anti-pattern (issue #1819).
"""

from __future__ import annotations

from .agent import OnlineResearchAgent
from .checklist import FeatureChecklistGenerator
from .clients import CurseForgeClient, ModrinthClient, YouTubeAnalyzer
from .models import (
    FeatureChecklistItem,
    ResearchSource,
    SourceType,
    ValidationReport,
)
from .multimodal import MultimodalAnalyzer
from .parsers import (
    CurseForgeManifestParser,
    CurseForgeParserAgent,
    ModPortalParserAgentBase,
    ModPortalParserBase,
    ModrinthPackParser,
    ModrinthParserAgent,
)
from .url_analyzer import URLAnalyzer

__all__ = [
    "CurseForgeClient",
    "CurseForgeManifestParser",
    "CurseForgeParserAgent",
    "FeatureChecklistGenerator",
    "FeatureChecklistItem",
    "ModPortalParserAgentBase",
    "ModPortalParserBase",
    "ModrinthClient",
    "ModrinthPackParser",
    "ModrinthParserAgent",
    "MultimodalAnalyzer",
    "OnlineResearchAgent",
    "ResearchSource",
    "SourceType",
    "URLAnalyzer",
    "ValidationReport",
    "YouTubeAnalyzer",
]
