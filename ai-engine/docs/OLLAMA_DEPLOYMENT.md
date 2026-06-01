# Ollama Deployment Guide for PortKit Coder Models

This document outlines the process for deploying PortKit's GRPO-trained models (GRPO6, GRPO7, GRPO8) to Ollama for local inference.

> **Note**: GRPO8 training completed (25 steps logged). GRPO6/GRPO7 models are on HuggingFace but need download + GGUF conversion before Ollama deployment.

## Prerequisites

- Ollama installed (`brew install ollama` or [https://ollama.ai](https://ollama.ai))
- ~20GB disk space for base model + adapters + converted GGUF
- Optional: GPU with CUDA support for faster inference

## Model Status

| Model | HuggingFace | Local | GGUF | Ollama Ready |
|-------|-------------|-------|------|--------------|
| GRPO6 | ✅ Downloaded | ❌ | ❌ | Pending |
| GRPO7 | ✅ Cached (empty) | ❌ | ❌ | Pending |
| GRPO8 | N/A | ✅ (checkpoints) | ❌ | Not trained |

## Deployment Steps

### Option A: Using the Deploy Script

The easiest way to deploy a model to Ollama:

```bash
cd ai-engine/mmsd/tinker

# List available models
python deploy_to_ollama.py --list

# Deploy GRPO6 (downloads from HuggingFace, merges with base, converts to GGUF)
# Note: GRPO8 training completed but GGUF export not yet run
python deploy_to_ollama.py --model grpo6 --model-path ./model输出
```

### Option B: Manual Deployment

#### 1. Export GRPO Model to GGUF Format

```bash
cd ai-engine/mmsd/tinker

# Download and merge GRPO6 with base Qwen3-8B, export to GGUF
python export_grpo6.py --model alexchapin/portkit-coder-8b-grpo6 --output ./model

# For local GRPO7 checkpoints:
python export_grpo7.py --push-merged  # Requires Tinker SDK + HF credits
```

#### 2. Create Ollama Modelfile

The `docs/Modelfile.template` already exists. Copy it to your model directory:

```bash
cp ai-engine/docs/Modelfile.template ./model/Modelfile
```

#### 3. Create and Run the Model in Ollama

```bash
# Create the model
ollama create portkit-coder-grpo6 -f ./model/Modelfile

# Test the model
ollama run portkit-coder-grpo6 "Translate to Bedrock: world.afterEvents.blockBreak.subscribe()"

# Verify it's listed
ollama list
```

## Integration with PortKit

Once the model is running in Ollama, set these environment variables:

```bash
# Use Ollama for inference
export INFERENCE_MODE=self_hosted
export INFERENCE_PROVIDER=ollama
export OLLAMA_MODEL=portkit-coder-grpo8
export OLLAMA_BASE_URL=http://localhost:11434
# Or for Docker:
export OLLAMA_BASE_URL=http://ollama:11434
```

The existing `rate_limiter.py` already supports Ollama as a fallback:

```python
from utils.rate_limiter import get_fallback_llm

# Returns a ChatOllama instance when configured
llm = get_fallback_llm()
```

## Docker Deployment

Add to `docker-compose.yml`:

```yaml
ollama:
  image: ollama/ollama
  ports:
    - '11434:11434'
  volumes:
    - ollama-data:/root/.ollama
  environment:
    - OLLAMA_MODEL=portkit-coder-grpo8
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

## Performance Notes

- **Latency**: 500ms-2s local vs 5-10s API round-trip
- **VRAM**: ~16GB for 8B model, ~17GB total with GRPO adapters
- **Privacy**: No mod code sent to external APIs
- **Offline**: Fully offline capable after initial model download
