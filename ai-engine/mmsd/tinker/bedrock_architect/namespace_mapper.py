"""Namespace Mapper — Java to Bedrock identifier translation.

Provides mapping rules for translating Java package/naming conventions to
Bedrock namespace format (e.g., ``com.example.mod`` → ``example:``).

Issue #1612 — Extracted from bedrock_architect.py for single responsibility.
"""

from __future__ import annotations

import re
from typing import Optional


# Reserved namespaces that should not be remapped
RESERVED_NAMESPACES = {"minecraft", "realms", "education", "mpe"}

# Java package segment to Bedrock identifier sanitization map
_SANITIZE_RULES: list[tuple[re.Pattern[str], str]] = [
    # Remove numeric prefixes (e.g., "1" in "1.12.2-utils")
    (re.compile(r"^\d+"), ""),
    # Replace separators with underscores for Bedrock compatibility
    (re.compile(r"[_\-]+"), "_"),
    # Collapse multiple underscores
    (re.compile(r"_{2,}"), "_"),
    # Remove leading/trailing underscores
    (re.compile(r"^_|_$"), ""),
]


def _sanitize_segment(segment: str) -> str:
    """Sanitize a package segment for use as Bedrock identifier."""
    result = segment.lower()
    for pattern, replacement in _SANITIZE_RULES:
        result = pattern.sub(replacement, result)
    return result


def java_to_bedrock_namespace(java_package: str) -> str:
    """Convert a Java package name to a Bedrock namespace identifier.

    Args:
        java_package: Full Java package like ``com.example.mod`` or ``net.minecraftforge``.

    Returns:
        Bedrock namespaced ID like ``example:`` or ``forge:``.
        Returns ``minecraft:`` for Minecraft core packages.

    Example:
        >>> java_to_bedrock_namespace("com.example.coolmod")
        'example:coolmod'
        >>> java_to_bedrock_namespace("net.minecraftforge.common")
        'forge:common'
    """
    if not java_package:
        return "minecraft:unknown"

    # Handle scoped minecraft packages
    if java_package.startswith("net.minecraft"):
        return f"minecraft:{_sanitize_segment(java_package.split('.', 2)[-1])}"
    if java_package.startswith("com.mojang"):
        return f"minecraft:{_sanitize_segment(java_package.split('.', 2)[-1])}"

    # Split and sanitize segments
    segments = [s for s in java_package.split(".") if s]

    if not segments:
        return "minecraft:unknown"

    # First segment becomes namespace (after sanitization)
    namespace = _sanitize_segment(segments[0])

    # Reserved namespaces stay as-is
    if namespace in RESERVED_NAMESPACES:
        if len(segments) > 1:
            return f"{namespace}:{_sanitize_segment(segments[-1])}"
        return f"{namespace}:"

    # Remaining segments form the path
    path = "/".join(_sanitize_segment(s) for s in segments[1:]) if len(segments) > 1 else ""

    if path:
        return f"{namespace}:{path}"
    return f"{namespace}:"


def bedrockify_java_class(java_class: str) -> str:
    """Convert a fully-qualified Java class name to Bedrock-style path.

    Args:
        java_class: Fully qualified class like ``com.example.mod.items.CoolItem``.

    Returns:
        Bedrock path like ``items/cool_item`` (no extension).

    Example:
        >>> bedrockify_java_class("com.example.mod.blocks.GoldBlock")
        'blocks/gold_block'
    """
    if not java_class:
        return ""

    # Strip the package part, keep only the class path
    segments = [s for s in java_class.split(".") if s]
    if len(segments) <= 1:
        return _sanitize_segment(segments[-1]) if segments else ""

    # Everything except the last segment is path, last segment is the name
    *path_parts, class_name = segments

    # Remove common suffixes
    for suffix in ("Block", "Item", "Entity", "TileEntity", "ItemStack"):
        if class_name.endswith(suffix):
            class_name = class_name[: -len(suffix)]
            break

    path = "/".join(_sanitize_segment(p) for p in path_parts)
    name = _sanitize_segment(class_name)

    if path:
        return f"{path}/{name}"
    return name


def parse_bedrock_identifier(identifier: str) -> tuple[str, str]:
    """Parse a Bedrock identifier into namespace and path.

    Args:
        identifier: Like ``example:cool_item`` or just ``cool_item``.

    Returns:
        Tuple of (namespace, path). If no namespace, defaults to ``minecraft``.

    Example:
        >>> parse_bedrock_identifier("example:items/cool_item")
        ('example', 'items/cool_item')
        >>> parse_bedrock_identifier("diamond_sword")
        ('minecraft', 'diamond_sword')
    """
    if not identifier:
        return ("minecraft", "")

    if ":" in identifier:
        namespace, path = identifier.split(":", 1)
        return (namespace or "minecraft", path or "")

    # No namespace — default to minecraft
    return ("minecraft", identifier)


def make_bedrock_path(namespace: str, *parts: str) -> str:
    """Construct a Bedrock namespaced path safely.

    Args:
        namespace: Target namespace (e.g., ``"example"``).
        *parts: Path components to join with ``/``.

    Returns:
        Full namespaced path like ``"example:blocks/stone"``.

    Example:
        >>> make_bedrock_path("example", "blocks", "cool_block")
        'example:blocks/cool_block'
    """
    clean_namespace = _sanitize_segment(namespace)
    clean_parts = [_sanitize_segment(p) for p in parts if p]
    path = "/".join(clean_parts)
    return f"{clean_namespace}:{path}" if path else f"{clean_namespace}:"


class NamespaceMapper:
    """Stateful namespace mapper with mod-specific overrides.

    Use this when you need per-mod namespace configuration that may
    include custom prefixes or legacy naming rules.
    """

    def __init__(self, mod_id: Optional[str] = None) -> None:
        """Initialize mapper with optional mod ID.

        Args:
            mod_id: Optional mod identifier for namespacing defaults.
        """
        self.mod_id = mod_id
        self._namespace_cache: dict[str, str] = {}
        self._class_path_cache: dict[str, str] = {}

    def map_package(self, java_package: str) -> str:
        """Map a Java package to Bedrock namespace (cached)."""
        if java_package not in self._namespace_cache:
            self._namespace_cache[java_package] = java_to_bedrock_namespace(java_package)
        return self._namespace_cache[java_package]

    def map_class(self, java_class: str) -> str:
        """Map a Java class to Bedrock path (cached)."""
        if java_class not in self._class_path_cache:
            self._class_path_cache[java_class] = bedrockify_java_class(java_class)
        return self._class_path_cache[java_class]

    def resolve(self, java_identifier: str) -> str:
        """Resolve a Java-style identifier to Bedrock format.

        Handles both fully-qualified class names and simple names.

        Args:
            java_identifier: Like ``com.example.mod.blocks.StoneBlock`` or just ``StoneBlock``.

        Returns:
            Resolved Bedrock identifier. Uses mod_id prefix if available.
        """
        if not java_identifier:
            return ""

        # Already has a colon — treat as Bedrock identifier
        if ":" in java_identifier:
            return java_identifier

        # Contains dots — likely a fully qualified name
        if "." in java_identifier and java_identifier.count(".") >= 2:
            mapped = self.map_class(java_identifier)
            if self.mod_id and ":" not in mapped:
                return f"{self.mod_id}:{mapped}"
            return mapped

        # Simple name — no dots
        sanitized = _sanitize_segment(java_identifier)
        if self.mod_id:
            return f"{self.mod_id}:{sanitized}"
        return sanitized

    def clear_cache(self) -> None:
        """Clear internal caches to free memory."""
        self._namespace_cache.clear()
        self._class_path_cache.clear()
