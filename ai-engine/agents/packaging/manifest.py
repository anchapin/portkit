"""
Manifest generation for Bedrock addon packages.

This module delegates to ManifestBuilder for manifest generation.
Extracted from the original manifest logic per issue #1581/#1640.

Per issue #1278: Split packaging_agent.py (42K) + packaging_validator.py (31K) into packaging/ subpackage
"""

import logging
from typing import Any, Dict, Tuple

from .manifest_builder import ManifestBuilder

logger = logging.getLogger(__name__)


class ManifestGenerator:
    """Handles manifest.json and pack_icon generation."""

    def __init__(self):
        self._builder = ManifestBuilder()
        self.manifest_template = self._builder.manifest_template

    def generate_manifest(self, mod_info: str, pack_type: str) -> str:
        """
        Generate manifest for a pack.

        Args:
            mod_info: JSON string containing mod information
            pack_type: Type of pack ("behavior", "resource", "both")

        Returns:
            JSON string with manifest data
        """
        return self._builder.generate_manifest(mod_info, pack_type)

    def generate_manifests(self, manifest_data: str) -> str:
        """
        Generate manifests for packaging.

        Args:
            manifest_data: JSON string or dict containing manifest information

        Returns:
            JSON string with generation results
        """
        return self._builder.generate_manifests(manifest_data)

    def generate_enhanced_manifests(self, data: Dict[str, Any]) -> Tuple[Dict, Dict]:
        """
        Generate enhanced Bedrock manifests.

        Args:
            data: Dict containing mod data

        Returns:
            Tuple of (behavior_pack_manifest, resource_pack_manifest)
        """
        return self._builder.generate_enhanced_manifests(data)
