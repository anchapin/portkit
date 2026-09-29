"""
QA report assembly and scoring.
"""

from typing import Any, Dict, List


ISSUE_SEVERITY = {
    "critical": {"weight": 10, "description": "Prevents functionality or causes crashes"},
    "major": {"weight": 5, "description": "Significantly impacts functionality"},
    "minor": {"weight": 2, "description": "Minor functionality impact"},
    "cosmetic": {"weight": 1, "description": "Visual or aesthetic issues only"},
}

QUALITY_THRESHOLDS = {
    "feature_conversion_rate": 0.8,
    "assumption_accuracy": 0.9,
    "bedrock_compatibility": 0.95,
    "performance_score": 0.7,
    "user_experience_score": 0.8,
}

PASS_THRESHOLD = 0.70

VALIDATION_CATEGORIES = {
    "structural": {
        "weight": 0.30,
        "description": "ZIP structure, required folders, no temp files",
    },
    "asset_validity": {
        "weight": 0.30,
        "description": "Textures, sounds exist and are valid",
    },
    "semantic_accuracy": {
        "weight": 0.20,
        "description": "Block/item/entity definitions are valid",
    },
    "best_practices": {
        "weight": 0.20,
        "description": "Manifest.json, UUID format, version",
    },
    "bedrock_compatibility": {
        "weight": 0.0,
        "description": "Bedrock-specific component and format validation",
    },
}


def get_category_status(checks: int, passed: int) -> str:
    """Get status for a validation category."""
    if checks == 0:
        return "unknown"

    percentage = passed / checks if checks > 0 else 0

    if percentage >= 0.9:
        return "pass"
    elif percentage >= 0.7:
        return "partial"
    else:
        return "fail"


def calculate_overall_score(result: Dict[str, Any], categories: Dict[str, Any]) -> int:
    """Calculate overall quality score (0-100%)."""
    total_weight = 0
    weighted_score = 0

    for category, config in categories.items():
        validation = result["validations"][category]
        weight = config["weight"]

        if validation["checks"] > 0:
            category_score = validation["passed"] / validation["checks"]
        else:
            category_score = 1.0

        weighted_score += category_score * weight
        total_weight += weight

    if total_weight > 0:
        overall = int((weighted_score / total_weight) * 100)
    else:
        overall = 0

    return max(0, min(100, overall))


def determine_status(result: Dict[str, Any], threshold: float = PASS_THRESHOLD) -> str:
    """Determine overall validation status."""
    score = result["overall_score"] / 100.0

    critical_errors = sum(
        1 for v in result["validations"].values() for issue in v.get("errors", [])
    )

    if critical_errors > 0:
        return "fail"

    if score >= threshold:
        return "pass"
    elif score >= threshold - 0.1:
        return "partial"
    else:
        return "fail"


def generate_recommendations(result: Dict[str, Any]) -> List[str]:
    """Generate actionable recommendations based on validation results."""
    recommendations = []

    for category, validation in result["validations"].items():
        if validation["errors"]:
            recommendations.append(
                f"Fix {len(validation['errors'])} critical error(s) in {category} validation"
            )

        if validation["warnings"]:
            recommendations.append(f"Review {len(validation['warnings'])} warning(s) in {category}")

    score = result["overall_score"]
    if score < 70:
        recommendations.append("Overall quality is below threshold - prioritize fixing errors")
    elif score < 90:
        recommendations.append("Good quality, address warnings to reach excellence")
    else:
        recommendations.append("Excellent quality! Add-on is ready for distribution")

    stats = result.get("stats", {})
    if stats.get("total_size_bytes", 0) > 100 * 1024 * 1024:
        recommendations.append("Consider optimizing assets to reduce file size")

    return recommendations


def collect_stats(zipf) -> Dict[str, Any]:
    """Collect statistics about the addon."""
    namelist = zipf.namelist()
    infolist = zipf.infolist()

    stats = {
        "total_files": len(namelist),
        "total_size_bytes": sum(info.file_size for info in infolist),
        "total_size_compressed": sum(info.compress_size for info in infolist),
        "file_types": {},
        "packs": {"behavior_packs": set(), "resource_packs": set()},
    }

    for name in namelist:
        from pathlib import Path

        ext = Path(name).suffix.lower()
        stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1

        if name.startswith("behavior_packs/"):
            parts = name.split("/")
            if len(parts) > 1:
                stats["packs"]["behavior_packs"].add(parts[1])
        elif name.startswith("resource_packs/"):
            parts = name.split("/")
            if len(parts) > 1:
                stats["packs"]["resource_packs"].add(parts[1])

    stats["packs"]["behavior_packs"] = list(stats["packs"]["behavior_packs"])
    stats["packs"]["resource_packs"] = list(stats["packs"]["resource_packs"])

    return stats


def create_empty_validation_result() -> Dict[str, Any]:
    """Create an empty validation result structure."""
    return {
        "overall_score": 0,
        "status": "unknown",
        "validation_time": None,
        "validations": {
            "structural": {
                "status": "unknown",
                "checks": 0,
                "passed": 0,
                "errors": [],
                "warnings": [],
            },
            "asset_validity": {
                "status": "unknown",
                "checks": 0,
                "passed": 0,
                "errors": [],
                "warnings": [],
            },
            "semantic_accuracy": {
                "status": "unknown",
                "checks": 0,
                "passed": 0,
                "errors": [],
                "warnings": [],
            },
            "best_practices": {
                "status": "unknown",
                "checks": 0,
                "passed": 0,
                "errors": [],
                "warnings": [],
            },
            "bedrock_compatibility": {
                "status": "unknown",
                "checks": 0,
                "passed": 0,
                "errors": [],
                "warnings": [],
            },
        },
        "issues": [],
        "recommendations": [],
        "stats": {},
    }
