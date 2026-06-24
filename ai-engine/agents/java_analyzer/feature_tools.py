"""Typed tools for Java mod *feature* & *asset* identification."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field

from ._base_tool import _BaseJavaAnalyzerTool

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.tools")


def _identify_features_impl(mod_data: Union[str, Dict]) -> str:
    """
    Identify features in the mod.

    Args:
        mod_data: JSON string containing analysis data

    Returns:
        JSON string with identified features
    """
    from agents.java_analyzer import JavaAnalyzerAgent

    JavaAnalyzerAgent.get_instance()

    def _categorize_features(features: List[Dict]) -> Dict:
        """Categorize features by type"""
        categories = {}
        for feature in features:
            feature_type = feature.get("feature_type", "unknown")
            if feature_type not in categories:
                categories[feature_type] = []
            categories[feature_type].append(feature)
        return categories

    def _analyze_feature_complexity(features: List[Dict]) -> Dict:
        """Analyze complexity of identified features"""
        return {
            "total_features": len(features),
            "complexity_distribution": {"simple": 0, "moderate": 0, "complex": 0},
            "high_priority_features": [f for f in features if f.get("confidence") == "high"],
        }

    def _identify_conversion_challenges(features: List[Dict], categories: Dict) -> List[str]:
        """Identify potential conversion challenges"""
        challenges = []

        if "dimensions" in categories:
            challenges.append("Custom dimensions require structural workarounds")

        if "gui" in categories:
            challenges.append("Custom GUIs need alternative interfaces")

        if "machinery" in categories:
            challenges.append("Complex machinery may lose functionality")

        return challenges

    try:
        if isinstance(mod_data, str):
            try:
                data = json.loads(mod_data)
                if "mod_data" in data:
                    mod_path = data["mod_data"]
                else:
                    mod_path = data.get("mod_path", "")
            except json.JSONDecodeError:
                mod_path = mod_data
        else:
            data = mod_data if isinstance(mod_data, dict) else {"mod_path": str(mod_data)}
            if "mod_data" in data:
                mod_path = data["mod_data"]
            else:
                mod_path = data.get("mod_path", str(mod_data))

        feature_results = {
            "identified_features": [],
            "feature_categories": {},
            "feature_complexity": {},
            "conversion_challenges": [],
        }

        if mod_path.endswith((".jar", ".zip")):
            analyzer_instance = JavaAnalyzerAgent.get_instance()
            ast_result = analyzer_instance.analyze_jar_with_ast(mod_path)
            if ast_result["success"]:
                features = []
                for feature_type, feature_list in ast_result.get("features", {}).items():
                    for feature in feature_list:
                        features.append(
                            {
                                "feature_id": f"{feature_type}_{feature.get('name', 'unknown').lower()}",
                                "feature_type": feature_type,
                                "name": feature.get("name", "Unknown"),
                                "source": "ast_analysis",
                                "confidence": "high",
                                "original_data": feature,
                            }
                        )
            else:
                features = []
        else:
            features = []

        categorized_features = _categorize_features(features)
        feature_results["identified_features"] = features
        feature_results["feature_categories"] = categorized_features

        complexity_analysis = _analyze_feature_complexity(features)
        feature_results["feature_complexity"] = complexity_analysis

        challenges = _identify_conversion_challenges(features, categorized_features)
        feature_results["conversion_challenges"] = challenges

        response = {
            "success": True,
            "feature_results": feature_results,
            "feature_summary": {"summary": f"Identified {len(features)} features"},
        }

        logger.info(f"Identified {len(features)} features in: {mod_path}")
        return json.dumps(response)

    except Exception as e:
        error_response = {"success": False, "error": f"Failed to identify features: {str(e)}"}
        logger.error(f"Feature identification error: {e}")
        return json.dumps(error_response)


def _extract_assets_impl(mod_data: Union[str, Dict]) -> str:
    """
    Extract assets from the mod.

    Args:
        mod_data: JSON string containing mod file path

    Returns:
        JSON string with asset information
    """
    from agents.java_analyzer import JavaAnalyzerAgent

    JavaAnalyzerAgent.get_instance()

    def _extract_assets_from_jar(jar_path: str, asset_types: List[str]) -> List[Dict]:
        """Extract assets from JAR"""
        assets = []
        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()

                for file_path in file_list:
                    if "/textures/" in file_path and file_path.endswith((".png", ".jpg", ".jpeg")):
                        assets.append(
                            {
                                "type": "texture",
                                "path": file_path,
                                "name": Path(file_path).name,
                                "size": jar.getinfo(file_path).file_size,
                            }
                        )
                    elif "/models/" in file_path and file_path.endswith((".json", ".obj")):
                        assets.append(
                            {
                                "type": "model",
                                "path": file_path,
                                "name": Path(file_path).name,
                                "size": jar.getinfo(file_path).file_size,
                            }
                        )
                    elif "/sounds/" in file_path and file_path.endswith((".ogg", ".wav")):
                        assets.append(
                            {
                                "type": "sound",
                                "path": file_path,
                                "name": Path(file_path).name,
                                "size": jar.getinfo(file_path).file_size,
                            }
                        )
                    elif "/lang/" in file_path and file_path.endswith(".json"):
                        assets.append(
                            {
                                "type": "lang",
                                "path": file_path,
                                "name": Path(file_path).name,
                                "size": jar.getinfo(file_path).file_size,
                            }
                        )
                    elif file_path.endswith("sounds.json") and "/sounds" in file_path:
                        assets.append(
                            {
                                "type": "sounds_json",
                                "path": file_path,
                                "name": Path(file_path).name,
                                "size": jar.getinfo(file_path).file_size,
                            }
                        )
        except Exception as e:
            logger.warning(f"Error extracting assets from JAR: {e}")

        return assets

    def _determine_asset_type(asset: Dict) -> str:
        """Determine asset type"""
        asset_type = asset.get("type", "unknown")
        if asset_type in ["texture", "model", "sound"]:
            return f"{asset_type}s"
        return "other_assets"

    try:
        if isinstance(mod_data, str):
            try:
                data = json.loads(mod_data)
                if "mod_data" in data:
                    mod_path = data["mod_data"]
                else:
                    mod_path = data.get("mod_path", "")
            except json.JSONDecodeError:
                mod_path = mod_data
        else:
            data = mod_data if isinstance(mod_data, dict) else {"mod_path": str(mod_data)}
            if "mod_data" in data:
                mod_path = data["mod_data"]
            else:
                mod_path = data.get("mod_path", str(mod_data))

        asset_results = {
            "textures": [],
            "models": [],
            "sounds": [],
            "other_assets": [],
            "asset_summary": {},
        }

        if mod_path.endswith((".jar", ".zip")):
            assets = _extract_assets_from_jar(mod_path, [])
        else:
            assets = []

        for asset in assets:
            asset_type = _determine_asset_type(asset)
            if asset_type in asset_results:
                asset_results[asset_type].append(asset)
            else:
                asset_results["other_assets"].append(asset)

        asset_results["asset_summary"] = {"summary": "Asset extraction completed"}

        response = {
            "success": True,
            "assets": asset_results,
            "conversion_notes": ["Assets ready for conversion analysis"],
        }

        total_assets = sum(
            len(assets) for assets in asset_results.values() if isinstance(assets, list)
        )
        logger.info(f"Extracted {total_assets} assets from: {mod_path}")
        return json.dumps(response)

    except Exception as e:
        error_response = {"success": False, "error": f"Failed to extract assets: {str(e)}"}
        logger.error(f"Asset extraction error: {e}")
        return json.dumps(error_response)


class _IdentifyFeaturesInput(BaseModel):
    """Args for :class:`_IdentifyFeaturesTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: Any = Field(
        description="JSON string or dict containing ``mod_path`` and feature options.",
    )


class _ExtractAssetsInput(BaseModel):
    """Args for :class:`_ExtractAssetsTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: Any = Field(
        description=(
            "JSON string or dict containing ``mod_path``, ``output_dir``, and "
            "optional ``asset_types`` filter."
        ),
    )


class _IdentifyFeaturesTool(_BaseJavaAnalyzerTool):
    name: str = "identify_features_tool"
    description: str = (
        "Identify mod features (blocks, items, entities, recipes, events) "
        "from source/jar inspection. "
        "Args: mod_data (str or dict, required) — mod_path and options."
    )
    args_schema: ClassVar[type[BaseModel]] = _IdentifyFeaturesInput

    def _run(self, mod_data: Any) -> str:  # type: ignore[override]
        return _identify_features_impl(mod_data)


class _ExtractAssetsTool(_BaseJavaAnalyzerTool):
    name: str = "extract_assets_tool"
    description: str = (
        "Extract assets (textures, models, sounds) from a Java mod. "
        "Args: mod_data (str or dict, required) — mod_path, output_dir, "
        "optional asset_types filter."
    )
    args_schema: ClassVar[type[BaseModel]] = _ExtractAssetsInput

    def _run(self, mod_data: Any) -> str:  # type: ignore[override]
        return _extract_assets_impl(mod_data)
