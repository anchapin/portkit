"""
Bundler for dependency resolution and MCADDON archive creation.

This module delegates to ZipAssembler for zip operations.
Extracted from the original bundler logic per issue #1581/#1641.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

import logging
from pathlib import Path
from typing import Any, Dict

from .zip_assembler import ZipAssembler

logger = logging.getLogger(__name__)


class Bundler:
    """Handles dependency resolution and MCADDON archive creation."""

    def __init__(self):
        self._zip_assembler = ZipAssembler()
        self.package_constraints = self._zip_assembler.package_constraints

    def build_mcaddon(self, build_data: Any) -> str:
        """Build the final mcaddon package."""
        return self._zip_assembler.build_mcaddon(build_data)

    def build_mcaddon_mvp(
        self, temp_dir: str, output_path: str, mod_name: str = None
    ) -> Dict[str, Any]:
        """Build .mcaddon file from temp directory structure for MVP pipeline."""
        return self._zip_assembler.build_mcaddon_mvp(temp_dir, output_path, mod_name)

    def _validate_mcaddon_file(self, mcaddon_path: Path) -> Dict[str, Any]:
        """Validate a created .mcaddon file."""
        return self._zip_assembler._validate_mcaddon_file(mcaddon_path)

    def get_package_constraints(self) -> Dict[str, Any]:
        """Get package constraints."""
        return self.package_constraints