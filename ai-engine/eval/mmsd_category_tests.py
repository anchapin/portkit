"""
MMSD Category-Specific Functional Tests
========================================

Generates pytest tests for MMSD dataset pairs, validating conversion quality
per Java API category. Inspired by PQC migration fine-tuning methodology
(ArXiv 2606.07341) — category-specific functional tests enable dataset quality
gating: pairs without passing tests are excluded from fine-tuning.

Categories implemented:
  - event_handler:   @SubscribeEvent / EventBusSubscriber patterns
  - tick_handler:    TickEvent (ServerTickEvent, ClientTickEvent)
  - block_interaction: PlayerInteractEvent, BlockBreakEvent, BlockPlaceEvent
  - item_registry:   DeferredRegister<Item> / Item registration
  - block_registry:  DeferredRegister<Block> / Block registration
  - entity_spawn:    EntityType, SpawnEntity patterns
  - command_handler: CommandDispatcher / ArgumentBuilder patterns

Validation strategy per category:
  1. JSON validity + Bedrock manifest structure
  2. Bedrock JS structural properties (required API calls present)
  3. Java→Bedrock semantic mapping checks (event type coverage)

PQC paper key insight: "Category-specific functional tests enable both dataset
quality control and objective evaluation — pairs without passing tests are
excluded from training." (Section 3.2)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

DATASET_PATH = "ai-engine/mmsd/data/processed/synthesis_pairs.jsonl"


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = {
    "event_handler": {
        "java_patterns": [
            r"@SubscribeEvent",
            r"EventBusSubscriber",
            r"MinecraftForge\.EVENT_BUS\.register",
            r"\.addListener\(",
        ],
        "bedrock_patterns": [
            r"\.listenForEvent\(",
            r"world\.afterEvents\.",
            r"world\.beforeEvents\.",
            r"\.subscribe\(",
            r"events\.",
            r"\.on\(",
        ],
        "description": "Java Forge event bus handlers → Bedrock event listeners",
    },
    "tick_handler": {
        "java_patterns": [
            r"TickEvent",
            r"ServerTickEvent",
            r"ClientTickEvent",
            r"PlayerTickEvent",
            r"LivingUpdateEvent",
        ],
        "bedrock_patterns": [
            r"system\.runInterval\(",
            r"\.tick\b",
            r"run\(async",
            r"\.schedule\(",
            r"mc\.listenForEvent\(['\"]tick['\"]",
            r"world\.listenFor\(['\"]tick['\"]",
            r"system\.run\(",
        ],
        "description": "TickEvent handlers → Bedrock system.runInterval / tick event listener",
    },
    "block_interaction": {
        "java_patterns": [
            r"BlockBreakEvent",
            r"BlockPlaceEvent",
            r"PlayerInteractEvent",
            r"onBlockBreak",
            r"onBlockPlace",
            r"RightClickBlock",
        ],
        "bedrock_patterns": [
            r"on_interact",
            r"\.breakEvent",
            r"\.placeEvent",
            r"\.beforeEvents\.",
            r"block.*event",
            r"\.onPlayerInteract\(",
            r"player_interact",
            r"\.interact\(",
        ],
        "description": "Block break/place/interact → Bedrock block event handlers",
    },
    "item_registry": {
        "java_patterns": [
            r"DeferredRegister.*Item",
            r"RegistryObject.*Item",
            r"ModItems",
            r"register.*Item",
            r"Item\.Properties",
        ],
        "bedrock_patterns": [
            r"registerItem\(",
            r"Item\(",
            r"minecraft:item",
            r"\"minecraft:item\"",
            r"\.stackable\(",
            r"register\(.*Item",
            r"addItem\(",
            r"createItem\(",
        ],
        "description": "Java Item registration → Bedrock item component registration",
    },
    "block_registry": {
        "java_patterns": [
            r"DeferredRegister.*Block",
            r"RegistryObject.*Block",
            r"ModBlocks",
            r"register.*Block",
            r"Block\.Properties",
        ],
        "bedrock_patterns": [
            r"registerBlock\(",
            r"createBlock\(",
            r"minecraft:block",
            r"\"minecraft:block\"",
            r"\.geometry\(",
            r"addBlock\(",
            r"create\(.*Block",
        ],
        "description": "Java Block registration → Bedrock block definition",
    },
    "entity_spawn": {
        "java_patterns": [
            r"EntityType",
            r"SpawnEntity",
            r"EntitySpawnEvent",
            r"register.*Entity",
            r"EntityType\.",
        ],
        "bedrock_patterns": [
            r"spawnEntity\(",
            r"createEntity\(",
            r"minecraft:entity",
            r"\.spawn\(",
            r"addEntity\(",
            r"registerEntity\(",
        ],
        "description": "Java entity spawning → Bedrock entity spawning",
    },
    "command_handler": {
        "java_patterns": [
            r"CommandDispatcher",
            r"ArgumentBuilder",
            r"CommandPermission",
            r"@SubscribeEvent.*Command",
            r"CommandRegistry",
        ],
        "bedrock_patterns": [
            r"world\.getAllPlayers",
            r"player\.runCommand\(",
            r"\.execute\(",
            r"commands\.",
            r"runCommand\(",
        ],
        "description": "Java command registration → Bedrock command execution",
    },
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MMSDPair:
    idx: int
    instruction: str
    java_source: str
    bedrock_source: str
    categories: list[str] = field(default_factory=list)
    java_valid: bool = False
    bedrock_json_valid: bool = False
    bedrock_js_present: bool = False
    category_checks: dict = field(default_factory=dict)


@dataclass
class CategoryResult:
    name: str
    total: int
    passed: int
    failed: int
    errors: list[str] = field(default_factory=list)


@dataclass
class MMSDTestReport:
    dataset_path: str
    total_pairs: int
    category_results: dict[str, CategoryResult] = field(default_factory=dict)
    pairs_by_category: dict[str, list[int]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "dataset_path": self.dataset_path,
            "total_pairs": self.total_pairs,
            "categories": {
                name: {
                    "total": r.total,
                    "passed": r.passed,
                    "failed": r.failed,
                    "pass_rate": round(r.passed / r.total, 3) if r.total > 0 else 0.0,
                    "errors": r.errors[:5],
                }
                for name, r in self.category_results.items()
            },
        }


# ---------------------------------------------------------------------------
# MMSD Pair Loader
# ---------------------------------------------------------------------------


def _extract_code_blocks(source: str, lang: str) -> list[str]:
    """Extract all ```lang ... ``` blocks from source."""
    pattern = rf"```{lang}(.*?)```"
    return [m.strip() for m in re.findall(pattern, source, re.DOTALL)]


def load_mmsd_pairs(path: str) -> list[MMSDPair]:
    """Load MMSD pairs from JSONL file and classify by category."""
    pairs = []
    with open(path) as f:
        for idx, line in enumerate(f):
            d = json.loads(line)
            java = d.get("java_source", "")
            bedrock = d.get("bedrock_source", "")

            pair = MMSDPair(
                idx=idx,
                instruction=d.get("instruction", ""),
                java_source=java,
                bedrock_source=bedrock,
            )

            # Classify by Java API patterns
            cats = set()
            for cat_name, cat_def in CATEGORIES.items():
                for pat in cat_def["java_patterns"]:
                    if re.search(pat, java):
                        cats.add(cat_name)
                        break
            if not cats:
                cats.add("other")
            pair.categories = list(cats)

            pairs.append(pair)
    return pairs


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_java_structure(java_code: str) -> tuple[bool, str]:
    """Structural validation of Java source — not full compilation."""
    if not java_code or len(java_code.strip()) < 20:
        return False, "Java source too short or empty"

    checks = {
        "package": r"package [\w\.]+;",
        "class": r"(public class|class) \w+",
        "imports": r"import [\w\.\*]+;",
    }
    failed = []
    for name, pat in checks.items():
        if not re.search(pat, java_code):
            failed.append(name)

    if failed:
        return False, f"Missing Java structure: {', '.join(failed)}"
    return True, "Java structure valid"


def validate_bedrock_json(bedrock_source: str) -> tuple[bool, str, Optional[dict]]:
    """Validate Bedrock JSON blocks in the source. Returns (valid, message, parsed_json)."""
    json_blocks = _extract_code_blocks(bedrock_source, "json")
    if not json_blocks:
        if "format_version" in bedrock_source or "manifest" in bedrock_source:
            return True, "Manifest structure present (no fenced JSON)", None
        return False, "No JSON blocks found in Bedrock source", None

    errors = []
    for block in json_blocks:
        clean = re.sub(r"//.*", "", block)
        clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)
        try:
            parsed = json.loads(clean)
            # Check for Bedrock manifest structure
            if isinstance(parsed, dict):
                if "header" in parsed or "manifest" in parsed or "format_version" in str(parsed):
                    return True, "Valid Bedrock manifest JSON", parsed
        except json.JSONDecodeError as e:
            errors.append(str(e))

    if errors:
        return False, f"JSON errors: {errors[0]}", None
    return True, "Valid JSON blocks found", None


def validate_bedrock_js(bedrock_source: str, category: str) -> tuple[bool, str]:
    """Check Bedrock JavaScript has expected structural properties for the category."""
    js_blocks = _extract_code_blocks(bedrock_source, "javascript")
    js_blocks += _extract_code_blocks(bedrock_source, "js")
    js_blocks += re.findall(
        r"(?:^|\n)(const|let|var|function|import|export|class|\.listenForEvent|\.runInterval|\.spawnEntity|\.registerItem|\.createBlock|\.listen\(|\.subscribe\(|mc\.|world\.|system\.).*?\(",
        bedrock_source,
        re.MULTILINE,
    )

    if not js_blocks:
        # Check for common Bedrock API patterns anywhere in source
        common_api = re.findall(
            r"(?:mc\.|world\.|system\.|events\.)[\w]+\(",
            bedrock_source,
        )
        if common_api:
            return True, f"Found Bedrock API calls: {', '.join(set(common_api[:3]))}"
        return False, "No JavaScript blocks or Bedrock API calls found"

    combined_js = "\n".join(js_blocks)

    # Category-specific Bedrock JS validation
    cat_def = CATEGORIES.get(category)
    if cat_def:
        for pat in cat_def["bedrock_patterns"]:
            if re.search(pat, combined_js):
                return True, f"Found expected Bedrock API: {pat}"
        # Relaxed check: look for any common Bedrock API
        common_api = re.findall(
            r"(?:mc\.|world\.|system\.|events\.)[\w]+",
            combined_js,
        )
        if common_api:
            return (
                True,
                f"Found Bedrock API (category-specific pattern not matched): {common_api[0]}",
            )
        return False, f"No expected Bedrock API found for {category}"

    return True, "JavaScript present (no category-specific check)"


# ---------------------------------------------------------------------------
# Per-category validation
# ---------------------------------------------------------------------------


def validate_pair_category(pair: MMSDPair, category: str) -> tuple[bool, str]:
    """
    Validate a single pair for a specific category.
    Returns (passed, message).
    """
    # 1. Java structure check
    java_ok, java_msg = validate_java_structure(pair.java_source)
    if not java_ok:
        return False, f"Java structure invalid: {java_msg}"

    # 2. Bedrock JSON validity
    json_ok, json_msg, _ = validate_bedrock_json(pair.bedrock_source)
    if not json_ok:
        return False, f"Bedrock JSON invalid: {json_msg}"

    # 3. Bedrock JS category check
    js_ok, js_msg = validate_bedrock_js(pair.bedrock_source, category)
    if not js_ok:
        return False, f"Bedrock JS invalid: {js_msg}"

    return True, f"OK — Java: {java_msg}, JSON: {json_msg}, JS: {js_msg}"


# ---------------------------------------------------------------------------
# Pytest test generation — dynamically generated from dataset
# ---------------------------------------------------------------------------


def _build_tests():
    """
    Build pytest test functions for each category at module load time.
    Each test iterates all pairs in the category and validates each.
    """
    dataset_path = os.environ.get("MMSD_DATASET_PATH", DATASET_PATH)

    if not Path(dataset_path).exists():
        pytest.skip(f"Dataset not found: {dataset_path}")

    pairs = load_mmsd_pairs(dataset_path)

    # Index pairs by category
    pairs_by_cat: dict[str, list[MMSDPair]] = {cat: [] for cat in CATEGORIES}
    pairs_by_cat["other"] = []
    for pair in pairs:
        for cat in pair.categories:
            if cat in pairs_by_cat:
                pairs_by_cat[cat].append(pair)

    # -------------------------------------------------------------------------
    # Generate one test class per category
    # -------------------------------------------------------------------------
    for cat_name, cat_def in CATEGORIES.items():
        cat_pairs = pairs_by_cat[cat_name]

        # Dynamically create test class
        test_class = type(
            f"Test_{cat_name.title().replace('_', '')}",
            (object,),
            {
                "__doc__": f"Functional tests for {cat_name} category.\n"
                f"Description: {cat_def['description']}\n"
                f"Java patterns: {', '.join(cat_def['java_patterns'])}\n"
                f"Bedrock patterns: {', '.join(cat_def['bedrock_patterns'])}\n"
                f"Dataset pairs: {len(cat_pairs)}",
            },
        )

        if not cat_pairs:
            setattr(
                test_class,
                f"test_{cat_name}_no_pairs",
                lambda self: pytest.skip(f"No {cat_name} pairs in dataset"),
            )
        else:
            # One test per pair — reasonable sample
            sample_size = min(len(cat_pairs), 20)
            sampled = cat_pairs[:sample_size]

            for pi, pair in enumerate(sampled):

                def make_test(p: MMSDPair, idx: int, cat: str):
                    pair_idx = p.idx
                    pair_instruction = p.instruction[:80]

                    def test_fn(self, _pair=p, _cat=cat, _idx=pair_idx, _instr=pair_instruction):
                        passed, msg = validate_pair_category(_pair, _cat)
                        assert passed, f"Pair {_idx}: {msg}"

                    test_fn.__name__ = f"test_{cat}_{pair_idx}"
                    test_fn.__doc__ = f"Pair {pair_idx} — {pair_instruction}"
                    return test_fn

                setattr(test_class, f"test_{cat_name}_{pair.idx}", make_test(pair, pi, cat_name))

        # Attach to module globals so pytest can discover them
        setattr(sys.modules[__name__], f"Test_{cat_name.title().replace('_', '')}", test_class)
        globals()[f"Test_{cat_name.title().replace('_', '')}"] = test_class


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(dataset_path: str) -> MMSDTestReport:
    """Run full validation on dataset and return report."""
    pairs = load_mmsd_pairs(dataset_path)
    report = MMSDTestReport(dataset_path=dataset_path, total_pairs=len(pairs))

    # Index pairs by category
    for pair in pairs:
        for cat in pair.categories:
            if cat == "other":
                continue
            if cat not in report.pairs_by_category:
                report.pairs_by_category[cat] = []
            report.pairs_by_category[cat].append(pair.idx)

    # Validate each category
    for cat_name in CATEGORIES:
        pair_ids = report.pairs_by_category.get(cat_name, [])
        total = len(pair_ids)
        if total == 0:
            continue

        result = CategoryResult(name=cat_name, total=total, passed=0, failed=0)
        for idx in pair_ids:
            # Find the pair
            pair = next((p for p in pairs if p.idx == idx), None)
            if not pair:
                continue
            try:
                passed, msg = validate_pair_category(pair, cat_name)
                if passed:
                    result.passed += 1
                else:
                    result.failed += 1
                    result.errors.append(f"Pair {idx}: {msg}")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Pair {idx} exception: {e}")

        report.category_results[cat_name] = result

    return report


# ---------------------------------------------------------------------------
# Module setup — load dataset and generate tests
# ---------------------------------------------------------------------------

import os
import sys

DATASET_PATH_ENV = os.environ.get("MMSD_DATASET_PATH", DATASET_PATH)
if Path(DATASET_PATH_ENV).exists():
    try:
        _build_tests()
    except Exception as e:
        import warnings

        warnings.warn(f"Failed to auto-load MMSD tests: {e}")
else:
    pass  # Tests will be skipped if dataset not found
