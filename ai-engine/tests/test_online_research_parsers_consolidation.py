"""Consolidation tests for the online_research parsers (issue #1730).

These tests pin the contract that ``ModrinthPackParser`` and
``CurseForgeManifestParser`` share their JSON-loading and structural-
validation mechanics via ``ModPortalParserBase``, and that the
``*ParserAgent`` wrappers share ``ModPortalParserAgentBase`` — without
changing any observable behaviour.
"""

import json
from pathlib import Path

import pytest

from agents.online_research.parsers.base import (
    ModPortalParserAgentBase,
    ModPortalParserBase,
)
from agents.online_research.parsers.curseforge import (
    CurseForgeManifestParser,
    CurseForgeParserAgent,
)
from agents.online_research.parsers.modrinth import (
    ModrinthPackParser,
    ModrinthParserAgent,
)


PARSERS = [ModrinthPackParser, CurseForgeManifestParser]
AGENTS = [ModrinthParserAgent, CurseForgeParserAgent]


class TestParserConsolidationBase:
    """Both parsers must derive from the shared base."""

    @pytest.mark.parametrize("parser_cls", PARSERS, ids=["modrinth", "curseforge"])
    def test_inherits_mod_portal_parser_base(self, parser_cls):
        assert issubclass(parser_cls, ModPortalParserBase)

    @pytest.mark.parametrize("agent_cls", AGENTS, ids=["modrinth", "curseforge"])
    def test_agent_inherits_base(self, agent_cls):
        assert issubclass(agent_cls, ModPortalParserAgentBase)

    @pytest.mark.parametrize("parser_cls", PARSERS, ids=["modrinth", "curseforge"])
    def test_shared_supported_versions(self, parser_cls):
        # Both portals support manifest/format versions 1 and 2.
        assert list(parser_cls.SUPPORTED_VERSIONS) == [1, 2]

    @pytest.mark.parametrize(
        "agent_cls,filename",
        [(ModrinthParserAgent, "modrinth.index.json"), (CurseForgeParserAgent, "manifest.json")],
        ids=["modrinth", "curseforge"],
    )
    def test_agent_manifest_filename(self, agent_cls, filename):
        assert agent_cls.manifest_filename == filename


class TestSharedJsonLoading:
    """The base JSON helpers are shared and raise portal-specific messages."""

    def test_load_json_file_missing(self, tmp_path: Path):
        missing = tmp_path / "nope.json"
        with pytest.raises(FileNotFoundError, match="not found"):
            ModPortalParserBase.load_json_file(missing, "Index not found", "Invalid JSON")

    def test_load_json_file_invalid(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(ValueError, match="Invalid JSON in index: "):
            ModPortalParserBase.load_json_file(bad, "missing", "Invalid JSON in index")

    def test_load_json_string_invalid(self):
        with pytest.raises(ValueError, match="Invalid JSON in manifest content: "):
            ModPortalParserBase.load_json_string("{bad", "Invalid JSON in manifest content")

    def test_require_supported_version_rejects_unknown(self):
        with pytest.raises(ValueError, match="Unsupported format version: 99"):
            ModPortalParserBase.require_supported_version(
                99, "Unsupported format version: {}"
            )

    def test_require_supported_version_accepts_known(self):
        # Should not raise for supported versions.
        for v in ModPortalParserBase.SUPPORTED_VERSIONS:
            ModPortalParserBase.require_supported_version(
                v, "Unsupported format version: {}"
            )


class TestConsolidatedBehaviourIdentical:
    """The consolidated parsers must yield identical output for identical input."""

    def test_modrinth_parse_identical_to_contract(self):
        index = {
            "format_version": 1,
            "pack": {"name": "Datapack Example", "version": "1.2.3"},
            "files": [
                {
                    "path": "mods/foo.jar",
                    "hashes": {"sha1": "abc"},
                    "env": {"client": "required", "server": "optional"},
                    "downloads": ["https://example.com/foo.jar"],
                    "fileSize": 1234,
                }
            ],
            "dependencies": {"minecraft": "1.20.4", "fabric-loader": {"version": "0.15"}},
        }
        parser = ModrinthPackParser()
        result = parser.parse_from_string(json.dumps(index))

        assert result["file_count"] == 1
        assert result["metadata"]["pack_type"] == "datapack"
        assert result["metadata"]["version"] == "1.2.3"
        assert result["dependencies"]["minecraft"] == "1.20.4"
        assert result["dependencies"]["fabric-loader"] == "0.15"
        assert result["has_client_files"] is True
        assert result["files"][0]["download_url"] == "https://example.com/foo.jar"

    def test_curseforge_parse_identical_to_contract(self):
        manifest = {
            "manifestType": "minecraftModpack",
            "manifestVersion": 1,
            "name": "My Pack",
            "version": "2.0.0",
            "minecraft": {"version": "1.20.4", "modLoaders": [{"id": "fabric-0.15"}]},
            "files": [
                {
                    "projectID": 123,
                    "fileID": 456,
                    "name": "Mod",
                    "required": True,
                    "dependencies": [{"projectID": 789, "fileID": 100}],
                }
            ],
            "overrides": "overrides",
        }
        parser = CurseForgeManifestParser()
        result = parser.parse_from_string(json.dumps(manifest))

        assert result["mod_count"] == 1
        assert result["metadata"]["minecraft_version"] == "1.20.4"
        assert result["metadata"]["overrides_path"] == "overrides"
        assert result["mods"][0]["project_id"] == 123
        assert result["mods"][0]["dependencies"] == [{"project_id": 789, "file_id": 100}]
        assert result["is_server_modpack"] is False
