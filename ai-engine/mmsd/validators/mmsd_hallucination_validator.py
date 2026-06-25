#!/usr/bin/env python3
"""
MMSD Hallucination Validator — PortKit AI Engine
==================================================
Post-processing validator that scans MMSD-generated Bedrock code for
hallucinated API calls and provides structured rejection/regeneration signals.

Based on hallucination_catalog.py patterns (23 hard + semantic + lingering).

Usage:
    from mmsd.validators.mmsd_hallucination_validator import MMSDHallucinationValidator, ValidationResult

    validator = MMSDHallucinationValidator()
    result = validator.validate(bedrock_script)
    if not result.is_valid:
        print(f"Hallucinated APIs: {result.hallucinated_apis}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Use the centralized hallucination catalog
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mmsd.tinker.hallucination_catalog import (
        HALLUCINATION_CATALOG,
        HallucinationCatalog,
        HallucinationFinding,
        HallucinationPattern,
        HallucinationType,
    )
except ImportError:
    from ai_engine.mmsd.tinker.hallucination_catalog import (
        HALLUCINATION_CATALOG,
        HallucinationCatalog,
        HallucinationFinding,
        HallucinationPattern,
        HallucinationType,
    )


# ── Known valid Bedrock Script API surfaces ─────────────────────────────────
# These are the ONLY valid APIs the model should reference.
# Any reference outside this set is a hallucination.

VALID_BEDROCK_APIS = {
    # Module: @minecraft/server
    # Core globals
    "world", "system", "player", "players", "dimension",
    # world events
    "WorldAfterEvents", "WorldBeforeEvents", "WorldInitializeEvent",
    "world.afterEvents", "world.beforeEvents",
    # player events
    "PlayerAfterEvents", "PlayerBeforeEvents",
    "player.afterEvents", "player.beforeEvents",
    # entity events
    "EntityAfterEvents", "EntityBeforeEvents",
    "entity.afterEvents", "entity.beforeEvents",
    # system events
    "system.runInterval", "system.runTimeout", "system.run",
    "SystemEvents",
    # Classes
    "Block", "BlockPermutation", "BlockState", "ItemStack",
    "Entity", "EntityInventoryComponent", "Player", "Container",
    "ItemEnchants", "Enchantment", "EnchantmentType",
    "Vector3", "BoundingBox", "Location",
    "MinecraftEntityTypes", "MinecraftBlockTypes", "MinecraftItemTypes",
    "DynamicPropertiesDefinition", "PropertyDefinition",
    "PropertyRegistry", "BoolSignProperty", "IntSignProperty",
    "MessageChannel", "RawMessage", "RawMessageWithArgs",
    "Scoreboard", "Objective", "ScoreboardIdentity",
    "BossBar", "BossBarDisplay",
    # Common method patterns (valid when called on correct object)
    ".sendMessage", ".getComponent", ".getEntities", ".spawnEntity",
    ".teleport", ".addCooldown", ".addTag", ".removeTag",
    ".dimension", ".location", ".typeId", ".name",
    ".runCommand", ".getAllPlayers", ".getDimension",
    ".setProperty", ".getProperty",
    ".setDynamicProperty", ".getDynamicProperty", ".getBlock",
    ".playSound", ".getEntitiesWithTag",
    ".subscribe", ".unsubscribe",
    ".tick", ".run", ".runInterval", ".runTimeout",
    # Events (afterEvents/beforeEvents properties)
    "worldInitialize", "tick", "playerInteractWithBlock",
    "playerBreakBlock", "blockPlace", "blockBreak",
    "entityDie", "entityHealthChanged", "playerSpawn",
    "itemUse", "itemUseOn", "beforeExplosion", "afterExplosion",
    "projectileHit", "entityHitEntity", "entityHitBlock",
    "playerDimensionChange", "entityHealthChanged",
}

# NEVER valid — these are the top hallucinated APIs reported in issue #1678
FORBIDDEN_API_PATTERNS = [
    (r"\bServerPlayerAPI\b", "ServerPlayerAPI — fake class, use Player from @minecraft/server"),
    (r"\bServerPlayer\b", "ServerPlayer — fake class, use Player from @minecraft/server"),
    (r"\bPlayerAPI\b", "PlayerAPI — fake class, does not exist in Bedrock"),
    (r"\bWorldEvent\b", "WorldEvent — fake class, use world.afterEvents/beforeEvents"),
    (r"\bBlockEntityAPI\b", "BlockEntityAPI — fake class, use world.getBlock and Block properties"),
    (r"\bEntityPlayerAPI\b", "EntityPlayerAPI — fake class, does not exist in Bedrock"),
    (r"\bWorldAPI\b", "WorldAPI — fake class, use world directly"),
    (r"\bmodEventBus\b", "modEventBus — Java mod loader pattern, does not exist in Bedrock"),
    (r'\brequire\(["\']@minecraft/server["\']\)', "CommonJS require — Bedrock uses ES6 import"),
    (r"\bregisterMod\(", "registerMod — Java mod loader pattern, use manifest.json"),
    (r"\bdefineMod\(", "defineMod — non-existent Bedrock API"),
    (r"\.createLightningBolt\(", "createLightningBolt — non-existent method, use dimension.spawnEntity"),
    (r"\.spawnLightning\(", "spawnLightning — non-existent method"),
    (r"\.registerEvent\(", "registerEvent — wrong API, use .subscribe() on afterEvents/beforeEvents"),
    (r"\.registerServerEvent\(", "registerServerEvent — non-existent API"),
    (r"\.onServerStart\(", "onServerStart — non-existent hook, use WorldInitializeEvent"),
    (r"\.onServerStop\(", "onServerStop — non-existent hook"),
    (r"event\.level\.", "event.level — non-existent property chain, use event.source or event.dimension"),
    (r"server\.getWorld\(", "server.getWorld — non-existent method, use world.getDimension"),
    (r"getServer\(\)", "getServer — non-existent singleton, use system or world directly"),
    (r"Server\.getInstance\(\)", "Server.getInstance — Java singleton pattern, does not exist in Bedrock"),
    (r"\.getTileEntity\(\).*?\.getInventory\(", "getTileEntity().getInventory — chained method that doesn't exist"),
    (r"world\.setBlock\(.*?\.getPosition\(", "world.setBlock with getPosition — non-existent API"),
    # Semantic wrong APIs (wrong namespace but plausible)
    (r"\bLightningBoltEvent\b", "LightningBoltEvent — non-existent event class"),
    (r"\bPlayerEvent\b(?!\.)", "PlayerEvent — ambiguous class, use PlayerAfterEvents or PlayerBeforeEvents"),
    (r"from\s+['\"]minecraft/server['\"]", "Wrong import path — must be '@minecraft/server' (with @)"),
    (r"\.register\(\s*\w+\s*,\s*\w+\s*\)", "Old .register() pattern — use .subscribe() instead"),
]


@dataclass
class HallucinationMatch:
    """A single hallucination match found in code."""
    pattern_id: str
    matched_text: str
    description: str
    line_number: int
    severity: str  # "hard", "semantic", "lingering"
    penalty: float


@dataclass
class ValidationResult:
    """Result of hallucination validation on generated code."""
    is_valid: bool
    hallucinated_apis: List[str]
    valid_apis_found: List[str]
    hallucination_rate: float
    matches: List[HallucinationMatch] = field(default_factory=list)
    regeneration_signal: str = ""
    hard_hallucination_count: int = 0
    semantic_hallucination_count: int = 0


class MMSDHallucinationValidator:
    """
    Post-generation hallucination validator for MMSD Bedrock outputs.

    Scans generated JavaScript for:
    1. Known hallucinated API patterns (from HallucinationCatalog)
    2. Forbidden API patterns listed in issue #1678
    3. Semantic violations (valid syntax, wrong API)

    Provides a structured ValidationResult that can be used to:
    - Reject and regenerate outputs with hard hallucinations
    - Flag outputs with semantic hallucinations for review
    """

    def __init__(self, strict: bool = True):
        """
        Initialize validator.

        Args:
            strict: If True, any hard hallucination makes is_valid=False.
                   If False, only 2+ hard hallucinations make is_valid=False.
        """
        self.strict = strict
        self.catalog = HALLUCINATION_CATALOG

    def validate(self, bedrock_script: str) -> ValidationResult:
        """
        Validate a generated Bedrock script for hallucinations.

        Args:
            bedrock_script: The JavaScript/code portion of the generated Bedrock output

        Returns:
            ValidationResult with hallucination details
        """
        if not bedrock_script or not bedrock_script.strip():
            return ValidationResult(
                is_valid=False,
                hallucinated_apis=[],
                valid_apis_found=[],
                hallucination_rate=1.0,
                regeneration_signal="EMPTY_OUTPUT",
            )

        matches: List[HallucinationMatch] = []
        hallucinated_apis: List[str] = []

        lines = bedrock_script.split('\n')

        for pattern_str, description in FORBIDDEN_API_PATTERNS:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            for line_num, line in enumerate(lines, 1):
                line_matches = pattern.finditer(line)
                for match in line_matches:
                    matched_text = match.group()
                    hallucinated_apis.append(matched_text)

                    # Determine severity
                    if any(x in matched_text.lower() for x in [
                        "serverplayerapi", "serverplayer", "playerapi",
                        "worldevent", "blockentityapi", "entityplayerapi",
                        "worldapi", "modeventbus", "registermod", "definemod",
                        "getserver", "server.getinstance", "createserver",
                    ]):
                        severity = "hard"
                    elif any(x in matched_text.lower() for x in [
                        "lightningboltevent", "playerevent", "require('@minecraft/server')",
                        ".register(", "minecraft/server",
                    ]):
                        severity = "semantic" if "@minecraft/server" not in matched_text else "lingering"
                    else:
                        severity = "hard"

                    matches.append(HallucinationMatch(
                        pattern_id=matched_text,
                        matched_text=matched_text,
                        description=description,
                        line_number=line_num,
                        severity=severity,
                        penalty=-0.3 if severity == "hard" else -0.15,
                    ))

        # Also run the catalog's own detection
        catalog_findings = self.catalog.detect(bedrock_script)
        for finding in catalog_findings:
            if not any(m.matched_text == finding.matched_text for m in matches):
                hallucinated_apis.append(finding.matched_text)
                matches.append(HallucinationMatch(
                    pattern_id=finding.pattern_id,
                    matched_text=finding.matched_text,
                    description="",  # already has description in catalog
                    line_number=finding.line_number,
                    severity=finding.hallucination_type.value,
                    penalty=finding.penalty,
                ))

        # Extract valid APIs found (for reporting)
        valid_apis = self._extract_valid_apis(bedrock_script)

        # Deduplicate hallucinated_apis
        hallucinated_apis = list(dict.fromkeys(hallucinated_apis))

        hard_count = sum(1 for m in matches if m.severity == "hard")
        semantic_count = sum(1 for m in matches if m.severity in ("semantic", "lingering"))

        # Determine validity
        if self.strict:
            is_valid = hard_count == 0
        else:
            is_valid = hard_count == 0 or (hard_count == 1 and semantic_count == 0)

        # Build regeneration signal
        if hard_count > 0:
            signal = (
                f"HARD_HALLUCINATION: {hard_count} hallucinated API(s) detected. "
                f"REJECT AND REGENERATE. "
                f"Do NOT use: {', '.join(hallucinated_apis[:5])}. "
                f"Use only valid Bedrock Script APIs: world.afterEvents, world.beforeEvents, "
                f"system.runInterval, player.sendMessage, dimension.spawnEntity, etc."
            )
        elif semantic_count > 0:
            signal = (
                f"SEMANTIC_HALLUCINATION: {semantic_count} suspicious API reference(s). "
                f"Review carefully: {', '.join(hallucinated_apis[:5])}"
            )
        else:
            signal = ""

        hallucination_rate = len(hallucinated_apis) / max(1, len(valid_apis) + len(hallucinated_apis))

        return ValidationResult(
            is_valid=is_valid,
            hallucinated_apis=hallucinated_apis,
            valid_apis_found=valid_apis,
            hallucination_rate=hallucination_rate,
            matches=matches,
            regeneration_signal=signal,
            hard_hallucination_count=hard_count,
            semantic_hallucination_count=semantic_count,
        )

    def _extract_valid_apis(self, script: str) -> List[str]:
        """Extract known valid Bedrock API calls from script."""
        valid_found = []
        for api in VALID_BEDROCK_APIS:
            if api.startswith("."):
                # Method pattern — look for it in context
                if api in script:
                    valid_found.append(api)
            else:
                # Class/global — check if referenced
                pattern = re.compile(rf"\b{re.escape(api)}\b")
                if pattern.search(script):
                    valid_found.append(api)
        return list(dict.fromkeys(valid_found))

    def validate_with_retry(
        self,
        bedrock_script: str,
        max_retries: int = 2,
    ) -> ValidationResult:
        """
        Validate and if invalid, annotate with retry guidance.

        For use in the premium_client convert loop — returns validation
        result with enough signal to determine if regeneration is needed.
        """
        result = self.validate(bedrock_script)

        if result.is_valid:
            return result

        # Add context about what valid looks like
        if result.hard_hallucination_count > 0:
            result.regeneration_signal += (
                "\n\nValid Bedrock Script API reference examples:\n"
                "  import { world, system, player } from '@minecraft/server';\n"
                "  world.afterEvents.blockPlace.subscribe(handler);\n"
                "  system.runInterval(() => { ... }, 20);\n"
                "  player.sendMessage('Hello');\n"
                "  dimension.spawnEntity('minecraft:cow', location);\n"
            )

        return result

    def get_hallucination_summary(self, result: ValidationResult) -> str:
        """Human-readable summary of validation result."""
        if result.is_valid:
            return (
                f"✓ No hallucinations detected "
                f"(found {len(result.valid_apis_found)} valid API references)"
            )

        lines = [
            f"✗ Hallucination detected:",
            f"  - Hard hallucinations: {result.hard_hallucination_count}",
            f"  - Semantic/lingering: {result.semantic_hallucination_count}",
            f"  - Hallucinated APIs: {', '.join(result.hallucinated_apis[:5])}",
        ]
        if result.matches:
            lines.append("  Line-by-line:")
            for m in result.matches[:5]:
                lines.append(f"    Line {m.line_number}: {m.matched_text} — {m.description}")

        return "\n".join(lines)


def create_validator(strict: bool = True) -> MMSDHallucinationValidator:
    """Factory function to create a validator."""
    return MMSDHallucinationValidator(strict=strict)


# ── CLI for testing ────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Validate Bedrock script for hallucinations")
    parser.add_argument("--script", "-s", help="Bedrock script to validate")
    parser.add_argument("--file", "-f", type=Path, help="File containing Bedrock script")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True,
                        help="Strict mode: any hard hallucination fails validation")
    args = parser.parse_args()

    if not args.script and not args.file:
        print("Error: provide --script or --file", file=sys.stderr)
        sys.exit(1)

    script = args.script
    if args.file:
        script = args.file.read_text()

    validator = MMSDHallucinationValidator(strict=args.strict)
    result = validator.validate(script)

    print(result.regeneration_signal if result.regeneration_signal else result.get_hallucination_summary(result))
    print(f"\nValid: {result.is_valid}")
    print(f"Hallucination rate: {result.hallucination_rate:.1%}")
    print(f"Hallucinated APIs: {result.hallucinated_apis}")

    sys.exit(0 if result.is_valid else 1)
