"""bedrock_architect subpackage — Bedrock addon conversion planning components.

This subpackage provides modular components extracted from the monolithic
bedrock_architect.py for single-responsibility design:

- namespace_mapper: Java → Bedrock namespace identifier translation
- manifest_generator: Bedrock manifest.json structure generation
- layout_planner: Addon directory tree skeleton planning
- behavior_planner: Block/entity/item/recipe behavior file generation
- dimension_porter: Biome and dimension porting logic

Issue #1622 — Coordinator __init__.py for bedrock_architect subpackage.
"""

from __future__ import annotations

# Re-export BedrockArchitectAgent from the original module for backward compat
from agents.bedrock_architect_original import BedrockArchitectAgent

# Import submodules using relative imports
from . import namespace_mapper
from . import manifest_generator
from . import layout_planner
from . import behavior_planner
from . import dimension_porter

# Re-export key classes and functions for convenience
from .namespace_mapper import (
    java_to_bedrock_namespace,
    bedrockify_java_class,
    parse_bedrock_identifier,
    make_bedrock_path,
    NamespaceMapper,
)

from .manifest_generator import (
    PackType,
    ModuleInfo,
    ManifestData,
    generate_pack_uuid,
    parse_version_string,
    determine_capabilities,
    create_behavior_manifest,
    create_resource_manifest,
    add_pack_dependency,
    generate_manifests_pair,
    write_manifest_to_file,
    validate_manifest,
    BedrockManifestGenerator,
)

from .layout_planner import (
    PackLayer,
    DirectoryNode,
    LayoutPlan,
    BEHAVIOR_PACK_STRUCTURE,
    RESOURCE_PACK_STRUCTURE,
    flatten_directory_tree,
    get_behavior_pack_dirs,
    get_resource_pack_dirs,
    create_layout_plan,
    create_directory_structure,
    add_custom_directory,
    add_required_file,
    LayoutPlanner,
)

from .behavior_planner import (
    ComponentType,
    DefinitionOptions,
    generate_block_definition,
    generate_item_definition,
    generate_entity_definition,
    generate_recipe_definition,
    generate_definition_json,
    BehaviorPlanner,
)

from .dimension_porter import (
    DimensionType,
    BiomeCategory,
    PortingWarning,
    DimensionPortingResult,
    BiomePortingResult,
    identify_dimension_type,
    map_java_biome,
    identify_biome_category,
    validate_dimension_compatibility,
    validate_biome_compatibility,
    port_dimension,
    port_biome,
    DimensionPorter,
)

__all__ = [
    # Backward compat
    "BedrockArchitectAgent",
    # Submodules
    "namespace_mapper",
    "manifest_generator",
    "layout_planner",
    "behavior_planner",
    "dimension_porter",
    # namespace_mapper
    "java_to_bedrock_namespace",
    "bedrockify_java_class",
    "parse_bedrock_identifier",
    "make_bedrock_path",
    "NamespaceMapper",
    # manifest_generator
    "PackType",
    "ModuleInfo",
    "ManifestData",
    "generate_pack_uuid",
    "parse_version_string",
    "determine_capabilities",
    "create_behavior_manifest",
    "create_resource_manifest",
    "add_pack_dependency",
    "generate_manifests_pair",
    "write_manifest_to_file",
    "validate_manifest",
    "BedrockManifestGenerator",
    # layout_planner
    "PackLayer",
    "DirectoryNode",
    "LayoutPlan",
    "BEHAVIOR_PACK_STRUCTURE",
    "RESOURCE_PACK_STRUCTURE",
    "flatten_directory_tree",
    "get_behavior_pack_dirs",
    "get_resource_pack_dirs",
    "create_layout_plan",
    "create_directory_structure",
    "add_custom_directory",
    "add_required_file",
    "LayoutPlanner",
    # behavior_planner
    "ComponentType",
    "DefinitionOptions",
    "generate_block_definition",
    "generate_item_definition",
    "generate_entity_definition",
    "generate_recipe_definition",
    "generate_definition_json",
    "BehaviorPlanner",
    # dimension_porter
    "DimensionType",
    "BiomeCategory",
    "PortingWarning",
    "DimensionPortingResult",
    "BiomePortingResult",
    "identify_dimension_type",
    "map_java_biome",
    "identify_biome_category",
    "validate_dimension_compatibility",
    "validate_biome_compatibility",
    "port_dimension",
    "port_biome",
    "DimensionPorter",
]