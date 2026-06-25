"""
Bedrock API Boundary Prober for Issue #1724.

Pre-generation probing mechanism that:
1. Identifies what Bedrock APIs the Java code NEEDS (demand side)
2. Retrieves what's AVAILABLE in the KB (supply side)
3. Injects relevant API context BEFORE generation to prevent hallucinations
4. Validates generated output for hallucinated APIs (post-generation)

This is complementary to the AST post-processor:
- AST post-processor = post-generation safety net (catches hallucinations after)
- API boundary prober = pre-generation prevention (injects knowledge before)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

from knowledge.patterns.bedrock_patterns import BedrockPatternRegistry
from knowledge.patterns.mappings import PatternMappingRegistry
from search.hallucination_tracker import BedrockComponentHallucinationTracker

logger = structlog.get_logger(__name__)


class APIProbingConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class JavaConstruct:
    """A Java construct that maps to Bedrock API needs."""

    construct_type: str  # "class", "method", "import", "event_handler"
    name: str
    raw_signature: str
    mapped_api_needs: List[str] = field(default_factory=list)


@dataclass
class BedrockAPISurface:
    """A retrieved Bedrock API surface from the KB."""

    api_name: str
    api_type: str  # "component", "event", "method", "class"
    description: str
    source_pattern: str
    relevance_score: float
    code_example: Optional[str] = None


@dataclass
class DemandGuidedContext:
    """Result of demand-guided context injection."""

    java_constructs: List[JavaConstruct]
    bedrock_api_surfaces: List[BedrockAPISurface]
    context_snippet: str  # Formatted for injection into prompt
    api_categories_found: Set[str]


@dataclass
class HallucinationValidationResult:
    """Result of post-generation hallucination validation."""

    is_valid: bool
    hallucinated_apis: List[str]
    valid_apis_found: List[str]
    hallucination_rate: float
    report: Dict[str, Any]


class BedrockAPIBoundaryProber:
    """
    Probes Bedrock API knowledge boundaries and provides demand-guided context injection.

    This prober:
    1. Analyzes Java code to identify what Bedrock APIs are needed (demand)
    2. Queries the knowledge base for available APIs (supply)
    3. Generates a targeted context snippet for injection
    4. Validates generated Bedrock code for hallucinated APIs
    """

    JAVA_TO_BEDROCK_MAPPINGS: Dict[str, List[str]] = {
        "Block_onPlaced": ["world.afterEvents.blockPlace", "player.dimension.setBlock"],
        "Block_onBroken": ["world.afterEvents.playerBreakBlock", "block.destroy"],
        "BlockEntity_tick": ["system.runInterval", "world.afterEvents.tick"],
        "PlayerInteractEvent": ["world.afterEvents.playerInteractWithBlock", "player.onScreenAchorToActionbar"],
        "Entity_onDeath": ["world.afterEvents.entityDie", "entity.kill"],
        "EntityLivingBase_onUpdate": ["system.runInterval", "world.beforeEvents.tick"],
        "ItemStack": ["ItemStack", "container.addItem", "container.getItem"],
        "World_playSound": ["dimension.playSound", "world.playSound"],
        "BlockState": ["BlockPermutation", "block.permutation"],
        "TileEntity": ["block.setDynamicProperty", "block.getDynamicProperty"],
        "Merchant": ["MinecraftMerchant", "player.openDialog"],
        "WorldSavedData": ["world.getDynamicProperty", "world.setDynamicProperty"],
        "Player_getLookAngle": ["player.getViewDirection"],
        "Vec3": ["Vector3", "Location"],
    }

    HALLUCINATED_API_EXAMPLES: Set[str] = {
        "minecraft:fake_component",
        "minecraft:custom_ai",
        "minecraft:non_existent_property",
        "minecraft:on_custom_event",
        "player.sendMessage",
        "player.getInventory",
        "block.getBlockEntity",
        "world.getTileEntity",
        "entity.getCustomName",
    }

    def __init__(self, strict_api: bool = False):
        """
        Initialize the prober.

        Args:
            strict_api: If True, enables strict API validation and injection.
                       When False, prober operates in passive mode.
        """
        self.strict_api = strict_api
        self._pattern_registry = BedrockPatternRegistry()
        self._mapping_registry = PatternMappingRegistry()
        self._hallucination_tracker = BedrockComponentHallucinationTracker()
        self._known_script_api_methods = self._load_known_script_api_methods()
        self._known_classes = self._load_known_classes()

    def _load_known_script_api_methods(self) -> Set[str]:
        """Load known Script API methods from bedrock patterns."""
        methods = set()
        for pattern in self._pattern_registry.get_all_patterns():
            bedrock_code = pattern.bedrock_example
            method_matches = re.findall(
                r"(?:player|world|dimension|block|entity|container|system)\.(\w+)\(",
                bedrock_code,
            )
            for m in method_matches:
                methods.add(m)
        return methods

    def _load_known_classes(self) -> Set[str]:
        """Load known Bedrock Script API classes."""
        classes = set()
        for pattern in self._pattern_registry.get_all_patterns():
            bedrock_code = pattern.bedrock_example
            import_matches = re.findall(r"import\s+\{([^}]+)\}\s+from", bedrock_code)
            for import_block in import_matches:
                names = [n.strip() for n in import_block.split(",")]
                for name in names:
                    if name and name[0].isupper():
                        classes.add(name)
        return classes

    def probe_java_demand(self, java_code: str) -> List[JavaConstruct]:
        """
        Analyze Java code to identify what Bedrock APIs are needed.

        Args:
            java_code: The Java source code to analyze

        Returns:
            List of JavaConstruct objects representing API needs
        """
        constructs = []

        for method_match in re.finditer(
            r"(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*\{",
            java_code,
        ):
            method_name = method_match.group(1)
            mapped_apis = []

            if method_name in self.JAVA_TO_BEDROCK_MAPPINGS:
                mapped_apis = self.JAVA_TO_BEDROCK_MAPPINGS[method_name]
            else:
                for prefix in ["Block_", "Entity_", "BlockEntity_", "Item_", "World_"]:
                    class_prefixed = f"{prefix}{method_name}"
                    if class_prefixed in self.JAVA_TO_BEDROCK_MAPPINGS:
                        mapped_apis = self.JAVA_TO_BEDROCK_MAPPINGS[class_prefixed]
                        break

            if mapped_apis:
                constructs.append(
                    JavaConstruct(
                        construct_type="method",
                        name=method_name,
                        raw_signature=method_match.group(0),
                        mapped_api_needs=mapped_apis,
                    )
                )

        for import_match in re.finditer(r"import\s+([\w\.]+);", java_code):
            import_path = import_match.group(1)
            if "forge" in import_path.lower() or "minecraft" in import_path.lower():
                pass

        for event_handler_match in re.finditer(
            r"@(\w+)\s*\(\s*(?:[\w\.]+)\s*\)\s*(?:public\s+)?void\s+(\w+)\s*\(",
            java_code,
        ):
            annotation = event_handler_match.group(1)
            handler_name = event_handler_match.group(2)
            constructs.append(
                JavaConstruct(
                    construct_type="event_handler",
                    name=handler_name,
                    raw_signature=f"@{annotation} void {handler_name}()",
                    mapped_api_needs=self._map_event_to_bedrock(annotation),
                )
            )

        logger.info("Java demand probing complete", constructs_found=len(constructs))
        return constructs

    def _map_event_to_bedrock(self, annotation: str) -> List[str]:
        """Map Java event annotations to Bedrock API equivalents."""
        event_mapping = {
            "SubscribeEvent": ["world.afterEvents.tick", "world.beforeEvents.tick"],
            "ModInit": ["world.initialize"],
            "ServerLifecycle": ["world.afterEvents.worldInitialize"],
        }
        return event_mapping.get(annotation, [])

    def probe_kb_supply(self, api_needs: List[str]) -> List[BedrockAPISurface]:
        """
        Query the KB for available Bedrock APIs matching the identified needs.

        Args:
            api_needs: List of API names/features needed

        Returns:
            List of BedrockAPISurface objects from the KB
        """
        surfaces = []
        seen_apis = set()

        for api_need in api_needs:
            api_need_lower = api_need.lower()

            for pattern in self._pattern_registry.get_all_patterns():
                bedrock_code = pattern.bedrock_example

                if api_need_lower in bedrock_code.lower():
                    api_name = self._extract_api_name(api_need, bedrock_code)

                    if api_name not in seen_apis:
                        surfaces.append(
                            BedrockAPISurface(
                                api_name=api_name,
                                api_type=self._classify_api_type(api_name),
                                description=pattern.description,
                                source_pattern=pattern.id,
                                relevance_score=0.85,
                                code_example=self._extract_relevant_snippet(
                                    api_name, bedrock_code
                                ),
                            )
                        )
                        seen_apis.add(api_name)
                    continue

                api_parts = api_need_lower.split(".")
                for i, part in enumerate(api_parts):
                    partial_need = ".".join(api_parts[i:])
                    if partial_need in bedrock_code.lower():
                        api_name = self._extract_api_name(api_need, bedrock_code)

                        if api_name not in seen_apis:
                            surfaces.append(
                                BedrockAPISurface(
                                    api_name=api_name,
                                    api_type=self._classify_api_type(api_name),
                                    description=pattern.description,
                                    source_pattern=pattern.id,
                                    relevance_score=0.7,
                                    code_example=self._extract_relevant_snippet(
                                        api_name, bedrock_code
                                    ),
                                )
                            )
                            seen_apis.add(api_name)
                        break

        surfaces.sort(key=lambda s: s.relevance_score, reverse=True)
        logger.info("KB supply probing complete", surfaces_found=len(surfaces))
        return surfaces

    def _extract_api_name(self, need: str, bedrock_code: str) -> str:
        """Extract the Bedrock API name from code context."""
        if "." in need:
            return need
        return need

    def _classify_api_type(self, api_name: str) -> str:
        """Classify the type of Bedrock API."""
        if api_name.startswith("minecraft:"):
            return "component"
        if "afterEvents" in api_name or "beforeEvents" in api_name:
            return "event"
        if "world" in api_name or "player" in api_name or "dimension" in api_name:
            return "script_api"
        return "unknown"

    def _extract_relevant_snippet(self, api_name: str, bedrock_code: str) -> str:
        """Extract the most relevant code snippet for an API."""
        lines = bedrock_code.split("\n")
        for i, line in enumerate(lines):
            if api_name in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                return "\n".join(lines[start:end])
        return bedrock_code[:300]

    def generate_context_snippet(
        self, demand: List[JavaConstruct], supply: List[BedrockAPISurface]
    ) -> str:
        """
        Generate a formatted context snippet for injection into the converter prompt.

        Args:
            demand: Identified Java constructs needing Bedrock APIs
            supply: Retrieved Bedrock API surfaces from KB

        Returns:
            Formatted context snippet with ## Available Bedrock APIs section
        """
        if not supply:
            return ""

        lines = [
            "",
            "## Available Bedrock APIs for this task:",
            "",
        ]

        categories: Dict[str, List[BedrockAPISurface]] = {}
        for surface in supply:
            cat = surface.api_type
            categories.setdefault(cat, []).append(surface)

        for category, surfaces in categories.items():
            lines.append(f"### {category.upper().replace('_', ' ')} APIs")
            for surface in surfaces[:5]:
                lines.append(f"- `{surface.api_name}`: {surface.description}")
                if surface.code_example:
                    lines.append(f"  ```javascript")
                    lines.append(f"  // Example: {surface.source_pattern}")
                    snippet_lines = surface.code_example.strip().split("\n")
                    for snippet_line in snippet_lines[:4]:
                        lines.append(f"  {snippet_line}")
                    lines.append(f"  ```")
            lines.append("")

        lines.append("### API Usage Rules")
        lines.append("- Only use APIs listed above or from @minecraft/server ^2.0.0")
        lines.append(
            "- Do NOT invent methods like `player.sendMessage()` — use `player.dimension.runCommand()` or `world.sendMessage()`"
        )
        lines.append(
            "- Do NOT use `block.getBlockEntity()` — Bedrock doesn't have tile entities like Java"
        )
        lines.append(
            "- Use `block.setDynamicProperty()` for persistent data on blocks"
        )
        lines.append(
            "- For world data, use `world.getDynamicProperty()` / `world.setDynamicProperty()`"
        )

        return "\n".join(lines)

    def build_demand_guided_context(self, java_code: str) -> DemandGuidedContext:
        """
        Build demand-guided context by matching Java needs to KB supply.

        Args:
            java_code: The Java source code to convert

        Returns:
            DemandGuidedContext with all relevant information
        """
        demand = self.probe_java_demand(java_code)

        all_api_needs = []
        for construct in demand:
            all_api_needs.extend(construct.mapped_api_needs)

        supply = self.probe_kb_supply(all_api_needs)

        context_snippet = self.generate_context_snippet(demand, supply)

        api_categories = {s.api_type for s in supply}

        return DemandGuidedContext(
            java_constructs=demand,
            bedrock_api_surfaces=supply,
            context_snippet=context_snippet,
            api_categories_found=api_categories,
        )

    def validate_output(self, bedrock_code: str) -> HallucinationValidationResult:
        """
        Validate generated Bedrock code for hallucinated API calls.

        Args:
            bedrock_code: The generated Bedrock code to validate

        Returns:
            HallucinationValidationResult with findings
        """
        report = self._hallucination_tracker.detect_hallucinations(bedrock_code)

        script_api_hallucinations = self._detect_script_api_hallucinations(bedrock_code)

        component_hallucinations = [
            hc.component_name for hc in report.hallucinated_components
            if "." in hc.component_name
        ]
        all_hallucinated = component_hallucinations + script_api_hallucinations

        valid_apis = self._extract_valid_script_apis(bedrock_code)

        hallucination_rate = (
            len(all_hallucinated) / max(len(valid_apis) + len(all_hallucinated), 1)
        )

        return HallucinationValidationResult(
            is_valid=len(all_hallucinated) == 0,
            hallucinated_apis=all_hallucinated,
            valid_apis_found=valid_apis,
            hallucination_rate=hallucination_rate,
            report={
                "total_detected": len(valid_apis) + len(all_hallucinated),
                "hallucinated_count": len(all_hallucinated),
                "component_report": asdict(report) if hasattr(report, "__dict__") else {},
                "script_api_hallucinations": script_api_hallucinations,
            },
        )

    def _detect_script_api_hallucinations(self, bedrock_code: str) -> List[str]:
        """Detect hallucinated Script API method calls."""
        hallucinations = []

        hallucinated_patterns = [
            (r"player\.sendMessage\s*\(", "player.sendMessage()"),
            (r"player\.getInventory\s*\(", "player.getInventory()"),
            (r"block\.getBlockEntity\s*\(", "block.getBlockEntity()"),
            (r"world\.getTileEntity\s*\(", "world.getTileEntity()"),
            (r"entity\.getCustomName\s*\(", "entity.getCustomName()"),
            (r"world\.setBlock\s*\([^)]+,\s*Block\.", "world.setBlock with Block member access"),
        ]

        for pattern, description in hallucinated_patterns:
            if re.search(pattern, bedrock_code):
                hallucinations.append(description)

        method_calls = re.findall(
            r"(?:player|world|dimension|block|entity|system)\.(\w+)\(",
            bedrock_code,
        )

        for method_call in method_calls:
            if (
                method_call not in self._known_script_api_methods
                and not method_call.startswith("get")
                and not method_call.startswith("set")
                and not method_call.startswith("run")
                and not method_call.startswith("on")
                and len(method_call) > 3
            ):
                if f"{method_call}()" not in hallucinations:
                    pass

        return hallucinations

    def _extract_valid_script_apis(self, bedrock_code: str) -> List[str]:
        """Extract valid Script API calls from Bedrock code."""
        valid_apis = []

        method_calls = re.findall(
            r"(?:player|world|dimension|block|entity|container|system)\.(\w+)\(",
            bedrock_code,
        )

        for method_call in method_calls:
            if method_call in self._known_script_api_methods:
                valid_apis.append(method_call)

        return list(set(valid_apis))

    def get_injection_prompt(self, java_code: str) -> str:
        """
        Get the full injection prompt for the converter.

        This is the main entry point for pre-generation API context injection.

        Args:
            java_code: The Java source code to convert

        Returns:
            Formatted prompt section for injection into converter prompt
        """
        if not self.strict_api:
            return ""

        context = self.build_demand_guided_context(java_code)

        if not context.context_snippet:
            return ""

        return context.context_snippet


def asdict(obj):
    """Convert dataclass to dict recursively."""
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            result[field_name] = asdict(value) if hasattr(value, "__dataclass_fields__") else value
        return result
    return obj
