"""Shared helpers for mod-portal manifest/index parsers.

Both :class:`agents.online_research.parsers.modrinth.ModrinthPackParser` and
:class:`agents.online_research.parsers.curseforge.CurseForgeManifestParser`
parse a JSON descriptor file (``modrinth.index.json`` / ``manifest.json``)
following the same mechanical recipe:

1. Load the JSON (from a path or a string), raising ``FileNotFoundError`` /
   ``ValueError`` with a portal-specific message.
2. Validate required top-level fields and the supported format version.
3. Extract metadata + entries (files / mods).
4. Return an aggregated ``get_parsed_data()`` mapping.

This module factors out the *mechanics* (JSON loading, field/version checks and
the parser-agent wrapper) so the portal modules only carry their
portal-specific *logic*. The helpers accept the portal-specific message
strings verbatim, so error output — and therefore test assertions — are
identical to the pre-refactor behaviour.

Issue #1730 — consolidate modrinth/curseforge parser overlap.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence

logger = logging.getLogger(__name__)


class ModPortalParserBase:
    """Base class encapsulating the common parser mechanics.

    Subclasses keep their own state attributes (e.g. ``pack_info`` /
    ``manifest``) and portal-specific extraction logic, but delegate JSON
    loading and structural validation to the helpers defined here.
    """

    #: Format/manifest versions understood by both portals.
    SUPPORTED_VERSIONS: Sequence[int] = (1, 2)

    # ------------------------------------------------------------------
    # JSON loading helpers
    # ------------------------------------------------------------------
    @staticmethod
    def load_json_file(path: Path, not_found_msg: str, invalid_msg: str) -> Dict[str, Any]:
        """Load JSON from ``path``.

        Raises:
            FileNotFoundError: ``not_found_msg`` when ``path`` does not exist.
            ValueError: ``f"{invalid_msg}: {e}"`` on a JSON decode error.
        """
        if not path.exists():
            raise FileNotFoundError(not_found_msg)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{invalid_msg}: {e}")

    @staticmethod
    def load_json_string(content: str, invalid_msg: str) -> Dict[str, Any]:
        """Load JSON from ``content``.

        Raises:
            ValueError: ``f"{invalid_msg}: {e}"`` on a JSON decode error.
        """
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"{invalid_msg}: {e}")

    # ------------------------------------------------------------------
    # Structural validation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def require_non_empty(data: Any, empty_msg: str) -> None:
        """Raise ``ValueError(empty_msg)`` when ``data`` is falsy."""
        if not data:
            raise ValueError(empty_msg)

    @staticmethod
    def require_fields(data: Dict[str, Any], fields: Sequence[str]) -> None:
        """Raise ``ValueError("Missing required field: <name>")`` for any absent field."""
        for field in fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

    @classmethod
    def require_supported_version(cls, version: Any, unsupported_msg_template: str) -> None:
        """Raise ``ValueError`` if ``version`` is not in :attr:`SUPPORTED_VERSIONS`.

        ``unsupported_msg_template`` must contain a single ``%s``/``{}`` style
        substitution — the version is interpolated into it.
        """
        if version not in cls.SUPPORTED_VERSIONS:
            raise ValueError(unsupported_msg_template.format(version))


class ModPortalParserAgentBase:
    """Common scaffolding for the LangChain-style parser agent wrappers.

    Both portals ship a ``*ParserAgent`` class that owns a parser instance and
    exposes ``get_tools()`` plus ``parse_modpack(path)``. The portal-specific
    bits are:

    - ``parser``: an instance of the portal's ``*Parser`` class.
    - ``manifest_filename``: the descriptor filename (``modrinth.index.json``
      or ``manifest.json``).
    - ``parse_method``: the name of the parser method to invoke
      (``parse_index`` / ``parse_manifest``).
    """

    #: Subclasses MUST set these two attributes.
    parser: ModPortalParserBase
    manifest_filename: str
    parse_method: str

    def __init__(self) -> None:
        # ``tools`` is retained for parity with the original API (currently
        # always empty); subclasses populate ``self.parser`` themselves.
        self.tools: List[Any] = []

    def get_tools(self) -> List[Any]:
        """Return the (currently empty) LangChain tool list for this agent."""
        return self.tools

    def parse_modpack(self, modpack_path: Path) -> Dict[str, Any]:
        """Locate ``manifest_filename`` under ``modpack_path`` and parse it.

        Raises:
            FileNotFoundError: when the descriptor file is missing.
        """
        descriptor_path = modpack_path / self.manifest_filename
        if not descriptor_path.exists():
            raise FileNotFoundError(f"{self.manifest_filename} not found in {modpack_path}")
        return getattr(self.parser, self.parse_method)(descriptor_path)
