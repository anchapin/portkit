# Ollama Deployment Guide for PortKit Coder Models

This document outlines the process for deploying PortKit's GRPO-trained models (GRPO6, GRPO7, GRPO8) to Ollama for local inference.

> **Status**: GRPO8 training is pending. GRPO6 and GRPO7 adapters have been trained but are not yet exported to HuggingFace. This guide provides the infrastructure and documentation to enable deployment once models are ready.

## Prerequisites

- Ollama installed ([https://ollama.ai](https://ollama.ai))
- Sufficient disk space (~17GB for full 8B model with adapters)
- Optional: GPU with CUDA support for faster inference

## Model Availability

| Model | HuggingFace | Status |
|-------|-----------|--------|
| SFT v1 | `alexchapin/portkit-coder-8b-sft1` | ✅ Available |
| GRPO6 | `alexchapin/portkit-coder-8b-grpo6` | ✅ Available |
| GRPO7 | (local only) | ⚠️ Local export complete, HF upload pending |
| GRPO8 | TBD | ⏳ Training pending |

## Deployment Steps

### 1. Export GRPO Model to GGUF Format

```bash
cd ai-engine/mmsd/tinker

# For GRPO6 (from HuggingFace)
python export_grpo6.py --model alexchapin/portkit-coder-8b-grpo6 --output ./model

# For GRPO7 (local export already complete at exports/grpo7_merged)
# Merge with base model and convert to GGUF
python export_grpo7.py --push-merged  # Requires Tinker SDK + HF credits
```

### 2. Create Ollama Modelfile

Create a `Modelfile` in your model directory:

```dockerfile
# Modelfile for PortKit Coder GRPO models
FROM ./model/converted.gguf

# Model parameters
PARAMETER temperature 0.2
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 4096
PARAMETER num_predict 2048

# System prompt for Java to Bedrock translation
SYSTEM """
You are an expert Java to Bedrock Edition Minecraft mod translator.
Your task is to convert Java Edition mod code to Bedrock Edition add-on format.

Key guidelines:
- Use Bedrock's module system (@minecraft/server)
- Convert event listeners to world.beforeEvents / world.afterEvents
- Translate Player APIs to entity components
- Use system.runInterval / system.runTimeout for ticking code
- Always validate against Bedrock API documentation

Common Java to Bedrock mappings:
- MinecraftServer.getServer().getWorld() → world
- player.sendMessage() → player.sendMessage() (same API)
- event listener registration → beforeEvents.<event>.subscribe()
"""

# Template for chat interactions
TEMPLATE """
{{ if .System }}{{ .System }}

{{ end }}{{ if .Prompt }}User: {{ .Prompt }}

{{ end }}Assistant: {{ .Response }}
"""
```

### 3. Create and Run the Model in Ollama

```bash
# Create the model
ollama create portkit-coder-grpo8 -f Modelfile

# Test the model
ollama run portkit-coder-grpo8 "Translate this Java code to Bedrock: system.runInterval(() => { player.sendMessage('Hello') })"

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
