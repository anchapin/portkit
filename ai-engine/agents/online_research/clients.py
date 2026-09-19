"""API clients for the Online Research agent.

Thin clients around the external content sources used by
:class:`~online_research.agent.OnlineResearchAgent`:

- :class:`CurseForgeClient` — CurseForge REST API (mocked).
- :class:`ModrinthClient` — Modrinth REST API (mocked).
- :class:`YouTubeAnalyzer` — YouTube video metadata + description mining.

These are the source-fetching counterparts to the descriptor-file parsers in
:mod:`online_research.parsers` (which parse already-downloaded pack
manifests). Issue #1730.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CurseForgeClient:
    """Client for fetching data from CurseForge API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("CURSEFORGE_API_KEY", "")
        self.base_url = "https://api.curseforge.com/v1"
        self.headers = (
            {"Accept": "application/json", "x-api-key": self.api_key} if self.api_key else {}
        )

    def get_mod_info(self, mod_id: str) -> Dict:
        """Fetch mod information from CurseForge."""
        print(f"Fetching CurseForge mod info for: {mod_id}")

        # In production, would call actual API
        # For now, return mock data
        return {
            "id": mod_id,
            "name": "Example Mod",
            "summary": "A sample mod for testing",
            "description": "This mod adds various features...",
            "categories": [{"name": "Mechanics"}, {"name": "Tools"}],
            "latestFiles": [{"fileName": "mod-1.0.jar", "gameVersion": ["1.20.4"]}],
            "downloadCount": 10000,
        }

    def get_mod_files(self, mod_id: str) -> List[Dict]:
        """Fetch mod files from CurseForge."""
        print(f"Fetching CurseForge files for: {mod_id}")

        # Mock response
        return [
            {
                "id": "file_1",
                "displayName": "mod-1.0.jar",
                "gameVersion": "1.20.4",
                "releaseType": "release",
                "downloadUrl": f"https://curseforge.com/minecraft/mc-mods/{mod_id}/download",
            },
            {
                "id": "file_2",
                "displayName": "mod-1.1.jar",
                "gameVersion": "1.20.4",
                "releaseType": "release",
                "downloadUrl": f"https://curseforge.com/minecraft/mc-mods/{mod_id}/download",
            },
        ]

    def is_available(self) -> bool:
        """Check if API is available."""
        return bool(self.api_key)


class ModrinthClient:
    """Client for fetching data from Modrinth API."""

    def __init__(self):
        self.base_url = "https://api.modrinth.com/v2"
        self.headers = {"Accept": "application/json"}

    def get_mod_info(self, mod_id: str) -> Dict:
        """Fetch mod information from Modrinth."""
        print(f"Fetching Modrinth mod info for: {mod_id}")

        # Mock response
        return {
            "id": mod_id,
            "title": "Example Mod",
            "description": "A sample mod for testing",
            "categories": ["mechanics", "tools"],
            "versions": ["1.20.4", "1.20.1"],
            "downloads": 5000,
        }

    def get_mod_versions(self, mod_id: str) -> List[Dict]:
        """Fetch mod versions from Modrinth."""
        print(f"Fetching Modrinth versions for: {mod_id}")

        return [
            {
                "id": "version_1",
                "version_number": "1.0.0",
                "game_versions": ["1.20.4"],
                "loaders": ["fabric", "forge"],
            }
        ]

    def is_available(self) -> bool:
        """Check if API is available."""
        return True


class YouTubeAnalyzer:
    """Analyzer for YouTube content."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        self.youtube_regex = r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"

    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from URL."""
        match = re.search(self.youtube_regex, url)
        return match.group(1) if match else None

    def get_video_info(self, video_id: str) -> Dict:
        """Fetch video information from YouTube."""
        print(f"Fetching YouTube video info for: {video_id}")

        # In production, would call YouTube API
        # Mock response
        return {
            "video_id": video_id,
            "title": "Mod Showcase Video",
            "description": "This video demonstrates the features of the mod...",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "duration_seconds": 300,
            "channel_name": "Example Channel",
        }

    def extract_features_from_description(self, description: str) -> List[str]:
        """Extract feature mentions from video description."""
        features = []

        # Common feature patterns
        patterns = [
            r"(?:adds?|introduces?|features?)\s+([^\.]+)",
            r"(?:new|custom)\s+(\w+(?:\s+\w+)?)",
            r"(\w+)\s+(?:feature|mechanic|system)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            features.extend(matches)

        return list(set(features))[:10]  # Limit to 10 features

    def is_available(self) -> bool:
        """Check if API is available."""
        return True
