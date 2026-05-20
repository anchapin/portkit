"""Layout Planner — Bedrock addon directory tree skeleton generation.

Provides functions to plan and create the standard Bedrock addon directory
structure including behavior pack and resource pack layouts.

Issue #1614 — Extracted from bedrock_architect.py for single responsibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PackLayer(Enum):
    """Which layer of the addon this directory belongs to."""

    BEHAVIOR = "behavior"
    RESOURCE = "resource"
    COMMON = "common"


@dataclass
class DirectoryNode:
    """Represents a directory entry in the addon structure."""

    path: str  # Relative path within the pack (e.g., "blocks", "items")
    required: bool = True  # Whether this dir is mandatory in a valid pack
    children: List["DirectoryNode"] = field(default_factory=list)
    description: str = ""  # Human-readable description of purpose


@dataclass
class LayoutPlan:
    """Complete layout plan for an addon with both packs."""

    behavior_dirs: List[str] = field(default_factory=list)
    resource_dirs: List[str] = field(default_factory=list)
    required_files: Set[str] = field(default_factory=set)
    optional_dirs: List[str] = field(default_factory=list)
    pack_type: str = "both"  # "behavior", "resource", or "both"


# Standard Bedrock behavior pack directory structure
BEHAVIOR_PACK_STRUCTURE = [
    DirectoryNode(path="scripts", required=False, description="JavaScript entry points"),
    DirectoryNode(path="entities", required=True, description="Entity definitions"),
    DirectoryNode(path="blocks", required=True, description="Block definitions"),
    DirectoryNode(path="items", required=True, description="Item definitions"),
    DirectoryNode(path="loot_tables", required=False, description="Loot table JSON files"),
    DirectoryNode(path="loot_tables/blocks", required=False, description="Block-specific loot"),
    DirectoryNode(path="loot_tables/chests", required=False, description="Chest loot tables"),
    DirectoryNode(path="loot_tables/entity", required=False, description="Entity loot tables"),
    DirectoryNode(path="recipes", required=False, description="Crafting recipes"),
    DirectoryNode(path="recipes/furnace", required=False, description="Furnace recipes"),
    DirectoryNode(path="recipes/shaped", required=False, description="Shaped crafting"),
    DirectoryNode(path="recipes/shapeless", required=False, description="Shapeless crafting"),
    DirectoryNode(path="functions", required=False, description="MCFunction files"),
    DirectoryNode(path="functions/tick", required=False, description="Tick function loop"),
    DirectoryNode(path="functions/load", required=False, description="Load-time init"),
    DirectoryNode(path="structures", required=False, description="Structure NBT files"),
    DirectoryNode(path="dialogue", required=False, description="NPC dialogue files"),
    DirectoryNode(path="spawn_rules", required=False, description="Entity spawn rules"),
    DirectoryNode(path="render_controllers", required=False, description="Render controller JSON"),
    DirectoryNode(path="attachables", required=False, description="Item attachment definitions"),
    DirectoryNode(path="client/registry", required=False, description="Client-side registry"),
]

# Standard Bedrock resource pack directory structure
RESOURCE_PACK_STRUCTURE = [
    DirectoryNode(path="textures", required=True, description="Texture files"),
    DirectoryNode(path="textures/blocks", required=False, description="Block textures"),
    DirectoryNode(path="textures/items", required=False, description="Item textures"),
    DirectoryNode(path="textures/entity", required=False, description="Entity textures"),
    DirectoryNode(path="textures/ui", required=False, description="UI element textures"),
    DirectoryNode(path="textures/models", required=False, description="Model textures"),
    DirectoryNode(path="textures/particles", required=False, description="Particle textures"),
    DirectoryNode(path="textures/misc", required=False, description="Misc textures"),
    DirectoryNode(path="models", required=False, description="Block/item models JSON"),
    DirectoryNode(path="models/block", required=False, description="Block models"),
    DirectoryNode(path="models/item", required=False, description="Item models"),
    DirectoryNode(path="models/entity", required=False, description="Entity models"),
    DirectoryNode(path="animations", required=False, description="Animation JSON"),
    DirectoryNode(path="animations/animation_controllers", required=False, description="Anim controllers"),
    DirectoryNode(path="animation_controllers", required=False, description="Animation controllers"),
    DirectoryNode(path="render_controllers", required=False, description="Render controllers"),
    DirectoryNode(path="entity", required=False, description="Entity JSON definitions"),
    DirectoryNode(path="font", required=False, description="Custom font textures"),
    DirectoryNode(path="ui", required=False, description="UI layout files"),
    DirectoryNode(path="sounds", required=False, description="Sound definitions"),
    DirectoryNode(path="sounds/music", required=False, description="Music tracks"),
    DirectoryNode(path="sounds/vvox", required=False, description="Voice/speech"),
    DirectoryNode(path="sounds/note", required=False, description="Note block sounds"),
    DirectoryNode(path="particles", required=False, description="Particle definitions"),
    DirectoryNode(path="textures/camera", required=False, description="Camera textures"),
]

# Required files that must exist in a valid Bedrock pack
REQUIRED_MANIFEST_FILE_BP = "manifest.json"
REQUIRED_MANIFEST_FILE_RP = "manifest.json"


def flatten_directory_tree(nodes: List[DirectoryNode]) -> List[str]:
    """Flatten a tree of DirectoryNodes into a list of path strings.

    Args:
        nodes: List of DirectoryNode to flatten.

    Returns:
        List of directory paths (relative, no leading slash).
    """
    result: List[str] = []

    def walk(node: DirectoryNode) -> None:
        result.append(node.path)
        for child in node.children:
            walk(child)

    for node in nodes:
        walk(node)

    return result


def get_behavior_pack_dirs() -> List[str]:
    """Get the standard list of behavior pack directories.

    Returns:
        List of directory paths for a behavior pack.
    """
    return flatten_directory_tree(BEHAVIOR_PACK_STRUCTURE)


def get_resource_pack_dirs() -> List[str]:
    """Get the standard list of resource pack directories.

    Returns:
        List of directory paths for a resource pack.
    """
    return flatten_directory_tree(RESOURCE_PACK_STRUCTURE)


def create_layout_plan(mod_name: str, pack_layers: str = "both") -> LayoutPlan:
    """Create a layout plan for a new addon.

    Args:
        mod_name: Name of the mod (used for context).
        pack_layers: Which packs to include — "behavior", "resource", or "both".

    Returns:
        A LayoutPlan describing the directory structure.
    """
    plan = LayoutPlan(pack_type=pack_layers)

    if pack_layers in ("behavior", "both"):
        plan.behavior_dirs = get_behavior_pack_dirs()
        plan.required_files.add(REQUIRED_MANIFEST_FILE_BP)

    if pack_layers in ("resource", "both"):
        plan.resource_dirs = get_resource_pack_dirs()
        plan.required_files.add(REQUIRED_MANIFEST_FILE_RP)

    logger.debug(f"Created layout plan for {mod_name} ({pack_layers})")
    return plan


def create_directory_structure(
    base_path: Path,
    plan: LayoutPlan,
    create_manifest: bool = True,
) -> List[Path]:
    """Create the directory structure described by the plan on disk.

    Args:
        base_path: Base directory to create structure under.
        plan: LayoutPlan describing what to create.
        create_manifest: If True, also create placeholder manifest files.

    Returns:
        List of all paths that were created (directories + optional manifests).
    """
    created: List[Path] = []

    if plan.pack_type in ("behavior", "both"):
        for dir_path in plan.behavior_dirs:
            full_path = base_path / "behavior_pack" / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            created.append(full_path)

    if plan.pack_type in ("resource", "both"):
        for dir_path in plan.resource_dirs:
            full_path = base_path / "resource_pack" / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            created.append(full_path)

    if create_manifest:
        if plan.pack_type in ("behavior", "both"):
            manifest_path = base_path / "behavior_pack" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            created.append(manifest_path)

        if plan.pack_type in ("resource", "both"):
            manifest_path = base_path / "resource_pack" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            created.append(manifest_path)

    logger.info(f"Created {len(created)} paths for layout under {base_path}")
    return created


def add_custom_directory(plan: LayoutPlan, dir_path: str, pack_layer: str) -> None:
    """Add a custom directory to an existing plan.

    Args:
        plan: LayoutPlan to modify.
        dir_path: Directory path to add.
        pack_layer: Which layer to add to — "behavior" or "resource".
    """
    if pack_layer in ("behavior", "both") and dir_path not in plan.behavior_dirs:
        plan.behavior_dirs.append(dir_path)
        plan.optional_dirs.append(dir_path)

    if pack_layer in ("resource", "both") and dir_path not in plan.resource_dirs:
        plan.resource_dirs.append(dir_path)
        plan.optional_dirs.append(dir_path)


def add_required_file(plan: LayoutPlan, file_path: str) -> None:
    """Mark a file as required in the plan.

    Args:
        plan: LayoutPlan to modify.
        file_path: Path to the required file.
    """
    plan.required_files.add(file_path)


class LayoutPlanner:
    """Stateful planner for managing addon layouts with feature detection.

    Use this class when you need to customize layouts based on mod features
    or generate different structures for different conversion scenarios.
    """

    def __init__(self, mod_name: str = "ConvertedMod") -> None:
        """Initialize planner with mod name.

        Args:
            mod_name: Name for this addon (used for path generation).
        """
        self.mod_name = mod_name
        self._custom_dirs: Dict[str, List[str]] = {"behavior": [], "resource": []}
        self._custom_files: Set[str] = set()

    def add_behavior_dir(self, dir_path: str) -> "LayoutPlanner":
        """Add a custom behavior pack directory.

        Args:
            dir_path: Path to add (e.g., "custom_folder/subfolder").

        Returns:
            Self for chaining.
        """
        if dir_path not in self._custom_dirs["behavior"]:
            self._custom_dirs["behavior"].append(dir_path)
        return self

    def add_resource_dir(self, dir_path: str) -> "LayoutPlanner":
        """Add a custom resource pack directory.

        Args:
            dir_path: Path to add.

        Returns:
            Self for chaining.
        """
        if dir_path not in self._custom_dirs["resource"]:
            self._custom_dirs["resource"].append(dir_path)
        return self

    def add_required_file(self, file_path: str) -> "LayoutPlanner":
        """Add a required file path.

        Args:
            file_path: Path to mark as required (e.g., "custom_file.json").

        Returns:
            Self for chaining.
        """
        self._custom_files.add(file_path)
        return self

    def generate_plan(self, include_both: bool = True) -> LayoutPlan:
        """Generate a layout plan with customizations applied.

        Args:
            include_both: If True, include both packs. Otherwise only behavior.

        Returns:
            Complete LayoutPlan with standard + custom directories.
        """
        pack_type = "both" if include_both else "behavior"
        plan = create_layout_plan(self.mod_name, pack_type)

        # Apply custom behavior dirs
        for d in self._custom_dirs["behavior"]:
            if d not in plan.behavior_dirs:
                plan.behavior_dirs.append(d)

        # Apply custom resource dirs
        for d in self._custom_dirs["resource"]:
            if d not in plan.resource_dirs:
                plan.resource_dirs.append(d)

        # Apply custom required files
        plan.required_files.update(self._custom_files)

        return plan

    def apply_from_features(self, features: List[Dict[str, Any]]) -> "LayoutPlanner":
        """Auto-add directories based on detected mod features.

        Args:
            features: List of feature dictionaries with "type" keys.

        Returns:
            Self for chaining.
        """
        for feature in features:
            feature_type = feature.get("type", "")

            if feature_type in ("custom_ui", "scripting"):
                self.add_behavior_dir("scripts")
                self.add_resource_dir("textures/ui")

            elif feature_type in ("block", "item"):
                self.add_behavior_dir("loot_tables/blocks")

            elif feature_type == "entity":
                self.add_behavior_dir("spawn_rules")

            elif feature_type == "recipe":
                self.add_behavior_dir("recipes/shaped")

        return self

    def create_on_disk(self, base_path: Path, include_both: bool = True) -> List[Path]:
        """Generate and create the full directory structure.

        Args:
            base_path: Base path to create structure under.
            include_both: Whether to create both packs.

        Returns:
            List of all created paths.
        """
        plan = self.generate_plan(include_both)
        return create_directory_structure(base_path, plan)