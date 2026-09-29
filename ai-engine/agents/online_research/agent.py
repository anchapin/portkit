"""Online Research Analysis Agent (coordinator).

This module hosts :class:`OnlineResearchAgent`, the Mode-2 coordinator of the
AI-Powered Validation & Comparison system. It accepts URLs to
CurseForge/Modrinth/YouTube for original mod content, performs multimodal
analysis, generates feature checklists, and validates the converted addon
against the checklist.

The heavy lifting lives in focused submodules (``url_analyzer``, ``clients``,
``multimodal``, ``checklist``); this module wires them together and owns the
addon-validation + report-export logic. Issue #495 (Phase 4b); #1730 split.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .checklist import FeatureChecklistGenerator
from .clients import CurseForgeClient, ModrinthClient, YouTubeAnalyzer
from .models import (
    FeatureChecklistItem,
    ResearchSource,
    SourceType,
    ValidationReport,
)
from .multimodal import MultimodalAnalyzer
from .url_analyzer import URLAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OnlineResearchAgent:
    """
    Main agent for online research analysis.

    This agent:
    1. Accepts URLs from CurseForge, Modrinth, YouTube
    2. Fetches and analyzes mod/modpack information
    3. Generates feature checklists
    4. Validates converted addons against checklists
    """

    def __init__(
        self, curseforge_api_key: Optional[str] = None, youtube_api_key: Optional[str] = None
    ):
        self.url_analyzer = URLAnalyzer()
        self.curseforge = CurseForgeClient(curseforge_api_key)
        self.modrinth = ModrinthClient()
        self.youtube = YouTubeAnalyzer(youtube_api_key)
        self.multimodal = MultimodalAnalyzer()
        self.checklist_generator = FeatureChecklistGenerator()

        self.research_history: List[ResearchSource] = []

    def analyze_url(self, url: str) -> ResearchSource:
        """Analyze a single URL and fetch its information."""
        print(f"\nAnalyzing URL: {url}")

        source_type = self.url_analyzer.analyze_url(url)
        identifier = self.url_analyzer.extract_identifier(url, source_type)

        # Fetch data based on source type
        metadata = {}
        title = ""
        description = ""

        if source_type == SourceType.CURSEFORGE:
            if self.curseforge.is_available() and identifier:
                mod_info = self.curseforge.get_mod_info(identifier)
                metadata = mod_info
                title = mod_info.get("name", "Unknown Mod")
                description = mod_info.get("description", "")
            else:
                title = "CurseForge Mod"
                description = "Mod from CurseForge (API not configured)"

        elif source_type == SourceType.MODRINTH:
            mod_info = self.modrinth.get_mod_info(identifier or url)
            metadata = mod_info
            title = mod_info.get("title", "Unknown Mod")
            description = mod_info.get("description", "")

        elif source_type == SourceType.YOUTUBE:
            video_id = self.youtube.extract_video_id(url)
            if video_id:
                video_info = self.youtube.get_video_info(video_id)
                metadata = video_info
                title = video_info.get("title", "YouTube Video")
                description = video_info.get("description", "")

                # Extract features from video description
                features = self.youtube.extract_features_from_description(description)
                metadata["extracted_features"] = features

        else:
            title = "External Resource"
            description = "Generic URL content"

        source = ResearchSource(
            url=url,
            source_type=source_type,
            title=title,
            description=description,
            metadata=metadata,
            fetched_at=datetime.now(),
        )

        self.research_history.append(source)

        print(f"Source analyzed: {source_type.value} - {title}")

        return source

    def research_mod(self, urls: List[str], conversion_id: Optional[str] = None) -> Dict:
        """
        Perform research on multiple URLs.

        Args:
            urls: List of URLs to research
            conversion_id: Optional conversion ID to link research

        Returns:
            Research data dictionary
        """
        print(f"\n{'=' * 60}")
        print(f"Starting Online Research for conversion: {conversion_id or 'unknown'}")
        print(f"URLs to research: {urls}")
        print(f"{'=' * 60}\n")

        research_results = {
            "conversion_id": conversion_id,
            "sources": [],
            "all_features": [],
            "categories": set(),
            "researched_at": datetime.now().isoformat(),
        }

        # Analyze each URL
        for url in urls:
            try:
                source = self.analyze_url(url)
                research_results["sources"].append(
                    {
                        "url": source.url,
                        "type": source.source_type.value,
                        "title": source.title,
                        "description": source.description,
                    }
                )

                # Extract features from this source
                features = self.multimodal.extract_features_from_text(source.description)
                research_results["all_features"].extend(features)

                # Track categories
                if "categories" in source.metadata:
                    research_results["categories"].update(source.metadata["categories"])

            except Exception as e:
                print(f"Error analyzing URL {url}: {e}")

        # Deduplicate features
        research_results["all_features"] = list(set(research_results["all_features"]))

        # Convert categories set to list for JSON
        research_results["categories"] = list(research_results["categories"])

        print(f"\nResearch complete. Found {len(research_results['all_features'])} features")

        return research_results

    def generate_checklist(
        self, research_data: Dict, source_type: SourceType = SourceType.GENERIC_URL
    ) -> List[FeatureChecklistItem]:
        """Generate a feature checklist from research data."""
        return self.checklist_generator.generate_checklist(research_data, source_type)

    def validate_addon(
        self, conversion_id: str, bedrock_addon_path: str, checklist: List[FeatureChecklistItem]
    ) -> ValidationReport:
        """
        Validate a converted addon against the feature checklist.

        Args:
            conversion_id: ID of the conversion
            bedrock_addon_path: Path to the converted Bedrock addon
            checklist: Feature checklist to validate against

        Returns:
            ValidationReport with results
        """
        print(f"\nValidating addon: {bedrock_addon_path}")

        # Analyze addon files
        addon_features = self._analyze_addon(bedrock_addon_path)

        # Validate each checklist item
        verified = []
        missing = []
        unclear = []

        for item in checklist:
            # Check if feature is present in addon
            if self._check_feature_in_addon(item.feature_name, addon_features):
                item.validation_status = "verified"
                item.detected = True
                verified.append(item.feature_name)
            elif self._partial_match(item.feature_name, addon_features):
                item.validation_status = "unclear"
                item.evidence.append("Partial match found in addon")
                unclear.append(item.feature_name)
            else:
                item.validation_status = "missing"
                item.detected = False
                missing.append(item.feature_name)

        # Calculate score
        total_items = len(checklist)
        if total_items > 0:
            score = (len(verified) / total_items) * 100
        else:
            score = 0.0

        # Generate recommendations
        recommendations = self._generate_validation_recommendations(
            verified, missing, unclear, score
        )

        report = ValidationReport(
            overall_score=round(score, 2),
            feature_checklist=checklist,
            verified_features=verified,
            missing_features=missing,
            unclear_features=unclear,
            recommendations=recommendations,
            research_sources=self.research_history,
        )

        print(f"\nValidation complete. Score: {score:.1f}%")
        print(f"Verified: {len(verified)}, Missing: {len(missing)}, Unclear: {len(unclear)}")

        return report

    def _analyze_addon(self, addon_path: str) -> Dict[str, List[str]]:
        """Analyze addon files to extract features."""
        print(f"Analyzing addon at: {addon_path}")

        features = {
            "blocks": [],
            "items": [],
            "recipes": [],
            "loot_tables": [],
            "functions": [],
            "entities": [],
        }

        # In production, would parse actual addon files
        # For now, return empty structure
        # This would read JSON files from the addon

        return features

    def _check_feature_in_addon(self, feature_name: str, addon_features: Dict) -> bool:
        """Check if a feature exists in the addon."""
        feature_lower = feature_name.lower()

        # Check each category
        for category, items in addon_features.items():
            if any(feature_lower in item.lower() for item in items):
                return True

        return False

    def _partial_match(self, feature_name: str, addon_features: Dict) -> bool:
        """Check for partial matches."""
        feature_words = feature_name.split()

        for category, items in addon_features.items():
            for item in items:
                item_lower = item.lower()
                if any(word in item_lower for word in feature_words if len(word) > 3):
                    return True

        return False

    def _generate_validation_recommendations(
        self, verified: List[str], missing: List[str], unclear: List[str], score: float
    ) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        if score >= 80:
            recommendations.append("Excellent: Most features were successfully validated.")
        elif score >= 50:
            recommendations.append("Good: Some features need review. Check missing features.")
        else:
            recommendations.append("Warning: Many features are missing. Manual review required.")

        if missing:
            recommendations.append(f"Missing {len(missing)} features: {', '.join(missing[:5])}")

        if unclear:
            recommendations.append(f"Review {len(unclear)} unclear features for accuracy.")

        # Add specific recommendations - use substring matching for robustness
        if any("dimension" in feature.lower() for feature in missing):
            recommendations.append(
                "Custom dimensions are not supported in Bedrock. Consider using structures or custom worlds."
            )

        if any("enchant" in feature.lower() for feature in missing):
            recommendations.append(
                "Enchanting systems may need to be converted to alternative mechanics in Bedrock."
            )

        if any("custom block" in feature.lower() for feature in missing):
            recommendations.append("Check that all custom blocks have proper behavior definitions.")

        return recommendations

    def export_research_report(self, research_data: Dict, output_path: str):
        """Export research data to a file."""
        with open(output_path, "w") as f:
            json.dump(research_data, f, indent=2)

        print(f"Research report exported to: {output_path}")

    def export_validation_report(self, report: ValidationReport, output_path: str):
        """Export validation report to a file."""
        report_dict = {
            "overall_score": report.overall_score,
            "verified_features": report.verified_features,
            "missing_features": report.missing_features,
            "unclear_features": report.unclear_features,
            "recommendations": report.recommendations,
            "checklist": [
                {
                    "feature": item.feature_name,
                    "category": item.category,
                    "priority": item.priority,
                    "status": item.validation_status,
                    "evidence": item.evidence,
                }
                for item in report.feature_checklist
            ],
            "sources": [
                {"url": s.url, "type": s.source_type.value, "title": s.title}
                for s in report.research_sources
            ],
        }

        with open(output_path, "w") as f:
            json.dump(report_dict, f, indent=2)

        print(f"Validation report exported to: {output_path}")
