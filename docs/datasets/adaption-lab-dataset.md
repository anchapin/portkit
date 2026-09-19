# Adaption Lab Dataset

## Overview

The **adaption lab datasets** are supplementary Minecraft mod conversion pairs intended to expand the MMSD (Modding Multi-Step Dataset) training data from ~1,400 pairs to 2,000+ pairs.

## Dataset Files

The expected adaption lab datasets are located at:

```
ai-engine/mmsd/data/processed/
├── adaption_minecraft_mod_to_bedrock.jsonl
├── adaption_minecraft_bedrock_mod_conversions.jsonl
├── adaption_minecraft_mod_conversion_pairs.jsonl
├── adaption_lab_merged.jsonl  (generated after validation)
└── adaption_lab_validated/    (individual validated files)
```

**Note:** These files are expected but may not be present until generated or sourced from the adaption lab.

## Schema

Each entry in the adaption datasets follows the MMSD schema:

```json
{
  "instruction": "Mod description text...",
  "reasoning_trace": "Detailed conversion reasoning...",
  "java_source": "```java\npublic class ExampleMod {...}\n```",
  "bedrock_source": "```json\n{...}\n```\n```javascript\n// scripts/main.js\n..."
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instruction` | string | Yes | Description of the mod's functionality |
| `reasoning_trace` | string | Yes | Step-by-step conversion explanation |
| `java_source` | string | Yes | Java/Forge source code (must use Mojmap naming) |
| `bedrock_source` | string | Yes | Bedrock Edition JSON/JS implementation |

## Validation Requirements

Per [MMSD README](../ai-engine/mmsd/README.md), all Java source code in training pairs **MUST** use Mojmap naming conventions.

### Mojmap Compliance

**Valid (Mojmap) patterns:**
```java
// Method names
public void registerBlock() {}
public BlockState getDefaultState() {}

// Package names
import net.minecraft.world.level.block.Block;
import net.minecraft.world.entity.Entity;

// Class names
public class SpellcastingStation extends Block {}
```

**Invalid (SRG/MCP) patterns:**
```java
// SRG method patterns
public void func_123456_a() {}
public int field_789012;

// SRG package patterns
import net_minecraft.world.entity.Entity;
```

### Validation Pipeline

The validation script (`validators/adaption_validator.py`) performs:

1. **Schema validation** - All required fields present and non-empty
2. **Error field check** - No `Error:` or `ERROR_PREFIX` markers
3. **Java syntax validation** - Structural checks + optional javac compilation
4. **Bedrock JSON validation** - JSON syntax and format_version checks
5. **Mojmap validation** - No SRG patterns in Java source
6. **Deduplication** - Hash-based deduplication against existing `validated_pairs.jsonl`

## Validation Script Usage

```bash
# Validate all adaption datasets in the default directory
python -m mmsd.validators.adaption_validator

# Specify custom data directory
python -m mmsd.validators.adaption_validator --data-dir /path/to/data

# Skip deduplication (for independent dataset)
python -m mmsd.validators.adaption_validator --skip-dedup
```

### Output

The script produces:
- `adaption_*_validated.jsonl` - Individual validated files
- `adaption_lab_merged.jsonl` - Combined and deduplicated dataset

## Data Loader

The `adaption_data_loader.py` module provides:

```python
from mmsd.adaption_data_loader import load_training_data, AdaptionDatasetLoader

# Load MMSD + adaption data
mmsd_pairs, adaption_pairs, stats = load_training_data(
    mmsd_path="ai-engine/mmsd/data/processed/validated_pairs.jsonl",
    adaption_data_dir="ai-engine/mmsd/data/processed",
    include_adaption=True,
    adaption_weight=1.0,
)

# Discover and inspect adaption files
loader = AdaptionDatasetLoader("ai-engine/mmsd/data/processed")
files = loader.discover_adaption_files()
stats = loader.get_adaption_stats()
```

## Integration with Training

To include adaption data in training:

```bash
# Via environment variable
INCLUDE_ADAPTION=1 python -m mmsd.train_portkit_coder

# With custom weight
ADAPTION_WEIGHT=0.5 INCLUDE_ADAPTION=1 python -m mmsd.train_portkit_coder
```

## Dataset Statistics

| Metric | Value |
|--------|-------|
| Current MMSD pairs | 1,400 |
| Target total pairs | 2,000+ |
| Expected adaption pairs | ~600 |
| Validation pass rate | ~70-80% (estimated) |

## Generating Synthetic Adaption Data

For testing the pipeline, synthetic adaption data can be generated:

```python
# The adaption datasets should be sourced from the adaption lab
# This is a placeholder for when real data is available
```

## Related Issues

- Resolves: GitHub Issue #1677

## References

- [MMSD README](../ai-engine/mmsd/README.md)
- [Mojmap Validator](../ai-engine/mmsd/validators/mojmap_validator.py)
- [Code Validator](../ai-engine/mmsd/validators/code_validator.py)
- [Adaption Validator](../ai-engine/mmsd/validators/adaption_validator.py)
