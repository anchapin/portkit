"""
Bedrock client-side entity definition generator (Issue #1773).

Produces the resource-pack half of a converted mob: the
``minecraft:client_entity`` document that binds a behavior-pack entity
identifier to a geometry model, a textures map, a materials list, a render
controller and the animation/animation-controller references.

Without this file Bedrock silently spawns an invisible, untextured "shadow"
of the mob, so the behavior-pack work is functionally wasted on the player.
The generator reuses the identifier and the animation-controller keys the
``EntityConverter`` already computes, keeping the BP/RP halves in parity.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CLIENT_ENTITY_FORMAT_VERSION = "1.10.0"
DEFAULT_MATERIAL = "entity_alphatest"
DEFAULT_RENDER_CONTROLLER = "controller.render.default"


def _resolve_identifier(bedrock_bp_entity: Dict[str, Any]) -> str:
    """Pull the BP entity identifier from a converted ``minecraft:entity`` dict."""
    try:
        return bedrock_bp_entity["minecraft:entity"]["description"]["identifier"]
    except (KeyError, TypeError) as exc:
        raise ValueError("bedrock_bp_entity is missing minecraft:entity.description.identifier") from exc


def _resolve_texture_path(java_entity: Dict[str, Any], entity_name: str) -> str:
    """
    Resolve the texture path key for the client entity.

    The texture pillar (diff-path computation from the source jar) is out of
    scope for this issue, so we resolve a deterministic resource-pack path
    from the Java entity's texture hint when present, falling back to the
    canonical ``textures/entity/<name>/<name>`` layout.
    """
    texture = java_entity.get("texture")
    if isinstance(texture, str) and texture:
        return texture
    if isinstance(texture, dict):
        path = texture.get("path") or texture.get("default")
        if isinstance(path, str) and path:
            return path
    return f"textures/entity/{entity_name}/{entity_name}"


def _collect_animation_refs(java_entity: Dict[str, Any], entity_name: str) -> Dict[str, str]:
    """
    Build the ``animations`` short-name -> reference map.

    Mirrors the keys produced by ``EntityConverter._generate_entity_animations``
    (``animation.<id>.<name>``).
    """
    refs: Dict[str, str] = {}
    for animation in java_entity.get("animations", []) or []:
        if not isinstance(animation, dict):
            continue
        anim_name = animation.get("name") or animation.get("id") or "default"
        short_name = animation.get("short_name") or anim_name
        refs[short_name] = f"animation.{entity_name}.{anim_name}"
    return refs


def _collect_animation_controller_refs(java_entity: Dict[str, Any]) -> List[str]:
    """
    Collect the animation-controller references for ``scripts.animate``.

    Mirrors the controller identifier keys produced by
    ``EntityConverter._generate_animation_controllers`` (via
    ``convert_animation_controller``), which are formatted as
    ``animation_controller.<controllerId>``.
    """
    refs: List[str] = []
    for controller in java_entity.get("animation_controllers", []) or []:
        if not isinstance(controller, dict):
            continue
        controller_id = controller.get("controllerId") or controller.get("id") or "default"
        refs.append(f"animation_controller.{controller_id}")
    return refs


def _has_spawn_egg(bedrock_bp_entity: Dict[str, Any]) -> bool:
    components = bedrock_bp_entity.get("minecraft:entity", {}).get("components", {}) or {}
    return "minecraft:spawn_egg" in components


def generate_client_entity(
    bedrock_bp_entity: Dict[str, Any],
    java_entity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a Bedrock ``minecraft:client_entity`` definition.

    Args:
        bedrock_bp_entity: The converted behavior-pack entity dict (the
            ``minecraft:entity`` document produced by ``EntityConverter``).
            Its ``description.identifier`` drives identifier parity.
        java_entity: The originating Java entity definition. Used to resolve
            the texture path and the animation/animation-controller references
            so the RP half mirrors the BP half. May be ``None`` for a
            behavior-only stub, in which case only the structural defaults are
            emitted.

    Returns:
        A dict with ``format_version`` and ``minecraft:client_entity`` keys
        suitable for serialization to ``rp/entity/<id>.entity.json``.
    """
    java_entity = java_entity or {}
    identifier = _resolve_identifier(bedrock_bp_entity)
    entity_name = identifier.split(":")[-1]

    description: Dict[str, Any] = {
        "identifier": identifier,
        "materials": {"default": DEFAULT_MATERIAL},
        "textures": {"default": _resolve_texture_path(java_entity, entity_name)},
        "geometry": {"default": f"geometry.{entity_name}"},
        "render_controllers": [DEFAULT_RENDER_CONTROLLER],
    }

    animation_refs = _collect_animation_refs(java_entity, entity_name)
    controller_refs = _collect_animation_controller_refs(java_entity)

    if animation_refs:
        description["animations"] = animation_refs

    # ``scripts.animate`` drives the state-machine controllers; mirror the
    # keys already produced by ``_generate_animation_controllers`` so the RP
    # half stays in lockstep with whatever the BP half emitted.
    if controller_refs:
        description["scripts"] = {"animate": controller_refs}

    if _has_spawn_egg(bedrock_bp_entity):
        description["spawn_egg"] = {"texture": f"{entity_name}_spawn_egg"}

    client_entity = {
        "format_version": CLIENT_ENTITY_FORMAT_VERSION,
        "minecraft:client_entity": {"description": description},
    }

    logger.debug("Generated client entity definition for %s", identifier)
    return client_entity
