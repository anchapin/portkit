"""
Unit tests for Issue #1773 - Bedrock client-side entity definitions.

Verifies that the entity converter emits a ``minecraft:client_entity``
document that wires geometry/texture/material/render controllers so the
converted mob renders in Bedrock, and that ``write_entities_to_disk``
materializes it under ``resource_pack/entity/``.
"""

import json
import sys
from pathlib import Path

import pytest

ai_engine_root = Path(__file__).parent.parent
sys.path.insert(0, str(ai_engine_root))

from agents.entity.client_entity_generator import generate_client_entity
from agents.entity_converter import EntityConverter


def _make_bp_entity(identifier: str) -> dict:
    """Build a minimal converted BP entity for parity checks."""
    return {
        "format_version": "1.19.0",
        "minecraft:entity": {
            "description": {
                "identifier": identifier,
                "is_spawnable": True,
                "is_summonable": True,
                "is_experimental": False,
            },
            "components": {},
            "component_groups": {},
            "events": {},
        },
    }


class TestGenerateClientEntity:
    """Direct tests for the ``generate_client_entity`` generator function."""

    def test_returns_client_entity_document_structure(self):
        bp = _make_bp_entity("testmod:forest_mob")
        client = generate_client_entity(bp, {"id": "forest_mob", "namespace": "testmod"})

        assert client["format_version"] == "1.10.0"
        assert "minecraft:client_entity" in client
        description = client["minecraft:client_entity"]["description"]
        assert description["identifier"] == "testmod:forest_mob"

    def test_identifier_parity_between_bp_and_rp_halves(self):
        bp = _make_bp_entity("testmod:parity_mob")
        client = generate_client_entity(bp, {"id": "parity_mob", "namespace": "testmod"})

        bp_id = bp["minecraft:entity"]["description"]["identifier"]
        rp_id = client["minecraft:client_entity"]["description"]["identifier"]
        assert bp_id == rp_id == "testmod:parity_mob"

    def test_geometry_texture_materials_present(self):
        bp = _make_bp_entity("testmod:render_mob")
        description = generate_client_entity(
            bp, {"id": "render_mob", "namespace": "testmod"}
        )["minecraft:client_entity"]["description"]

        assert description["materials"] == {"default": "entity_alphatest"}
        assert description["geometry"] == {"default": "geometry.render_mob"}
        assert "default" in description["textures"]
        # Default texture path resolves from the canonical layout.
        assert description["textures"]["default"] == "textures/entity/render_mob/render_mob"

    def test_render_controllers_default_wired(self):
        bp = _make_bp_entity("testmod:rc_mob")
        description = generate_client_entity(bp, {"id": "rc_mob", "namespace": "testmod"})[
            "minecraft:client_entity"
        ]["description"]

        assert description["render_controllers"] == ["controller.render.default"]

    def test_texture_path_resolved_from_java_texture_hint(self):
        bp = _make_bp_entity("testmod:textured_mob")
        java = {
            "id": "textured_mob",
            "namespace": "testmod",
            "texture": "textures/entity/custom/skin",
        }
        description = generate_client_entity(bp, java)["minecraft:client_entity"]["description"]
        assert description["textures"]["default"] == "textures/entity/custom/skin"

    def test_animation_refs_mirror_animation_names(self):
        bp = _make_bp_entity("testmod:anim_mob")
        java = {
            "id": "anim_mob",
            "namespace": "testmod",
            "animations": [
                {"name": "idle", "loop": True},
                {"name": "walk", "loop": True},
            ],
        }
        description = generate_client_entity(bp, java)["minecraft:client_entity"]["description"]

        assert description["animations"] == {
            "idle": "animation.anim_mob.idle",
            "walk": "animation.anim_mob.walk",
        }

    def test_scripts_animate_mirrors_controller_keys(self):
        bp = _make_bp_entity("testmod:ctrl_mob")
        java = {
            "id": "ctrl_mob",
            "namespace": "testmod",
            "animation_controllers": [
                {"controllerId": "move_controller", "initialState": "idle", "states": {}},
                {"controllerId": "attack_controller", "initialState": "idle", "states": {}},
            ],
        }
        description = generate_client_entity(bp, java)["minecraft:client_entity"]["description"]

        # scripts.animate mirrors the animation_controller.<id> keys that
        # _generate_animation_controllers emits on the BP half.
        assert description["scripts"]["animate"] == [
            "animation_controller.move_controller",
            "animation_controller.attack_controller",
        ]

    def test_spawn_egg_texture_when_bp_has_spawn_egg(self):
        bp = _make_bp_entity("testmod:egg_mob")
        bp["minecraft:entity"]["components"]["minecraft:spawn_egg"] = {
            "base_color": "#5A1D1D",
            "overlay_color": "#1D1D1D",
        }
        description = generate_client_entity(bp, {"id": "egg_mob", "namespace": "testmod"})[
            "minecraft:client_entity"
        ]["description"]

        assert description["spawn_egg"] == {"texture": "egg_mob_spawn_egg"}

    def test_no_spawn_egg_when_bp_lacks_spawn_egg(self):
        bp = _make_bp_entity("testmod:no_egg_mob")
        description = generate_client_entity(bp, {"id": "no_egg_mob", "namespace": "testmod"})[
            "minecraft:client_entity"
        ]["description"]

        assert "spawn_egg" not in description

    def test_java_entity_none_emits_structural_defaults(self):
        bp = _make_bp_entity("testmod:stub_mob")
        # Should not raise when java_entity is None (behavior-only stub).
        client = generate_client_entity(bp, None)

        description = client["minecraft:client_entity"]["description"]
        assert description["identifier"] == "testmod:stub_mob"
        assert "materials" in description
        assert "geometry" in description

    def test_invalid_bp_entity_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_client_entity({"minecraft:entity": {}}, {})


class TestEntityConverterClientEntityIntegration:
    """Integration tests covering EntityConverter end-to-end wiring."""

    def setup_method(self):
        self.converter = EntityConverter()

    def test_convert_entities_emits_client_entity_key(self):
        java_entities = [
            {
                "id": "forest_mob",
                "namespace": "testmod",
                "category": "passive",
            }
        ]

        result = self.converter.convert_entities(java_entities)

        client_key = "testmod:forest_mob_client_entity"
        assert client_key in result
        client = result[client_key]
        assert client["format_version"] == "1.10.0"
        assert (
            client["minecraft:client_entity"]["description"]["identifier"]
            == "testmod:forest_mob"
        )

    def test_bp_and_rp_identifiers_match_for_same_entity(self):
        java_entities = [
            {"id": "parity_mob", "namespace": "testmod", "category": "hostile"}
        ]

        result = self.converter.convert_entities(java_entities)

        bp_id = result["testmod:parity_mob"]["minecraft:entity"]["description"]["identifier"]
        rp_id = result["testmod:parity_mob_client_entity"]["minecraft:client_entity"]["description"][
            "identifier"
        ]
        assert bp_id == rp_id == "testmod:parity_mob"

    def test_client_entity_mirrors_animation_controller_keys(self):
        java_entities = [
            {
                "id": "animated_mob",
                "namespace": "testmod",
                "category": "passive",
                "animation_controllers": [
                    {
                        "controllerId": "move_controller",
                        "initialState": "idle",
                        "states": {"idle": {}},
                    },
                ],
            }
        ]

        result = self.converter.convert_entities(java_entities)

        client = result["testmod:animated_mob_client_entity"]
        controllers = result["testmod:animated_mob_animation_controllers"]

        # The scripts.animate entries must match the controller identifier keys.
        expected_keys = list(controllers.keys())
        assert expected_keys == ["animation_controller.move_controller"]
        assert client["minecraft:client_entity"]["description"]["scripts"]["animate"] == expected_keys


class TestWriteEntitiesToDiskClientEntity:
    """Verify write_entities_to_disk materializes the RP client entity file."""

    def setup_method(self):
        self.converter = EntityConverter()

    def test_writes_client_entity_under_resource_pack_entity_dir(self, tmp_path):
        java_entities = [
            {"id": "disk_mob", "namespace": "testmod", "category": "hostile"}
        ]
        result = self.converter.convert_entities(java_entities)

        bp_path = tmp_path / "behavior_pack"
        rp_path = tmp_path / "resource_pack"

        written = self.converter.write_entities_to_disk(result, bp_path, rp_path)

        assert "entities_rp" in written
        assert len(written["entities_rp"]) == 1
        client_file = written["entities_rp"][0]
        assert client_file.exists()
        # Issue spec: file lands under resource_pack/entity/<id>.entity.json
        assert client_file.parent == rp_path / "entity"
        assert client_file.name == "disk_mob.entity.json"

        with open(client_file) as f:
            loaded = json.load(f)
        assert loaded["format_version"] == "1.10.0"
        assert (
            loaded["minecraft:client_entity"]["description"]["identifier"] == "testmod:disk_mob"
        )

    def test_write_entities_to_disk_writes_rp_and_bp_halves(self, tmp_path):
        java_entities = [
            {"id": "dual_mob", "namespace": "testmod", "category": "passive"}
        ]
        result = self.converter.convert_entities(java_entities)

        bp_path = tmp_path / "behavior_pack"
        rp_path = tmp_path / "resource_pack"

        written = self.converter.write_entities_to_disk(result, bp_path, rp_path)

        # BP half
        assert len(written["entities"]) == 1
        assert written["entities"][0].parent == bp_path / "entities"
        # RP half
        assert len(written["entities_rp"]) == 1
        assert written["entities_rp"][0].parent == rp_path / "entity"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
