#!/usr/bin/env python3
"""
Hallucination Injection Pipeline — Synthetic Training Data Generator
================================================================
Takes clean Java code and injects synthetic hallucinations to create
negative training examples for anti-hallucination training.

Usage:
    pipeline = HallucinationInjectionPipeline()
    synthetic_data = pipeline.generate_dataset(clean_samples, injection_rate=0.3)

Injection Strategy:
    1. Randomly select injection locations in code
    2. Choose hallucination type based on context
    3. Insert hallucination preserving code validity
    4. Label with ground truth for supervised learning
"""

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from hallucination_catalog import (
    HALLUCINATION_CATALOG,
    HallucinationPattern,
    HallucinationType,
)


@dataclass
class InjectionSite:
    """Location in code where hallucination can be injected."""
    line_number: int
    line_content: str
    context_before: List[str]
    context_after: List[str]
    insertion_point: int  # Character offset in line
    suitable_patterns: List[HallucinationPattern] = field(default_factory=list)


@dataclass
class InjectionResult:
    """Result of injecting a hallucination into code."""
    original_code: str
    injected_code: str
    injected_hallucination: str
    pattern_id: str
    injection_type: HallucinationType
    line_number: int
    is_valid: bool  # Code still parses/validates


class InjectionStrategy:
    """Base strategy for hallucination injection."""

    def __init__(self, catalog: Optional[type] = None):
        self.catalog = catalog or HALLUCINATION_CATALOG

    def select_pattern(self, context: str, available_patterns: List[HallucinationPattern]) -> Optional[HallucinationPattern]:
        """Select hallucination pattern based on context."""
        raise NotImplementedError


class RandomInjectionStrategy(InjectionStrategy):
    """Randomly select patterns regardless of context."""

    def select_pattern(self, context: str, available_patterns: List[HallucinationPattern]) -> Optional[HallucinationPattern]:
        if not available_patterns:
            return None
        return random.choice(available_patterns)


class ContextAwareInjectionStrategy(InjectionStrategy):
    """Select patterns based on code context (imports, existing patterns, etc.)."""

    def select_pattern(self, context: str, available_patterns: List[HallucinationPattern]) -> Optional[HallucinationPattern]:
        """Select pattern based on what would be believable in context."""
        has_import = bool(re.search(r"from\s+['\"]@minecraft/server['\"]", context))
        has_world = bool(re.search(r"\bworld\b", context))
        has_player = bool(re.search(r"\bplayer\b", context))
        has_system = bool(re.search(r"\bsystem\b", context))

        # Filter patterns by what's believable
        suitable = []
        for p in available_patterns:
            # If code imports @minecraft/server, semantic patterns more believable
            if has_import and p.Hallucination_type == HallucinationType.SEMANTIC:
                suitable.append(p)
            # If code uses world/player/system, hard patterns more believable
            elif (has_world or has_player or has_system) and p.Hallucination_type == HallucinationType.HARD:
                suitable.append(p)
            else:
                suitable.append(p)

        if not suitable:
            return None
        return random.choice(suitable)


class HallucinationInjectionPipeline:
    """
    Pipeline for injecting synthetic hallucinations into clean code.

    Generates negative training examples for anti-hallucination training.
    """

    # Hallucination templates for injection
    HALLUCINATION_TEMPLATES: dict[str, List[str]] = {
        # Hard hallucinations — fake classes and methods
        "hard_001": [  # ServerPlayerAPI
            "const playerApi = new ServerPlayerAPI();",
            "ServerPlayerAPI.getPlayerByName(name);",
        ],
        "hard_002": [  # ServerPlayer
            "const sp = new ServerPlayer(player);",
            "ServerPlayer.sendMessage('Hello');",
        ],
        "hard_003": [  # PlayerAPI
            "const api = PlayerAPI.getInstance();",
            "PlayerAPI.getAllPlayers();",
        ],
        "hard_004": [  # WorldEvent
            "WorldEvent.broadcast('tick');",
            "WorldEvent.listen('worldLoad', handler);",
        ],
        "hard_005": [  # modEventBus
            "modEventBus.register(handler);",
            "modEventBus.listen('tick', callback);",
        ],
        "hard_006": [  # BlockEntityAPI
            "const be = BlockEntityAPI.getByLocation(loc);",
            "BlockEntityAPI.create('chest', loc);",
        ],
        "hard_007": [  # EntityPlayerAPI
            "const ep = new EntityPlayerAPI(entity);",
            "EntityPlayerAPI.getEntitiesInRange(loc, 10);",
        ],
        "hard_008": [  # WorldAPI
            "const wa = WorldAPI.getInstance();",
            "WorldAPI.createWorld('new_world');",
        ],
        "hard_009": [  # require @minecraft/server
            "const { world } = require('@minecraft/server');",
            "const server = require('@minecraft/server');",
        ],
        "hard_010": [  # registerMod
            "registerMod({ id: 'my_mod', name: 'My Mod' });",
            "registerMod('my_mod', config);",
        ],
        "hard_011": [  # defineMod
            "defineMod('my_mod', { init: fn });",
            "defineMod({ name: 'test', version: '1.0' });",
        ],
        "hard_012": [  # createLightningBolt
            "world.createLightningBolt(player.location);",
            "dimension.createLightningBolt(location);",
        ],
        "hard_013": [  # spawnLightning
            "dimension.spawnLightning(location);",
            "world.spawnLightning(targetPos);",
        ],
        "hard_014": [  # registerEvent
            "player.registerEvent('interact', onInteract);",
            "world.registerEvent('playerJoin', handler);",
        ],
        "hard_015": [  # registerServerEvent
            "system.registerServerEvent('init', handler);",
            "world.registerServerEvent('worldStart', callback);",
        ],
        "hard_016": [  # onServerStart
            "world.onServerStart(() => { console.log('started'); });",
            "system.onServerStart(handler);",
        ],
        "hard_017": [  # onServerStop
            "world.onServerStop(() => { cleanup(); });",
            "system.onServerStop(handler);",
        ],
        "hard_018": [  # event.level
            "event.level.createBlock(location, 'stone');",
            "event.level.getEntities({ type: 'player' });",
        ],
        "hard_019": [  # server.getWorld
            "const w = server.getWorld('overworld');",
            "server.getWorld('nether');",
        ],
        "hard_020": [  # getServer()
            "getServer().getAllPlayers();",
            "getServer().broadcast('Hello!');",
        ],
        "hard_021": [  # Server.getInstance
            "Server.getInstance().getWorld('overworld');",
            "Server.getInstance().broadcast('msg');",
        ],
        "hard_022": [  # getTileEntity().getInventory
            "const inv = block.getTileEntity().getInventory();",
            "tile.getTileEntity().getInventory().addItem(item);",
        ],
        "hard_023": [  # world.setBlock with getPosition
            "world.setBlock(location.getPosition(), 'stone');",
            "world.setBlock(pos.getPosition(), blockType);",
        ],
        # Semantic hallucinations — valid syntax, wrong API
        "sem_001": [  # LightningBoltEvent
            "world.afterEvents.lightningBolt.subscribe(handler);",
            "import { LightningBoltEvent } from '@minecraft/server';",
        ],
        "sem_002": [  # PlayerEvent
            "player.PlayerEvent.subscribe(handler);",
            "world.PlayerEvent.onPlayerSpawn(handler);",
        ],
        "sem_003": [  # WorldEvent
            "world.WorldEvent.listen(handler);",
            "import { WorldEvent } from '@minecraft/server';",
        ],
        # Lingering — deprecated patterns
        "ling_001": [  # old register pattern
            "events.tick.register(onTick);",
            "events.blockPlace.register(handler, this);",
        ],
        "ling_002": [  # wrong import path
            "import { world } from 'minecraft/server';",
            "const { player } = require('minecraft/server');",
        ],
    }

    def __init__(
        self,
        strategy: Optional[InjectionStrategy] = None,
        seed: Optional[int] = None,
    ):
        """
        Initialize pipeline.

        Args:
            strategy: Pattern selection strategy (default: ContextAware)
            seed: Random seed for reproducibility
        """
        self.strategy = strategy or ContextAwareInjectionStrategy()
        self.catalog = HALLUCINATION_CATALOG
        if seed is not None:
            random.seed(seed)

    def find_injection_sites(self, code: str) -> List[InjectionSite]:
        """Find locations in code where hallucinations can be injected."""
        lines = code.split('\n')
        sites = []

        for i, line in enumerate(lines, 1):
            # Find good insertion points
            insertion_points = []

            # After imports
            if re.match(r"^\s*import\s+", line):
                insertion_points.append(len(line))

            # Inside functions after opening brace
            if re.search(r"\{\s*$", line):
                insertion_points.append(len(line))

            # At start of function body
            if re.search(r"\(\s*\)\s*\{", line):
                insertion_points.append(line.index('{') + 1)

            # After variable declarations
            if re.match(r"^\s*(const|let|var)\s+\w+", line):
                insertion_points.append(len(line))

            # At end of lines with semicolons (statement ends)
            if ';' in line and not line.strip().endswith('//'):
                insertion_points.append(len(line) - 1)

            for point in insertion_points:
                # Find suitable patterns for this context
                suitable = self._find_suitable_patterns(line, code)
                sites.append(InjectionSite(
                    line_number=i,
                    line_content=line,
                    context_before=lines[max(0, i-3):i],
                    context_after=lines[i:min(len(lines), i+2)],
                    insertion_point=point,
                    suitable_patterns=suitable
                ))

        return sites

    def _find_suitable_patterns(self, line: str, full_context: str) -> List[HallucinationPattern]:
        """Find hallucination patterns suitable for injection at this location."""
        suitable = []

        # If inside import block, suggest semantic patterns
        if re.match(r"^\s*import\s+", line):
            suitable.extend([
                p for p in self.catalog.SEMANTIC_HALLUCINATIONS
                if 'import' in p.description.lower()
            ])

        # If has @minecraft/server import, suggest hard patterns
        if re.search(r"@minecraft/server", full_context):
            suitable.extend(self.catalog.HARD_HALLUCINATIONS[:10])  # First 10 hard patterns

        # Suggest lingering patterns
        if re.search(r"import\s+\{", full_context):
            suitable.extend(self.catalog.LINGERING_HALLUCINATIONS)

        # Default to hard patterns
        if not suitable:
            suitable = self.catalog.HARD_HALLUCINATIONS[:5]

        return suitable

    def inject_hallucination(
        self,
        code: str,
        pattern: Optional[HallucinationPattern] = None,
        site: Optional[InjectionSite] = None,
    ) -> InjectionResult:
        """
        Inject a hallucination into code at a random or specified site.

        Args:
            code: Clean code to inject into
            pattern: Specific pattern to inject (random if None)
            site: Specific site to inject at (random if None)

        Returns:
            InjectionResult with original/injected code and metadata
        """
        sites = self.find_injection_sites(code)
        if not sites:
            return InjectionResult(
                original_code=code,
                injected_code=code,
                injected_hallucination="",
                pattern_id="",
                injection_type=HallucinationType.HARD,
                line_number=-1,
                is_valid=False
            )

        # Select site and pattern
        selected_site = site or random.choice(sites)
        available_patterns = selected_site.suitable_patterns if selected_site.suitable_patterns else self.catalog.HARD_HALLUCINATIONS
        selected_pattern = pattern or self.strategy.select_pattern(code, available_patterns)

        if not selected_pattern:
            return InjectionResult(
                original_code=code,
                injected_code=code,
                injected_hallucination="",
                pattern_id="",
                injection_type=HallucinationType.HARD,
                line_number=-1,
                is_valid=False
            )

        # Get hallucination template
        templates = self.HALLUCINATION_TEMPLATES.get(selected_pattern.id, [
            f"// Hallucinated: {selected_pattern.id}",
            f"const _fake_{selected_pattern.id} = {selected_pattern.pattern};"
        ])
        hallucination = random.choice(templates)

        # Insert hallucination
        lines = code.split('\n')
        line_idx = selected_site.line_number - 1
        line = lines[line_idx]

        # Insert at appropriate point
        if selected_site.insertion_point >= len(line):
            new_line = line + "\n" + hallucination
        else:
            new_line = line[:selected_site.insertion_point] + "\n" + hallucination + "\n" + line[selected_site.insertion_point:]

        lines[line_idx] = new_line
        injected_code = "\n".join(lines)

        return InjectionResult(
            original_code=code,
            injected_code=injected_code,
            injected_hallucination=hallucination,
            pattern_id=selected_pattern.id,
            injection_type=selected_pattern.Hallucination_type,
            line_number=selected_site.line_number,
            is_valid=True
        )

    def generate_dataset(
        self,
        clean_samples: List[dict],
        injection_rate: float = 0.3,
        max_injections_per_sample: int = 3,
    ) -> List[dict]:
        """
        Generate synthetic dataset with injected hallucinations.

        Args:
            clean_samples: List of dicts with 'prompt', 'completion' keys
            injection_rate: Probability of injecting hallucination per sample
            max_injections_per_sample: Maximum hallucinations per sample

        Returns:
            List of dicts with original and injected versions + labels
        """
        synthetic_data = []

        for sample in clean_samples:
            prompt = sample.get("prompt", "")
            completion = sample.get("completion", sample.get("reference", ""))

            # Decide number of injections
            n_injections = 0
            if random.random() < injection_rate:
                n_injections = random.randint(1, max_injections_per_sample)

            current_code = completion
            injected_hallucinations = []

            for _ in range(n_injections):
                result = self.inject_hallucination(current_code)
                if result.is_valid:
                    current_code = result.injected_code
                    injected_hallucinations.append({
                        "pattern_id": result.pattern_id,
                        "type": result.injection_type.value,
                        "hallucination": result.injected_hallucination,
                        "line": result.line_number,
                    })

            # Build synthetic sample
            synthetic_sample = {
                "prompt": prompt,
                "original_completion": completion,
                "augmented_completion": current_code,
                "has_hallucination": len(injected_hallucinations) > 0,
                "hallucination_count": len(injected_hallucinations),
                "hallucinations": injected_hallucinations,
                "is_synthetic": True,
            }
            synthetic_data.append(synthetic_sample)

            # Also add clean sample without injection
            clean_sample = {
                "prompt": prompt,
                "original_completion": completion,
                "augmented_completion": completion,
                "has_hallucination": False,
                "hallucination_count": 0,
                "hallucinations": [],
                "is_synthetic": True,
                "is_clean": True,
            }
            synthetic_data.append(clean_sample)

        return synthetic_data

    def save_dataset(self, dataset: List[dict], output_path: Path) -> None:
        """Save dataset to JSONL file."""
        with open(output_path, 'w') as f:
            for item in dataset:
                f.write(json.dumps(item) + '\n')


def load_clean_samples(data_path: Path) -> List[dict]:
    """Load clean training samples from JSONL."""
    samples = []
    with open(data_path) as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic hallucination data")
    parser.add_argument("--input", type=Path, required=True, help="Clean training data")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--rate", type=float, default=0.3, help="Injection rate")
    parser.add_argument("--max-per-sample", type=int, default=3, help="Max injections per sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print(f"Loading clean samples from {args.input}")
    clean_samples = load_clean_samples(args.input)
    print(f"Loaded {len(clean_samples)} clean samples")

    pipeline = HallucinationInjectionPipeline(seed=args.seed)
    synthetic_data = pipeline.generate_dataset(
        clean_samples,
        injection_rate=args.rate,
        max_injections_per_sample=args.max_per_sample
    )
    print(f"Generated {len(synthetic_data)} synthetic samples")

    pipeline.save_dataset(synthetic_data, args.output)
    print(f"Saved to {args.output}")

    # Stats
    with_halluc = sum(1 for d in synthetic_data if d["has_hallucination"])
    print(f"Samples with hallucinations: {with_halluc} ({100*with_halluc/len(synthetic_data):.1f}%)")
