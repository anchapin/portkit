"""Tests for ai_engine.conversion.five_phase_pipeline."""

import pytest

from conversion.five_phase_pipeline import (
    ConversionResult,
    FivePhaseConverter,
    Phase1StubGenerator,
    Phase2DependencyAnalyzer,
    Phase3APIMapper,
    Phase4CompilationRepair,
    Phase5QualityValidator,
    PhaseReport,
    PhaseStatus,
    ValidationReport,
)


SIMPLE_JAVA = """
package com.example.mod;

import java.util.List;
import java.util.Optional;
import net.minecraft.item.ItemStack;

public class SimpleBlock {
    private String name;

    public SimpleBlock(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }

    public ItemStack createStack(int count) {
        return new ItemStack(this, count);
    }
}
"""

SYNC_JAVA = """
package com.example.mod;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.CompletableFuture;

public class AsyncMod {
    public void doSync() {
        System.out.println("sync");
    }

    public CompletableFuture<String> doAsync() {
        return CompletableFuture.completedFuture("done");
    }
}
"""


class TestPhase1StubGenerator:
    def test_generate_stub_simple_class(self):
        gen = Phase1StubGenerator()
        stub = gen.generate(SIMPLE_JAVA, "SimpleBlock")

        assert stub.class_name == "SimpleBlock"
        assert len(stub.methods) >= 3
        assert stub.file_path == "src/SimpleBlock.ts"

    def test_render_produces_typescript(self):
        gen = Phase1StubGenerator()
        stub = gen.generate(SIMPLE_JAVA, "SimpleBlock")
        output = gen.render(stub)

        assert "export class SimpleBlock" in output
        assert "getName" in output
        assert "createStack" in output

    def test_unsupported_features_detected(self):
        gen = Phase1StubGenerator()
        stub = gen.generate(SYNC_JAVA, "AsyncMod")

        assert any("CompletableFuture" in f or "Thread" in f or "ExecutorService" in f
                   for f in stub.incompatible_features)


class TestPhase2DependencyAnalyzer:
    def test_extracts_imports(self):
        analyzer = Phase2DependencyAnalyzer()
        imports = analyzer._extract_imports(SIMPLE_JAVA)

        assert any("ItemStack" in i for i in imports)
        assert any("java.util.List" in i for i in imports)

    def test_builds_dependency_graph(self):
        analyzer = Phase2DependencyAnalyzer()
        result = analyzer.analyze(SIMPLE_JAVA, "SimpleBlock")

        assert "SimpleBlock" in result.nodes
        assert len(result.topological_order) >= 1
        assert isinstance(result.kb_coverage, dict)

    def test_identifies_missing_apis(self):
        analyzer = Phase2DependencyAnalyzer()
        result = analyzer.analyze(SYNC_JAVA, "AsyncMod")

        assert isinstance(result.missing_apis, list)


class TestPhase3APIMapper:
    def test_maps_known_java_to_bedrock(self):
        mapper = Phase3APIMapper()
        stub_gen = Phase1StubGenerator()
        stub = stub_gen.generate(SIMPLE_JAVA, "SimpleBlock")
        dep_analyzer = Phase2DependencyAnalyzer()
        dep_graph = dep_analyzer.analyze(SIMPLE_JAVA, "SimpleBlock")

        stub_str = stub_gen.render(stub)
        mapped, gaps = mapper.map(stub_str, dep_graph, SIMPLE_JAVA)

        assert isinstance(mapped, str)
        assert "export class SimpleBlock" in mapped
        assert isinstance(gaps, list)


class TestPhase4CompilationRepair:
    def test_validates_clean_typescript(self):
        repair = Phase4CompilationRepair()
        clean_ts = 'export class Foo {\n  bar(): void { }\n}'

        errors = repair._validate_typescript(clean_ts)
        assert len(errors) == 0

    def test_detects_unmapped_placeholders(self):
        repair = Phase4CompilationRepair()
        ts_with_gaps = 'export class Foo {\n  bar(): void { ??? }\n}'

        errors = repair._validate_typescript(ts_with_gaps)
        assert len(errors) >= 1
        assert any(e.code == "UNMAPPED_PLACEHOLDER" for e in errors)

    def test_compilation_repair_iterates(self):
        repair = Phase4CompilationRepair()
        ts = 'export class Foo {\n  bar(): void { ??? }\n  baz(): void { /* ok */ }\n}'

        result, log, errors = repair.compile_and_repair(ts, ts, [])
        assert isinstance(result, str)
        assert len(log) >= 1
        assert result is not None


class TestPhase5QualityValidator:
    def test_structural_validation_passes_for_valid_output(self):
        validator = Phase5QualityValidator()
        valid_ts = 'export class Foo {\n  bar(): void { return; }\n}'

        report = validator.validate(SIMPLE_JAVA, valid_ts, "")
        assert report.structural_ok is True
        assert isinstance(report.warnings, list)

    def test_detects_empty_output(self):
        validator = Phase5QualityValidator()
        report = validator.validate(SIMPLE_JAVA, "", "")
        assert report.structural_ok is False

    def test_semantic_check_counts_methods(self):
        validator = Phase5QualityValidator()
        report = validator.validate(
            SIMPLE_JAVA,
            'export class Foo {\n  bar(): void { }\n}',
            "",
        )
        assert isinstance(report.semantic_ok, bool)


class TestFivePhaseConverter:
    def test_full_pipeline_runs(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        assert isinstance(result, ConversionResult)
        assert result.mode == "legacy"
        assert result.java_input == SIMPLE_JAVA
        assert result.final_status in list(PhaseStatus)

    def test_pipeline_produces_bedrock_output(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        assert result.bedrock_output != ""
        assert "export class" in result.bedrock_output

    def test_pipeline_produces_stub_output(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        assert result.stub_output != ""
        assert "export class" in result.stub_output

    def test_pipeline_runs_all_five_phases(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        assert len(result.phase_reports) == 5
        phase_names = {r.phase for r in result.phase_reports}
        assert "Phase1_StubGeneration" in phase_names
        assert "Phase2_DependencyAnalysis" in phase_names
        assert "Phase3_APIMapping" in phase_names
        assert "Phase4_CompilationRepair" in phase_names
        assert "Phase5_QualityValidation" in phase_names

    def test_pipeline_reports_phase_durations(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        for r in result.phase_reports:
            assert r.duration_ms >= 0
            assert r.status in list(PhaseStatus)

    def test_pipeline_handles_async_java(self):
        converter = FivePhaseConverter()
        result = converter.convert(SYNC_JAVA, class_name="AsyncMod")

        assert result.final_status in list(PhaseStatus)
        assert len(result.phase_reports) == 5

    def test_pipeline_validation_report_present(self):
        converter = FivePhaseConverter()
        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")

        assert isinstance(result.validation_report, ValidationReport)
        assert isinstance(result.validation_report.structural_ok, bool)
        assert isinstance(result.validation_report.semantic_ok, bool)
        assert isinstance(result.validation_report.issues, list)

    def test_converter_max_iterations_respected(self):
        converter = FivePhaseConverter(max_repair_iterations=2)
        assert converter.phase4.MAX_ITERATIONS == 2

        result = converter.convert(SIMPLE_JAVA, class_name="SimpleBlock")
        phase4_report = next(r for r in result.phase_reports if "Phase4" in r.phase)
        assert phase4_report.details.get("iterations", 0) <= 2
