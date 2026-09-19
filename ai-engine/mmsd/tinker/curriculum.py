#!/usr/bin/env python3
"""
PortKit Curriculum Learning for GRPO Training
=============================================
Implements difficulty-based curriculum learning for Minecraft Java→Bedrock conversion.

Curriculum Phases:
  Phase 1 (Steps 0-30%):   Easy only (foundational patterns)
  Phase 2 (Steps 30-60%):  Easy + Medium (building complexity)
  Phase 3 (Steps 60-100%): All difficulties (full range)

Difficulty Classification Criteria (Issue #1604):
  - Number of distinct Java classes/entities referenced
  - Complexity of event handling patterns
  - Number of Bedrock API chains required
  - Number of files/sections in output (manifest + scripts)
  - API usage depth (chain length)

Difficulty Buckets:
  Easy:   Single Block/Item conversion, simple events, 1-2 API calls
  Medium: Multiple entities, event chains, 3-4 API calls
  Hard:   Complex systems, custom entities, deep API chains (5+)

Author: PortKit AI Engine
Issues: #1585, #1604, #1609, #1610, #1616
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_TRAIN_DATA = DATA_DIR / "train.jsonl"


class Difficulty(Enum):
    """Difficulty levels for training examples."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class TrainingExample:
    """A training example with difficulty metadata."""

    idx: int
    messages: list[dict]
    difficulty: Difficulty
    difficulty_score: float
    # Detailed metrics
    java_entity_count: int
    event_pattern_count: int
    api_chain_depth: int
    output_file_count: int


@dataclass
class CurriculumConfig:
    """Configuration for curriculum learning phases."""

    # Phase boundaries (as fraction of max_steps)
    phase1_end: float = 0.30  # 0-30%: easy only
    phase2_end: float = 0.60  # 30-60%: easy + medium
    phase3_end: float = 1.00  # 60-100%: all difficulties

    # Sampling weights per phase
    # Format: {difficulty: weight}
    phase1_weights: dict = None  # Easy only
    phase2_weights: dict = None  # Easy + Medium
    phase3_weights: dict = None  # All difficulties

    def __post_init__(self):
        if self.phase1_weights is None:
            self.phase1_weights = {
                Difficulty.EASY: 1.0,
                Difficulty.MEDIUM: 0.0,
                Difficulty.HARD: 0.0,
            }
        if self.phase2_weights is None:
            self.phase2_weights = {
                Difficulty.EASY: 0.5,
                Difficulty.MEDIUM: 0.5,
                Difficulty.HARD: 0.0,
            }
        if self.phase3_weights is None:
            # Issue #1616: Weight harder examples higher as training progresses
            self.phase3_weights = {
                Difficulty.EASY: 0.2,
                Difficulty.MEDIUM: 0.3,
                Difficulty.HARD: 0.5,
            }


# ─────────────────────────────────────────────────────────────
# Difficulty Classification (Issue #1604)
# ─────────────────────────────────────────────────────────────


def count_java_entities(user_message: str) -> int:
    """Count distinct Java entities/classes referenced in source.

    Issues: #1604 - Complexity indicator
    """
    # Match class patterns: Block, Item, Entity, TileEntity, Registry, etc.
    patterns = [
        r"\bclass\s+\w+",  # Class definitions
        r"\b(Block|Item|Entity)\b",  # Core types
        r"\b(Block|Item|Entity)_\w+\b",  # Subclass variants
        r"@Mod\w*",  # Mod annotations
        r"@SubscribeEvent",  # Event subscribers
        r"\b(TileEntity|World)\b",  # Tile and world classes
    ]
    count = 0
    for pattern in patterns:
        matches = re.findall(pattern, user_message)
        count += len(set(matches))  # Deduplicate
    return count


def count_event_patterns(content: str) -> int:
    """Count event handling patterns in code.

    Issues: #1604 - Event complexity
    """
    event_patterns = [
        r"@SubscribeEvent",
        r"events?\.\w+\s*\(",
        r"EventHandler",
        r"(player|block|entity).(interact|break|place|use)\w*",
        r"TickEvent",
        r"LivingTickEvent",
        r"WorldTickEvent",
    ]
    count = 0
    for pattern in event_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        count += len(matches)
    return count


def measure_api_depth(code: str) -> int:
    """Measure API chain depth in Bedrock script.

    Issues: #1604 - API usage depth
    Higher depth = more complex API usage (e.g., world.afterEvents.X.subscribe)
    """
    max_depth = 0
    # Find all dot-access chains
    chains = re.findall(r"\b\w+(?:\.\w+)+\b", code)
    for chain in chains:
        depth = chain.count(".")
        max_depth = max(max_depth, depth)
    return max_depth


def count_output_files(assistant_content: str) -> int:
    """Count distinct files/sections in output.

    Issues: #1604 - Output complexity
    """
    files = set()
    # Manifest files
    if '"format_version"' in assistant_content or '"header"' in assistant_content:
        files.add("manifest")
    # JS/script files
    if "@minecraft/server" in assistant_content:
        files.add("script")
    # Entity definitions
    if re.search(r'"type"\s*:\s*"(entity|behavior)"', assistant_content):
        files.add("entity")
    # Item definitions
    if re.search(r'"type"\s*:\s*"(item|client|server)"', assistant_content):
        files.add("item")
    # Block definitions
    if re.search(r'"type"\s*:\s*"(block|data)"', assistant_content):
        files.add("block")
    return len(files) if files else 1  # At least one file/section


def classify_difficulty(
    java_entity_count: int,
    event_pattern_count: int,
    api_chain_depth: int,
    output_file_count: int,
) -> tuple[Difficulty, float]:
    """Classify example difficulty based on multiple metrics.

    Issues: #1604 - Difficulty classification criteria

    Returns:
        tuple of (Difficulty level, difficulty_score)

    Scoring Formula:
        score = 0.25 * java_entities + 0.20 * events + 0.30 * api_depth + 0.25 * files
    """
    # Issue #1616: Normalize metrics to 0-1 scale
    java_score = min(java_entity_count / 10, 1.0)  # 0-10 → 0-1
    event_score = min(event_pattern_count / 5, 1.0)  # 0-5 → 0-1
    api_score = min(api_chain_depth / 4, 1.0)  # 0-4 → 0-1
    file_score = min(output_file_count / 4, 1.0)  # 0-4 → 0-1

    weighted_score = 0.25 * java_score + 0.20 * event_score + 0.30 * api_score + 0.25 * file_score

    # Classify based on weighted score
    if weighted_score < 0.25:
        return Difficulty.EASY, weighted_score
    elif weighted_score < 0.50:
        return Difficulty.MEDIUM, weighted_score
    else:
        return Difficulty.HARD, weighted_score


# ─────────────────────────────────────────────────────────────
# Data Loading with Curriculum (Issue #1610)
# ─────────────────────────────────────────────────────────────


def compute_example_metrics(messages: list[dict]) -> dict:
    """Compute all metrics for a training example."""
    user_content = ""
    assistant_content = ""

    for msg in messages:
        if msg["role"] == "user":
            user_content += msg["content"]
        elif msg["role"] == "assistant":
            assistant_content += msg["content"]

    java_entity_count = count_java_entities(user_content)
    event_pattern_count = count_event_patterns(user_content + assistant_content)
    api_chain_depth = measure_api_depth(assistant_content)
    output_file_count = count_output_files(assistant_content)

    return {
        "java_entity_count": java_entity_count,
        "event_pattern_count": event_pattern_count,
        "api_chain_depth": api_chain_depth,
        "output_file_count": output_file_count,
    }


def load_training_examples(train_data_path: str) -> list[TrainingExample]:
    """Load all training examples with difficulty classification.

    Issues: #1609 - Classify existing 1260 training examples into difficulty buckets
    """
    examples = []

    with open(train_data_path) as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            data = json.loads(line)
            messages = data.get("messages", [])

            metrics = compute_example_metrics(messages)
            difficulty, score = classify_difficulty(
                java_entity_count=metrics["java_entity_count"],
                event_pattern_count=metrics["event_pattern_count"],
                api_chain_depth=metrics["api_chain_depth"],
                output_file_count=metrics["output_file_count"],
            )

            example = TrainingExample(
                idx=idx, messages=messages, difficulty=difficulty, difficulty_score=score, **metrics
            )
            examples.append(example)

    return examples


def load_prompts_and_references(train_data_path, max_samples=None):
    """Load training conversations (legacy interface).

    This function is kept for backward compatibility with existing training scripts.
    For curriculum learning, use load_training_examples() instead.
    """
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
# Curriculum Sampling (Issue #1610, #1616)
# ─────────────────────────────────────────────────────────────


def get_curriculum_weights(step: int, max_steps: int, config: CurriculumConfig) -> dict:
    """Get sampling weights for current training step.

    Issues: #1616 - Weight harder examples higher as training progresses

    As training progresses through phases:
      - Phase 1 (0-30%): Easy examples only (build foundations)
      - Phase 2 (30-60%): Mix of easy and medium
      - Phase 3 (60-100%): All difficulties, favoring hard
    """
    progress = step / max_steps

    if progress < config.phase1_end:
        return config.phase1_weights.copy()
    elif progress < config.phase2_end:
        # Interpolate between phase 1 and phase 2
        phase_progress = (progress - config.phase1_end) / (config.phase2_end - config.phase1_end)
        return _interpolate_weights(config.phase1_weights, config.phase2_weights, phase_progress)
    else:
        # Interpolate between phase 2 and phase 3
        phase_progress = (progress - config.phase2_end) / (config.phase3_end - config.phase2_end)
        return _interpolate_weights(config.phase2_weights, config.phase3_weights, phase_progress)


def _interpolate_weights(weights1: dict, weights2: dict, progress: float) -> dict:
    """Interpolate between two weight dictionaries."""
    result = {}
    all_keys = set(weights1.keys()) | set(weights2.keys())
    for key in all_keys:
        w1 = weights1.get(key, 0.0)
        w2 = weights2.get(key, 0.0)
        result[key] = w1 + (w2 - w1) * progress
    return result


def sample_curriculum_batch(
    examples: list[TrainingExample],
    step: int,
    max_steps: int,
    batch_size: int,
    config: Optional[CurriculumConfig] = None,
    seed: int = 42,
) -> list[int]:
    """Sample a batch of examples based on curriculum weights.

    Issues: #1610 - Implement curriculum phases
    Issues: #1616 - Weight harder examples higher as training progresses

    Args:
        examples: List of TrainingExample with difficulty metadata
        step: Current training step
        max_steps: Maximum training steps
        batch_size: Number of examples to sample
        config: Curriculum configuration
        seed: Random seed

    Returns:
        List of example indices to use in this batch
    """
    import random

    if config is None:
        config = CurriculumConfig()

    weights = get_curriculum_weights(step, max_steps, config)

    # Group examples by difficulty
    by_difficulty = {Difficulty.EASY: [], Difficulty.MEDIUM: [], Difficulty.HARD: []}
    for ex in examples:
        by_difficulty[ex.difficulty].append(ex.idx)

    # Sample from each difficulty pool according to weights
    sampled = []
    total_weight = sum(weights.values())

    for difficulty, weight in weights.items():
        if weight <= 0:
            continue
        # Allocate samples to this difficulty
        num_from_group = int(batch_size * (weight / total_weight))
        available = by_difficulty[difficulty]
        if available:
            sampled.extend(random.sample(available, min(num_from_group, len(available))))

    # Shuffle final batch
    random.shuffle(sampled)

    # Ensure we have batch_size examples (fill with easy if needed)
    if len(sampled) < batch_size:
        remaining = batch_size - len(sampled)
        easy_pool = by_difficulty[Difficulty.EASY]
        additional = [i for i in easy_pool if i not in sampled]
        sampled.extend(random.sample(additional, min(remaining, len(additional))))

    return sampled[:batch_size]


# ─────────────────────────────────────────────────────────────
# Difficulty Statistics
# ─────────────────────────────────────────────────────────────


def print_difficulty_stats(examples: list[TrainingExample]) -> None:
    """Print statistics about difficulty distribution."""
    by_difficulty = {Difficulty.EASY: 0, Difficulty.MEDIUM: 0, Difficulty.HARD: 0}
    for ex in examples:
        by_difficulty[ex.difficulty] += 1

    total = len(examples)

    print("\n" + "=" * 60)
    print("Curriculum Learning - Difficulty Distribution")
    print("=" * 60)
    print(f"  Total examples:  {total}")
    print(
        f"  Easy:            {by_difficulty[Difficulty.EASY]:5d} ({100 * by_difficulty[Difficulty.EASY] / total:.1f}%)"
    )
    print(
        f"  Medium:          {by_difficulty[Difficulty.MEDIUM]:5d} ({100 * by_difficulty[Difficulty.MEDIUM] / total:.1f}%)"
    )
    print(
        f"  Hard:            {by_difficulty[Difficulty.HARD]:5d} ({100 * by_difficulty[Difficulty.HARD] / total:.1f}%)"
    )
    print("=" * 60)

    # Print average scores by difficulty
    print("\nAverage Difficulty Scores:")
    for diff in Difficulty:
        scores = [ex.difficulty_score for ex in examples if ex.difficulty == diff]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {diff.value:8s}: {avg:.3f} (n={len(scores)})")


# ─────────────────────────────────────────────────────────────
# Main / Analysis
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PortKit Curriculum Learning Analysis")
    parser.add_argument("--train-data", default=str(DEFAULT_TRAIN_DATA))
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    print("Loading training data...")
    examples = load_training_examples(args.train_data)

    if args.max_samples:
        examples = examples[: args.max_samples]

    print_difficulty_stats(examples)

    # Show sample examples from each difficulty
    print("\nSample Examples:")
    for diff in Difficulty:
        samples = [ex for ex in examples if ex.difficulty == diff][:1]
        for ex in samples:
            print(f"\n  {diff.value.upper()} (score={ex.difficulty_score:.3f}):")
            print(f"    Java entities: {ex.java_entity_count}")
            print(f"    Event patterns: {ex.event_pattern_count}")
            print(f"    API depth: {ex.api_chain_depth}")
            print(f"    Output files: {ex.output_file_count}")
