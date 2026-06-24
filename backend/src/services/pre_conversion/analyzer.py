"""
Pre-Conversion Analyzer

Analyzes uploaded Java mod files before conversion to identify
patterns and features that may fail or have reduced success rates.

Issue: #1769 - Split pre_conversion_scanner.py into focused modules
"""

import logging
import zipfile
import re
from typing import Any, Dict, List, Optional

from .models import (
    RiskCategory,
    RiskItem,
    RiskSeverity,
    ScanMetadata,
    PreConversionScanResult,
)

logger = logging.getLogger(__name__)


class PreConversionScanner:
    """
    Scans mod files to identify potential conversion issues before upload.
    """

    KNOWN_PROBLEMATIC_PATTERNS = {
        "mixin": {
            "severity": RiskSeverity.HIGH,
            "category": RiskCategory.ARCHITECTURE,
            "title": "Mixin Dependency Detected",
            "description": "This mod uses Mixin framework which requires special handling during conversion. Mixin is not natively supported in Bedrock.",
            "suggestion": "Consider using a Mixin-free alternative or acknowledging that gameplay modifications will require manual conversion.",
            "conversion_impact": "Mixin-based features may not convert automatically",
        },
        "asm": {
            "severity": RiskSeverity.HIGH,
            "category": RiskCategory.ARCHITECTURE,
            "title": "ASM/Bytecode Manipulation",
            "description": "This mod uses bytecode manipulation libraries (ASM, Javassist, etc.) which cannot be directly converted.",
            "suggestion": "Consider finding a Bedrock equivalent mod or manually recreating the functionality.",
            "conversion_impact": "Bytecode-level modifications will not transfer",
        },
        "reflection": {
            "severity": RiskSeverity.MEDIUM,
            "category": RiskCategory.PATTERN,
            "title": "Heavy Reflection Usage",
            "description": "This mod uses Java reflection extensively. Reflection does not exist in Bedrock scripting.",
            "suggestion": "Identify reflection-based patterns and plan for manual conversion or alternative approaches.",
            "conversion_impact": "Reflection-based functionality may need redesign",
        },
        "obfuscation": {
            "severity": RiskSeverity.CRITICAL,
            "category": RiskCategory.SECURITY,
            "title": "Obfuscated Code Detected",
            "description": "This mod appears to be obfuscated. Obfuscated code cannot be analyzed or converted.",
            "suggestion": "Obtain or use a non-obfuscated version of this mod for conversion.",
            "conversion_impact": "Conversion not possible - code analysis failed",
        },
    }

    PROBLEMATIC_DEPENDENCIES = {
        "com.evmisc": "Cauldron/Mohist server mod - not compatible with Bedrock",
        "org.glowbot": "GlowBot - server mod incompatible with Bedrock",
        "kdot.bungee": "BungeeCord/Waterfall - server proxies not applicable",
        "net.md_5": "BungeeCord API - server-side only",
        "org.spigotmc": "Spigot server API - not compatible",
        "org.bukkit": "Bukkit API - not compatible with Bedrock",
        "paper": "Paper server API - server-side only",
        "ca.neralabs": "Cauldron server - not Bedrock compatible",
        "mixin": "Mixin framework - not supported in Bedrock",
        "org.spongepowered": "Sponge API - server mod API",
    }

    COMPLEXITY_INDICATORS = {
        "nested_inner_classes": {
            "threshold": 10,
            "severity": RiskSeverity.MEDIUM,
            "title": "High Number of Inner Classes",
            "description": "This mod has many nested inner classes which increases conversion complexity.",
            "suggestion": "Consider simplifying nested structures if possible.",
        },
        "lambda_expressions": {
            "threshold": 50,
            "severity": RiskSeverity.LOW,
            "title": "Heavy Lambda Usage",
            "description": "This mod uses many lambda expressions. Most will convert but may need review.",
            "suggestion": "Review converted lambdas for correct behavior.",
        },
        "generics_depth": {
            "threshold": 3,
            "severity": RiskSeverity.MEDIUM,
            "title": "Deep Generics Usage",
            "description": "This mod uses deeply nested generics which may not fully convert.",
            "suggestion": "Review generic type translations carefully.",
        },
        "anonymous_classes": {
            "threshold": 20,
            "severity": RiskSeverity.MEDIUM,
            "title": "Many Anonymous Classes",
            "description": "Many anonymous inner classes detected. These can complicate conversion.",
            "suggestion": "Consider refactoring to named inner classes if possible.",
        },
    }

    ASSET_RISKS = {
        ".png": {
            "issues": ["misaligned_alpha", "non_power_of_two", "invalid_dimensions"],
            "severity": RiskSeverity.MEDIUM,
            "title": "Texture File Issues",
            "description": "Texture files may have issues that affect Bedrock rendering.",
        },
        ".ogg": {
            "issues": ["invalid_codec", "corrupted", "unsupported_sample_rate"],
            "severity": RiskSeverity.LOW,
            "title": "Sound File Potential Issues",
            "description": "Sound files may need format verification.",
        },
        ".mcmeta": {
            "issues": ["invalid_animation_config", "missing_frames", "corrupted"],
            "severity": RiskSeverity.LOW,
            "title": "Animation Metadata Issues",
            "description": "Animation configuration files may need verification.",
        },
    }

    def __init__(self) -> None:
        self.version = "1.0"

    async def scan_file(self, file_path: str, filename: str) -> PreConversionScanResult:
        """
        Scan a mod file for potential conversion issues.

        Args:
            file_path: Path to the uploaded file
            filename: Original filename

        Returns:
            PreConversionScanResult with identified risks
        """
        import uuid
        from datetime import datetime, timezone

        scan_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        risks: List[RiskItem] = []
        metadata = ScanMetadata(
            filename=filename,
            file_size=0,
            file_count=0,
            has_manifest=False,
        )

        try:
            import os

            metadata.file_size = os.path.getsize(file_path)

            with zipfile.ZipFile(file_path, "r") as zf:
                metadata.file_count = len(zf.namelist())

                risks.extend(self._scan_manifest(zf))
                risks.extend(await self._scan_java_files(zf))
                risks.extend(self._scan_dependencies(zf))
                risks.extend(self._scan_assets(zf))
                risks.extend(self._scan_complexity_indicators(zf))

        except zipfile.BadZipFile:
            risks.append(
                RiskItem(
                    risk_id="invalid_archive",
                    severity=RiskSeverity.CRITICAL,
                    category=RiskCategory.SECURITY,
                    title="Invalid ZIP/JAR Archive",
                    description="The file is not a valid JAR/ZIP archive and cannot be processed.",
                    suggestion="Ensure the file is a valid Minecraft mod JAR archive.",
                    conversion_impact="File cannot be analyzed",
                )
            )
        except Exception as e:
            logger.error(f"Error scanning file: {e}")
            risks.append(
                RiskItem(
                    risk_id="scan_error",
                    severity=RiskSeverity.MEDIUM,
                    category=RiskCategory.SECURITY,
                    title="Scan Error",
                    description=f"An error occurred during scanning: {str(e)}",
                    suggestion="Try uploading the file again or contact support if the problem persists.",
                    conversion_impact="Scan incomplete - some issues may not be detected",
                )
            )

        overall_risk = self._calculate_overall_risk(risks)
        can_proceed = overall_risk not in (RiskSeverity.CRITICAL,)

        recommendations = self._generate_recommendations(risks)
        warnings_summary = self._generate_summary(risks, overall_risk)

        return PreConversionScanResult(
            scan_id=scan_id,
            metadata=metadata,
            overall_risk_level=overall_risk,
            total_issues=len(risks),
            risks=risks,
            can_proceed=can_proceed,
            warnings_summary=warnings_summary,
            recommendations=recommendations,
            scan_timestamp=timestamp,
        )

    def _scan_manifest(self, zf: zipfile.ZipFile) -> List[RiskItem]:
        """Scan for mod manifest and metadata issues."""
        risks: List[RiskItem] = []

        manifest_paths = [
            "META-INF/mods.toml",
            "META-INF/neoforge.mods.toml",
            "fabric.mod.json",
            "mcmod.info",
        ]
        manifest_found = None

        for path in manifest_paths:
            if path in zf.namelist():
                manifest_found = path
                break

        if manifest_found:
            try:
                content = zf.read(manifest_found).decode("utf-8", errors="ignore")

                if "mods.toml" in manifest_found:
                    if "version" not in content.lower():
                        risks.append(
                            RiskItem(
                                risk_id="missing_version_manifest",
                                severity=RiskSeverity.LOW,
                                category=RiskCategory.COMPATIBILITY,
                                title="Missing Version in Manifest",
                                description="The mod manifest does not specify a version.",
                                suggestion="Add version information to the manifest for better tracking.",
                            )
                        )
                    if (
                        "mcversion" not in content.lower()
                        and "minecraftversion" not in content.lower()
                    ):
                        risks.append(
                            RiskItem(
                                risk_id="missing_mc_version",
                                severity=RiskSeverity.MEDIUM,
                                category=RiskCategory.COMPATIBILITY,
                                title="Missing Minecraft Version",
                                description="Cannot determine target Minecraft version from manifest.",
                                suggestion="Ensure the mod is compatible with the target Bedrock version.",
                            )
                        )
                elif "fabric.mod.json" in manifest_found:
                    import json

                    try:
                        data = json.loads(content)
                        if "depends" in data:
                            depends = data["depends"]
                            if "minecraft" in depends:
                                mc_version = depends["minecraft"]
                                if mc_version.startswith("1.8") or mc_version.startswith("1.7"):
                                    risks.append(
                                        RiskItem(
                                            risk_id="old_mc_version",
                                            severity=RiskSeverity.HIGH,
                                            category=RiskCategory.COMPATIBILITY,
                                            title="Outdated Minecraft Version",
                                            description=f"Mod targets Minecraft {mc_version} which is very old.",
                                            suggestion="Consider updating to a more recent version if possible.",
                                            conversion_impact="Older versions may have reduced conversion accuracy",
                                            evidence=[f"Target: {mc_version}"],
                                        )
                                    )
                    except json.JSONDecodeError:
                        pass

            except Exception as e:
                logger.warning(f"Could not read manifest {manifest_found}: {e}")

        return risks

    async def _scan_java_files(self, zf: zipfile.ZipFile) -> List[RiskItem]:
        """Scan Java source files for problematic patterns."""
        risks: List[RiskItem] = []
        java_files = [f for f in zf.namelist() if f.endswith(".java")]

        for java_file in java_files[:100]:
            try:
                content = zf.read(java_file).decode("utf-8", errors="ignore").lower()

                for pattern_key, pattern_info in self.KNOWN_PROBLEMATIC_PATTERNS.items():
                    if pattern_key in content:
                        existing_ids = [r.risk_id for r in risks]
                        risk_id = f"{pattern_key}_detected"
                        if risk_id not in existing_ids:
                            risks.append(
                                RiskItem(
                                    risk_id=risk_id,
                                    severity=pattern_info["severity"],
                                    category=pattern_info["category"],
                                    title=pattern_info["title"],
                                    description=pattern_info["description"],
                                    location=java_file,
                                    suggestion=pattern_info.get("suggestion"),
                                    conversion_impact=pattern_info.get("conversion_impact"),
                                )
                            )

                if len(content) > 50000:
                    risks.append(
                        RiskItem(
                            risk_id=f"large_java_file",
                            severity=RiskSeverity.LOW,
                            category=RiskCategory.COMPLEXITY,
                            title="Large Java File",
                            description=f"{java_file} is unusually large ({len(content)} chars). Large files may take longer to convert.",
                            suggestion="Consider splitting large classes for easier conversion.",
                            location=java_file,
                        )
                    )

            except Exception as e:
                logger.debug(f"Could not scan {java_file}: {e}")

        return risks

    def _scan_dependencies(self, zf: zipfile.ZipFile) -> List[RiskItem]:
        """Scan for incompatible dependencies."""
        risks: List[RiskItem] = []
        found_problematic: List[str] = []

        for name in zf.namelist():
            name_lower = name.lower().replace("/", ".").replace("\\", ".")
            path_parts = set(name_lower.split("."))

            for dep_pattern, dep_info in self.PROBLEMATIC_DEPENDENCIES.items():
                if dep_pattern in name_lower or dep_pattern in path_parts:
                    if dep_pattern not in found_problematic:
                        found_problematic.append(dep_pattern)
                        risks.append(
                            RiskItem(
                                risk_id=f"incompatible_dep_{dep_pattern}",
                                severity=RiskSeverity.HIGH,
                                category=RiskCategory.DEPENDENCY,
                                title="Incompatible Dependency",
                                description=dep_info,
                                location=name,
                                suggestion="Remove or replace this dependency with a Bedrock-compatible alternative.",
                                conversion_impact="This dependency will not work in Bedrock",
                            )
                        )

        return risks

    def _scan_assets(self, zf: zipfile.ZipFile) -> List[RiskItem]:
        """Scan asset files for potential issues."""
        risks: List[RiskItem] = []
        asset_files = [
            f
            for f in zf.namelist()
            if any(f.endswith(ext) for ext in [".png", ".ogg", ".mcmeta", ".json"])
        ]

        texture_count = len([f for f in asset_files if f.endswith(".png")])

        if texture_count > 200:
            risks.append(
                RiskItem(
                    risk_id="high_texture_count",
                    severity=RiskSeverity.MEDIUM,
                    category=RiskCategory.ASSET,
                    title="High Number of Textures",
                    description=f"This mod has {texture_count} texture files. Large texture packs may take longer to convert.",
                    suggestion="Consider organizing textures efficiently.",
                    conversion_impact="More textures = longer conversion time",
                )
            )

        json_files = [f for f in asset_files if f.endswith(".json")]
        for json_file in json_files:
            try:
                content = zf.read(json_file).decode("utf-8", errors="ignore")

                if "blockbench" in content.lower():
                    risks.append(
                        RiskItem(
                            risk_id="blockbench_model",
                            severity=RiskSeverity.LOW,
                            category=RiskCategory.ASSET,
                            title="Blockbench Model Detected",
                            description="This mod uses Blockbench for model creation. Blockbench models generally convert well.",
                            location=json_file,
                        )
                    )

                try:
                    import json

                    data = json.loads(content)
                    if "format_version" in data:
                        version = data["format_version"]
                        if isinstance(version, list):
                            version_str = ".".join(map(str, version))
                        else:
                            version_str = str(version)

                        if (
                            version_str.startswith("1.")
                            and not version_str.startswith("1.16")
                            and not version_str.startswith("1.17")
                            and not version_str.startswith("1.18")
                            and not version_str.startswith("1.19")
                            and not version_str.startswith("1.20")
                        ):
                            risks.append(
                                RiskItem(
                                    risk_id="old_format_version",
                                    severity=RiskSeverity.MEDIUM,
                                    category=RiskCategory.COMPATIBILITY,
                                    title="Old Bedrock Format Version",
                                    description=f"Asset uses format version {version_str} which may not be fully supported.",
                                    location=json_file,
                                    suggestion="Consider updating to a more recent format version if possible.",
                                    conversion_impact="Older formats may not convert correctly",
                                )
                            )
                except (json.JSONDecodeError, ValueError):
                    pass

            except Exception as e:
                logger.debug(f"Could not analyze asset {json_file}: {e}")

        return risks

    def _scan_complexity_indicators(self, zf: zipfile.ZipFile) -> List[RiskItem]:
        """Scan for complexity indicators."""
        risks: List[RiskItem] = []

        java_files = [f for f in zf.namelist() if f.endswith(".java")]
        total_classes = 0
        total_inner_classes = 0
        total_anonymous = 0
        total_lambdas = 0

        for java_file in java_files[:50]:
            try:
                content = zf.read(java_file).decode("utf-8", errors="ignore")

                class_matches = re.findall(r"class\s+\w+", content)
                total_classes += len(class_matches)

                inner_class_matches = re.findall(r"class\s+\w+\s*\$", content)
                total_inner_classes += len(inner_class_matches)

                anonymous_matches = re.findall(r"new\s+\w+\s*\(", content)
                total_anonymous += len(anonymous_matches)

                lambda_matches = re.findall(r"->\s*\{|\->\s*\w+\s*\{", content)
                total_lambdas += len(lambda_matches)

            except Exception:
                pass

        if total_inner_classes > 10:
            indicator = self.COMPLEXITY_INDICATORS["nested_inner_classes"]
            risks.append(
                RiskItem(
                    risk_id="nested_inner_classes",
                    severity=indicator["severity"],
                    category=RiskCategory.COMPLEXITY,
                    title=indicator["title"],
                    description=f"Found {total_inner_classes} inner classes (threshold: 10). {indicator['description']}",
                    suggestion=indicator["suggestion"],
                    conversion_impact="High nesting complexity may affect conversion accuracy",
                    evidence=[f"Inner classes: {total_inner_classes}"],
                )
            )

        if total_lambdas > 50:
            indicator = self.COMPLEXITY_INDICATORS["lambda_expressions"]
            risks.append(
                RiskItem(
                    risk_id="lambda_expressions",
                    severity=indicator["severity"],
                    category=RiskCategory.COMPLEXITY,
                    title=indicator["title"],
                    description=f"Found {total_lambdas} lambda expressions. {indicator['description']}",
                    suggestion=indicator["suggestion"],
                    evidence=[f"Lambda count: {total_lambdas}"],
                )
            )

        return risks

    def _calculate_overall_risk(self, risks: List[RiskItem]) -> RiskSeverity:
        """Calculate overall risk level based on identified issues."""
        if not risks:
            return RiskSeverity.LOW

        severity_counts = {
            RiskSeverity.CRITICAL: 0,
            RiskSeverity.HIGH: 0,
            RiskSeverity.MEDIUM: 0,
            RiskSeverity.LOW: 0,
        }

        for risk in risks:
            severity_counts[risk.severity] = severity_counts.get(risk.severity, 0) + 1

        if severity_counts[RiskSeverity.CRITICAL] > 0:
            return RiskSeverity.CRITICAL
        if severity_counts[RiskSeverity.HIGH] >= 3:
            return RiskSeverity.HIGH
        if severity_counts[RiskSeverity.HIGH] >= 1:
            return RiskSeverity.MEDIUM
        if severity_counts[RiskSeverity.MEDIUM] >= 3:
            return RiskSeverity.MEDIUM
        if severity_counts[RiskSeverity.MEDIUM] >= 1:
            return RiskSeverity.LOW

        return RiskSeverity.LOW

    def _generate_recommendations(self, risks: List[RiskItem]) -> List[str]:
        """Generate recommendations based on identified risks."""
        recommendations: List[str] = []

        severity_to_rec = {
            RiskSeverity.CRITICAL: "Address critical issues before attempting conversion.",
            RiskSeverity.HIGH: "Review high-severity issues - these may significantly impact conversion.",
            RiskSeverity.MEDIUM: "Consider addressing medium-severity issues for better results.",
            RiskSeverity.LOW: "Low-risk issues detected. Conversion should proceed normally.",
        }

        categories_present = set(risk.category for risk in risks)

        if RiskCategory.ARCHITECTURE in categories_present:
            recommendations.append(
                "This mod uses advanced Java patterns. Review the conversion report carefully after completion."
            )

        if RiskCategory.DEPENDENCY in categories_present:
            recommendations.append(
                "Some dependencies are not compatible with Bedrock. Identify alternatives before conversion."
            )

        if RiskCategory.COMPATIBILITY in categories_present:
            recommendations.append(
                "Version compatibility issues detected. Ensure your Bedrock target version is appropriate."
            )

        if RiskCategory.ASSET in categories_present:
            recommendations.append(
                "Asset file issues detected. Verify texture and sound files after conversion."
            )

        if not recommendations:
            recommendations.append("No major issues detected. Proceed with standard conversion.")

        return recommendations

    def _generate_summary(self, risks: List[RiskItem], overall_risk: RiskSeverity) -> str:
        """Generate a human-readable summary of scan results."""
        if not risks:
            return "No potential issues detected. The mod appears to be a good candidate for conversion."

        count_by_severity = {}
        for risk in risks:
            severity = risk.severity.value
            count_by_severity[severity] = count_by_severity.get(severity, 0) + 1

        severity_parts = []
        for sev in ["critical", "high", "medium", "low"]:
            if sev in count_by_severity:
                severity_parts.append(f"{count_by_severity[sev]} {sev}")

        summary = f"Found {len(risks)} potential issues ({', '.join(severity_parts)}). "

        if overall_risk == RiskSeverity.CRITICAL:
            summary += "Conversion is not recommended until critical issues are resolved."
        elif overall_risk == RiskSeverity.HIGH:
            summary += "Conversion may have reduced success rate. Review recommendations."
        elif overall_risk == RiskSeverity.MEDIUM:
            summary += "Conversion should proceed but review issues after completion."
        else:
            summary += "Conversion is likely to succeed with minor issues possible."

        return summary
