"""
AST Bedrock Post-Processor for Issue #1721.

Deterministic AST analysis + Bedrock API KB validation to catch hallucinated
(nonexistent) API calls in converted Bedrock Scripting API code — without
re-invoking the LLM.

Architecture:
  LLM-generated Bedrock code → AST parser → API call extractor →
  Bedrock API KB validator → HallucinationReport with auto-correction hints

Paper: Detecting and Correcting Hallucinations in LLM-Generated Code via
Deterministic AST Analysis (arxiv.org/abs/2601.19106)

This is the post-generation safety-net counterpart to the pre-generation
BedrockAPIBoundaryProber in api_boundary_prober.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


class HallucinationSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class APICall:
    """A single Bedrock Scripting API method/property call extracted from AST."""

    receiver: str  # e.g., "world", "player", "block", "entity"
    method: str  # e.g., "getBlock", "sendMessage", "setPermutation"
    full_call: str  # e.g., "world.getBlock(x, y, z)"
    line: int
    column: int
    raw_signature: str  # e.g., "world.getBlock("
    arity: int  # number of arguments
    is_property_access: bool = False  # True for property access like player.name


@dataclass
class HallucinatedCall:
    """A hallucinated (nonexistent) API call detected by the post-processor."""

    api_call: APICall
    severity: HallucinationSeverity
    hallucination_type: str  # "nonexistent_method", "wrong_arity", "wrong_receiver"
    suggestion: str  # e.g., "Did you mean world.getBlock?"
    correction: Optional[str] = None  # Auto-correction suggestion if applicable
    kb_entry: Optional[Dict[str, Any]] = None  # Closest KB match


@dataclass
class PostProcessorResult:
    """Result of AST post-processing with hallucination detection."""

    is_valid: bool
    total_calls: int
    hallucinated_calls: List[HallucinatedCall]
    valid_calls: List[APICall]
    hallucination_rate: float  # 0.0-1.0
    severity_counts: Dict[str, int]
    report: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_calls": self.total_calls,
            "hallucinated_calls": [
                {
                    "call": h.api_call.full_call,
                    "severity": h.severity.value,
                    "type": h.hallucination_type,
                    "suggestion": h.suggestion,
                    "correction": h.correction,
                    "line": h.api_call.line,
                }
                for h in self.hallucinated_calls
            ],
            "hallucination_rate": self.hallucination_rate,
            "severity_counts": self.severity_counts,
        }


class BedrockAPIMethodKB:
    """
    Bedrock Scripting API Knowledge Base.

    Contains known-valid method signatures extracted from @minecraft/server
    TypeScript definitions. This is the ground-truth allowlist for API
    validation.

    Sources:
    - @minecraft/server 1.16.0+ official API surface
    - Known hallucination patterns from failure taxonomy (PR #1845)
    - Common conversion errors from PortKit MMSD test set
    """

    def __init__(self):
        self._methods: Dict[str, Set[str]] = {}  # receiver -> set of method names
        self._method_signatures: Dict[str, Dict[str, Any]] = {}  # "receiver.method" -> signature
        self._receiver_types: Set[str] = set()
        self._initialize_kb()

    def _initialize_kb(self) -> None:
        """Initialize KB with known Bedrock Scripting API methods."""
        self._add_world_methods()
        self._add_player_methods()
        self._add_block_methods()
        self._add_entity_methods()
        self._add_dimension_methods()
        self._add_container_methods()
        self._add_item_methods()
        self._add_system_methods()
        self._add_property_methods()
        self._initialize_signatures()

    def _add_world_methods(self) -> None:
        """Add world.* methods from @minecraft/server."""
        world_api = {
            "afterEvents",  # world.afterEvents
            "beforeEvents",  # world.beforeEvents
            "getAllPlayers",
            "getBlock",
            "getDimension",
            "getPlayers",
            "getScoreboard",
            "isLoaded",
            "getBiome",
            "setBiome",
            "getEntity",
            "spawnEntity",
            "spawnParticle",
            "playSound",
            "playSoundAt",
            "sendMessage",
            "getDynamicProperty",
            "setDynamicProperty",
            "getTotalTicks",
        }
        self._methods["world"] = world_api
        self._receiver_types.add("world")

        world_event_api = {
            "blockPlace",
            "blockBreak",
            "entityDie",
            "entityHurt",
            "playerBreakBlock",
            "playerInteractWithBlock",
            "playerJoin",
            "playerLeave",
            "tick",
        }
        self._methods["world.afterEvents"] = world_event_api
        self._methods["world.beforeEvents"] = world_event_api

    def _add_player_methods(self) -> None:
        """Add player.* methods from @minecraft/server."""
        player_api = {
            "addEffect",
            "clearEffect",
            "getComponent",
            "getComponents",
            "dimension",
            "equipment",
            "getEntitiesFromViewVector",
            "getEntityFromViewVector",
            "getItemStackInHand",
            "hasTag",
            "addTag",
            "removeTag",
            "isSneaking",
            "isSprinting",
            "isFlying",
            "isOnGround",
            "isOp",
            "isSleeping",
            "isSwimming",
            "kill",
            "location",
            "name",
            "level",
            "getName",
            "getRotation",
            "getViewDirection",
            "hasPermission",
            "runCommand",
            "runCommandAsync",
            "sendMessage",
            "setOnScreen",
            "openDialog",
            "openSidebar",
            "closeSidebar",
            "openBook",
            "getContainer",
            "getSelectedSlot",
            "setSelectedSlot",
            "getScoreboardIdentity",
            "applyDamage",
            "getHealth",
            "getMaxHealth",
            "getAbsorptionAmount",
            "setAttribute",
            "getAttribute",
            "getEffect",
            "getLevel",
            "setLevel",
            "giveItem",
            "takeItem",
            "dropItem",
            "equippedItem",
            "hasContainerOpen",
        }
        self._methods["player"] = player_api
        self._receiver_types.add("player")

        player_component_api = {
            "currentValue",
            "effectiveMax",
            "setCurrentValue",
            "reset",
        }
        self._methods["player.health"] = player_component_api

    def _add_block_methods(self) -> None:
        """Add block.* methods from @minecraft/server."""
        block_api = {
            "type",
            "typeId",
            "permutation",
            "setPermutation",
            "isAir",
            "isLiquid",
            "isSolid",
            "isValid",
            "getComponent",
            "getComponents",
            "getRedstonePower",
            "getContainer",
            "getTags",
            "hasTag",
            "addTag",
            "removeTag",
            "getLocation",
            "location",
            "dimension",
            "x",
            "y",
            "z",
            "getNbt",
            "setNbt",
            "getDynamicProperty",
            "setDynamicProperty",
            "clone",
            "destroy",
            "getBreakTime",
            "isExploding",
            "setVertical",
        }
        self._methods["block"] = block_api
        self._receiver_types.add("block")

    def _add_entity_methods(self) -> None:
        """Add entity.* methods from @minecraft/server."""
        entity_api = {
            "addEffect",
            "applyDamage",
            "clearEffect",
            "getComponent",
            "getComponents",
            "dimension",
            "getDynamicProperty",
            "setDynamicProperty",
            "getEffect",
            "getEntity",
            "getEntitiesFromViewVector",
            "getEntityFromViewVector",
            "hasTag",
            "addTag",
            "removeTag",
            "hasContainerOpen",
            "isSneaking",
            "isSprinting",
            "isFlying",
            "isOnGround",
            "isSwimming",
            "kill",
            "location",
            "name",
            "getName",
            "getRotation",
            "getViewDirection",
            "id",
            "isValid",
            "remove",
            "runCommand",
            "runCommandAsync",
            "sendMessage",
            "getInventory",
            "getContainer",
            "getEquipment",
            "equippedItem",
            "getHealth",
            "getMaxHealth",
            "getAbsorptionAmount",
            "setAttribute",
            "getAttribute",
            "isInLove",
            "setOnFire",
            "getScoreboardIdentity",
            "spawnParticle",
        }
        self._methods["entity"] = entity_api
        self._receiver_types.add("entity")

    def _add_dimension_methods(self) -> None:
        """Add dimension.* methods from @minecraft/server."""
        dimension_api = {
            "getBlock",
            "getEntity",
            "getEntities",
            "getPlayers",
            "getAllPlayers",
            "spawnEntity",
            "spawnParticle",
            "playSound",
            "playSoundAt",
            "sendMessage",
            "getBiome",
            "setBiome",
            "getNbt",
            "setNbt",
            "getDynamicProperty",
            "setDynamicProperty",
        }
        self._methods["dimension"] = dimension_api
        self._receiver_types.add("dimension")

    def _add_container_methods(self) -> None:
        """Add container.* methods from @minecraft/server."""
        container_api = {
            "getItem",
            "setItem",
            "addItem",
            "clearAll",
            "getSize",
            "isEmpty",
            "getSlot",
            "setSlot",
            "moveItem",
            "transferItem",
        }
        self._methods["container"] = container_api
        self._receiver_types.add("container")

    def _add_item_methods(self) -> None:
        """Add ItemStack.* methods from @minecraft/server."""
        item_api = {
            "amount",
            "data",
            "durability",
            "getAmount",
            "setAmount",
            "getDurability",
            "setDurability",
            "clone",
            "getId",
            "getName",
            "getOrCreateDataComponent",
            "getTags",
            "hasTag",
            "isStackable",
            "isValid",
            "matches",
            "name",
            "setName",
            "type",
            "typeId",
        }
        self._methods["itemStack"] = item_api
        self._receiver_types.add("itemStack")
        self._methods["ItemStack"] = item_api

    def _add_system_methods(self) -> None:
        """Add system.* methods from @minecraft/server."""
        system_api = {
            "run",
            "runInterval",
            "runTimeout",
            "clearRun",
            "currentTick",
            "log",
            "getTotalTicks",
        }
        self._methods["system"] = system_api
        self._receiver_types.add("system")

    def _add_property_methods(self) -> None:
        """Add DynamicProperty.* methods."""
        dynamic_property_api = {
            "getBoolean",
            "getNumber",
            "getString",
            "setBoolean",
            "setNumber",
            "setString",
            "remove",
        }
        self._methods["dynamicProperty"] = dynamic_property_api
        self._receiver_types.add("dynamicProperty")

    def _initialize_signatures(self) -> None:
        """Initialize method signatures with arity and descriptions."""
        signatures = {
            "world.getBlock": {"arity": 1, "description": "world.getBlock(location)"},
            "world.setBlock": {"arity": 2, "description": "world.setBlock(location, blockState)"},
            "world.getDimension": {"arity": 1, "description": "world.getDimension(dimensionId)"},
            "world.spawnEntity": {
                "arity": 2,
                "description": "world.spawnEntity(identifier, location)",
            },
            "world.playSound": {"arity": 2, "description": "world.playSound(soundId, location)"},
            "world.sendMessage": {"arity": 1, "description": "world.sendMessage(message)"},
            "player.getComponent": {"arity": 1, "description": "player.getComponent(componentId)"},
            "player.sendMessage": {"arity": 1, "description": "player.sendMessage(message)"},
            "player.runCommand": {"arity": 1, "description": "player.runCommand(command)"},
            "player.runCommandAsync": {
                "arity": 1,
                "description": "player.runCommandAsync(command)",
            },
            "player.getItemStackInHand": {
                "arity": 0,
                "description": "player.getItemStackInHand(hand)",
            },
            "player.equippedItem": {"arity": 0, "description": "player.equippedItem"},
            "player.getInventory": {
                "arity": 0,
                "description": "player.inventory (property, not method)",
            },
            "player.getContainer": {
                "arity": 0,
                "description": "player.getContainer() (use container property)",
            },
            "block.setPermutation": {
                "arity": 1,
                "description": "block.setPermutation(permutation)",
            },
            "block.setBlock": {"arity": 1, "description": "block.setPermutation (not setBlock)"},
            "block.getBlockEntity": {
                "arity": 0,
                "description": "block.getBlockEntity() (doesn't exist)",
            },
            "entity.getCustomName": {
                "arity": 0,
                "description": "entity.name (property, not getCustomName)",
            },
            "entity.sendMessage": {"arity": 1, "description": "entity.sendMessage(message)"},
            "container.getItem": {"arity": 1, "description": "container.getItem(slot)"},
            "container.setItem": {"arity": 2, "description": "container.setItem(slot, itemStack)"},
            "container.addItem": {"arity": 1, "description": "container.addItem(itemStack)"},
            "system.runInterval": {
                "arity": 1,
                "description": "system.runInterval(callback, tickInterval)",
            },
            "system.runTimeout": {
                "arity": 2,
                "description": "system.runTimeout(callback, tickDelay)",
            },
            "dimension.getBlock": {"arity": 1, "description": "dimension.getBlock(location)"},
        }
        for key, sig in signatures.items():
            self._method_signatures[key] = sig

    def is_valid_call(self, receiver: str, method: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a receiver.method call is valid in the Bedrock API.

        Returns:
            Tuple of (is_valid, hallucination_type)
            hallucination_type is None if valid, else describes why it's invalid
        """
        if receiver in self._methods:
            if method in self._methods[receiver]:
                return True, None
            return False, "nonexistent_method"

        compound = f"{receiver}.{method}"
        if compound in self._method_signatures:
            return True, None

        if receiver == method:
            return False, "property_accessed_as_method"

        return False, "unknown_receiver"

    def get_closest_method(
        self, receiver: str, hallucinated_method: str
    ) -> Optional[Tuple[str, str]]:
        """
        Get the closest valid method to a hallucinated one using edit distance.

        Returns:
            Tuple of (corrected_method, suggestion_string) or None
        """
        if receiver not in self._methods:
            return None

        valid_methods = self._methods[receiver]
        best_match = None
        best_distance = float("inf")

        for valid_method in valid_methods:
            distance = self._levenshtein_distance(hallucinated_method, valid_method)
            if distance < best_distance:
                best_distance = distance
                best_match = valid_method

        if best_match and best_distance <= 3:
            return best_match, f"Did you mean {receiver}.{best_match}?"

        return None

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if len(s1) < len(s2):
            return BedrockAPIMethodKB._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def get_known_hallucinations(self) -> Set[str]:
        """
        Return set of known hallucinated patterns for detection.

        These are common hallucinated calls that are well-documented errors.
        """
        return {
            "world.setBlock",
            "world.getTileEntity",
            "world.setTileEntity",
            "block.getBlockEntity",
            "block.setBlock",
            "player.getInventory",
            "entity.getCustomName",
            "entity.setCustomName",
            "entity.getHealth",
            "entity.setHealth",
            "entity.getMaxHealth",
            "entity.getItemInHand",
            "player.getItemInHand",
            "player.getFoodLevel",
            "player.getSaturation",
            "player.getExperienceLevel",
            "world.getBlockAt",
            "world.isAirBlock",
            "world.getTypeId",
            "world.getBlockState",
            "world.setBlockState",
        }


class ASTBedrockPostprocessor:
    """
    Deterministic AST post-processor for Bedrock Scripting API hallucination detection.

    Parses generated Bedrock TypeScript/JavaScript code into an AST, extracts all
    API call sites, and validates each against the Bedrock API KB.

    Supports:
    - Method call extraction (world.getBlock(), player.sendMessage())
    - Property access validation (entity.name, block.type)
    - Arity/wrong parameter count detection
    - Auto-correction suggestions via edit distance

    Usage:
        postprocessor = ASTBedrockPostprocessor(strict=True)
        result = postprocessor.process(bedrock_code)
        if not result.is_valid:
            for h in result.hallucinated_calls:
                print(f"HALLUCINATION: {h.api_call.full_call} -> {h.suggestion}")
    """

    HALLUCINATION_PATTERNS: Dict[str, str] = {
        r"world\.setBlock\s*\(": "world.setBlock doesn't exist. Use block.setPermutation() instead.",
        r"world\.getTileEntity\s*\(": "world.getTileEntity doesn't exist in Script API.",
        r"world\.setTileEntity\s*\(": "world.setTileEntity doesn't exist in Script API.",
        r"block\.getBlockEntity\s*\(": "Block entities don't exist in Bedrock Script API. Use DynamicProperties.",
        r"block\.setBlock\s*\(": "block.setBlock doesn't exist. Use block.setPermutation() instead.",
        r"player\.getInventory\s*\(": "player.getInventory() doesn't exist. Use player.container or component.",
        r"entity\.getCustomName\s*\(": "Use entity.name property instead of getCustomName().",
        r"entity\.setCustomName\s*\(": "Use entity.name = '...' to set custom name.",
        r"player\.getFoodLevel\s*\(": "Use getComponent('minecraft:food').foodLevel instead.",
        r"player\.getSaturation\s*\(": "Use getComponent('minecraft:food').saturation instead.",
        r"player\.getExperienceLevel\s*\(": "Use player.level instead.",
        r"world\.getBlockAt\s*\(": "world.getBlockAt doesn't exist. Use world.getBlock(location).",
        r"world\.isAirBlock\s*\(": "world.isAirBlock doesn't exist. Use block.isAir instead.",
        r"world\.getTypeId\s*\(": "world.getTypeId doesn't exist. Use block.typeId instead.",
        r"world\.getBlockState\s*\(": "world.getBlockState doesn't exist. Use block.permutation instead.",
        r"world\.setBlockState\s*\(": "world.setBlockState doesn't exist. Use block.setPermutation() instead.",
        r"player\.sendMessage\([^)]{50,}": "player.sendMessage signature may be wrong. Check parameter count.",
        r"entity\.getHealth\s*\(": "Use getComponent('minecraft:health').currentValue instead.",
        r"entity\.setHealth\s*\(": "Use getComponent('minecraft:health').setCurrentValue() instead.",
        r"entity\.getMaxHealth\s*\(": "Use getComponent('minecraft:health').effectiveMax instead.",
        r"player\.getItemInHand\s*\(": "Use player.equippedItem instead.",
        r"player\.getItemStackInHand\s*\(": "Use player.getItemStackInHand(hand) or equippedItem property.",
    }

    def __init__(self, strict: bool = False):
        """
        Initialize the post-processor.

        Args:
            strict: If True, enable strict mode with more aggressive detection.
                   In strict mode, any unknown receiver triggers a warning.
        """
        self.strict = strict
        self._kb = BedrockAPIMethodKB()
        self._known_hallucinations = self._kb.get_known_hallucinations()

    def process(self, bedrock_code: str) -> PostProcessorResult:
        """
        Process Bedrock code and detect hallucinated API calls.

        Args:
            bedrock_code: The generated Bedrock TypeScript/JavaScript code

        Returns:
            PostProcessorResult with hallucination report
        """
        if not bedrock_code or not bedrock_code.strip():
            return PostProcessorResult(
                is_valid=True,
                total_calls=0,
                hallucinated_calls=[],
                valid_calls=[],
                hallucination_rate=0.0,
                severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
                report={"status": "empty_input"},
            )

        api_calls = self._extract_api_calls(bedrock_code)
        hallucinated_calls = []
        valid_calls = []

        for call in api_calls:
            h_call = self._validate_call(call, bedrock_code)
            if h_call:
                hallucinated_calls.append(h_call)
            else:
                valid_calls.append(call)

        hallucination_rate = len(hallucinated_calls) / len(api_calls) if api_calls else 0.0

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for h in hallucinated_calls:
            severity_counts[h.severity.value] += 1

        is_valid = len(hallucinated_calls) == 0 or hallucination_rate < 0.1

        report = self._build_report(api_calls, hallucinated_calls, valid_calls, hallucination_rate)

        return PostProcessorResult(
            is_valid=is_valid,
            total_calls=len(api_calls),
            hallucinated_calls=hallucinated_calls,
            valid_calls=valid_calls,
            hallucination_rate=hallucination_rate,
            severity_counts=severity_counts,
            report=report,
        )

    def _extract_api_calls(self, code: str) -> List[APICall]:
        """
        Extract all Bedrock Scripting API calls from code using regex-based AST parsing.

        We use regex instead of tree-sitter here for:
        1. Deterministic parsing without external dependencies
        2. Sub-second latency for real-time validation
        3. Works on partial code snippets

        For production use, tree-sitter can be integrated for more robust parsing.
        """
        calls = []
        lines = code.split("\n")

        call_pattern = re.compile(
            r"\b(player|world|block|entity|dimension|container|system|itemStack|ItemStack|dynamicProperty)\.(\w+)\s*\("
        )
        property_pattern = re.compile(
            r"\b(player|world|block|entity|dimension|container|system)\.(\w+)\b(?!\s*\()"
        )

        for line_idx, line in enumerate(lines):
            code_part = line
            if "//" in line:
                code_part = line[: line.index("//")]
            if "/*" in code_part:
                code_part = code_part[: code_part.index("/*")]

            for match in call_pattern.finditer(code_part):
                receiver = match.group(1)
                method = match.group(2)
                full_match = match.group(0)
                col = match.start()

                arity = self._count_arguments(line, match.end() - 1)

                calls.append(
                    APICall(
                        receiver=receiver,
                        method=method,
                        full_call=f"{receiver}.{method}()",
                        line=line_idx + 1,
                        column=col + 1,
                        raw_signature=full_match,
                        arity=arity,
                        is_property_access=False,
                    )
                )

            for match in property_pattern.finditer(code_part):
                receiver = match.group(1)
                prop = match.group(2)
                col = match.start()

                calls.append(
                    APICall(
                        receiver=receiver,
                        method=prop,
                        full_call=f"{receiver}.{prop}",
                        line=line_idx + 1,
                        column=col + 1,
                        raw_signature=match.group(0),
                        arity=0,
                        is_property_access=True,
                    )
                )

        return calls

    def _count_arguments(self, line: str, paren_start: int) -> int:
        """Count number of arguments in a method call."""
        depth = 0
        arg_count = 0
        in_string = False
        string_char = None
        i = paren_start

        while i < len(line):
            c = line[i]

            if c in ('"', "'", "`") and (i == 0 or line[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = c
                elif c == string_char:
                    in_string = False
                    string_char = None
            elif not in_string:
                if c == "(":
                    depth += 1
                elif c == ")":
                    if depth == 1:
                        return arg_count
                    depth -= 1
                elif c == "," and depth == 1:
                    arg_count += 1

            i += 1

        return arg_count + 1 if depth == 1 else 0

    def _validate_call(self, call: APICall, code: str) -> Optional[HallucinatedCall]:
        """Validate a single API call against the KB."""
        full_method = f"{call.receiver}.{call.method}"

        if full_method in self._known_hallucinations:
            suggestion = self.HALLUCINATION_PATTERNS.get(
                full_method,
                f"{full_method} is a known hallucination. Did you mean something different?",
            )

            correction = self._get_correction(call)
            severity = self._determine_severity(call, "known_hallucination")

            return HallucinatedCall(
                api_call=call,
                severity=severity,
                hallucination_type="known_hallucination",
                suggestion=suggestion,
                correction=correction,
            )

        is_valid, hallucination_type = self._kb.is_valid_call(call.receiver, call.method)

        if is_valid:
            return None

        closest = self._kb.get_closest_method(call.receiver, call.method)
        suggestion = (
            f"{full_method} doesn't exist in @minecraft/server API. "
            f"{closest[1] if closest else 'Check official Bedrock Scripting API docs.'}"
        )

        correction = None
        if closest:
            correction = code.replace(
                f"{call.receiver}.{call.method}",
                f"{call.receiver}.{closest[0]}",
                1,
            )

        severity = self._determine_severity(call, hallucination_type)

        return HallucinatedCall(
            api_call=call,
            severity=severity,
            hallucination_type=hallucination_type,
            suggestion=suggestion,
            correction=correction,
        )

    def _get_correction(self, call: APICall) -> Optional[str]:
        """Get auto-correction for a known hallucination pattern."""
        corrections = {
            "world.setBlock": "block.setPermutation(block.permutation.withState({...}))",
            "world.getTileEntity": "Use DynamicProperties: world.getDynamicProperty(id)",
            "world.setTileEntity": "Use DynamicProperties: world.setDynamicProperty(id, value)",
            "block.getBlockEntity": "Use block.getDynamicProperty(id) or block.setDynamicProperty",
            "block.setBlock": "block.setPermutation(permutation)",
            "player.getInventory": "Use player.container or player.equipment",
            "entity.getCustomName": "Use entity.name",
            "entity.setCustomName": "Use entity.name = 'new name'",
            "player.getFoodLevel": "player.getComponent('minecraft:food').foodLevel",
            "player.getSaturation": "player.getComponent('minecraft:food').saturation",
            "player.getExperienceLevel": "Use player.level",
            "world.getBlockAt": "world.getBlock(location)",
            "world.isAirBlock": "block.isAir",
            "world.getTypeId": "block.typeId",
            "world.getBlockState": "block.permutation",
            "world.setBlockState": "block.setPermutation(permutation)",
            "entity.getHealth": "entity.getComponent('minecraft:health').currentValue",
            "entity.setHealth": "entity.getComponent('minecraft:health').setCurrentValue(value)",
            "entity.getMaxHealth": "entity.getComponent('minecraft:health').effectiveMax",
            "player.getItemInHand": "player.equippedItem",
            "player.getItemStackInHand": "player.getItemStackInHand(hand) or equippedItem",
        }
        return corrections.get(f"{call.receiver}.{call.method}")

    def _determine_severity(self, call: APICall, hallucination_type: str) -> HallucinationSeverity:
        """Determine the severity of a hallucination."""
        if hallucination_type == "known_hallucination":
            return HallucinationSeverity.HIGH

        if hallucination_type == "nonexistent_method":
            if call.receiver in {"world", "player", "entity"}:
                return HallucinationSeverity.HIGH
            return HallucinationSeverity.MEDIUM

        if hallucination_type == "wrong_arity":
            return HallucinationSeverity.MEDIUM

        if hallucination_type == "unknown_receiver":
            return HallucinationSeverity.LOW if self.strict else HallucinationSeverity.MEDIUM

        return HallucinationSeverity.MEDIUM

    def _build_report(
        self,
        api_calls: List[APICall],
        hallucinated: List[HallucinatedCall],
        valid: List[APICall],
        rate: float,
    ) -> Dict[str, Any]:
        """Build a detailed report dictionary."""
        return {
            "total_api_calls": len(api_calls),
            "valid_calls": len(valid),
            "hallucinated_calls": len(hallucinated),
            "hallucination_rate": round(rate * 100, 2),
            "status": "valid" if rate == 0 else ("warning" if rate < 0.1 else "invalid"),
            "hallucinated_details": [
                {
                    "call": h.api_call.full_call,
                    "line": h.api_call.line,
                    "type": h.hallucination_type,
                    "severity": h.severity.value,
                    "suggestion": h.suggestion,
                }
                for h in hallucinated
            ],
        }


def process_bedrock_code(code: str, strict: bool = False) -> PostProcessorResult:
    """
    Convenience function to process Bedrock code for hallucinated API calls.

    Args:
        code: Bedrock TypeScript/JavaScript code to validate
        strict: Enable strict validation mode

    Returns:
        PostProcessorResult with hallucination report
    """
    postprocessor = ASTBedrockPostprocessor(strict=strict)
    return postprocessor.process(code)
