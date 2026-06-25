"""
SwiftTrans dual-stage translation strategy — top-level orchestrator.

Wires Stage 1 (:class:`MpTranslator`) and Stage 2 (:class:`DiffSelector`)
into a single opt-in entry point intended to be called from the LangGraph
conversion pipeline (:mod:`orchestration.langgraph`).

The strategy is *opt-in* via :class:`SwiftTransConfig.enabled`. When
disabled, :meth:`SwiftTransStrategy.run` short-circuits and returns the
caller-provided ``baseline`` candidate unchanged, preserving the existing
single-pass translation behaviour. This makes the new path safe to land
behind a flag while we gather efficiency-regression telemetry on real
conversions.

Reference: *SwiftTrans: Bridging Functional Correctness and Runtime
Efficiency Gaps in LLM-Based Code Translation*
(https://arxiv.org/abs/2606.17683).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from swifttrans.candidate_generator import (
    Translator,
    create_mp_translator,
)
from swifttrans.diff_selector import (
    RankingJudge,
    create_diff_selector,
)
from swifttrans.efficiency_scorer import BedrockEfficiencyScorer, create_efficiency_scorer
from swifttrans.models import (
    CandidateRanking,
    DualStageResult,
    SwiftTransConfig,
    TranslationCandidate,
)

logger = logging.getLogger(__name__)


class SwiftTransStrategy:
    """Top-level dual-stage strategy.

    Lifecycle of :meth:`run`:

    1. If ``config.enabled`` is ``False`` → return the baseline candidate
       untouched (single-pass passthrough).
    2. **Stage 1** — :class:`MpTranslator` generates ``num_candidates``
       variant candidates from the Java source.
    3. **Stage 2** — :class:`DiffSelector` scores (Phase 3) + ranks
       (Phase 2) the candidates and returns the best.
    4. Wrap the result in :class:`DualStageResult` with full provenance.

    The class is intentionally agnostic about *where* the candidates come
    from: callers may bypass Stage 1 by passing ``candidates=`` directly
    (useful when integrating with an external LangGraph fan-out that already
    produces multiple variants).
    """

    def __init__(
        self,
        config: Optional[SwiftTransConfig] = None,
        translator: Optional[Translator] = None,
        scorer: Optional[BedrockEfficiencyScorer] = None,
        judge: Optional[RankingJudge] = None,
        correctness_proxy: Optional[Callable[[TranslationCandidate], float]] = None,
    ):
        self.config = config or SwiftTransConfig()
        self.translator = translator
        self.scorer = scorer or create_efficiency_scorer()
        self.judge = judge
        self.correctness_proxy = correctness_proxy

        self._mp = create_mp_translator(translator=self.translator, config=self.config)
        self._selector = create_diff_selector(
            scorer=self.scorer,
            judge=self.judge,
            config=self.config,
            correctness_proxy=self.correctness_proxy,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(
        self,
        java_source: str,
        *,
        baseline: Optional[TranslationCandidate] = None,
        candidates: Optional[list[TranslationCandidate]] = None,
        location: Optional[str] = None,
    ) -> DualStageResult:
        """Execute the dual-stage strategy.

        Args:
            java_source: Java source to translate. Ignored when
                ``candidates`` is supplied directly.
            baseline: Caller-supplied single-pass candidate. Used as a
                fallback when ``config.enabled`` is ``False`` *and* when
                Stage 1 + Stage 2 somehow produce no survivors (which
                should not happen given DiffSelector's safety fallback, but
                is guarded defensively).
            candidates: Pre-generated candidates. When supplied, Stage 1 is
                skipped — useful for wiring into an existing LangGraph
                ``Send`` fan-out.
            location: Optional component id forwarded to the efficiency
                scorer and DiffSelector summary for audit.

        Returns:
            A :class:`DualStageResult` carrying the selected candidate,
            the full ranking, and the resolved config.
        """
        # --- Opt-in gate -------------------------------------------------
        if not self.config.enabled:
            logger.debug("SwiftTrans disabled; returning baseline passthrough.")
            return DualStageResult(
                selected=baseline,
                ranking=CandidateRanking(
                    ranked=[baseline] if baseline else [],
                    summary="SwiftTrans disabled; baseline passthrough.",
                ),
                config=self.config,
                stage1_skipped=True,
            )

        # --- Stage 1 -----------------------------------------------------
        if candidates is None:
            try:
                candidates = self._mp.generate_candidates(java_source)
            except RuntimeError as exc:
                # No translator wired in. Fall back to baseline if provided,
                # otherwise re-raise — silently emitting empty output would
                # mask a misconfiguration.
                if baseline is None:
                    raise
                logger.warning("Stage 1 failed (%s); falling back to baseline.", exc)
                return DualStageResult(
                    selected=baseline,
                    ranking=CandidateRanking(
                        ranked=[baseline],
                        summary=f"Stage 1 unavailable ({exc}); baseline fallback.",
                    ),
                    config=self.config,
                    stage1_skipped=True,
                )

        # Attach the caller-provided baseline as an additional comparison
        # point so Stage 2 can prefer the existing pipeline's output when
        # the SwiftTrans variants are all worse — the paper's "do no harm"
        # guarantee.
        if baseline is not None and baseline not in candidates:
            candidates.append(baseline)

        # --- Stage 2 -----------------------------------------------------
        ranking = self._selector.select(candidates, location=location)
        selected = ranking.best

        if selected is None and baseline is not None:
            selected = baseline

        return DualStageResult(
            selected=selected,
            ranking=ranking,
            config=self.config,
            stage1_skipped=False,
        )

    # ------------------------------------------------------------------ #
    # Introspection helpers (for telemetry / debugging)
    # ------------------------------------------------------------------ #
    def describe(self) -> dict[str, Any]:
        """Return a static description of the configured strategy."""
        return {
            "enabled": self.config.enabled,
            "num_candidates": self.config.num_candidates,
            "variants": [v.value for v in self.config.variants],
            "scorer": type(self.scorer).__name__,
            "judge": type(self.judge or self._selector.judge).__name__,
            "has_translator": self.translator is not None,
            "has_correctness_proxy": self.correctness_proxy is not None,
        }


# ---------------------------------------------------------------------- #
# Factory
# ---------------------------------------------------------------------- #


def create_swifttrans_strategy(
    config: Optional[SwiftTransConfig] = None,
    translator: Optional[Translator] = None,
    scorer: Optional[BedrockEfficiencyScorer] = None,
    judge: Optional[RankingJudge] = None,
    correctness_proxy: Optional[Callable[[TranslationCandidate], float]] = None,
) -> SwiftTransStrategy:
    """Factory: build a :class:`SwiftTransStrategy` with sane defaults.

    Pass ``SwiftTransConfig(enabled=True)`` to activate the dual-stage path.
    Without a ``translator`` the strategy will short-circuit to the
    baseline on :meth:`run` — see :class:`MpTranslator` for the expected
    callable signature.
    """
    return SwiftTransStrategy(
        config=config,
        translator=translator,
        scorer=scorer,
        judge=judge,
        correctness_proxy=correctness_proxy,
    )


__all__ = [
    "SwiftTransStrategy",
    "create_swifttrans_strategy",
]
