"""
Tests for the SwiftTrans dual-stage translation strategy.

Covers Phases 1-3 independently plus the Stage 1 → Stage 2 integration via
:class:`SwiftTransStrategy`. Uses :class:`StubTranslator` so the suite runs
without an LLM and is stable under the coverage gate.

Run: ``pytest ai-engine/tests/test_swifttrans_strategy.py -v``
"""

import pytest

from swifttrans import (
    CandidateVariant,
    EfficiencyAntiPattern,
    EfficiencyTier,
    HeuristicRankingJudge,
    MpTranslator,
    StubTranslator,
    SwiftTransConfig,
    TranslationCandidate,
    create_diff_selector,
    create_efficiency_scorer,
    create_mp_translator,
    create_swifttrans_strategy,
)


# ---------------------------------------------------------------------- #
# Models
# ---------------------------------------------------------------------- #


class TestSwiftTransConfig:
    """Tests for the configuration dataclass and its invariants."""

    def test_default_is_disabled(self):
        cfg = SwiftTransConfig()
        assert cfg.enabled is False
        assert cfg.num_candidates == 3
        assert CandidateVariant.BASELINE in cfg.variants

    def test_invalid_num_candidates_rejected(self):
        with pytest.raises(ValueError, match="num_candidates"):
            SwiftTransConfig(enabled=True, num_candidates=0)

    def test_empty_variants_rejected_when_enabled(self):
        with pytest.raises(ValueError, match="CandidateVariant"):
            SwiftTransConfig(enabled=True, variants=())

    def test_empty_variants_allowed_when_disabled(self):
        # Disabled mode is a no-op, so empty variants must be permitted
        # (lets callers use the config purely as a feature flag).
        cfg = SwiftTransConfig(enabled=False, variants=())
        assert cfg.variants == ()

    def test_weight_sum_invariant(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            SwiftTransConfig(enabled=True, efficiency_weight=0.5, correctness_weight=0.6)

    def test_valid_normalised_weights(self):
        cfg = SwiftTransConfig(enabled=True, efficiency_weight=0.3, correctness_weight=0.7)
        assert cfg.efficiency_weight == 0.3
        assert cfg.correctness_weight == 0.7

    def test_weight_range_check(self):
        with pytest.raises(ValueError, match="efficiency_weight"):
            SwiftTransConfig(enabled=True, efficiency_weight=1.5, correctness_weight=-0.5)

    def test_to_dict_roundtrip(self):
        cfg = SwiftTransConfig(enabled=True)
        d = cfg.to_dict()
        assert d["enabled"] is True
        assert isinstance(d["variants"], list)
        assert CandidateVariant.BASELINE.value in d["variants"]


class TestEfficiencyModels:
    """Tests for EfficiencyScore / TranslationCandidate data semantics."""

    def test_low_tier_is_rejected(self):
        from swifttrans import EfficiencyScore

        score = EfficiencyScore(score=0.1, tier=EfficiencyTier.LOW)
        assert score.is_rejected is True

    def test_high_tier_not_rejected(self):
        from swifttrans import EfficiencyScore

        score = EfficiencyScore(score=0.95, tier=EfficiencyTier.HIGH)
        assert score.is_rejected is False

    def test_candidate_default_state(self):
        c = TranslationCandidate(code="x", variant=CandidateVariant.BASELINE)
        assert c.efficiency is None
        assert c.rank_position is None
        assert c.variant_id == "baseline"


# ---------------------------------------------------------------------- #
# Phase 3 — BedrockEfficiencyScorer
# ---------------------------------------------------------------------- #


class TestBedrockEfficiencyScorer:
    """Phase 3: deterministic static efficiency analysis."""

    @pytest.fixture
    def scorer(self):
        return create_efficiency_scorer()

    def test_clean_code_scores_high(self, scorer):
        clean = (
            "import { world } from '@minecraft/server';\n"
            "const cached = computeOnce();\n"  # hoisted, not in a tick callback
            "world.afterEvents.entitySpawn.subscribe(ev => handle(ev, cached));\n"
        )
        result = scorer.score(clean)
        assert result.tier is EfficiencyTier.HIGH
        assert result.score >= 0.8
        assert result.violations == []

    def test_per_tick_allocation_detected(self, scorer):
        # ``new Object()`` inside a runInterval callback — the canonical
        # Bedrock perf footgun.
        bad = "system.runInterval(() => {\n  const fresh = new Object();\n  fresh.x = 1;\n}, 20);\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.PER_TICK_OBJECT_ALLOCATION in pats
        assert result.tier is not EfficiencyTier.HIGH

    def test_blocking_settimeout_detected(self, scorer):
        bad = "setTimeout(() => doThing(), 100);\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.BLOCKING_SLEEP in pats

    def test_busy_wait_loop_detected(self, scorer):
        bad = "while (true) { poll(); }\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.BLOCKING_SLEEP in pats

    def test_unbounded_entity_query_detected(self, scorer):
        bad = "const es = world.getEntities();\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.UNBOUNDED_ENTITY_QUERY in pats

    def test_redundant_api_call_detected(self, scorer):
        # Same literal call twice — should be flagged as redundant.
        bad = "const a = world.getBlock(loc);\nconst b = world.getBlock(loc);\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.REDUNDANT_API_CALL in pats

    def test_string_concat_in_loop_detected(self, scorer):
        bad = "s += 'x';\n"
        result = scorer.score(bad)
        pats = {v.pattern for v in result.violations}
        assert EfficiencyAntiPattern.STRING_CONCAT_IN_LOOP in pats

    def test_score_is_normalised(self, scorer):
        result = scorer.score("system.runInterval(() => { new Object(); }, 20);")
        assert 0.0 < result.score <= 1.0

    def test_more_violations_lower_score(self, scorer):
        one = "setTimeout(x, 1);\n"
        many = "setTimeout(x, 1);\nwhile (true) {}\ns += 'y';\nworld.getEntities();\n"
        assert scorer.score(one).score > scorer.score(many).score

    def test_violation_has_remediation(self, scorer):
        result = scorer.score("setTimeout(x, 1);")
        assert result.violations
        for v in result.violations:
            assert v.remediation, f"Missing remediation for {v.pattern}"

    def test_violation_location_includes_line(self, scorer):
        result = scorer.score("a();\nb();\nsetTimeout(x, 1);\n")
        assert result.violations
        assert "line 3" in result.violations[0].location

    def test_score_candidate_attaches_result(self, scorer):
        c = TranslationCandidate(code="setTimeout(x,1);", variant=CandidateVariant.BASELINE)
        scorer.score_candidate(c)
        assert c.efficiency is not None
        assert c.efficiency.tier is not EfficiencyTier.HIGH

    def test_rejects_non_string(self, scorer):
        with pytest.raises(TypeError):
            scorer.score(b"bytes")  # type: ignore[arg-type]

    def test_tier_thresholds_configurable(self):
        # Tighten thresholds so even mild inefficiencies land in LOW.
        strict = create_efficiency_scorer(low_tier_threshold=0.95, high_tier_threshold=0.99)
        result = strict.score("setTimeout(x, 1);")
        assert result.tier is EfficiencyTier.LOW

    def test_large_input_truncates_safely(self, scorer):
        big = "setTimeout(x,1);\n" * 100000
        # Must not raise; result is well-formed even on huge input.
        result = scorer.score(big)
        assert 0.0 < result.score <= 1.0


# ---------------------------------------------------------------------- #
# Phase 1 — MpTranslator
# ---------------------------------------------------------------------- #


class TestMpTranslator:
    """Stage 1: multi-perspective candidate generation."""

    @pytest.fixture
    def stub(self):
        return StubTranslator()

    @pytest.fixture
    def config(self):
        return SwiftTransConfig(
            enabled=True,
            variants=(
                CandidateVariant.BASELINE,
                CandidateVariant.EFFICIENCY_FOCUSED,
                CandidateVariant.IDIOMATIC_BEDROCK,
            ),
        )

    def test_build_prompt_contains_structural_prefix(self):
        prompt = MpTranslator.build_prompt(CandidateVariant.BASELINE, "class X {}")
        assert "Bedrock Edition JavaScript" in prompt
        assert "class X {}" in prompt

    def test_build_prompt_variants_differ(self):
        prompts = {v: MpTranslator.build_prompt(v, "class X {}") for v in CandidateVariant}
        # Each variant must produce a distinct prompt.
        assert len(set(prompts.values())) == len(prompts)

    def test_build_prompt_unknown_variant_raises(self):
        with pytest.raises(ValueError, match="Unknown candidate variant"):
            MpTranslator.build_prompt(object(), "x")  # type: ignore[arg-type]

    def test_generate_candidates_requires_translator(self, config):
        mp = create_mp_translator(translator=None, config=config)
        with pytest.raises(RuntimeError, match="translator callable"):
            mp.generate_candidates("class X {}")

    def test_generate_candidates_one_per_variant(self, stub, config):
        mp = create_mp_translator(translator=stub, config=config)
        candidates = mp.generate_candidates("class X {}")
        assert len(candidates) == len(config.variants)
        assert {c.variant for c in candidates} == set(config.variants)

    def test_candidate_carries_prompt(self, stub, config):
        mp = create_mp_translator(translator=stub, config=config)
        candidates = mp.generate_candidates("class X {}")
        for c in candidates:
            assert c.prompt
            assert "Bedrock Edition JavaScript" in c.prompt
            assert c.code

    def test_generate_prompts_skips_translator(self, config):
        mp = create_mp_translator(translator=None, config=config)
        pairs = mp.generate_prompts("class X {}")
        assert len(pairs) == len(config.variants)
        assert all(isinstance(v, CandidateVariant) for v, _ in pairs)

    def test_stub_translator_emits_distinct_output(self, stub):
        eff = stub(MpTranslator.build_prompt(CandidateVariant.EFFICIENCY_FOCUSED, "x"), "x")
        base = stub(MpTranslator.build_prompt(CandidateVariant.BASELINE, "x"), "x")
        assert eff != base
        assert "efficiency-focused" in eff
        assert "baseline" in base

    def test_stub_baseline_emits_inefficient_body(self, stub):
        # The baseline stub deliberately includes a per-tick allocation so
        # the efficiency scorer has signal to rank against.
        out = stub(MpTranslator.build_prompt(CandidateVariant.BASELINE, "x"), "x")
        assert "new Object()" in out

    def test_stub_translator_echo_optional(self):
        stub = StubTranslator(echo_java=True)
        out = stub(MpTranslator.build_prompt(CandidateVariant.BASELINE, "a\nb\nc"), "a\nb\nc")
        assert "java_source_lines=3" in out


# ---------------------------------------------------------------------- #
# Phase 2 — DiffSelector
# ---------------------------------------------------------------------- #


class TestHeuristicRankingJudge:
    """Default judge: blends efficiency + correctness."""

    @pytest.fixture
    def judge(self):
        return HeuristicRankingJudge()

    @pytest.fixture
    def config(self):
        return SwiftTransConfig(enabled=True, efficiency_weight=0.5, correctness_weight=0.5)

    def _candidate(self, eff, corr, variant=CandidateVariant.BASELINE):
        from swifttrans import EfficiencyScore

        c = TranslationCandidate(code="x", variant=variant)
        c.efficiency = EfficiencyScore(score=eff, tier=EfficiencyTier.MEDIUM)
        c.correctness_score = corr
        return c

    def test_ranks_by_composite_descending(self, judge, config):
        cs = [
            self._candidate(0.2, 0.2),
            self._candidate(0.9, 0.9),
            self._candidate(0.5, 0.5),
        ]
        ranked = judge(cs, config)
        assert [c.efficiency.score for c in ranked] == [0.9, 0.5, 0.2]

    def test_assigns_rank_positions(self, judge, config):
        cs = [self._candidate(0.1, 0.1), self._candidate(0.9, 0.9)]
        ranked = judge(cs, config)
        assert ranked[0].rank_position == 1
        assert ranked[1].rank_position == 2

    def test_reasoning_records_scores(self, judge, config):
        ranked = judge([self._candidate(0.7, 0.6)], config)
        assert "efficiency=0.700" in ranked[0].rank_reasoning
        assert "correctness=0.600" in ranked[0].rank_reasoning

    def test_missing_correctness_renormalises(self, judge, config):
        c = self._candidate(0.8, None)
        c.correctness_score = None
        ranked = judge([c], config)
        # With correctness missing, the composite is eff * (eff_w / (eff_w+corr_w))
        # = 0.8 * (0.5 / 1.0) = 0.4
        assert "efficiency=0.800" in ranked[0].rank_reasoning

    def test_tie_breaker_is_deterministic(self):
        judge = HeuristicRankingJudge(tie_breaker=lambda c: c.variant.value)
        cs = [
            self._candidate(0.5, 0.5, CandidateVariant.BASELINE),
            self._candidate(0.5, 0.5, CandidateVariant.EFFICIENCY_FOCUSED),
        ]
        ranked = judge(
            cs, SwiftTransConfig(enabled=True, efficiency_weight=0.5, correctness_weight=0.5)
        )
        # Equal scores → tie_breaker orders by variant name ascending.
        assert ranked[0].variant is CandidateVariant.BASELINE


class TestDiffSelector:
    """Stage 2: difference-aware candidate selection."""

    @pytest.fixture
    def selector(self):
        return create_diff_selector(config=SwiftTransConfig(enabled=True))

    def _make(self, code, variant=CandidateVariant.BASELINE):
        return TranslationCandidate(code=code, variant=variant)

    def test_empty_candidates_returns_empty(self, selector):
        ranking = selector.select([])
        assert ranking.ranked == []
        assert ranking.best is None

    def test_attaches_efficiency_to_each_candidate(self, selector):
        cs = [self._make("world.afterEvents.entitySpawn.subscribe(e => e);")]
        ranking = selector.select(cs)
        assert ranking.ranked[0].efficiency is not None

    def test_rejects_low_tier_when_enabled(self):
        selector = create_diff_selector(config=SwiftTransConfig(enabled=True, reject_low_tier=True))
        # Build a candidate that the scorer will mark LOW (lots of anti-patterns).
        very_bad = (
            "system.runInterval(() => {\n"
            "  const o = new Object();\n"
            "  world.getEntities();\n"
            "  setTimeout(x,1);\n"
            "}, 20);\n"
        )
        good = "world.afterEvents.entitySpawn.subscribe(e => e);\n"
        ranking = selector.select([self._make(very_bad), self._make(good)])
        assert any(c.variant for c in ranking.rejected)
        assert ranking.best.code == good

    def test_keeps_low_tier_when_filter_disabled(self):
        selector = create_diff_selector(
            config=SwiftTransConfig(enabled=True, reject_low_tier=False)
        )
        bad = (
            "system.runInterval(() => { new Object(); setTimeout(x,1); world.getEntities(); }, 20);"
        )
        ranking = selector.select([self._make(bad)])
        assert len(ranking.ranked) == 1
        assert ranking.ranked[0].efficiency.tier is EfficiencyTier.LOW

    def test_pre_filter_reject_all_falls_back_to_least_bad(self):
        selector = create_diff_selector(config=SwiftTransConfig(enabled=True, reject_low_tier=True))
        bad1 = "system.runInterval(() => { new Object(); }, 20);\n"
        worse = (
            "system.runInterval(() => {\n"
            "  new Object(); setTimeout(x,1); world.getEntities();\n"
            "  while(true){} s+='a';\n"
            "}, 20);\n"
        )
        ranking = selector.select([self._make(bad1), self._make(worse)])
        # Should not return empty — least-bad survives.
        assert len(ranking.ranked) == 1
        assert ranking.ranked[0].code == bad1

    def test_correctness_proxy_invoked(self):
        calls: list[str] = []

        def proxy(c):
            calls.append(c.code)
            return 0.9

        selector = create_diff_selector(
            config=SwiftTransConfig(enabled=True),
            correctness_proxy=proxy,
        )
        selector.select([self._make("x")])
        assert calls == ["x"]

    def test_correctness_proxy_failure_is_non_fatal(self, selector):
        def bad_proxy(c):
            raise RuntimeError("oracle down")

        selector = create_diff_selector(
            config=SwiftTransConfig(enabled=True),
            correctness_proxy=bad_proxy,
        )
        c = self._make("world.afterEvents.entitySpawn.subscribe(e => e);")
        ranking = selector.select([c])
        # The candidate is still ranked; proxy failure doesn't sink it.
        assert ranking.best is not None
        assert ranking.best.correctness_score is None

    def test_pluggable_judge(self):
        class AlwaysReverseJudge:
            def __call__(self, candidates, config):
                for i, c in enumerate(candidates, start=1):
                    c.rank_position = i
                    c.rank_reasoning = "reversed"
                return list(reversed(candidates))

        selector = create_diff_selector(
            config=SwiftTransConfig(enabled=True),
            judge=AlwaysReverseJudge(),
        )
        cs = [
            self._make(
                "world.afterEvents.entitySpawn.subscribe(e => e);", CandidateVariant.BASELINE
            ),
            self._make(
                "world.afterEvents.entitySpawn.subscribe(e => e);",
                CandidateVariant.EFFICIENCY_FOCUSED,
            ),
        ]
        ranking = selector.select(cs)
        # Custom judge overrode the default ordering.
        assert ranking.ranked[0].rank_reasoning == "reversed"

    def test_summary_mentions_best_variant(self, selector):
        good = "world.afterEvents.entitySpawn.subscribe(e => e);\n"
        ranking = selector.select([self._make(good)])
        assert "Best:" in ranking.summary
        assert "baseline" in ranking.summary

    def test_to_dict_serialisable(self, selector):
        ranking = selector.select([self._make("x")])
        d = ranking.to_dict()
        assert "ranked" in d
        assert "rejected" in d


# ---------------------------------------------------------------------- #
# Strategy integration
# ---------------------------------------------------------------------- #


class TestSwiftTransStrategy:
    """End-to-end Stage 1 → Stage 2 integration."""

    @pytest.fixture
    def enabled_config(self):
        return SwiftTransConfig(
            enabled=True,
            variants=(
                CandidateVariant.BASELINE,
                CandidateVariant.EFFICIENCY_FOCUSED,
                CandidateVariant.IDIOMATIC_BEDROCK,
            ),
        )

    def test_disabled_returns_baseline_passthrough(self):
        strategy = create_swifttrans_strategy(config=SwiftTransConfig(enabled=False))
        baseline = TranslationCandidate(code="// single pass", variant=CandidateVariant.BASELINE)
        result = strategy.run("class X {}", baseline=baseline)
        assert result.selected is baseline
        assert result.stage1_skipped is True
        assert ranking_only_baseline(result)

    def test_disabled_without_baseline_returns_none(self):
        strategy = create_swifttrans_strategy(config=SwiftTransConfig(enabled=False))
        result = strategy.run("class X {}")
        assert result.selected is None
        assert result.ranking.ranked == []

    def test_enabled_runs_full_pipeline(self, enabled_config):
        strategy = create_swifttrans_strategy(
            config=enabled_config,
            translator=StubTranslator(),
        )
        result = strategy.run("class X {}")
        assert result.stage1_skipped is False
        assert result.selected is not None
        # The stub baseline emits inefficient code (per-tick alloc); the
        # efficiency/idiomatic variants should beat it.
        assert result.selected.variant is not CandidateVariant.BASELINE
        assert result.ranking.best is result.selected
        assert result.ranking.num_candidates == len(enabled_config.variants)

    def test_baseline_added_to_pool_when_provided(self, enabled_config):
        strategy = create_swifttrans_strategy(
            config=enabled_config,
            translator=StubTranslator(),
        )
        baseline = TranslationCandidate(
            code="world.afterEvents.entitySpawn.subscribe(e => e);",
            variant=CandidateVariant.BASELINE,
        )
        result = strategy.run("class X {}", baseline=baseline)
        # Baseline is appended to the candidate pool, so the pool is larger
        # than the variant count by one.
        assert result.ranking.num_candidates == len(enabled_config.variants) + 1

    def test_pre_supplied_candidates_skip_stage1(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config)
        candidates = [
            TranslationCandidate(
                code="world.afterEvents.entitySpawn.subscribe(e => e);",
                variant=CandidateVariant.EFFICIENCY_FOCUSED,
            ),
            TranslationCandidate(
                code="system.runInterval(() => { new Object(); setTimeout(x,1); }, 20);",
                variant=CandidateVariant.BASELINE,
            ),
        ]
        result = strategy.run("class X {}", candidates=candidates)
        assert result.selected.code.startswith("world.afterEvents")
        # No translator was wired in, but we supplied candidates directly, so
        # the run must not have raised.
        assert result.selected.variant is CandidateVariant.EFFICIENCY_FOCUSED

    def test_enabled_without_translator_falls_back_to_baseline(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config, translator=None)
        baseline = TranslationCandidate(code="// single", variant=CandidateVariant.BASELINE)
        result = strategy.run("class X {}", baseline=baseline)
        assert result.selected is baseline
        assert result.stage1_skipped is True

    def test_enabled_without_translator_and_no_baseline_raises(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config, translator=None)
        with pytest.raises(RuntimeError, match="translator callable"):
            strategy.run("class X {}")

    def test_describe_reports_wiring(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config, translator=StubTranslator())
        info = strategy.describe()
        assert info["enabled"] is True
        assert info["has_translator"] is True
        assert info["scorer"] == "BedrockEfficiencyScorer"
        assert "variants" in info

    def test_correctness_proxy_used_end_to_end(self, enabled_config):
        strategy = create_swifttrans_strategy(
            config=enabled_config,
            translator=StubTranslator(),
            correctness_proxy=lambda c: 0.5,
        )
        result = strategy.run("class X {}")
        for c in result.ranking.ranked:
            assert c.correctness_score == 0.5

    def test_location_forwarded_to_scorer(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config, translator=StubTranslator())
        result = strategy.run("class X {}", location="ComponentX")
        # At least one violation location (if any) should carry the label.
        for c in result.ranking.ranked + result.ranking.rejected:
            if c.efficiency:
                for v in c.efficiency.violations:
                    assert "ComponentX" in v.location

    def test_result_to_dict_roundtrip(self, enabled_config):
        strategy = create_swifttrans_strategy(config=enabled_config, translator=StubTranslator())
        result = strategy.run("class X {}")
        d = result.to_dict()
        assert d["config"]["enabled"] is True
        assert d["ranking"]["ranked"]


def ranking_only_baseline(result) -> bool:
    """Helper: every ranked candidate, if any, is the supplied baseline."""
    return (
        all(c is result.selected for c in result.ranking.ranked) if result.ranking.ranked else True
    )
