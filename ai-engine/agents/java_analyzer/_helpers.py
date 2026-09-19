"""Registry-name helpers shared across feature extraction mixins."""

from __future__ import annotations


def _class_name_to_registry_name(class_name: str) -> str:
    """Convert Java class name to registry name format."""
    name = class_name
    if name.endswith("Block") and len(name) > 5:
        name = name[:-5]
    elif name.startswith("Block") and len(name) > 5 and name[5].isupper():
        name = name[5:]

    name = _snake_case(name)

    if not name:
        return "unknown"
    return name


def _snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re

    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    return name
