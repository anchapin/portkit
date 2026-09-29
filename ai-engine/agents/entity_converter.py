"""
Entity Converter for converting Java entities to Bedrock format
Part of the Bedrock Add-on Generation System (Issue #6)

This module is now a thin wrapper re-exporting from agents.entity subpackage.
The core implementation has been split into the entity/ subpackage per Issue #1276.
"""

from agents.entity.entity_converter import EntityConverter
from agents.entity.nbt_parser import EntityProperties, EntityType, MobCategory

EntityConverterAgent = EntityConverter

__all__ = [
    "EntityConverter",
    "EntityConverterAgent",
    "EntityType",
    "MobCategory",
    "EntityProperties",
]
