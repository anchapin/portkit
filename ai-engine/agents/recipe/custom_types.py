"""
Custom recipe types converter for NeoForge, Farmer's Delight, Create, and
ImmersiveEngineering — backwards-compatibility facade.

This module is a thin composition/re-export shim (issue #1745). The real
per-mod conversion logic now lives in focused, domain-scoped modules:

- ``converter_base.py`` — shared base class, the Forge recipe-type registry
  loader (``_load_custom_recipe_types`` / ``CUSTOM_RECIPE_TYPES``), and the
  ``is_custom_recipe_type`` membership check.
- ``create_converter.py`` — Farmer's Delight + Create conversion methods
  (``CreateConverterMixin``).
- ``immersive_engineering_converter.py`` — ImmersiveEngineering conversion
  methods (``ImmersiveEngineeringConverterMixin``).

``CustomTypesConverter`` is composed from the two domain mixins so the public
API (``CustomTypesConverter(map_fn).convert_*`` and the module-level
``CUSTOM_RECIPE_TYPES`` / ``is_custom_recipe_type`` / ``_load_custom_recipe_types``
symbols) is preserved exactly. Existing imports such as
``from agents.recipe.custom_types import CustomTypesConverter`` keep working.
"""

from agents.recipe.converter_base import (
    CUSTOM_RECIPE_TYPES,
    _load_custom_recipe_types,
    is_custom_recipe_type,
)
from agents.recipe.create_converter import CreateConverterMixin
from agents.recipe.immersive_engineering_converter import (
    ImmersiveEngineeringConverterMixin,
)


class CustomTypesConverter(CreateConverterMixin, ImmersiveEngineeringConverterMixin):
    """Converter for custom Forge recipe types.

    Composed from :class:`CreateConverterMixin` (Farmer's Delight + Create)
    and :class:`ImmersiveEngineeringConverterMixin`, both of which inherit
    the shared item-mapping and manual-review helpers from
    :class:`CustomConverterBase`. The MRO is::

        CustomTypesConverter
          -> CreateConverterMixin
          -> ImmersiveEngineeringConverterMixin
          -> CustomConverterBase
          -> object

    so ``self._map_java_item`` / ``self._create_manual_review_result``
    resolve to the shared base.
    """


__all__ = [
    "CUSTOM_RECIPE_TYPES",
    "CustomTypesConverter",
    "is_custom_recipe_type",
    "_load_custom_recipe_types",
]

__all__ = [
    "CUSTOM_RECIPE_TYPES",
    "CustomTypesConverter",
    "is_custom_recipe_type",
    "_load_custom_recipe_types",
]
