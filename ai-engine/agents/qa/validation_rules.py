"""
Validation rules for Bedrock add-on QA validation.
"""

VALIDATION_RULES = {
    "manifest": {
        "format_version": [1, 2],
        "required_fields": ["uuid", "name", "version", "description"],
        "uuid_pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        "version_format": "array_3_ints",
        "min_engine_version": [1, 21, 0],
    },
    "blocks": {
        "required_fields": ["format_version", "minecraft:block"],
        "texture_reference": "must_exist",
        "identifier_format": "namespace:name",
    },
    "items": {
        "required_fields": ["format_version", "minecraft:item"],
        "texture_reference": "must_exist",
    },
    "entities": {
        "required_fields": ["format_version", "minecraft:entity"],
        "identifier_format": "namespace:name",
    },
    "textures": {
        "format": "PNG",
        "valid_extensions": [".png"],
        "dimensions": "power_of_2",
        "max_size": 1024,
    },
    "models": {
        "valid_extensions": [".geo.json", ".json"],
        "max_vertices": 3000,
    },
    "sounds": {
        "valid_extensions": [".ogg", ".wav"],
        "max_size_mb": 10,
    },
}
