"""parsers — consolidated Modrinth/CurseForge descriptor-file parsers.

Shared JSON-loading and structural-validation mechanics live in
:mod:`.base` (:class:`ModPortalParserBase` / :class:`ModPortalParserAgentBase`);
portal-specific logic lives in :mod:`.modrinth` and :mod:`.curseforge`.
Issue #1730 — eliminate modrinth/curseforge parser overlap.
"""

from __future__ import annotations

from .base import ModPortalParserAgentBase, ModPortalParserBase
from .curseforge import CurseForgeManifestParser, CurseForgeParserAgent
from .modrinth import ModrinthPackParser, ModrinthParserAgent

__all__ = [
    "CurseForgeManifestParser",
    "CurseForgeParserAgent",
    "ModPortalParserAgentBase",
    "ModPortalParserBase",
    "ModrinthPackParser",
    "ModrinthParserAgent",
]
