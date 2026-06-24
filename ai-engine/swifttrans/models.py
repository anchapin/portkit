"""
Shared data models for the SwiftTrans dual-stage translation strategy.

Implements the data structures described in *SwiftTrans: Bridging Functional
Correctness and Runtime Efficiency Gaps in LLM-Based Code Translation*
(https://arxiv.org/abs/2606.17683).

These models are intentionally framework-agnostic: Stage 1 (MpTranslator),
Stage 2 (DiffSelector) and the Bedrock static efficiency scorer all read and
return the types defined here so each stage can be unit-tested in isolation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EfficiencyTier(Enum):
    """Ordinal efficiency tier assigned to a translation candidate.

    Tiers are ordered worst-to-best so that ``max(candidates, key=lambda c:
    c.efficiency.tier)`` picks the most efficient candidate. The static
    Bedrock scorer (Phase 3) assigns tiers deterministically; the DiffSelector
    (Phase 2) uses them as a pre-filter before invoking the LLM ranker.
    """

    LOW = "low"  # Clear anti-patterns; reject without LLM ranking
    MEDIUM = "medium"  # Acceptable; send to LLM ranker
    HIGH = "high"  # Idiomatic; strong baseline


class EfficiencyAntiPattern(Enum):
    """Bedrock scripting anti-patterns the static scorer flags.

    The set is deliberately conservative: each pattern must be (a) cheap to
    detect via regex/lightweight AST analysis, (b) unambiguously a runtime
    cost on the Bedrock Scripting API tick budget, and (c) actionable — i.e.
    a human-readable remediation exists.
    """

    PER_TICK_OBJECT_ALLOCATION = "per_tick_object_allocation"
    """``new`` inside a ``system.runInterval`` / ``tick`` callback allocates
    garbage on every tick (20 Hz). Should hoist outside the callback."""

    SYNC_ENTITY_QUERY_LOOP = "sync_entity_query_loop"
    """``world.getEntities()`` / ``dimension.getEntities()`` called inside a
    tight loop or per-tick without caching the result."""

    REDUNDANT_API_CALL = "redundant_api_call"
    """Same expensive API call (e.g. ``world.getBlock``) repeated with
    identical literal arguments instead of being cached in a local."""

    BLOCKING_SLEEP = "blocking_sleep"
    """``await new Promise(r => setTimeout(r, ...))`` or busy-wait loops in
    tick handlers — these stall the Bedrock event loop."""

    UNBOUNDED_ENTITY_QUERY = "unbounded_entity_query"
    """``getEntities(...)`` / ``getPlayers()`` without a bounding box / max
    count, scanning the whole dimension each tick."""

    DEEP_NESTED_LOOP = "deep_nested_loop"
    """3+ levels of nested loops over runtime-sized collections inside a
    tick handler — O(n^3) per tick."""

    STRING_CONCAT_IN_LOOP = "string_concat_in_loop"
    """``+=`` string concatenation inside a hot loop instead of ``.push()``
    + ``.join()`` — quadratic on Bedrock's V8."""


class CandidateVariant(Enum):
    """Prompt-strategy variants for Stage 1 (MpTranslator).

    Each variant produces a translation candidate emphasising a different
    axis of the SwiftTrans *Hierarchical Guidance*: structural constraints
    first, then semantic / efficiency constraints. The variants are
    deliberately orthogonal so the DiffSelector has genuine differences to
    compare (the core empirical finding of the paper).
    """

    BASELINE = "baseline"  # Vanilla single-pass translation (control)
    EFFICIENCY_FOCUSED = "efficiency_focused"  # Explicit tick-budget constraint
    IDIOMATIC_BEDROCK = "idiomatic_bedrock"  # Prefer native Bedrock APIs
    MINIMAL_ALLOCATION = "minimal_allocation"  # Hoist allocations, cache calls
    STRUCTURAL_FIRST = "structural_first"  # Structural correctness first


@dataclass
class EfficiencyViolation:
    """A single detected anti-pattern occurrence in a candidate."""

    pattern: EfficiencyAntiPattern
    location: str
    """Human-readable location, e.g. ``line 12`` or ``tickInterval callback``."""

    snippet: str = ""
    severity: float = 1.0
    """Weight contributed to the penalty score (0-1 scale, 1 = most severe)."""

    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "location": self.location,
            "snippet": self.snippet,
            "severity": self.severity,
            "remediation": self.remediation,
        }


@dataclass
class EfficiencyScore:
    """Result of Phase 3 static efficiency analysis on one candidate.

    The score is the *complement* of the weighted violation penalty,
    normalised to ``[0.0, 1.0]``. ``tier`` is the ordinal bucket the
    DiffSelector uses to short-circuit obvious bad candidates.
    """

    score: float
    tier: EfficiencyTier
    violations: list[EfficiencyViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_rejected(self) -> bool:
        """Whether the candidate should be dropped before LLM ranking."""
        return self.tier is EfficiencyTier.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "tier": self.tier.value,
            "violations": [v.to_dict() for v in self.violations],
            "notes": self.notes,
        }


@dataclass
class TranslationCandidate:
    """A single generated translation candidate from Stage 1.

    The DiffSelector augments this with ``efficiency`` (Phase 3) and
    ``rank_position`` (Phase 2) as the pipeline progresses.
    """

    code: str
    variant: CandidateVariant
    prompt: str = ""
    """The full prompt used to generate this candidate (for audit / debug)."""

    metadata: dict[str, Any] = field(default_factory=dict)

    # Populated by downstream stages.
    efficiency: Optional[EfficiencyScore] = None
    correctness_score: Optional[float] = None
    """Optional correctness proxy in ``[0, 1]`` from the rubric evaluator
    (#1367). May be ``None`` when only static analysis is run."""

    rank_position: Optional[int] = None
    """1-based rank assigned by the DiffSelector (1 = best)."""

    rank_reasoning: str = ""

    @property
    def variant_id(self) -> str:
        return self.variant.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant.value,
            "prompt": self.prompt,
            "metadata": self.metadata,
            "efficiency": self.efficiency.to_dict() if self.efficiency else None,
            "correctness_score": self.correctness_score,
            "rank_position": self.rank_position,
            "rank_reasoning": self.rank_reasoning,
        }


@dataclass
class CandidateRanking:
    """Output of the Stage 2 DiffSelector: candidates in ranked order."""

    ranked: list[TranslationCandidate]
    rejected: list[TranslationCandidate] = field(default_factory=list)
    summary: str = ""

    @property
    def best(self) -> Optional[TranslationCandidate]:
        """Return the highest-ranked candidate, or None if empty."""
        return self.ranked[0] if self.ranked else None

    @property
    def num_candidates(self) -> int:
        return len(self.ranked) + len(self.rejected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked": [c.to_dict() for c in self.ranked],
            "rejected": [c.to_dict() for c in self.rejected],
            "summary": self.summary,
        }


@dataclass
class SwiftTransConfig:
    """Opt-in configuration for the dual-stage strategy.

    Defaults are conservative: ``enabled=False`` preserves the existing
    single-pass behaviour. Setting ``enabled=True`` activates the full
    MpTranslator + DiffSelector flow. Phase 4 (MMSD fine-tuning enrichment)
    is intentionally out of scope here — it is a data-labelling task on the
    training pipeline, documented in ``docs/swifttrans-dual-stage.md``.
    """

    enabled: bool = False
    """Master switch. When ``False``, the strategy is a no-op pass-through."""

    num_candidates: int = 3
    """Number of parallel candidates Stage 1 generates (paper recommends 3-5)."""

    variants: tuple[CandidateVariant, ...] = (
        CandidateVariant.BASELINE,
        CandidateVariant.EFFICIENCY_FOCUSED,
        CandidateVariant.IDIOMATIC_BEDROCK,
    )
    """Which prompt variants to fan out. ``num_candidates`` must be >= len(variants)."""

    reject_low_tier: bool = True
    """Phase 3 pre-filter: drop ``EfficiencyTier.LOW`` before LLM ranking."""

    efficiency_weight: float = 0.4
    """DiffSelector blended score weight for the static efficiency score."""

    correctness_weight: float = 0.6
    """DiffSelector blended score weight for the correctness proxy."""

    java_source: str = ""
    """Original Java source, used by the prompt builder and (optionally)
    passed to the correctness proxy for behavioural comparison."""

    def __post_init__(self) -> None:
        if self.num_candidates < 1:
            raise ValueError("num_candidates must be >= 1")
        if self.enabled and not self.variants:
            raise ValueError("at least one CandidateVariant must be enabled")
        if not 0.0 <= self.efficiency_weight <= 1.0:
            raise ValueError("efficiency_weight must be in [0, 1]")
        if not 0.0 <= self.correctness_weight <= 1.0:
            raise ValueError("correctness_weight must be in [0, 1]")

        # Blended weights must sum to 1 so the composite score stays in [0, 1].
        total = self.efficiency_weight + self.correctness_weight
        if total > 0 and abs(total - 1.0) > 1e-6:
            raise ValueError(
                "efficiency_weight + correctness_weight must sum to 1.0 "
                f"(got {total}); normalise the weights"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "num_candidates": self.num_candidates,
            "variants": [v.value for v in self.variants],
            "reject_low_tier": self.reject_low_tier,
            "efficiency_weight": self.efficiency_weight,
            "correctness_weight": self.correctness_weight,
        }


@dataclass
class DualStageResult:
    """Final output of :class:`SwiftTransStrategy.run`.

    Wraps the selected candidate plus full provenance (which variants were
    generated, which were rejected, the composite scores) so callers can
    audit *why* a particular translation was chosen — a key requirement for
    B2B mod conversions where efficiency regressions must be explainable.
    """

    selected: Optional[TranslationCandidate]
    ranking: CandidateRanking
    config: SwiftTransConfig
    stage1_skipped: bool = False
    """True if the strategy short-circuited because ``config.enabled=False``."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.to_dict() if self.selected else None,
            "ranking": self.ranking.to_dict(),
            "config": self.config.to_dict(),
            "stage1_skipped": self.stage1_skipped,
        }
