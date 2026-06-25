"""URL classification for the Online Research agent.

:class:`URLAnalyzer` determines the :class:`~online_research.models.SourceType`
of a given URL and extracts the mod/pack/video identifier embedded in it
(issue #1730).
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from .models import SourceType

logger = logging.getLogger(__name__)


class URLAnalyzer:
    """Analyzes URLs to determine source type and extract information."""

    def __init__(self):
        self.source_patterns = {
            SourceType.CURSEFORGE: [
                r"curseforge\.com/minecraft/mc-mods/([^/]+)",
                r"curseforge\.com/minecraft/modpacks/([^/]+)",
            ],
            SourceType.MODRINTH: [r"modrinth\.com/mod/([^/]+)", r"modrinth\.com/modpack/([^/]+)"],
            SourceType.YOUTUBE: [r"youtube\.com/watch\?v=([^&]+)", r"youtu\.be/([^/]+)"],
        }

    def analyze_url(self, url: str) -> SourceType:
        """Determine the type of URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if "curseforge" in domain:
            return SourceType.CURSEFORGE
        elif "modrinth" in domain:
            return SourceType.MODRINTH
        elif "youtube" in domain or "youtu.be" in domain:
            return SourceType.YOUTUBE

        return SourceType.GENERIC_URL

    def extract_identifier(self, url: str, source_type: SourceType) -> Optional[str]:
        """Extract the mod/pack identifier from URL."""
        for pattern in self.source_patterns.get(source_type, []):
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
