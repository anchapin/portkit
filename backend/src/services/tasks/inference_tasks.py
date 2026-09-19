"""
Inference-related Celery tasks.

Self-hosted LLM inference via RunPod Flash or SGLang/vLLM, plus the generic
heavy-processing task.

Task names are preserved as ``services.celery_tasks.*`` for runtime
compatibility (celery routing, beat schedule, in-flight tasks).

Issue: #1203 - Self-hosted inference after fine-tuned model weights available
Issue: #1743 - Split celery_tasks.py into task domain modules
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="services.celery_tasks.llm_inference_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def llm_inference_task(
    self,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """
    Self-hosted LLM inference via RunPod Flash or SGLang/vLLM.

    Phase 2 (Issue #1203): Replaces hosted OpenRouter API calls with
    self-hosted inference after #997 produces fine-tuned model weights.

    Architecture:
    - Celery worker picks up task from Redis queue
    - Calls RunPod Flash endpoint (vLLM + fine-tuned model)
    - Or calls SGLang/vLLM via OpenAI-compatible API
    - Result stored in Redis, returned to client

    Args:
        self: Celery task instance (provided by bind=True)
        messages: Chat messages list [{"role": "user", "content": "..."}]
        model: Model name (uses SELF_HOSTED_MODEL env var if None)
        temperature: Sampling temperature (default 0.1)
        max_tokens: Max output tokens (default 4096)

    Returns:
        Dict with success, content, model, provider, duration, cost, error
    """
    from utils.self_hosted_inference import (
        SelfHostedInferenceClient,
        InferenceConfig,
        InferenceProvider,
        InferenceMode,
    )
    import os

    provider_str = os.getenv("INFERENCE_PROVIDER", "openrouter").lower()
    provider = InferenceProvider.OPENROUTER
    if provider_str == "runpod_flash":
        provider = InferenceProvider.RUNPOD_FLASH
    elif provider_str == "sglang":
        provider = InferenceProvider.SGLANG
    elif provider_str == "vllm":
        provider = InferenceProvider.VLLM

    config = InferenceConfig(
        provider=provider,
        mode=InferenceMode.SELF_HOSTED,
        model_name=model or os.getenv("SELF_HOSTED_MODEL", "Qwen3-Coder-7B"),
        endpoint_url=os.getenv("SELF_HOSTED_ENDPOINT") or os.getenv("RUNPOD_ENDPOINT"),
        api_key=os.getenv("SELF_HOSTED_API_KEY") or os.getenv("RUNPOD_API_KEY"),
        runpod_endpoint_id=os.getenv("RUNPOD_ENDPOINT_ID"),
        runpod_api_key=os.getenv("RUNPOD_API_KEY"),
        sglang_url=os.getenv("SGLANG_URL"),
        vllm_url=os.getenv("VLLM_URL"),
        max_tokens=max_tokens,
        temperature=temperature,
    )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    client = SelfHostedInferenceClient(config)

    try:
        result = loop.run_until_complete(
            client.complete(
                messages=messages,
                model=config.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        return {
            "success": result.success,
            "content": result.content,
            "model": result.model,
            "provider": result.provider,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration": result.duration,
            "cost": result.cost,
            "error": result.error,
        }
    except Exception as e:
        logger.error(f"LLM inference task failed: {e}")
        raise self.retry(exc=e)


@shared_task(name="services.celery_tasks.heavy_task")
def heavy_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Heavy processing task for batch operations."""
    logger.info(f"Processing heavy task")
    return {"status": "completed"}
