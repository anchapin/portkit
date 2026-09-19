"""
Modal inference server for PortKit's fine-tuned Qwen2.5-Coder-7B model.

Deploys alexchapin/portkit-7b (QLoRA-merged) on Modal's GPU infrastructure
with vLLM for high-throughput inference.

Usage:
    modal deploy ai-engine/services/modal_inference.py
    modal app status portkit-inference

Quantization approach:
    - fp16 (bf16): Full precision, ~14GB VRAM on A10G. Best quality.
    - AWQ 4-bit: More memory-efficient, slightly lower quality than fp16.
    - Q5_K_M is the documented MINIMUM floor (GGUF), but vLLM uses fp16/bf16/AWQ.
    - vLLM FP8 (E4M3): ~7GB VRAM, good quality/efficiency balance on H100.

vLLM does not support GGUF directly. For GGUF quantization, use SGLang or
llama.cpp-based servers instead.
"""

import os
import time

import modal

stub = modal.App("portkit-inference")

MODEL_REPO = "alexchapin/portkit-7b"
MODEL_REVISION = "main"

GPU_CONFIG = modal.gpu.A10G()
MODEL_VOLUME = modal.Volume.from_name("portkit-model-cache", create=True)


@stub.cls(
    gpu=GPU_CONFIG,
    volumes={"/model_cache": MODEL_VOLUME},
    timeout=3600,
    container_idle_timeout=300,
    allow_concurrent_inputs=10,
    retries=2,
)
class PortkitInference:
    """
    Inference endpoint for PortKit's fine-tuned Qwen2.5-Coder-7B model.

    Loads the model at fp16 (full precision) via vLLM for maximum quality.
    A10G (24GB) comfortably fits Qwen2.5-Coder-7B at fp16 with room for
    long context (8192 tokens).

    Quantization floor (issue #1320):
        - GGUF: Q5_K_M minimum (use SGLang for GGUF)
        - vLLM: fp16/bf16 recommended; AWQ 4-bit also supported
        - This deployment uses fp16 — quality is ABOVE the minimum floor
    """

    def __enter__(self):
        from vllm import LLM
        from transformers import AutoTokenizer

        model_path = f"/model_cache/{MODEL_REPO.replace('/', '_')}"
        os.makedirs(model_path, exist_ok=True)

        from huggingface_hub import snapshot_download

        print(f"Downloading {MODEL_REPO} to {model_path}...")
        try:
            snapshot_download(
                MODEL_REPO,
                revision=MODEL_REVISION,
                local_dir=model_path,
                token=os.getenv("HF_TOKEN"),
            )
        except Exception as e:
            print(f"Download failed: {e}")
            raise

        print(f"Loading vLLM (fp16, max_model_len=8192)...")
        self.llm = LLM(
            model=model_path,
            dtype="bfloat16",
            max_model_len=8192,
            tensor_parallel_size=1,
            gpu_memory_utilization=0.85,
            trust_remote_code=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
        )
        print("Model loaded successfully")

    def __exit__(self, *args):
        del self.llm
        del self.tokenizer

    @modal.method()
    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system_prompt: str = "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) to Bedrock Edition Add-ons.",
    ) -> dict:
        """
        Generate a Bedrock conversion response.

        Args:
            messages: Chat messages [{role: str, content: str}]
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            system_prompt: Override system prompt

        Returns:
            {"content": str, "usage": dict, "latency": float}
        """
        from vllm import SamplingParams

        prompt = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system_prompt}] + messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        start = time.time()
        outputs = self.llm.generate(
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

    @modal.method()
    def health(self) -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "model": MODEL_REPO,
            "quantization": "bfloat16 (above Q5_K_M minimum floor)",
            "gpu": str(GPU_CONFIG),
        }

    @modal.method()
    def chat_completions(self, body: dict) -> dict:
        """OpenAI-compatible /v1/chat/completions endpoint (reuses loaded model)."""
        from vllm import SamplingParams

        messages = body.get("messages", [])
        temperature = body.get("temperature", 0.1)
        max_tokens = body.get("max_tokens", 4096)

        system_prompt = next(
            (m["content"] for m in messages if m.get("role") == "system"),
            "You are PortKit, an expert at converting Minecraft Java Edition mods (Forge) to Bedrock Edition Add-ons.",
        )
        user_messages = [m for m in messages if m.get("role") != "system"]

        prompt = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system_prompt}] + user_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        outputs = self.llm.generate(
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
            "model": MODEL_REPO,
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


@stub.function()
@modal.web_endpoint(method="POST", label="portkit-inference")
def chat_completions(body: dict) -> dict:
    """OpenAI-compatible /v1/chat/completions endpoint (thin wrapper)."""
    return PortkitInference().chat_completions.call(body)


@stub.function()
@modal.web_endpoint(method="GET", label="portkit-inference-health")
def health():
    return {"status": "ok", "service": "portkit-inference"}


if __name__ == "__main__":
    with stub.run():
        infer = PortkitInference()
        result = infer.generate(
            messages=[
                {
                    "role": "user",
                    "content": "Convert this Java mod to Bedrock: a simple chat hook that prints Hello World to the console.",
                }
            ],
        )
        print(result)
