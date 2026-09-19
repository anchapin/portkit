"""
QA Validator Agent for validating conversion quality and generating comprehensive reports.
Implements real validation framework for Bedrock .mcaddon files.

This module is DEPRECATED. Import from agents.qa instead:
    from agents.qa import QAValidatorAgent

The qa_validator.py has been split into agents/qa/ subpackage:
- agents/qa/__init__.py          # QAValidatorAgent coordinator
- agents/qa/cache.py              # ValidationCache
- agents/qa/validation_rules.py   # VALIDATION_RULES
- agents/qa/manifest_validator.py  # Manifest field checks
- agents/qa/texture_validator.py  # PNG format, dimensions checks
- agents/qa/structure_validator.py # Block/item/entity/sound schema checks
- agents/qa/report_generator.py    # QA report assembly and scoring
"""

import warnings

warnings.warn(
    "agents.qa_validator is deprecated. Import from agents.qa instead: "
    "from agents.qa import QAValidatorAgent",
    DeprecationWarning,
    stacklevel=2,
)

from agents.qa import (
    QAValidatorAgent,
    ValidationCache,
    VALIDATION_RULES,
    VALIDATION_CATEGORIES,
    PASS_THRESHOLD,
    VALID_BLOCK_COMPONENTS,
    VALID_ENTITY_COMPONENTS,
    VALID_SOUND_FORMATS,
)

__all__ = [
    "QAValidatorAgent",
    "ValidationCache",
    "VALIDATION_RULES",
    "VALIDATION_CATEGORIES",
    "PASS_THRESHOLD",
    "VALID_BLOCK_COMPONENTS",
    "VALID_ENTITY_COMPONENTS",
    "VALID_SOUND_FORMATS",
]
