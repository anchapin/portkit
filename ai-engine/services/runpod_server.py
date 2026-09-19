"""
RunPod serverless FastAPI inference server for PortKit.

Exposes OpenAI-compatible /v1/chat/completions endpoint backed by vLLM.
Model is pre-downloaded by runpod_entrypoint.sh before this process starts.

Quantization floor (issue #1320):
    - vLLM uses fp16/bf16 — above GGUF Q5_K_M minimum floor
    - For lower VRAM, switch to AWQ 4-bit via vLLM's quantization="AWQ"
"""

import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer

app = FastAPI(title="portkit-inference", version="1.0.0")

MODEL_REPO = os.getenv("MODEL_REPO", "alexchapin/portkit-7b")
MODEL_REVISION = os.getenv("MODEL_REVISION", "main")
MODEL_DIR = os.getenv("MODEL_DIR", "/model_cache/portkit_7b")
MAX_MODEL_LEN = int(os.getenv("MAX_MODEL_LEN", "8192"))

llm: LLM | None = None
tokenizer: AutoTokenizer | None = None


def load_model() -> tuple[LLM, AutoTokenizer]:
    """Load vLLM model and tokenizer."""
    print(f"[server] Loading vLLM (bfloat16, max_model_len={MAX_MODEL_LEN})...")
    llm = LLM(
        model=MODEL_DIR,
        dtype="bfloat16",
        max_model_len=MAX_MODEL_LEN,
        tensor_parallel_size=1,
        gpu_memory_utilization=0.85,
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_DIR,
        trust_remote_code=True,
    )
    print("[server] Model loaded successfully")
    return llm, tokenizer


@app.on_event("startup")
def startup():
    global llm, tokenizer
    llm, tokenizer = load_model()


@app.get("/health")
def health():
    return JSONResponse(
        {
            "status": "ok",
            "model": MODEL_REPO,
            "quantization": "bfloat16 (above Q5_K_M minimum floor)",
        }
    )


@app.post("/v1/chat/completions")
def chat_completions(body: dict):
    """
    OpenAI-compatible /v1/chat/completions endpoint.
    Compatible with SelfHostedInferenceClient via INFERENCE_MODE=self_hosted.
    """
    if llm is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    messages = body.get("messages", [])
    model = body.get("model", MODEL_REPO)
    temperature = body.get("temperature", 0.1)
    max_tokens = body.get("max_tokens", 4096)

    system_prompt = next(
        (m["content"] for m in messages if m.get("role") == "system"),
        "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) to Bedrock Edition Add-ons.",
    )
    user_messages = [m for m in messages if m.get("role") != "system"]

    prompt = tokenizer.apply_chat_template(
        [{"role": "system", "content": system_prompt}] + user_messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    outputs = llm.generate(
        prompt,
        SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["</s>", "<|end|>"],
        ),
    )

    return {
        "id": f"chatcmpl-{MODEL_REPO}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": outputs[0].outputs[0].text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(outputs[0].prompt_token_ids),
            "completion_tokens": len(outputs[0].outputs[0].token_ids),
        },
    }


@app.post("/generate")
def generate(body: dict):
    """Structured inference endpoint (non OpenAI-compatible)."""
    if llm is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    messages = body.get("messages", [])
    temperature = body.get("temperature", 0.1)
    max_tokens = body.get("max_tokens", 4096)
    system_prompt = body.get(
        "system_prompt",
        "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) to Bedrock Edition Add-ons.",
    )

    prompt = tokenizer.apply_chat_template(
        [{"role": "system", "content": system_prompt}] + messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    start = time.time()
    outputs = llm.generate(
        prompt,
        SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["</s>", "<|end|>"],
        ),
    )
    latency = time.time() - start

    return {
        "content": outputs[0].outputs[0].text,
        "usage": {
            "prompt_tokens": len(outputs[0].prompt_token_ids),
            "completion_tokens": len(outputs[0].outputs[0].token_ids),
        },
        "latency": latency,
        "model": MODEL_REPO,
    }
