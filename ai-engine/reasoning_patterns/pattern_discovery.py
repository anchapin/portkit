"""
Pattern Discovery Engine for Agentic Reasoning

Implements automatic discovery of optimal reasoning patterns using
environment feedback, based on "LLMs Improving LLMs" (arxiv:2605.08083v1).

The discovery process:
1. Generate candidate patterns for a feature type
2. Test patterns against validation outcomes
3. Score patterns based on conversion success
4. Select and refine best-performing patterns
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .reasoning_pattern import (
    ReasoningPattern,
    ReasoningStep,
    PatternPerformance,
    FeatureType,
    HANDCRAFTED_PATTERNS,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryConfig:
    """Configuration for pattern discovery."""

    min_sample_size: int = 5
    max_patterns_per_type: int = 10
    mutation_probability: float = 0.2
    crossover_probability: float = 0.3
    exploration_weight: float = 0.1
    exploitation_weight: float = 0.9
    early_stopping_threshold: float = 0.95
    convergence_check_interval: int = 10


@dataclass
class PatternCandidate:
    """A candidate pattern being evaluated during discovery."""

    pattern: ReasoningPattern
    performance: PatternPerformance
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    is_mutated: bool = False


class PatternDiscoveryEngine:
    """
    Discovers optimal reasoning patterns for test-time scaling.

    Uses evolutionary search with environment feedback to find patterns
    that maximize conversion success rates for each feature type.
    """

    def __init__(self, config: Optional[DiscoveryConfig] = None):
        """
        Initialize pattern discovery engine.

        Args:
            config: Discovery configuration
        """
        self.config = config or DiscoveryConfig()
        self.patterns: Dict[FeatureType, List[PatternCandidate]] = {ft: [] for ft in FeatureType}
        self.performance_cache: Dict[str, PatternPerformance] = {}
        self._initialize_handcrafted()

    def _initialize_handcrafted(self) -> None:
        """Initialize with handcrafted baseline patterns."""
        for pattern in HANDCRAFTED_PATTERNS:
            candidate = PatternCandidate(
                pattern=pattern,
                performance=PatternPerformance(
                    pattern_id=pattern.id,
                    feature_type=pattern.feature_type,
                ),
                generation=0,
            )
            self.patterns[pattern.feature_type].append(candidate)

    async def discover_patterns(
        self,
        feature_type: FeatureType,
        validation_fn: Callable[[ReasoningPattern, FeatureType], tuple[bool, float, float]],
        max_generations: int = 20,
    ) -> List[ReasoningPattern]:
        """
        Discover optimal patterns for a feature type.

        Args:
            feature_type: The feature type to optimize for
            validation_fn: Async function that tests a pattern and returns
                           (success: bool, reward: float, confidence: float)
            max_generations: Maximum evolutionary generations

        Returns:
            List of discovered patterns sorted by performance
        """
        logger.info(f"Starting pattern discovery for {feature_type.value}")

        for generation in range(max_generations):
            candidates = self.patterns.get(feature_type, [])

            if not candidates:
                logger.warning(f"No initial candidates for {feature_type.value}, using handcrafted")
                await self._seed_initial_candidates(feature_type)

            await self._evaluate_generation(feature_type, validation_fn)

            if generation < max_generations - 1:
                await self._evolve_generation(feature_type)

            if self._check_convergence(feature_type):
                logger.info(f"Converged at generation {generation + 1}")
                break

        return self._get_best_patterns(feature_type)

    async def _seed_initial_candidates(self, feature_type: FeatureType) -> None:
        """Seed initial candidates from handcrafted patterns."""
        for hp in HANDCRAFTED_PATTERNS:
            if hp.feature_type == feature_type or hp.feature_type == FeatureType.UNKNOWN:
                candidate = PatternCandidate(
                    pattern=hp,
                    performance=PatternPerformance(
                        pattern_id=hp.id,
                        feature_type=feature_type,
                    ),
                    generation=0,
                )
                self.patterns[feature_type].append(candidate)

    async def _evaluate_generation(
        self,
        feature_type: FeatureType,
        validation_fn: Callable[[ReasoningPattern, FeatureType], tuple[bool, float, float]],
    ) -> None:
        """Evaluate all candidates in current generation."""
        candidates = self.patterns.get(feature_type, [])
        evaluated = 0

        for candidate in candidates:
            if candidate.performance.total_attempts >= self.config.min_sample_size:
                continue

            try:
                success, reward, confidence = await validation_fn(candidate.pattern, feature_type)
                candidate.performance.record_attempt(success, reward, confidence)
                evaluated += 1
            except Exception as e:
                logger.warning(f"Validation failed for {candidate.pattern.id}: {e}")

        logger.info(
            f"Evaluated {evaluated} candidates for {feature_type.value}, "
            f"best score: {self._get_best_score(feature_type):.4f}"
        )

    async def _evolve_generation(self, feature_type: FeatureType) -> None:
        """Evolve patterns to next generation via mutation and crossover."""
        candidates = self.patterns.get(feature_type, [])
        if len(candidates) < 2:
            return

        scored = [(c, c.performance.get_score()) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)

        new_candidates: List[PatternCandidate] = []
        top_candidates = [c for c, _ in scored[:3]]

        for candidate, score in scored[: self.config.max_patterns_per_type // 2]:
            if random.random() < self.config.mutation_probability:
                mutated = self._mutate_pattern(candidate.pattern)
                if mutated:
                    new_candidates.append(
                        PatternCandidate(
                            pattern=mutated,
                            performance=PatternPerformance(
                                pattern_id=mutated.id,
                                feature_type=feature_type,
                            ),
                            generation=candidate.generation + 1,
                            parent_ids=[candidate.pattern.id],
                            is_mutated=True,
                        )
                    )

        if (
            len(candidates) >= 2
            and random.random() < self.config.crossover_probability
            and len(top_candidates) >= 2
        ):
            crossed = self._crossover_patterns(top_candidates[0].pattern, top_candidates[1].pattern)
            if crossed:
                new_candidates.append(
                    PatternCandidate(
                        pattern=crossed,
                        performance=PatternPerformance(
                            pattern_id=crossed.id,
                            feature_type=feature_type,
                        ),
                        generation=max(c.generation for c in candidates) + 1,
                        parent_ids=[top_candidates[0].pattern.id, top_candidates[1].pattern.id],
                    )
                )

        exploration_count = max(1, int(len(candidates) * self.config.exploration_weight))
        for _ in range(exploration_count):
            generated = self._generate_random_pattern(feature_type)
            if generated:
                new_candidates.append(
                    PatternCandidate(
                        pattern=generated,
                        performance=PatternPerformance(
                            pattern_id=generated.id,
                            feature_type=feature_type,
                        ),
                        generation=max(c.generation for c in candidates) + 1,
                    )
                )

        candidates.extend(new_candidates)

        candidates.sort(key=lambda c: c.performance.get_score(), reverse=True)
        self.patterns[feature_type] = candidates[: self.config.max_patterns_per_type]

    def _mutate_pattern(self, pattern: ReasoningPattern) -> Optional[ReasoningPattern]:
        """Mutate a pattern by modifying its steps."""
        if not pattern.steps:
            return None

        mutation_type = random.choice(["reorder", "modify", "add", "remove"])
        new_steps = [s for s in pattern.steps]

        if mutation_type == "reorder" and len(new_steps) > 1:
            idx1, idx2 = random.sample(range(len(new_steps)), 2)
            new_steps[idx1], new_steps[idx2] = new_steps[idx2], new_steps[idx1]
            for i, step in enumerate(new_steps):
                step.order = i + 1

        elif mutation_type == "modify" and new_steps:
            idx = random.randint(0, len(new_steps) - 1)
            step = new_steps[idx]
            new_action = self._mutate_action(step.action)
            new_steps[idx] = ReasoningStep(
                order=step.order,
                action=new_action,
                description=self._mutate_description(step.description),
                examples=step.examples,
                expected_output=step.expected_output,
            )

        elif mutation_type == "add" and len(new_steps) < 10:
            new_step = self._generate_random_step(len(new_steps) + 1)
            insert_pos = random.randint(0, len(new_steps))
            new_steps.insert(insert_pos, new_step)
            for i, step in enumerate(new_steps):
                step.order = i + 1

        elif mutation_type == "remove" and len(new_steps) > 2:
            idx = random.randint(0, len(new_steps) - 1)
            new_steps.pop(idx)
            for i, step in enumerate(new_steps):
                step.order = i + 1

        return ReasoningPattern(
            id=f"{pattern.id}_mut_{random.randint(1000, 9999)}",
            name=f"{pattern.name} (mutated)",
            description=pattern.description,
            feature_type=pattern.feature_type,
            steps=new_steps,
            success_threshold=pattern.success_threshold,
            is_discovered=True,
            metadata={"parent_id": pattern.id, "mutation_type": mutation_type},
        )

    def _mutate_action(self, action: str) -> str:
        """Mutate an action text."""
        mutations = [
            lambda a: a.replace("Analyze", "Examine"),
            lambda a: a.replace("Map", "Convert"),
            lambda a: a.replace("Handle", "Process"),
            lambda a: a.replace("Identify", "Detect"),
            lambda a: f"Carefully {a.lower()}",
            lambda a: f"Thoroughly {a.lower()}",
        ]
        return random.choice(mutations)(action)

    def _mutate_description(self, desc: str) -> str:
        """Mutate a description text."""
        mutations = [
            lambda d: d.replace(".", " with validation."),
            lambda d: f"Ensure proper {d.lower()}",
            lambda d: f"Verify {d.lower()}",
            lambda d: f"Carefully {d.lower()}",
        ]
        return random.choice(mutations)(desc)

    def _crossover_patterns(
        self, pattern1: ReasoningPattern, pattern2: ReasoningPattern
    ) -> Optional[ReasoningPattern]:
        """Create new pattern by combining elements of two patterns."""
        if not pattern1.steps or not pattern2.steps:
            return None

        steps1 = pattern1.steps
        steps2 = pattern2.steps

        pivot = random.randint(1, min(len(steps1), len(steps2)) - 1)
        new_steps = list(steps1[:pivot]) + list(steps2[pivot:])

        for i, step in enumerate(new_steps):
            step.order = i + 1

        return ReasoningPattern(
            id=f"cross_{pattern1.id}_{pattern2.id}_{random.randint(1000, 9999)}",
            name=f"Hybrid: {pattern1.name} + {pattern2.name}",
            description=f"Combines {pattern1.name} approach with {pattern2.name} strategy",
            feature_type=pattern1.feature_type,
            steps=new_steps,
            is_discovered=True,
            metadata={"crossover": True, "parents": [pattern1.id, pattern2.id]},
        )

    def _generate_random_pattern(self, feature_type: FeatureType) -> Optional[ReasoningPattern]:
        """Generate a random reasoning pattern."""
        step_count = random.randint(3, 7)
        steps = [self._generate_random_step(i + 1) for i in range(step_count)]

        return ReasoningPattern(
            id=f"generated_{feature_type.value}_{random.randint(10000, 99999)}",
            name=f"Generated {feature_type.value.replace('_', ' ').title()} Pattern",
            description=f"Auto-generated pattern for {feature_type.value} conversion",
            feature_type=feature_type,
            steps=steps,
            is_discovered=True,
        )

    def _generate_random_step(self, order: int) -> ReasoningStep:
        """Generate a random reasoning step."""
        actions = [
            "Analyze structure",
            "Identify components",
            "Map to equivalents",
            "Convert logic",
            "Handle edge cases",
            "Validate output",
            "Test behavior",
            "Document assumptions",
        ]
        return ReasoningStep(
            order=order,
            action=random.choice(actions),
            description=f"Auto-generated step {order}",
            examples=[],
            expected_output=None,
        )

    def _check_convergence(self, feature_type: FeatureType) -> bool:
        """Check if patterns have converged to optimal solutions."""
        candidates = self.patterns.get(feature_type, [])
        if len(candidates) < 2:
            return False

        scores = [c.performance.get_score() for c in candidates]
        top_score = max(scores)

        if top_score < 0.1:
            return False

        if top_score > self.config.early_stopping_threshold:
            return True

        variance = sum((s - top_score) ** 2 for s in scores) / len(scores)
        return variance < 0.01

    def _get_best_score(self, feature_type: FeatureType) -> float:
        """Get the best score for a feature type."""
        candidates = self.patterns.get(feature_type, [])
        if not candidates:
            return 0.0
        return max(c.performance.get_score() for c in candidates)

    def _get_best_patterns(self, feature_type: FeatureType) -> List[ReasoningPattern]:
        """Get the best performing patterns for a feature type."""
        candidates = self.patterns.get(feature_type, [])
        sorted_candidates = sorted(
            candidates, key=lambda c: c.performance.get_score(), reverse=True
        )

        discovered = [c for c in sorted_candidates if c.pattern.is_discovered]
        handcrafted = [
            c
            for c in sorted_candidates
            if not c.pattern.is_discovered and c.performance.total_attempts > 0
        ]

        return [c.pattern for c in (discovered + handcrafted)[:5]]

    def get_pattern_for_feature(self, feature_type: FeatureType) -> Optional[ReasoningPattern]:
        """
        Get the best pattern for a specific feature type.

        Args:
            feature_type: The feature type to get pattern for

        Returns:
            Best performing pattern for the feature type
        """
        candidates = self.patterns.get(feature_type, [])
        if not candidates:
            ft_candidates = self.patterns.get(FeatureType.UNKNOWN, [])
            if ft_candidates:
                best = max(ft_candidates, key=lambda c: c.performance.get_score())
                return best.pattern
            return None

        best = max(candidates, key=lambda c: c.performance.get_score())
        return best.pattern

    def record_conversion_result(
        self,
        pattern_id: str,
        feature_type: FeatureType,
        success: bool,
        reward: float,
        confidence: float,
    ) -> None:
        """
        Record a conversion result to improve pattern selection.

        Args:
            pattern_id: ID of the pattern used
            feature_type: Feature type that was converted
            success: Whether the conversion succeeded
            reward: Reward score (0.0-1.0)
            confidence: Confidence score (0.0-1.0)
        """
        cache_key = f"{pattern_id}_{feature_type.value}"
        perf = self.performance_cache.get(cache_key)
        if not perf:
            perf = PatternPerformance(pattern_id=pattern_id, feature_type=feature_type)
            self.performance_cache[cache_key] = perf

        perf.record_attempt(success, reward, confidence)

        for candidates in self.patterns.values():
            for candidate in candidates:
                if candidate.pattern.id == pattern_id:
                    candidate.performance.record_attempt(success, reward, confidence)

    def get_all_patterns(self) -> Dict[FeatureType, List[ReasoningPattern]]:
        """Get all patterns organized by feature type."""
        result = {}
        for ft, candidates in self.patterns.items():
            if candidates:
                result[ft] = [c.pattern for c in candidates]
        return result

    def get_discovery_stats(self) -> Dict:
        """Get statistics about pattern discovery."""
        total_candidates = sum(len(candidates) for candidates in self.patterns.values())
        discovered_count = sum(
            1
            for candidates in self.patterns.values()
            for c in candidates
            if c.pattern.is_discovered
        )

        return {
            "total_candidates": total_candidates,
            "discovered_patterns": discovered_count,
            "handcrafted_patterns": total_candidates - discovered_count,
            "feature_types_with_patterns": sum(
                1 for candidates in self.patterns.values() if candidates
            ),
            "performance_cache_size": len(self.performance_cache),
        }
