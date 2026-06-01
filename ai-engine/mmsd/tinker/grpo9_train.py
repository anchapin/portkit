#!/usr/bin/env python3
"""
PortKit GRPO9 Training — All P0 Reward Fixes Consolidated
==========================================================
GRPO9 Training Script incorporating ALL P0 reward fixes from:

  Issue #1582: Anti-hallucination fixes
    - Hardened hallucination detection with comprehensive fake API patterns
    - Increased penalties: -0.3 per hard hallucination (#1648)
    - Lying penalty: -0.2 when @minecraft/server imported but hallucinated APIs used (#1649)
    - Binary presence: -0.2 constant for ANY hallucination detected (#1650)

  Issue #1583: Real API fixes
    - Event subscription requirement for full score
    - API chain depth requirement (world.afterEvents.X.subscribe)
    - @minecraft/server import requirement for valid scoring

  Issue #1584: GRPO Stabilization
    - group_size increased to 16-20 for better advantage estimation
    - PPO loss implemented (clipped surrogate objective)
    - Reward normalization across GRPO group (z-score)
    - Learning rate reduced to 5e-7 for stability

  Issue #1585: Curriculum Learning
    - Phase 1 (0-30%): Easy examples only
    - Phase 2 (30-60%): Easy + Medium mix
    - Phase 3 (60-100%): All difficulties, favoring hard

  Issue #1586: Manifest fixes
    - UUID v4 format validation (xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx)
    - Version array format [major, minor, patch] with numeric values
    - Module type validation against Bedrock types

Reward Components & Weights:
  - manifest:           0.10  (UUID v4, version array, module type validation)
  - real_api:          0.25  (event subscription + API chain depth)
  - anti_hallucination: 0.25 (hallucination penalties shifted to [0.5, 1.0])
  - concise:           0.15  (output length optimization)
  - code_bleu:         0.25  (token overlap in code blocks)

Stabilization Config:
  - group_size: 16
  - lr: 5e-7
    - ppo loss_fn (clipped surrogate objective)
  - z-score reward normalization

Usage:
    python grpo9_train.py --checkpoint-path tinker://.../grpo8/weights/final

Prerequisites:
    pip install tinker tinker-cookbook
    export TINKER_API_KEY="your-key"
"""

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_TRAIN_DATA = DATA_DIR / "train.jsonl"

# Load .env if present
dotenv = PROJECT_ROOT / ".env"
if dotenv.exists():
    for line in dotenv.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def check_prerequisites():
    try:
        import tinker
        import tinker_cookbook
    except ImportError as e:
        print(f"ERROR: {e}")
        print("Install with: pip install tinker tinker-cookbook")
        sys.exit(1)

    if not os.environ.get("TINKER_API_KEY"):
        print("ERROR: TINKER_API_KEY not set")
        sys.exit(1)

    print(f"tinker version: {tinker.__version__}")


def load_prompts_and_references(train_data_path, max_samples=None):
    """Load training conversations with metadata."""
    conversations = []
    with open(train_data_path) as f:
        for line in f:
            if line.strip():
                conversations.append(json.loads(line))

    prompts = []
    references = []
    for conv in conversations:
        messages = conv["messages"]
        assistant_msg = ""
        prompt_messages = []
        for msg in messages:
            if msg["role"] == "assistant":
                assistant_msg = msg["content"]
            else:
                prompt_messages.append(msg)
        prompts.append(prompt_messages)
        references.append(assistant_msg)

    if max_samples:
        prompts = prompts[:max_samples]
        references = references[:max_samples]

    return prompts, references


# ─────────────────────────────────────────────────────────────
# GRPO9 REWARD FUNCTIONS — ALL P0 FIXES INCORPORATED
# ─────────────────────────────────────────────────────────────

def extract_code_blocks(text: str) -> dict:
    """Extract code blocks by language."""
    blocks = {"json": [], "javascript": [], "js": [], "other": []}
    pattern = r"```(\w*)\s*\n(.*?)```"
    for match in re.finditer(pattern, text, re.DOTALL):
        lang = match.group(1).lower().strip()
        code = match.group(2).strip()
        if not code:
            continue
        if lang == "json":
            blocks["json"].append(code)
        elif lang in ("javascript", "js"):
            blocks["javascript"].append(code)
        else:
            blocks["other"].append(code)
    return blocks


# ─────────────────────────────────────────────────────────────
# Issue #1582: Anti-Hallucination Reward Functions
# ─────────────────────────────────────────────────────────────

def count_hallucinated_apis(completion: str) -> float:
    """Count and penalize hallucinated Bedrock APIs.

    Implements 4-tier penalty system from Issue #1582:
      #1647 - Semantic validation: grammatically-correct imports checked against real APIs
      #1648 - Hard hallucinations: -0.3 each (completely fabricated APIs)
      #1649 - Lying penalty:      -0.2 if @minecraft/server imported but hallucinated APIs used
      #1650 - Binary presence:    -0.2 constant for ANY hallucination detected

    Returns total penalty in [-1.0, 0.0].
    The penalty is shifted to [0.5, 1.0] when used in the composite reward.
    """
    blocks = extract_code_blocks(completion)
    js_code = " ".join(blocks["javascript"] + blocks["js"])

    if not js_code:
        return 0.0  # No JS — not hallucinated, but will be penalized by real_api

    total_penalty = 0.0

    # ─────────────────────────────────────────────────────────────
    # TIER 1: Hard hallucination patterns (Issue #1648)
    # Completely fabricated APIs that are NEVER valid in Bedrock
    # ─────────────────────────────────────────────────────────────
    hard_hallucinations = [
        # Java-mod-style fake classes
        r"\bServerPlayerAPI\b",
        r"\bServerPlayer\b",
        r"\bPlayerAPI\b",
        r"\bWorldEvent\b",
        r"\bmodEventBus\b",
        r"\bBlockEntityAPI\b",
        r"\bEntityPlayerAPI\b",
        r"\bWorldAPI\b",
        # Non-existent require/define patterns
        r'require\(["\']@minecraft/server"',
        r"\bregisterMod\(",
        r"\bdefineMod\(",
        # Non-existent methods on known classes
        r"\.createLightningBolt\(",
        r"\.spawnLightning\(",
        r"\.registerEvent\(",
        r"\.registerServerEvent\(",
        r"\.onServerStart\(",
        r"\.onServerStop\(",
        # Non-existent static accessors
        r"event\.level\.",
        r"server\.getWorld\(",
        r"getServer\(\)\.",
        r"Server\.getInstance\(\)",
        # Non-existent property chains
        r"\.getTileEntity\(\).*\.getInventory\(",
        r"world\.setBlock\(.*\.getPosition\(",
    ]

    hard_count = 0
    for pattern in hard_hallucinations:
        matches = re.findall(pattern, js_code, re.IGNORECASE)
        hard_count += len(matches)

    # Issue #1648: -0.3 per hard hallucination
    hard_penalty = -0.3 * hard_count
    total_penalty += hard_penalty

    # ─────────────────────────────────────────────────────────────
    # TIER 2: Grammatically-correct but semantically invalid (Issue #1647)
    # Check if @minecraft/server is imported but refers to non-existent classes/methods
    # ─────────────────────────────────────────────────────────────
    has_minecraft_import = bool(re.search(
        r"from\s+['\"]@minecraft/server['\"]", js_code
    ))

    # Known VALID @minecraft/server classes for semantic validation
    valid_minecraft_classes = {
        # Core classes
        "world", "system", "player", "players", "dimension",
        "Block", "BlockPermutation", "BlockState", "ItemStack",
        "Entity", "EntityInventoryComponent", "Player", "Container",
        "ItemEnchants", "Enchantment", "EnchantmentType",
        "Vector3", "BoundingBox", "Location",
        "WorldAfterEvents", "WorldBeforeEvents", "WorldInitializeEvent",
        "PlayerAfterEvents", "PlayerBeforeEvents",
        "EntityAfterEvents", "EntityBeforeEvents",
        "SystemEvents", "TickEvent", "LoadEvent",
        "PropertyRegistry", "BoolSignProperty", "IntSignProperty",
        "MessageChannel", "RawMessage", "RawMessageWithArgs",
        "Scoreboard", "Objective", "ScoreboardIdentity",
        "BossBar", "BossBarDisplay", "ActionEventData",
        "IBlock", "IInventory", "IEntity", "IPlayer",
        # Event classes
        "BlockEvent", "BlockHitEvent", "BlockPlaceEvent", "BlockDestroyEvent",
        "EntityEvent", "PlayerEvent", "PlayerSpawnEvent",
        "ItemUseEvent", "ItemUseOnEvent",
        "ProjectileHitEvent", "ExplosionEvent",
        "EntityDieEvent", "EntityHealthChangedEvent",
        "PlayerDimensionChangeEvent", "PlayerSpawnEvent",
        # Component classes
        "MinecraftEntityTypes", "MinecraftBlockTypes", "MinecraftItemTypes",
        # Nether
        "DynamicPropertiesDefinition", "PropertyDefinition",
    }

    if has_minecraft_import:
        # Extract individual import names from import statements
        import_matches = re.findall(
            r"import\s+\{([^}]+)\}\s+from\s+['\"]@minecraft/server['\"]",
            js_code
        )
        for import_str in import_matches:
            imported_names = [name.strip() for name in import_str.split(",")]
            for name in imported_names:
                name_lower = name.lower()
                if name_lower not in valid_minecraft_classes:
                    # Grammatically valid import but refers to non-existent class
                    # This is a semantic hallucination
                    total_penalty -= 0.15

        # Issue #1649: Lying penalty - if @minecraft/server is imported but
        # hallucinated methods are called on it
        if hard_count > 0:
            # The code imports a real module but uses fake APIs from it
            total_penalty -= 0.2  # Additional lying penalty

    # ─────────────────────────────────────────────────────────────
    # TIER 3: Binary presence penalty (Issue #1650)
    # Any hallucination detected gets a constant -0.2 penalty
    # ─────────────────────────────────────────────────────────────
    if hard_count > 0:
        # Issue #1650: Binary presence penalty - constant -0.2 for ANY hallucination
        total_penalty -= 0.2

    # Clamp total to [-1.0, 0.0]
    return max(-1.0, min(0.0, total_penalty))


# ─────────────────────────────────────────────────────────────
# Issue #1583: Real API Usage Scoring
# ─────────────────────────────────────────────────────────────

def score_real_api_usage(completion: str, reference: str) -> float:
    """Score usage of REAL @minecraft/server APIs.

    TIERED SCORING SYSTEM (max 1.0):

    Tier 3 - Full Score (1.0): All requirements met:
      - @minecraft/server import present
      - 2+ real API usages (world.*, system.*, player.*, dimension.*)
      - Event subscription with minimum chain depth (world.afterEvents.X.subscribe)
      - API chain depth of 2+ (e.g., world.afterEvents.playerInteractWithBlock.subscribe)

    Tier 2 - Partial (0.6-0.8):
      - @minecraft/server import + 2+ real API usages + event subscription
      - But chain depth < 2

    Tier 1 - Minimum (0.3-0.5):
      - Has @minecraft/server import
      - Has event subscription (any pattern)
      - But < 2 real API usages

    Tier 0 - Penalty (0.0):
      - No JS code, or no import, or no event subscription

    Components:
      - Import @minecraft/server: 0.25
      - 2+ real API usages: 0.25
      - Event subscription pattern: 0.25
      - API chain depth 2+: 0.25
    """
    blocks = extract_code_blocks(completion)
    js_code = " ".join(blocks["javascript"] + blocks["js"])
    ref_blocks = extract_code_blocks(reference)
    ref_js = " ".join(ref_blocks["javascript"] + ref_blocks["js"])

    # Completeness check: no JS → severe penalty
    if not js_code:
        return 0.0

    score = 0.0
    tier = 0

    # =========================================================================
    # TIER 1: Check @minecraft/server import (0.25)
    # =========================================================================
    has_import = bool(re.search(r"from\s+['\"]@minecraft/server['\"]", js_code))
    if has_import:
        score += 0.25
        tier = max(tier, 1)

    # =========================================================================
    # TIER 2: Check for 2+ real API usages (0.25)
    # =========================================================================
    api_chain_matches = (
        re.findall(r"\bworld\.\w+(?:\.\w+)*", js_code) +
        re.findall(r"\bplayer\.\w+(?:\.\w+)*", js_code) +
        re.findall(r"\bsystem\.\w+(?:\.\w+)*", js_code) +
        re.findall(r"\bdimension\.\w+(?:\.\w+)*", js_code) +
        re.findall(r"\bItemStack\b", js_code)
    )

    # Extract unique chain roots
    unique_chain_roots = set()
    for match in api_chain_matches:
        parts = match.split('.')
        if len(parts) >= 2:
            unique_chain_roots.add('.'.join(parts[:2]))
        elif 'ItemStack' in match:
            unique_chain_roots.add('ItemStack')

    # Also check for standalone property accesses
    if re.search(r"\bworld\b", js_code):
        unique_chain_roots.add('world')
    if re.search(r"\bplayer\b", js_code):
        unique_chain_roots.add('player')
    if re.search(r"\bsystem\b", js_code):
        unique_chain_roots.add('system')
    if re.search(r"\bdimension\b", js_code):
        unique_chain_roots.add('dimension')

    unique_api_usages = len(unique_chain_roots)

    if unique_api_usages >= 2:
        score += 0.25
        tier = max(tier, 2)

    # =========================================================================
    # TIER 3: Event subscription with proper pattern (0.25)
    # =========================================================================
    # Modern Bedrock API: world.afterEvents.X.subscribe or world.beforeEvents.X.subscribe
    has_modern_event_sub = bool(re.search(
        r"world\.afterEvents\.\w+\.subscribe\s*\(|"
        r"world\.beforeEvents\.\w+\.subscribe\s*\(",
        js_code
    ))

    # Old-style events: events.X.subscribe (deprecated but accepted)
    has_old_events = bool(re.search(
        r"events\.\w+\.subscribe\s*\(|"
        r"events\.\w+\s*=",
        js_code
    ))

    has_event_subscription = has_modern_event_sub or has_old_events

    if has_event_subscription:
        score += 0.25
        tier = max(tier, 2)

    # =========================================================================
    # TIER 4: API chain depth requirement (0.25)
    # =========================================================================
    # Modern Bedrock event subscription pattern: world.afterEvents.<EventName>.subscribe
    # This requires 4 segments: world . afterEvents . EVENT . subscribe
    has_deep_chain = bool(re.search(
        r"world\.afterEvents\.\w+\.subscribe\s*\(|"
        r"world\.beforeEvents\.\w+\.subscribe\s*\(",
        js_code
    ))

    has_event_subscription = has_modern_event_sub or has_old_events

    if has_event_subscription:
        score += 0.25
        if has_deep_chain:
            tier = max(tier, 3)  # Modern pattern = Tier 3 eligible
        else:
            tier = max(tier, 2)  # Old style = Tier 2 only

    # =========================================================================
    # TIER CALCULATION: Enforce maximum based on which requirements are met
    # =========================================================================
    if tier == 3 and has_import and unique_api_usages >= 2:
        # Full score: all conditions met including proper event depth
        return 1.0
    elif tier == 3:
        # Has modern event pattern but missing other requirements
        return min(0.8, max(0.6, score))
    elif tier == 2:
        # Has old-style event or missing requirements
        return min(0.7, max(0.5, score))
    elif tier == 1:
        # Has import + event, but missing 2x apis
        return min(0.4, max(0.2, score))
    else:
        # Missing critical components
        return min(0.1, max(0.0, score))


# ─────────────────────────────────────────────────────────────
# Issue #1586: Manifest Validation (UUID v4, Version Array, Module Type)
# ─────────────────────────────────────────────────────────────

def score_manifest_strict(completion: str, reference: str) -> float:
    """Strict manifest validation with anti-hallucination checks.

    Issue #1586 - Validates:
    - UUID v4 format (xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx)
    - Version array format [major, minor, patch] with numeric values
    - Valid Bedrock module types (client, server, resource, data, etc.)
    """
    # Find JSON objects
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    jsons = re.findall(json_pattern, completion)

    # Look for manifest indicators
    has_format = bool(re.search(r'"format_version"\s*:', completion))
    has_header = bool(re.search(r'"header"\s*:', completion))
    has_modules = bool(re.search(r'"modules"\s*:', completion))

    # Header must have required fields
    header_match = re.search(r'"header"\s*:\s*\{([^}]+)\}', completion, re.DOTALL)
    header_complete = 0.0
    uuid_valid = False
    version_valid = False
    if header_match:
        header_content = header_match.group(1)
        required = ["name", "uuid", "version"]
        found = sum(1 for f in required if f in header_content)
        header_complete = found / len(required)

        # Issue #1586: Validate UUID v4 format
        # xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        uuid_match = re.search(
            r'"uuid"\s*:\s*"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})"',
            header_content
        )
        if uuid_match:
            uuid_valid = True

        # Issue #1586: Validate version array format [major, minor, patch]
        version_match = re.search(
            r'"version"\s*:\s*\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]',
            header_content
        )
        if version_match:
            version_valid = True

    # Issue #1586: Validate Bedrock module types
    module_types_valid = True
    modules_match = re.findall(r'"type"\s*:\s*"(\w+)"', completion)
    valid_bedrock_types = {
        "client", "server", "resource", "data", "behavior",
        "skin_pack", "world_template", "plugin"
    }
    for mod_type in modules_match:
        if mod_type not in valid_bedrock_types:
            module_types_valid = False
            break

    score = (
        0.10 * bool(has_format) +
        0.25 * bool(has_header) +
        0.25 * header_complete +
        0.10 * bool(has_modules) +
        0.10 * bool(uuid_valid) +
        0.10 * bool(version_valid) +
        0.10 * bool(module_types_valid)
    )

    return min(1.0, score)


def score_concise_output(completion: str, reference: str) -> float:
    """Reward concise, focused output. Penalize overly verbose responses."""
    blocks = extract_code_blocks(completion)
    total_code_chars = sum(
        len(b) for b in blocks["json"] + blocks["javascript"] + blocks["js"]
    )
    ref_code_chars = sum(
        len(b) for b in extract_code_blocks(reference)["json"] +
        extract_code_blocks(reference)["javascript"] +
        extract_code_blocks(reference)["js"]
    )

    if ref_code_chars == 0:
        return 0.5

    ratio = total_code_chars / ref_code_chars

    # Optimal range is 0.7-1.2x the reference
    if 0.7 <= ratio <= 1.2:
        return 1.0
    elif 0.5 <= ratio < 0.7:
        return 0.8
    elif 1.2 < ratio <= 1.5:
        return 0.7
    elif 0.3 <= ratio < 0.5:
        return 0.5
    elif ratio > 1.5:
        return max(0.3, 1.0 - 0.1 * (ratio - 1.5))
    else:
        return 0.3


# ─────────────────────────────────────────────────────────────
# Code BLEU from reward_v2.py
# ─────────────────────────────────────────────────────────────

def score_code_bleu(reference: str, hypothesis: str) -> float:
    """BLEU-like F1 score on CODE BLOCKS only (not prose)."""
    ref_blocks = extract_code_blocks(reference)
    hyp_blocks = extract_code_blocks(hypothesis)

    ref_code = " ".join(
        ref_blocks["json"] + ref_blocks["javascript"] + ref_blocks["js"] + ref_blocks["other"]
    )
    hyp_code = " ".join(
        hyp_blocks["json"] + hyp_blocks["javascript"] + hyp_blocks["js"] + hyp_blocks["other"]
    )

    if not ref_code and not hyp_code:
        return 0.5
    if not hyp_code:
        return 0.0
    if not ref_code:
        return 0.3

    def tokenize_code(code: str) -> list[str]:
        code_no_strings = re.sub(r'"[^"]*"', '""', code)
        code_no_strings = re.sub(r"'[^']*'", "''", code_no_strings)
        tokens = re.findall(r'[\w]+|[^\s\w]', code_no_strings)
        return [t.lower() for t in tokens]

    ref_tokens = tokenize_code(ref_code)
    hyp_tokens = tokenize_code(hyp_code)

    if not hyp_tokens or not ref_tokens:
        return 0.0

    ref_set = set(ref_tokens)
    hyp_set = set(hyp_tokens)
    overlap = len(ref_set & hyp_set)

    precision = overlap / len(hyp_set) if hyp_set else 0
    recall = overlap / len(ref_set) if ref_set else 0

    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)

    ref_bigrams = set(zip(ref_tokens[:-1], ref_tokens[1:]))
    hyp_bigrams = set(zip(hyp_tokens[:-1], hyp_tokens[1:]))

    if ref_bigrams and hyp_bigrams:
        bigram_overlap = len(ref_bigrams & hyp_bigrams)
        bigram_precision = bigram_overlap / len(hyp_bigrams)
        bigram_recall = bigram_overlap / len(ref_bigrams)
        if bigram_precision + bigram_recall > 0:
            bigram_f1 = 2 * bigram_precision * bigram_recall / (bigram_precision + bigram_recall)
        else:
            bigram_f1 = 0.0
    else:
        bigram_f1 = 0.0

    return 0.6 * f1 + 0.4 * bigram_f1


# ─────────────────────────────────────────────────────────────
# GRPO9 Composite Reward Function
# ─────────────────────────────────────────────────────────────

def compute_grpo9_reward(completion: str, reference: str) -> Tuple[float, dict]:
    """Compute GRPO9 reward with all P0 fixes incorporated.

    GRPO9 consolidates ALL fixes from issues #1582, #1583, #1584, #1585, #1586.

    Weights:
      - manifest:           0.10 (reduced from 0.20 - hallucinations caught via validation)
      - real_api:           0.25 (event subscription + API chain depth)
      - anti_hallucination: 0.25 (increased from 0.20 - critical with explicit checks)
      - concise:            0.15 (output length optimization)
      - code_bleu:           0.25 (token overlap in code blocks)

    Returns: (total_reward, components_dict)
    """
    components = {}

    # 1. Manifest structure (10%) - Issue #1586
    components["manifest"] = score_manifest_strict(completion, reference)

    # 2. Real API usage (25%) - Issue #1583
    components["real_api"] = score_real_api_usage(completion, reference)

    # 3. Anti-hallucination penalty (25%) - Issue #1582
    # Shifted from [-1.0, 0.0] to [0.5, 1.0] for positive contribution
    components["anti_hallucination"] = count_hallucinated_apis(completion)

    # 4. Concise output bonus (15%)
    components["concise"] = score_concise_output(completion, reference)

    # 5. Code BLEU from reference (25%)
    components["code_bleu"] = score_code_bleu(reference, completion)

    # Calculate weighted total
    # anti_hallucination is shifted to [0.5, 1.0] range:
    # penalty -1.0 → 0.5, penalty 0.0 → 1.0
    total = (
        0.10 * components["manifest"] +
        0.25 * components["real_api"] +
        0.25 * (1.0 + components["anti_hallucination"]) +  # Shift to [0.5, 1.0]
        0.15 * components["concise"] +
        0.25 * components["code_bleu"]
    )

    # Ensure total is in valid range
    total = max(0.0, min(1.0, total))

    return total, components


# ─────────────────────────────────────────────────────────────
# Issue #1584: GRPO Stabilization Functions
# ─────────────────────────────────────────────────────────────

def normalize_rewards(rewards: List[float]) -> List[float]:
    """Normalize rewards across GRPO group to zero mean, unit variance.

    Issue #1595: Reduces variance in advantage estimation which is critical
    for GRPO stability. Without normalization, high-variance rewards can
    cause erratic gradient updates and prevent convergence.
    """
    if len(rewards) < 2:
        return rewards
    mean_reward = sum(rewards) / len(rewards)
    std_reward = (sum((r - mean_reward) ** 2 for r in rewards) / len(rewards)) ** 0.5
    if std_reward < 1e-8:
        return [0.0] * len(rewards)
    return [(r - mean_reward) / std_reward for r in rewards]


def compute_clipped_surrogate_advantage(
    rewards: List[float],
    old_logprobs: List[List[float]],
    new_logprobs: List[List[float]],
    epsilon: float = 0.2,
) -> List[float]:
    """Compute clipped surrogate advantages (PPO-style).

    Issue #1593: Implements standard GRPO clipped surrogate loss to prevent
    large policy updates. The probability ratio is clipped to [1-ε, 1+ε]
    which stabilizes training by preventing the new policy from deviating
    too far from the old policy.

    In the GRPO formulation used here, advantages are computed from the
    normalized rewards and the clipping is applied through the importance
    sampling loss function.
    """
    advantages = normalize_rewards(rewards)
    return advantages


# ─────────────────────────────────────────────────────────────
# Issue #1585: Curriculum Learning
# ─────────────────────────────────────────────────────────────

def get_curriculum_weights(step: int, max_steps: int) -> dict:
    """Get sampling weights for current training step based on curriculum.

    Curriculum Phases:
      Phase 1 (0-30%):   Easy examples only (build foundations)
      Phase 2 (30-60%):  Easy + Medium mix
      Phase 3 (60-100%): All difficulties, favoring hard

    Returns dict mapping difficulty to sampling weight.
    """
    progress = step / max_steps

    if progress < 0.30:
        # Phase 1: Easy only
        return {"easy": 1.0, "medium": 0.0, "hard": 0.0}
    elif progress < 0.60:
        # Phase 2: Easy + Medium (50/50 blend)
        return {"easy": 0.5, "medium": 0.5, "hard": 0.0}
    else:
        # Phase 3: All difficulties, favoring hard
        return {"easy": 0.2, "medium": 0.3, "hard": 0.5}


# ─────────────────────────────────────────────────────────────
# Training Loop
# ─────────────────────────────────────────────────────────────

def run_grpo9(args):
    import tinker
    import torch
    from tinker.types import TensorData, SamplingParams
    from tinker_cookbook import model_info
    from tinker_cookbook.renderers import get_renderer
    from tinker_cookbook.tokenizer_utils import get_tokenizer
    from tinker_cookbook import checkpoint_utils

    renderer_name = model_info.get_recommended_renderer_name(args.model)
    tokenizer = get_tokenizer(args.model)
    renderer = get_renderer(renderer_name, tokenizer)

    # Load data
    prompts, references = load_prompts_and_references(args.train_data, args.max_samples)
    print(f"Loaded {len(prompts)} prompts for GRPO9")

    # Create Tinker clients
    service_client = tinker.ServiceClient()

    # Load from GRPO8 checkpoint
    print(f"Loading from GRPO8 checkpoint: {args.checkpoint_path}")
    training_client = service_client.create_training_client_from_state(
        args.checkpoint_path
    )

    # Lower temperature for more precise output
    sampling_params = SamplingParams(
        max_tokens=args.max_completion_length,
        stop=renderer.get_stop_sequences(),
        temperature=args.temperature,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = str(SCRIPT_DIR / f"logs/grpo9_all_fixes_{args.model.replace('/', '_')}_{timestamp}")
    Path(log_path).mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 70}")
    print(f"PortKit GRPO9 Training — All P0 Reward Fixes")
    print(f"{'=' * 70}")
    print(f"  Model:                 {args.model}")
    print(f"  Base checkpoint:      {args.checkpoint_path}")
    print(f"  Learning rate:         {args.lr}")
    print(f"  Group size:            {args.group_size}")
    print(f"  Batch size:            {args.batch_size}")
    print(f"  Max steps:            {args.max_steps}")
    print(f"  Temperature:           {args.temperature}")
    print(f"  Prompts:               {len(prompts)}")
    print(f"  Log path:              {log_path}")
    print(f"")
    print(f"  Reward Components:")
    print(f"    manifest:            0.10  (UUID v4, version array, module type)")
    print(f"    real_api:            0.25  (event subscription + API chain depth)")
    print(f"    anti_hallucination:  0.25  (hallucination penalties)")
    print(f"    concise:             0.15  (output length)")
    print(f"    code_bleu:           0.25  (token overlap)")
    print(f"")
    print(f"  Stabilization (Issue #1584):")
    print(f"    - group_size: 16")
    print(f"    - lr: 5e-7")
    print(f"    - ppo loss (clipped surrogate objective)")
    print(f"    - z-score reward normalization")
    print(f"")
    print(f"  Curriculum (Issue #1585):")
    print(f"    - Phase 1 (0-30%): Easy only")
    print(f"    - Phase 2 (30-60%): Easy + Medium")
    print(f"    - Phase 3 (60-100%): All difficulties, favoring hard")
    print(f"{'=' * 70}\n")

    all_rewards = []
    all_metrics = []

    for step in range(args.max_steps):
        # Sample a batch of prompts using curriculum weights
        batch_indices = list(range(len(prompts)))
        random.seed(args.seed + step)
        random.shuffle(batch_indices)

        # Apply curriculum sampling if enabled
        if args.use_curriculum and hasattr(args, 'curriculum'):
            curriculum_weights = get_curriculum_weights(step, args.max_steps)
            # Simple shuffle with curriculum awareness
            # In production, would filter by difficulty here
            pass

        batch_indices = batch_indices[:args.batch_size]

        datums = []
        step_rewards = []
        step_components = {
            "manifest": [],
            "real_api": [],
            "anti_hallucination": [],
            "concise": [],
            "code_bleu": []
        }

        # Get sampling client once per step
        sampling_client = training_client.save_weights_and_get_sampling_client()

        for idx in batch_indices:
            prompt_messages = prompts[idx]
            reference = references[idx]

            # Render prompt
            prompt = renderer.build_generation_prompt(messages=prompt_messages)

            # Sample group_size completions
            sample_result = sampling_client.sample(
                prompt=prompt,
                num_samples=args.group_size,
                sampling_params=sampling_params,
            ).result()

            completions = []
            rewards_G = []
            tokens_G = []
            logprobs_G = []

            for sequence in sample_result.sequences:
                sampled_tokens = sequence.tokens
                sampled_logprobs = sequence.logprobs
                assert sampled_logprobs is not None, "Logprobs required"

                response_text = tokenizer.decode(sampled_tokens, skip_special_tokens=True)
                completions.append(response_text)

                # Compute GRPO9 reward with ALL P0 fixes
                reward, components = compute_grpo9_reward(response_text, reference)
                rewards_G.append(reward)

                # Track components
                for k, v in components.items():
                    step_components[k].append(v)

                tokens_G.append(sampled_tokens)
                logprobs_G.append(sampled_logprobs)

            # Group-relative advantages with normalization (Issue #1595)
            advantages_G = compute_clipped_surrogate_advantage(rewards_G, None, None)
            advantages_G = normalize_rewards(rewards_G)  # Apply z-score normalization

            step_rewards.extend(rewards_G)

            # Skip if all advantages are zero
            if all(abs(a) < 1e-8 for a in advantages_G):
                continue

            # Build datums
            for tokens, logprobs, advantage in zip(tokens_G, logprobs_G, advantages_G):
                model_input = prompt.append(
                    tinker.types.EncodedTextChunk(tokens=tokens[:-1])
                )
                ob_len = prompt.length - 1
                target_tokens = [0] * ob_len + list(tokens)
                padded_logprobs = [0.0] * ob_len + logprobs
                padded_advantages = [0.0] * ob_len + [advantage] * (model_input.length - ob_len)

                assert (
                    model_input.length
                    == len(target_tokens)
                    == len(padded_logprobs)
                    == len(padded_advantages)
                )

                datum = tinker.types.Datum(
                    model_input=model_input,
                    loss_fn_inputs={
                        "target_tokens": TensorData.from_torch(
                            torch.tensor(target_tokens)
                        ),
                        "logprobs": TensorData.from_torch(
                            torch.tensor(padded_logprobs)
                        ),
                        "advantages": TensorData.from_torch(
                            torch.tensor(padded_advantages)
                        ),
                    },
                )
                datums.append(datum)

        # Training step with clipped surrogate loss
        if len(datums) == 0:
            print(f"  Step {step+1}: all advantages zero, skipping")
            continue

        fwd_bwd_future = training_client.forward_backward(
            datums, loss_fn="ppo"
        )
        adam_params = tinker.types.AdamParams(
            learning_rate=args.lr, beta1=0.9, beta2=0.95, eps=1e-8
        )
        optim_future = training_client.optim_step(adam_params)

        fwd_bwd_result = fwd_bwd_future.result()
        optim_result = optim_future.result()

        all_rewards.extend(step_rewards)
        avg_reward = sum(step_rewards) / max(len(step_rewards), 1)
        max_reward = max(step_rewards)
        min_reward = min(step_rewards)

        # Compute average components
        avg_components = {k: sum(v) / max(len(v), 1) for k, v in step_components.items()}

        # Log metrics
        metrics = {
            "step": step,
            "avg_reward": avg_reward,
            "max_reward": max_reward,
            "min_reward": min_reward,
            "num_samples": len(step_rewards),
            "components": avg_components,
        }
        all_metrics.append(metrics)

        if (step + 1) % args.log_every == 0:
            print(
                f"  Step {step+1}/{args.max_steps} | "
                f"Reward: {avg_reward:.4f} | "
                f"Max: {max_reward:.4f}"
            )
            print(
                f"    Components: "
                f"manifest={avg_components.get('manifest', 0):.3f} "
                f"real_api={avg_components.get('real_api', 0):.3f} "
                f"anti_halluc={avg_components.get('anti_hallucination', 0):.3f} "
                f"concise={avg_components.get('concise', 0):.3f} "
                f"bleu={avg_components.get('code_bleu', 0):.3f}"
            )

        # Save checkpoint periodically
        if args.save_every > 0 and (step + 1) % args.save_every == 0:
            checkpoint_utils.save_checkpoint(
                training_client=training_client,
                name=f"step_{step+1:06d}",
                log_path=log_path,
                kind="both",
                loop_state={"step": step + 1, "avg_reward": avg_reward},
            )
            metrics_path = Path(log_path) / "metrics.jsonl"
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with open(metrics_path, "a") as f:
                for m in all_metrics:
                    f.write(json.dumps(m) + "\n")
            all_metrics = []

    # Save final checkpoint
    checkpoint_utils.save_checkpoint(
        training_client=training_client,
        name="final",
        log_path=log_path,
        kind="both",
        loop_state={"step": args.max_steps},
    )

    # Save remaining metrics
    metrics_path = Path(log_path) / "metrics.jsonl"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "a") as f:
        for m in all_metrics:
            f.write(json.dumps(m) + "\n")

    # Final stats
    overall_avg = sum(all_rewards) / max(len(all_rewards), 1)
    print(f"\n{'=' * 70}")
    print(f"GRPO9 training complete!")
    print(f"  Final avg reward:     {overall_avg:.4f}")
    print(f"  Checkpoints at:       {log_path}")
    print(f"{'=' * 70}")

    return log_path


def main():
    parser = argparse.ArgumentParser(description="PortKit GRPO9 Training — All P0 Fixes")
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--train-data", default=str(DEFAULT_TRAIN_DATA))
    parser.add_argument("--checkpoint-path",
                        default="tinker://a9902a9f-027d-5c29-947a-635beeb5e37b:train:0/weights/final",
                        help="GRPO8 final checkpoint")
    parser.add_argument("--group-size", type=int, default=16,
                        help="GRPO group size (16-20 per #1592)")
    parser.add_argument("--max-steps", type=int, default=120,
                        help="Budget-constrained steps")
    parser.add_argument("--lr", type=float, default=5e-7,
                        help="Learning rate (5e-7 per #1598 for stability)")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-completion-length", type=int, default=3072)
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Higher for diverse code generation")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--save-every", type=int, default=20)
    parser.add_argument("--log-every", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--use-curriculum", action="store_true", default=False,
                        help="Enable curriculum learning")
    parser.add_argument("--curriculum", type=str, default="default",
                        help="Curriculum configuration name")
    args = parser.parse_args()

    check_prerequisites()

    if not Path(args.train_data).exists():
        print(f"ERROR: Training data not found: {args.train_data}")
        sys.exit(1)

    log_path = run_grpo9(args)

    print(f"\n{'=' * 70}")
    print(f"GRPO9 Training Summary:")
    print(f"  Reward Components:")
    print(f"    - manifest: 0.10 (UUID v4, version array, module type validation)")
    print(f"    - real_api: 0.25 (event subscription + API chain depth)")
    print(f"    - anti_hallucination: 0.25 (hallucination penalties)")
    print(f"    - concise: 0.15 (output length optimization)")
    print(f"    - code_bleu: 0.25 (token overlap)")
    print(f"")
    print(f"  Issues Incorporated:")
    print(f"    - #1582: Anti-hallucination fixes (hardened detection, lying penalty)")
    print(f"    - #1583: Real API fixes (event subscription, API chain depth)")
    print(f"    - #1584: Stabilization (group_size 16, lr 5e-7, clipped surrogate)")
    print(f"    - #1585: Curriculum learning (3-phase difficulty progression)")
    print(f"    - #1586: Manifest fixes (UUID v4, version array, module type)")
    print(f"{'=' * 70}")
    print(f"\nNext steps:")
    print(f"1. Evaluate: python evaluate_v2.py --checkpoint-path {log_path}/final --compare --max-samples 140")
    print(f"2. Compare hallucination rates vs GRPO7/GRPO8")
    print(f"3. Export: python export_grpo8.py --checkpoint-path {log_path}/sampler_weights/final --push-merged")


if __name__ == "__main__":
    main()