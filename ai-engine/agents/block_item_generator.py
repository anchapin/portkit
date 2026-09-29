"""
Block and Item Generator for creating Bedrock block and item definitions
Part of the Bedrock Add-on Generation System (Issue #6)

This module is now a thin wrapper re-exporting from agents.entity subpackage.
The core implementation has been split into the entity/ subpackage per Issue #1276.
"""

from agents.entity.block_item_generator import (
    ArmorProperties,
    ArmorType,
    BlockItemGenerator,
    MaterialType,
    RareItemProperties,
    RangedWeaponProperties,
    ToolProperties,
    ToolType,
)

BlockItemGeneratorAgent = BlockItemGenerator

__all__ = [
    "BlockItemGenerator",
    "BlockItemGeneratorAgent",
    "MaterialType",
    "ToolType",
    "ArmorType",
    "ToolProperties",
    "ArmorProperties",
    "BlockProperties",
    "ItemProperties",
    "ConsumableProperties",
    "RangedWeaponProperties",
    "RareItemProperties",
]
