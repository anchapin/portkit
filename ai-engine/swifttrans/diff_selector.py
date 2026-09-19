"""
Phase 2 — DiffSelector: difference-aware translation candidate ranking.

Implements the *Difference-Aware Selection* stage of SwiftTrans
(https://arxiv.org/abs/2606.17683, §3.2). Given the N candidates produced
by Stage 1 (:class:`MpTranslator`), DiffSelector ranks them by *explicitly
comparing differences* between candidates using Ordinal Guidance — i.e.
teaching the ranker to *order* candidates rather than score each in
isolation.

This module wires together the two determinants of rank:

1. **Static efficiency** (Phase 3, :class:`BedrockEfficiencyScorer`) — used
   as a cheap deterministic pre-filter that rejects obviously-bad candidates
   before any LLM ranking cost is incurred.
2. **Correctness proxy** — supplied by the caller; in PortKit this is the
   rubric-grounded evaluator (#1367) score, but any ``[0, 1]`` callable works.

The LLM ordinal-rank judge is pluggable via :class:`RankingJudge`. A
default :class:`HeuristicRankingJudge` blends efficiency + correctness
deterministically so the DiffSelector is fully functional without an LLM
round-trip — the paper notes that the heuristic alone already captures
most of the win, with the LLM judge being a refinement on top.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from swifttrans.efficiency_scorer import BedrockEfficiencyScorer, create_efficiency_scorer
from swifttrans.models import (
    CandidateRanking,
    EfficiencyTier,
    SwiftTransConfig,
    TranslationCandidate,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class RankingJudge(Protocol):
    """Ordinal ranker over a candidate set.

    A judge receives the full candidate list (with efficiency scores
    already attached) and the configuration, and must return the candidates
    in *ranked order* (best first) along with a human-readable ``reasoning``
    per candidate. The protocol deliberately exposes the whole set rather
    than pairwise comparisons so an LLM judge can implement Ordinal Guidance
    (rank-all-at-once) per the SwiftTrans paper.
    """

    def __call__(
        self,
        candidates: list[TranslationCandidate],
        config: SwiftTransConfig,
    ) -> list[TranslationCandidate]:
        """Return ``candidates`` sorted best-first, with rank metadata set."""
        ...


# ---------------------------------------------------------------------- #
# Default heuristic judge
# ---------------------------------------------------------------------- #


class HeuristicRankingJudge:
    """Deterministic default judge that blends efficiency + correctness.

    The composite score is::

        score = efficiency_weight * efficiency_score
              + correctness_weight * correctness_score

    where the weights come from :class:`SwiftTransConfig` and are guaranteed
    by that dataclass to sum to 1.0. Candidates with a missing correctness
    proxy fall back to the efficiency score alone, weighted by
    ``efficiency_weight / (efficiency_weight + correctness_weight)`` so the
    composite stays normalised — this is the behaviour the SwiftTrans
    evaluation harness uses when the correctness oracle is unavailable.
    """

    def __init__(self, *, tie_breaker: Optional[Callable[[TranslationCandidate], Any]] = None):
        self.tie_breaker = tie_breaker or (lambda c: c.variant.value)

    def __call__(
        self,
        candidates: list[TranslationCandidate],
        config: SwiftTransConfig,
    ) -> list[TranslationCandidate]:
        scored = [(c, self._composite(c, config)) for c in candidates]
        # Stable sort preserves input order on exact ties before the tie-breaker,
        # which keeps the ranking deterministic and unit-test friendly.
        scored.sort(
            key=lambda pair: (-pair[1], self.tie_breaker(pair[0])),
        )

        ranked: list[TranslationCandidate] = []
        for position, (candidate, score) in enumerate(scored, start=1):
            candidate.rank_position = position
            candidate.rank_reasoning = (
                f"Heuristic composite={score:.3f} "
                f"(efficiency={self._eff_of(candidate):.3f}, "
                f"correctness={self._corr_of(candidate):.3f})."
            )
            ranked.append(candidate)
        return ranked

    @staticmethod
    def _eff_of(candidate: TranslationCandidate) -> float:
        return candidate.efficiency.score if candidate.efficiency else 0.0

    @staticmethod
    def _corr_of(candidate: TranslationCandidate) -> float:
        return candidate.correctness_score if candidate.correctness_score is not None else 0.0

    def _composite(self, candidate: TranslationCandidate, config: SwiftTransConfig) -> float:
        eff = self._eff_of(candidate)
        corr = self._corr_of(candidate)

        if candidate.correctness_score is None:
            # No correctness oracle: renormalise the efficiency weight so the
            # composite stays in [0, 1] rather than collapsing toward 0.
            denom = config.efficiency_weight + config.correctness_weight
            if denom <= 0:
                return eff
            return eff * (config.efficiency_weight / denom)

        return config.efficiency_weight * eff + config.correctness_weight * corr


# ---------------------------------------------------------------------- #
# DiffSelector
# ---------------------------------------------------------------------- #


class DiffSelector:
    """Stage 2 — rank Stage 1 candidates by efficiency + correctness.

    The selector's job, per the SwiftTrans paper, is to make the
    *differences* between candidates explicit. We do this in two passes:

    1. **Pre-filter** (deterministic): score every candidate with the
       :class:`BedrockEfficiencyScorer` and, when ``reject_low_tier`` is
       set, drop ``EfficiencyTier.LOW`` candidates outright. This is the
       paper's recommended "cheap elimination" step.
    2. **Rank** (pluggable): hand the survivors to a :class:`RankingJudge`,
       which returns them in best-first order with reasoning attached.

    The class is safe to reuse across runs: it carries no per-run state
    outside the candidates passed to :meth:`select`.
    """

    def __init__(
        self,
        scorer: Optional[BedrockEfficiencyScorer] = None,
        judge: Optional[RankingJudge] = None,
        config: Optional[SwiftTransConfig] = None,
        correctness_proxy: Optional[Callable[[TranslationCandidate], float]] = None,
    ):
        self.scorer = scorer or create_efficiency_scorer()
        self.judge: RankingJudge = judge or HeuristicRankingJudge()
        self.config = config or SwiftTransConfig()
        self.correctness_proxy = correctness_proxy

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def select(
        self,
        candidates: list[TranslationCandidate],
        location: Optional[str] = None,
    ) -> CandidateRanking:
        """Rank ``candidates`` best-first.

        Args:
            candidates: Raw candidates from Stage 1 (efficiency / rank
                metadata may be absent and will be populated here).
            location: Optional location label forwarded to the efficiency
                scorer for audit (e.g. component id).

        Returns:
            A :class:`CandidateRanking` with ``ranked`` (survivors,
            best-first) and ``rejected`` (low-tier pre-filter drops).
        """
        if not candidates:
            return CandidateRanking(ranked=[], rejected=[], summary="No candidates provided.")

        # Step 1 — attach efficiency scores (Phase 3).
        for c in candidates:
            self.scorer.score_candidate(c, location=location)

        # Step 2 — optional correctness proxy.
        if self.correctness_proxy is not None:
            for c in candidates:
                try:
                    c.correctness_score = float(self.correctness_proxy(c))
                except Exception as exc:  # noqa: BLE001 — proxy is user-supplied
                    logger.warning(
                        "Correctness proxy failed for variant=%s: %s",
                        c.variant.value,
                        exc,
                    )
                    c.correctness_score = None

        # Step 3 — deterministic pre-filter.
        survivors: list[TranslationCandidate] = []
        rejected: list[TranslationCandidate] = []
        for c in candidates:
            if self.config.reject_low_tier and c.efficiency and c.efficiency.is_rejected:
                c.rank_reasoning = (
                    f"Rejected by Phase 3 pre-filter (tier={c.efficiency.tier.value})."
                )
                rejected.append(c)
            else:
                survivors.append(c)

        # Edge case: pre-filter rejected everything. Preserve the least-bad
        # candidate so downstream stages always have something to emit —
        # returning an empty ranking would silently break the pipeline.
        if not survivors:
            logger.warning(
                "DiffSelector pre-filter rejected all %d candidates; "
                "falling back to highest-scoring rejected candidate.",
                len(rejected),
            )
            survivors = sorted(
                rejected, key=lambda c: c.efficiency.score if c.efficiency else 0.0, reverse=True
            )[:1]
            rejected = [c for c in rejected if c not in survivors]

        # Step 4 — ordinal ranking (Phase 2).
        ranked = self.judge(survivors, self.config)

        summary = self._build_summary(ranked, rejected, candidates)
        return CandidateRanking(ranked=ranked, rejected=rejected, summary=summary)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_summary(
        ranked: list[TranslationCandidate],
        rejected: list[TranslationCandidate],
        all_candidates: list[TranslationCandidate],
    ) -> str:
        best = ranked[0] if ranked else None
        best_desc = (
            f"variant={best.variant.value} efficiency={best.efficiency.score:.3f}"
            if best and best.efficiency
            else "none"
        )
        return (
            f"Ranked {len(ranked)}/{len(all_candidates)} candidates "
            f"(rejected {len(rejected)} via Phase 3 pre-filter). "
            f"Best: {best_desc}."
        )


# ---------------------------------------------------------------------- #
# Factories
# ---------------------------------------------------------------------- #


def create_diff_selector(
    scorer: Optional[BedrockEfficiencyScorer] = None,
    judge: Optional[RankingJudge] = None,
    config: Optional[SwiftTransConfig] = None,
    correctness_proxy: Optional[Callable[[TranslationCandidate], float]] = None,
) -> DiffSelector:
    """Factory: build a :class:`DiffSelector` with sane defaults."""
    return DiffSelector(
        scorer=scorer,
        judge=judge,
        config=config,
        correctness_proxy=correctness_proxy,
    )


def create_heuristic_judge(
    *, tie_breaker: Optional[Callable[[TranslationCandidate], Any]] = None
) -> HeuristicRankingJudge:
    """Factory: build the default :class:`HeuristicRankingJudge`."""
    return HeuristicRankingJudge(tie_breaker=tie_breaker)


__all__ = [
    "DiffSelector",
    "HeuristicRankingJudge",
    "RankingJudge",
    "create_diff_selector",
    "create_heuristic_judge",
]


# Kept for forward-compat typing; silence unused-import linter.
_ = Any, EfficiencyTier
