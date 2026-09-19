"""
Entity package - modular entity, block, and item conversion.

Provides the same public API as the original entity_converter and
block_item_generator modules by re-exporting from the subpackage modules.

Subpackage structure:
├── __init__.py              # Thin coordinator (this file)
├── nbt_parser.py            # NBT tag and Java property extraction
├── attribute_mapper.py       # Entity attribute → Bedrock component mapping
├── block_state_parser.py    # Block state variant resolution
├── block_generator.py       # Bedrock block behavior JSON assembly
├── item_generator.py        # Bedrock item JSON + model resolution
├── type_registry.py          # Java entity/block/item type → Bedrock identifier lookups
├── entity_converter.py       # Main entity converter (replaces entity_converter.py)
└── block_item_generator.py  # Main block/item generator (replaces block_item_generator.py)
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
from agents.entity.entity_converter import (
    EntityConverter,
    EntityType,
    MobCategory,
)

EntityConverterAgent = EntityConverter
BlockItemGeneratorAgent = BlockItemGenerator

__all__ = [
    "EntityConverter",
    "EntityConverterAgent",
    "BlockItemGenerator",
    "BlockItemGeneratorAgent",
    "EntityType",
    "MobCategory",
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
    "nbt_parser",
    "attribute_mapper",
    "block_state_parser",
    "block_generator",
    "item_generator",
    "type_registry",
]
