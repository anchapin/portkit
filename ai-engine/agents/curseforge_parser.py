"""curseforge_parser - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.curseforge_parser`` (the old single-file module).

The actual implementation has been consolidated into the
``online_research/parsers/`` subpackage and shares its JSON-loading /
structural-validation mechanics with the Modrinth parser via
``online_research.parsers.base.ModPortalParserBase``.

Issue #1730 — Stub file for backward compatibility.

For new code, import from the subpackage directly:
- ``from agents.online_research.parsers.curseforge import CurseForgeManifestParser``
- ``from agents.online_research.parsers.curseforge import CurseForgeParserAgent``

For backward compatibility, continue importing from:
``from agents.curseforge_parser import CurseForgeManifestParser, CurseForgeParserAgent``
"""

from __future__ import annotations

from agents.online_research.parsers.curseforge import (
    CurseForgeManifestParser,
    CurseForgeParserAgent,
)

__all__ = [
    "CurseForgeManifestParser",
    "CurseForgeParserAgent",
]
