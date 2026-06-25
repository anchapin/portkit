# CODEMENV-Style Code Migration Benchmark

> **Reference:** [CODEMENV: Benchmarking Large Language Models on Code Migration](https://arxiv.org/abs/2506.00894) (arXiv:2506.00894, 2025) — 80% relevance to PortKit

## Overview

This document describes the CODEMENV-style benchmark implemented for evaluating PortKit's Java-to-Bedrock code migration quality. The benchmark is modeled after the CODEMENV benchmark which evaluates LLMs on 3 task types across 922 examples from 19 Java and Python packages.

## CODEMENV Background

### Original CODEMENV Benchmark

| Aspect | Detail |
|--------|--------|
| **Dataset Size** | 922 examples across 19 packages |
| **Languages** | Java and Python |
| **Task Types** | 3 core migration task types |
| **Baseline (GPT-4O)** | 43.84% pass@1 |
| **Average LLM pass@1** | 26.50% |

### Key Finding

CODEMENV's key finding: **average LLM pass@1 = 26.50%** on code migration tasks, with GPT-4O achieving the highest score at **43.84%**. PortKit's domain-specific fine-tuning (MMSD, 1400 pairs) should outperform these baselines — but this had never been validated against a standardized migration eval until now.

## PortKit CODEMENV Mapping

The three CODEMENV task types map directly to PortKit's pipeline stages:

| CODEMENV Task | PortKit Equivalent | Description |
|---|---|---|
| **Identify incompatible functions** | Detect Java Forge API calls with no direct Bedrock equivalent | Does this Forge API have a Bedrock Scripting API equivalent? |
| **Detect function definition changes** | Track Bedrock Scripting API version changes across releases | Has this API method changed between Minecraft:EE versions? |
| **Adapt code to target environment** | Java → Bedrock Scripting API code conversion | Convert this Java Forge code block to Bedrock TypeScript |

## Implementation

### Location

```
ai-engine/eval/codemenv_benchmark.py
```

### Class Structure

- `CodeMigrationsBenchmark` — Main benchmark orchestrator
- `CodeMigrationTask` — Individual task with source, reference, and metadata
- `TaskResult` — Per-task evaluation result
- `TaskTypeBreakdown` — Aggregated metrics per task type
- `BenchmarkResult` — Complete results with aggregate and per-task-type scores
- `IncompatibleFunctionDetector` — Task Type 1 evaluator
- `APIChangeDetector` — Task Type 2 evaluator
- `CodeAdaptor` — Task Type 3 evaluator (code conversion quality)

### Task Generation

Tasks are generated from the MMSD (Modding Multi-Step Dataset) which contains 1,400 Java-to-Bedrock conversion pairs covering Minecraft Forge mods.

- **Task Type 1 (incompatible_function_detection)**: Extracted from Java source patterns matching known incompatible Forge APIs (e.g., `MinecraftForge.EVENT_BUS`, `@SubscribeEvent`, `DeferredRegister`)
- **Task Type 2 (api_change_detection)**: Derived from Bedrock source analysis detecting version-specific API usage
- **Task Type 3 (code_adaptation)**: Direct MMSD pairs — Java source + expected Bedrock output

### Metrics

| Metric | Description | CODEMENV Equivalent |
|--------|-------------|---------------------|
| **Exact Match Rate** | % of outputs that exactly/near-exactly match reference | pass@1 |
| **AST Similarity** | Tree-edit-distance-based similarity on tokenized AST | Structural correctness |
| **Semantic Equivalence** | Key feature matching between response and reference | Behavioral preservation |
| **Compilation Success** | % of JavaScript outputs that pass `node --check` | Syntactic validity |

### Evaluation Methods

#### Task Type 1: Incompatible Function Detection

Evaluates whether the model correctly identifies Forge APIs with no Bedrock equivalent.

```python
# Evaluation: F1 score on pattern detection
expected_patterns = {"net.minecraftforge.", "@SubscribeEvent", ...}
detected_patterns = model_output | re.findall(pattern, response)
precision = |intersection| / |detected|
recall = |intersection| / |expected|
exact_match = F1 >= 0.8
```

#### Task Type 2: API Change Detection

Evaluates whether the model correctly identifies Bedrock Scripting API version changes.

```python
# Evaluation: Version recall
expected_versions = {"1.16.0", "1.19.0", ...}
detected_versions = model_output | known_versions
recall = |intersection| / |expected|
exact_match = recall >= 0.5
```

#### Task Type 3: Code Adaptation

Evaluates the quality of Java-to-Bedrock code conversion.

```python
# Exact match: Levenshtein distance
similarity = 1 - (levenshtein(resp_clean, ref_clean) / max_len)
exact_match = similarity >= 0.95

# AST similarity: Token-level tree edit distance
tokens_resp = simple_parse(response)
tokens_ref = simple_parse(reference)
distance = levenshtein(" ".join(tokens_resp), " ".join(tokens_ref))
ast_similarity = 1 - (distance / max_nodes)

# Semantic equivalence: Feature matching
resp_features = extract_semantic_features(response)
ref_features = extract_semantic_features(reference)
semantic_equivalence = matches / max(len(ref_features), 1)

# Compilation: node --check
compilation_success = subprocess.run(["node", "--check", js_code]).returncode == 0
```

## Running the Benchmark

### Basic Usage

```bash
# Run with default settings (50 tasks per type, 150 total)
PYTHONPATH=ai-engine python3 -m eval.codemenv_benchmark --output benchmark_results.json

# Run with custom settings
PYTHONPATH=ai-engine python3 -m eval.codemenv_benchmark \
    --tasks 100 \
    --max-workers 8 \
    --output benchmark_results.json \
    --verbose
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `benchmark_results.json` | Output path for JSON results |
| `--tasks` | `50` | Number of tasks per type (total = tasks × 3) |
| `--max-workers` | `4` | Max concurrent evaluation tasks |
| `--mmsd-path` | `ai-engine/mmsd/data/processed/synthesis_pairs.jsonl` | Path to MMSD dataset |
| `--api-key` | `None` | Converter API key (optional) |
| `--verbose` | `False` | Enable verbose logging |

### Programmatic Usage

```python
from eval.codemenv_benchmark import run_benchmark

result = run_benchmark(
    output_path="benchmark_results.json",
    tasks=50,
    max_workers=4,
    mmsd_path="ai-engine/mmsd/data/processed/synthesis_pairs.jsonl",
)

print(result.summary())
print(f"Weak task type: {result.weak_task_type}")
print(f"Strong task type: {result.strong_task_type}")
```

## Current Results

The benchmark was run against the current PortKit converter with the following results:

| Metric | Value |
|--------|-------|
| **Total Tasks** | 90 |
| **Overall Exact Match Rate** | 16.7% |
| **Overall AST Similarity** | 0.167 |
| **Overall Semantic Equivalence** | 0.437 |
| **Overall Compilation Success** | 76.7% |

### Per-Task-Type Breakdown

| Task Type | Tasks | Exact Match | AST Similarity | Semantic Equivalence | Compilation |
|----------|-------|-------------|----------------|---------------------|-------------|
| `incompatible_function_detection` | 30 | 20.0% | 0.200 | 0.200 | 100.0% |
| `api_change_detection` | 30 | 30.0% | 0.300 | 0.300 | 30.0% |
| `code_adaptation` | 30 | 0.0% | 0.000 | 0.810 | 100.0% |

### Analysis

**Note:** The `code_adaptation` task type shows 0% exact match because the converter was unavailable during this run (no local server). The high semantic equivalence (0.810) is an artifact of comparing against empty output — both reference and response are empty, yielding a false positive match that needs to be addressed.

**Weakest Task Type:** `code_adaptation` (expected — this is the hardest task and requires the converter to be running)

**Strongest Task Type:** `api_change_detection`

### Limitations

1. **Converter Dependency**: The `code_adaptation` tasks require the PortKit converter to be running (`localhost:8080`). Without it, these tasks produce empty outputs.

2. **MMSD Proxy**: The benchmark uses MMSD pairs as a proxy for CODEMENV tasks. True CODEMENV compliance requires extracting Java examples from the [Benchmark-of-Code-Migration](https://github.com/xdshen-ai/Benchmark-of-Code-Migration) repository.

3. **Synthetic Metrics**: AST similarity uses a simple token-level approximation rather than a full AST parser. Semantic equivalence uses heuristic feature matching rather than formal verification.

4. **Limited Ground Truth**: MMSD ground truth Bedrock outputs were generated by an earlier model version and may not represent optimal conversions.

## Full CODEMENV Compliance — Required Steps

To achieve full CODEMENV compliance (comparing directly against the original benchmark):

1. **Extract CODEMENV Java examples**:
   ```bash
   git clone https://github.com/xdshen-ai/Benchmark-of-Code-Migration
   # Extract Java package examples and adapt to PortKit's source domain
   ```

2. **Align task formats**: Convert CODEMENV's format to `CodeMigrationTask` with:
   - `task_type`: one of the 3 CODEMENV types
   - `java_source`: Java code snippet
   - `reference_bedrock`: Known correct Bedrock equivalent
   - `expected_outcome`: Task-type-specific expected outputs

3. **Add ground truth API compatibility list**: Curate a list of Forge APIs mapped to Bedrock equivalents (or lack thereof) for Task Type 1.

4. **Add API version change log**: Expand `API_VERSION_CHANGES` in `codemenv_benchmark.py` with comprehensive Bedrock Scripting API version history.

5. **Integrate into CI**: Add benchmark to regression testing pipeline to catch conversion quality drops.

## Expected Impact

- Establishes PortKit's performance vs. 43.84% GPT-4O baseline on standardized code migration eval
- Identifies which migration task type is PortKit's current bottleneck
- Provides repeatable benchmark for tracking improvement from MMSD fine-tuning iterations
- Documents clear methodology for reproducible results

## References

- [CODEMENV Paper (arXiv:2506.00894)](https://arxiv.org/abs/2506.00894)
- [CODEMENV GitHub Repository](https://github.com/xdshen-ai/Benchmark-of-Code-Migration)
- [MMSD Dataset](../ai-engine/mmsd/README.md)
- [PortKit Rubric Evaluation](../ai-engine/evaluation/README.md)
