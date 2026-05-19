#!/usr/bin/env python3
"""
APF (Aggressive-Partial-Functional) Reward Function for MMSD Fine-tuning
======================================================================

The APF reward encourages partial functionality - it provides meaningful
rewards for partially correct translations rather than requiring full correctness.

This is particularly valuable for:
1. Early training stages where full coverage is rare
2. Complex conversions where complete translation is difficult
3. Encouraging the model to translate what it CAN even if not everything

Key Design Decisions (Issue #1605):
  1. Entity coverage reward: 30% - Rewards block/item/entity definitions
  2. Event coverage reward: 30% - Rewards event handler translations
  3. API coverage reward: 25% - Rewards API call patterns
  4. Structural correctness: 15% - Rewards valid output structure

The APF reward isAGGGRESSIVE because:
  - Partial translations get significant rewards (not just 0)
  - Even 1 correct entity out of 5 earns reward
  - Coverage is computed from the IR, not just string matching

APF vs Traditional Rewards:
  - Traditional: All-or-nothing (full credit or no credit)
  - APF: Gradient of credit based on coverage percentage
  - APF: Can reward 40% correct even if 60% is missing

Author: PortKit AI Engine
Issues: #1578, #1605, #1621
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from pivot_ir.schema import PivotIR, compute_coverage


# ─────────────────────────────────────────────────────────────────────────────
# APF Reward Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class APFRewardConfig:
    """Configuration for APF reward computation.
    
    Attributes:
        entity_weight: Weight for entity coverage (0.0-1.0)
        event_weight: Weight for event coverage (0.0-1.0)
        api_weight: Weight for API coverage (0.0-1.0)
        structure_weight: Weight for structural correctness (0.0-1.0)
        partial_bonus: Bonus for having ANY partial functionality
        completeness_bonus: Bonus for approaching full coverage
        hallucination_penalty: Penalty per hallucinated API
        coverage_floor: Minimum coverage to get partial credit
    """
    entity_weight: float = 0.30
    event_weight: float = 0.30
    api_weight: float = 0.25
    structure_weight: float = 0.15
    partial_bonus: float = 0.10  # Bonus if ANY translation succeeded
    completeness_bonus: float = 0.05  # Bonus per 10% coverage
    hallucination_penalty: float = -0.15  # Per hallucinated API
    coverage_floor: float = 0.0  # Minimum coverage for partial credit


# Default configuration matching legacy reward weights
DEFAULT_APF_CONFIG = APFRewardConfig()


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Scoring Functions
# ─────────────────────────────────────────────────────────────────────────────

def score_entity_coverage(ir: PivotIR, reference_ir: Optional[PivotIR] = None) -> float:
    """Score entity coverage in the IR.
    
    Entities are blocks, items, and entities defined in the IR.
    Coverage = translated_entities / total_entities
    
    Args:
        ir: The generated Pivot IR
        reference_ir: Optional reference IR to compare against
        
    Returns:
        Coverage score in [0.0, 1.0]
    """
    if ir.total_entities == 0:
        # No entities to translate - check if this is correct
        return 0.5  # Neutral if no entities expected
    
    coverage = ir.translated_entities / ir.total_entities
    
    # Check for partial entities
    partial_count = 0
    for block in ir.blocks.values():
        if block.partial:
            partial_count += 1
    for item in ir.items.values():
        if item.partial:
            partial_count += 1
    for entity in ir.entities.values():
        if entity.partial:
            partial_count += 1
    
    # Partial entities get reduced credit
    if partial_count > 0:
        coverage *= 0.5  # 50% credit for partial
    
    return min(coverage, 1.0)


def score_event_coverage(ir: PivotIR, reference_ir: Optional[PivotIR] = None) -> float:
    """Score event handler coverage in the IR.
    
    Events are handlers that map Java events to Bedrock events.
    Coverage = translated_events / total_events
    
    Args:
        ir: The generated Pivot IR
        reference_ir: Optional reference IR to compare against
        
    Returns:
        Coverage score in [0.0, 1.0]
    """
    if ir.total_events == 0:
        return 0.5  # Neutral if no events expected
    
    coverage = ir.translated_events / ir.total_events
    
    # Check for partial translations
    partial_events = 0
    all_events = (
        list(ir.global_events) +
        [h for b in ir.blocks.values() for h in b.event_handlers] +
        [h for i in ir.items.values() for h in i.event_handlers] +
        [h for e in ir.entities.values() for h in e.event_handlers]
    )
    for event in all_events:
        if event.partial:
            partial_events += 1
    
    if partial_events > 0:
        coverage *= 0.75  # 75% credit for partial
    
    return min(coverage, 1.0)


def score_api_coverage(ir: PivotIR, reference_ir: Optional[PivotIR] = None) -> float:
    """Score API call coverage in the IR.
    
    APIs are method calls like player.sendMessage, world.getBlock, etc.
    Coverage = translated_apis / total_apis
    
    Args:
        ir: The generated Pivot IR
        reference_ir: Optional reference IR to compare against
        
    Returns:
        Coverage score in [0.0, 1.0]
    """
    if ir.total_api_calls == 0:
        return 0.5  # Neutral if no APIs expected
    
    coverage = ir.translated_api_calls / ir.total_api_calls
    
    # Check for partial API calls
    partial_apis = 0
    all_apis = (
        list(ir.global_apis) +
        [a for b in ir.blocks.values() for a in b.api_calls] +
        [a for i in ir.items.values() for a in i.api_calls] +
        [a for e in ir.entities.values() for a in e.api_calls]
    )
    for api in all_apis:
        if api.partial:
            partial_apis += 1
    
    if partial_apis > 0:
        coverage *= 0.9  # 90% credit for partial (APIs are often reusable)
    
    return min(coverage, 1.0)


def score_structure(completion: str, reference: str) -> float:
    """Score structural correctness of output.
    
    Checks:
    - Has valid JSON manifest
    - Has JavaScript code
    - Proper import statement
    - Event subscription pattern
    
    Args:
        completion: The generated output
        reference: The reference output
        
    Returns:
        Structure score in [0.0, 1.0]
    """
    score = 0.0
    
    # Check for JSON manifest
    json_blocks = re.findall(r"```json\s*(\{[^}]*(?:\{[^}]*\}[^}]*)*\})", completion, re.DOTALL)
    if json_blocks:
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if "format_version" in parsed or "header" in parsed:
                    score += 0.3
                    break
            except json.JSONDecodeError:
                pass
    
    # Check for JavaScript code
    js_blocks = re.findall(r"```(?:javascript|js)\s*([\s\S]*?)```", completion)
    if js_blocks:
        # Has JS code
        score += 0.2
        
        # Check for proper import
        if any("@minecraft/server" in block for block in js_blocks):
            score += 0.15
        
        # Check for event subscription pattern
        if any(".subscribe" in block for block in js_blocks):
            score += 0.15
    
    # Check for overall structure (non-code sections)
    has_conversion_plan = "Conversion" in completion or "Plan" in completion
    has_explanation = len(completion) > 200  # Some explanation present
    
    if has_conversion_plan:
        score += 0.05
    if has_explanation:
        score += 0.05
    
    # Penalize if reference has code but completion doesn't
    ref_has_json = '"format_version"' in reference or '"header"' in reference
    ref_has_js = "@minecraft/server" in reference or "world.afterEvents" in reference
    
    comp_has_json = '"format_version"' in completion or '"header"' in completion
    comp_has_js = "@minecraft/server" in completion or "world.afterEvents" in completion
    
    if ref_has_json and not comp_has_json:
        score -= 0.1
    if ref_has_js and not comp_has_js:
        score -= 0.1
    
    return min(max(score, 0.0), 1.0)


def count_hallucinated_apis_in_completion(completion: str) -> int:
    """Count hallucinated APIs in the completion text.
    
    This is used to penalize completely fabricated APIs.
    
    Args:
        completion: The generated output
        
    Returns:
        Count of hallucinated APIs
    """
    # Known hallucination patterns
    hallucinations = [
        r"\bServerPlayerAPI\b",
        r"\bPlayerAPI\b",
        r"\bWorldEvent\b",
        r"\bmodEventBus\b",
        r"\bBlockEntityAPI\b",
        r"\brequire\(['\"]@minecraft/server['\"]",
        r"\.createLightningBolt\(",
        r"\.spawnLightning\(",
        r"\.registerEvent\(",
        r"\.onServerStart\(",
        r"\.getTileEntity\(\).*\.getInventory\(",
        r"event\.level\.",
        r"server\.getWorld\(",
        r"getServer\(\)\.",
        r"Server\.getInstance\(\)",
    ]
    
    count = 0
    for pattern in hallucinations:
        matches = re.findall(pattern, completion, re.IGNORECASE)
        count += len(matches)
    
    return count


# ─────────────────────────────────────────────────────────────────────────────
# APF Reward Computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_apf_reward(
    completion: str,
    reference: str,
    ir: Optional[PivotIR] = None,
    config: Optional[APFRewardConfig] = None,
) -> tuple[float, dict[str, float]]:
    """Compute APF (Aggressive-Partial-Functional) reward.
    
    This reward function provides meaningful rewards for partial correctness:
    - Entity coverage: 30% of reward
    - Event coverage: 30% of reward
    - API coverage: 25% of reward
    - Structure: 15% of reward
    
    Plus bonuses for having ANY partial functionality.
    
    Args:
        completion: The generated output
        reference: The reference output
        ir: Optional Pivot IR to use for coverage (if not provided, extracts from completion)
        config: Optional APF configuration
        
    Returns:
        Tuple of (total_reward, component_scores dict)
    """
    if config is None:
        config = DEFAULT_APF_CONFIG
    
    component_scores = {}
    
    # ─────────────────────────────────────────────────────────────────
    # 1. Entity Coverage (30%)
    # ─────────────────────────────────────────────────────────────────
    if ir is not None:
        entity_score = score_entity_coverage(ir)
    else:
        # Fallback: estimate from completion
        entity_score = estimate_entity_coverage(completion)
    
    component_scores["entity_coverage"] = entity_score
    entity_reward = config.entity_weight * entity_score
    
    # ─────────────────────────────────────────────────────────────────
    # 2. Event Coverage (30%)
    # ─────────────────────────────────────────────────────────────────
    if ir is not None:
        event_score = score_event_coverage(ir)
    else:
        event_score = estimate_event_coverage(completion)
    
    component_scores["event_coverage"] = event_score
    event_reward = config.event_weight * event_score
    
    # ─────────────────────────────────────────────────────────────────
    # 3. API Coverage (25%)
    # ─────────────────────────────────────────────────────────────────
    if ir is not None:
        api_score = score_api_coverage(ir)
    else:
        api_score = estimate_api_coverage(completion)
    
    component_scores["api_coverage"] = api_score
    api_reward = config.api_weight * api_score
    
    # ─────────────────────────────────────────────────────────────────
    # 4. Structural Correctness (15%)
    # ─────────────────────────────────────────────────────────────────
    structure_score = score_structure(completion, reference)
    component_scores["structure"] = structure_score
    structure_reward = config.structure_weight * structure_score
    
    # ─────────────────────────────────────────────────────────────────
    # 5. Base Reward (partial functionality bonus)
    # ─────────────────────────────────────────────────────────────────
    has_any_translation = (
        entity_score > 0 or
        event_score > 0 or
        api_score > 0 or
        structure_score > 0.5
    )
    partial_bonus = config.partial_bonus if has_any_translation else 0.0
    component_scores["partial_bonus"] = partial_bonus
    
    # ─────────────────────────────────────────────────────────────────
    # 6. Completeness Bonus
    # ─────────────────────────────────────────────────────────────────
    overall_coverage = (entity_score + event_score + api_score) / 3
    completeness_steps = int(overall_coverage * 10)
    completeness_bonus = completeness_steps * config.completeness_bonus
    component_scores["completeness_bonus"] = completeness_bonus
    
    # ─────────────────────────────────────────────────────────────────
    # 7. Hallucination Penalty
    # ─────────────────────────────────────────────────────────────────
    hallucination_count = count_hallucinated_apis_in_completion(completion)
    hallucination_penalty = hallucination_count * config.hallucination_penalty
    component_scores["hallucination_count"] = hallucination_count
    component_scores["hallucination_penalty"] = hallucination_penalty
    
    # ─────────────────────────────────────────────────────────────────
    # Total Reward
    # ─────────────────────────────────────────────────────────────────
    total_reward = (
        entity_reward +
        event_reward +
        api_reward +
        structure_reward +
        partial_bonus +
        completeness_bonus +
        hallucination_penalty
    )
    
    # Clamp to valid range
    total_reward = min(max(total_reward, -0.5), 1.0)
    component_scores["total"] = total_reward
    
    return total_reward, component_scores


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Estimation (when IR not available)
# ─────────────────────────────────────────────────────────────────────────────

def estimate_entity_coverage(completion: str) -> float:
    """Estimate entity coverage from completion text.
    
    Used when Pivot IR is not provided.
    """
    # Check for manifest
    has_manifest = bool(re.search(r'"format_version"', completion) and re.search(r'"header"', completion))
    
    # Check for entity definitions
    has_entities = bool(re.search(r'"minecraft:\w+"', completion) or re.search(r"Entity\s*\(", completion))
    
    # Estimate based on manifest presence
    if has_manifest and has_entities:
        return 0.7
    elif has_manifest:
        return 0.5
    else:
        return 0.2


def estimate_event_coverage(completion: str) -> float:
    """Estimate event coverage from completion text.
    
    Used when Pivot IR is not provided.
    """
    # Check for event subscriptions
    modern_events = len(re.findall(r"world\.afterEvents\.\w+\.subscribe", completion))
    old_events = len(re.findall(r"events\.\w+\.subscribe", completion))
    
    total_events = modern_events + old_events
    
    if total_events >= 3:
        return 0.8
    elif total_events >= 1:
        return 0.5
    else:
        return 0.1


def estimate_api_coverage(completion: str) -> float:
    """Estimate API coverage from completion text.
    
    Used when Pivot IR is not provided.
    """
    # Check for real API usage
    world_apis = len(re.findall(r"world\.\w+", completion))
    player_apis = len(re.findall(r"player\.\w+", completion))
    dimension_apis = len(re.findall(r"dimension\.\w+", completion))
    
    total_apis = world_apis + player_apis + dimension_apis
    
    if total_apis >= 3:
        return 0.7
    elif total_apis >= 1:
        return 0.4
    else:
        return 0.1


# ─────────────────────────────────────────────────────────────────────────────
# Composite with Other Rewards
# ─────────────────────────────────────────────────────────────────────────────

def compute_apf_with_legacy(
    completion: str,
    reference: str,
    ir: Optional[PivotIR] = None,
    apf_weight: float = 0.6,
    legacy_weight: float = 0.4,
) -> tuple[float, dict[str, float]]:
    """Combine APF reward with legacy reward for hybrid training.
    
    Args:
        completion: The generated output
        reference: The reference output
        ir: Optional Pivot IR
        apf_weight: Weight for APF reward
        legacy_weight: Weight for legacy reward
        
    Returns:
        Tuple of (combined_reward, all component scores)
    """
    # Compute APF reward
    apf_reward, apf_components = compute_apf_reward(completion, reference, ir)
    
    # Import legacy reward
    try:
        from pivot_ir.reward import compute_reward as legacy_reward
    except ImportError:
        from reward import compute_reward as legacy_reward
    
    # Compute legacy reward
    legacy = legacy_reward(completion, reference)
    
    # Combine
    combined = apf_weight * apf_reward + legacy_weight * legacy
    
    # Add legacy component
    all_components = {**apf_components, "legacy_reward": legacy, "combined": combined}
    
    return combined, all_components


# ─────────────────────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test cases
    test_cases = [
        # Case 1: Good coverage
        ("Good translation", """
```json
{
  "format_version": 2,
  "header": {
    "name": "TestMod",
    "uuid": "abc-123",
    "version": [1, 0, 0]
  }
}
```

```javascript
import { world } from "@minecraft/server";

world.afterEvents.playerSpawn.subscribe((event) => {
    event.player.sendMessage("Welcome!");
});

world.afterEvents.tick.subscribe(() => {
    console.warn("Tick!");
});
```
"""),
        # Case 2: Partial coverage (only JSON)
        ("Partial (JSON only)", """
```json
{
  "format_version": 2,
  "header": {
    "name": "TestMod",
    "uuid": "def-456",
    "version": [1, 0, 0]
  }
}
```
"""),
        # Case 3: With hallucinations
        ("With hallucinations", """
```json
{
  "format_version": 2,
  "header": { "name": "TestMod" }
}
```

```javascript
import { world } from "@minecraft/server";
ServerPlayerAPI.registerMod("test");
world.createLightningBolt(player.getPosition());
```
"""),
    ]
    
    reference = """
```json
{
  "format_version": 2,
  "header": {
    "name": "TestMod",
    "uuid": "ref-123",
    "version": [1, 0, 0]
  }
}
```

```javascript
import { world, player } from "@minecraft/server";

world.afterEvents.playerSpawn.subscribe((event) => {
    event.player.sendMessage("Spawned!");
});

world.afterEvents.tick.subscribe(() => {
    // Tick handler
});
```
"""
    
    print("APF Reward Function Tests")
    print("=" * 70)
    
    for name, completion in test_cases:
        print(f"\n{name}:")
        reward, components = compute_apf_reward(completion, reference)
        print(f"  Total Reward: {reward:.3f}")
        for key, value in components.items():
            if key != "total":
                print(f"    {key}: {value:.3f}")
    
    print("\n" + "=" * 70)
    print("Combined APF + Legacy Test:")
    reward, components = compute_apf_with_legacy(
        test_cases[0][1], reference, apf_weight=0.6, legacy_weight=0.4
    )
    print(f"  Combined Reward: {reward:.3f}")
    print(f"    APF component: {components['total']:.3f}")
    print(f"    Legacy component: {components['legacy_reward']:.3f}")