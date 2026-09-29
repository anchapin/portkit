"""modrinth_parser - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.modrinth_parser`` (the old single-file module).

The actual implementation has been consolidated into the
``online_research/parsers/`` subpackage and shares its JSON-loading /
structural-validation mechanics with the CurseForge parser via
``online_research.parsers.base.ModPortalParserBase``.

Issue #1730 — Stub file for backward compatibility.

For new code, import from the subpackage directly:
- ``from agents.online_research.parsers.modrinth import ModrinthPackParser``
- ``from agents.online_research.parsers.modrinth import ModrinthParserAgent``

For backward compatibility, continue importing from:
``from agents.modrinth_parser import ModrinthPackParser, ModrinthParserAgent``
"""

from __future__ import annotations

from agents.online_research.parsers.modrinth import (
    ModrinthPackParser,
    ModrinthParserAgent,
)

__all__ = [
    "ModrinthPackParser",
    "ModrinthParserAgent",
]
