"""
LLM backend factory and rate-limited model construction.

Issue #1201: LangChain/LangGraph migration — this module now exposes
stock LangChain ``BaseChatModel`` instances (``ChatOpenAI`` /
``ChatOllama``) with a built-in ``langchain_core.rate_limiters.InMemoryRateLimiter``
instead of bespoke ``RateLimitedChatOpenAI`` / ``RateLimitedZAI`` /
``OpenAICompatibleLLM`` wrappers. The previous wrappers used
``__getattr__`` delegation which broke LangGraph ``isinstance`` checks
and tool-calling.

Public API kept stable for in-tree callers:
    get_llm_backend() -> BaseChatModel
    get_fallback_llm() -> BaseChatModel
    create_rate_limited_llm(...) -> ChatOpenAI
    create_z_ai_llm(...) -> ChatOpenAI    (ZAI is OpenAI-compatible)
    create_openai_compatible_llm(...) -> ChatOpenAI
    create_ollama_llm(...) -> ChatOllama

Provider priority for ``get_llm_backend()`` is unchanged:
    OpenAI-compatible (LLM_BASE_URL set) -> Z.AI (USE_Z_AI=true)
    -> Ollama (USE_OLLAMA=true) -> OpenAI

Issue #1205 cost guardrails: callers can wrap the returned model with
the cost middleware via ``utils.cost_guardrails`` if needed; the
LLM wrappers no longer record cost themselves to keep the
``BaseChatModel`` surface clean.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclasses (kept stable for backwards-compatibility)
# ---------------------------------------------------------------------------


@dataclass
class RateLimitConfig:
    """Configuration for in-process LLM rate limiting."""

    requests_per_minute: int = 60
    tokens_per_minute: int = 60000
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0


@dataclass
class ZAIConfig:
    """Configuration for Z.AI LLM backend (OpenAI-compatible API)."""

    api_key: str = ""
    model: str = "glm-4-plus"
    base_url: str = "https://api.z.ai/v1"
    max_retries: int = 3
    timeout: int = 300
    temperature: float = 0.1
    max_tokens: int = 4000


@dataclass
class OpenAICompatibleConfig:
    """Configuration for OpenAI-compatible LLM backends.

    Covers OpenRouter, LM Studio, vLLM, Together, and any other provider
    that speaks the OpenAI HTTP API.
    """

    api_key: str = ""
    model: str = "gpt-4"
    base_url: str = "https://api.openai.com/v1"
    provider: str = "openai"
    max_retries: int = 3
    timeout: int = 300
    temperature: float = 0.1
    max_tokens: int = 4000


# ---------------------------------------------------------------------------
# RateLimiter: lightweight legacy shim
# ---------------------------------------------------------------------------


class RateLimiter:
    """Legacy rate-limiter shim retained for backwards compatibility.

    New code should use ``langchain_core.rate_limiters.InMemoryRateLimiter``
    directly via the factory functions in this module. This class is kept
    so callers that constructed a ``RateLimiter(RateLimitConfig(...))``
    still import cleanly.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()

    def wait_if_needed(self, estimated_tokens: int = 1000) -> None:  # pragma: no cover - shim
        # Delegated to the LangChain limiter attached to each model.
        return None

    def record_request(self, tokens_used: int = 1000) -> None:  # pragma: no cover - shim
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_in_memory_limiter(rpm: int) -> InMemoryRateLimiter:
    """Build a LangChain in-memory limiter from a requests-per-minute setting."""
    # Convert rpm to requests-per-second; check_every_n_seconds slightly
    # smaller than the request interval keeps latency low without busy-waiting.
    rps = max(rpm / 60.0, 0.1)
    return InMemoryRateLimiter(
        requests_per_second=rps,
        check_every_n_seconds=max(0.05, 1.0 / max(rps * 4, 1.0)),
        max_bucket_size=max(int(rpm), 1),
    )


def _env_rpm(default: int = 50) -> int:
    """Return the OpenAI requests-per-minute limit from env (or default)."""
    val = os.getenv("OPENAI_RPM_LIMIT")
    if val:
        try:
            return int(val)
        except ValueError:
            logger.warning(f"Invalid OPENAI_RPM_LIMIT={val!r}; using default {default}")
    return default


def _env_max_retries(default: int = 3) -> int:
    val = os.getenv("OPENAI_MAX_RETRIES")
    if val:
        try:
            return int(val)
        except ValueError:
            logger.warning(f"Invalid OPENAI_MAX_RETRIES={val!r}; using default {default}")
    return default


# ---------------------------------------------------------------------------
# Factory functions — return stock LangChain BaseChatModel instances
# ---------------------------------------------------------------------------


def create_rate_limited_llm(
    model_name: str = "gpt-4",
    *,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an OpenAI ``ChatOpenAI`` chat model with built-in rate limiting.

    Drop-in replacement for the previous ``RateLimitedChatOpenAI``: returns
    a true ``BaseChatModel`` that supports ``.bind_tools()``,
    ``.with_structured_output()``, and LangGraph's ``isinstance`` checks.
    """
    from langchain_openai import ChatOpenAI

    rpm = _env_rpm(50)
    max_retries = _env_max_retries(3)
    api_key = api_key or kwargs.pop("openai_api_key", None) or os.getenv("OPENAI_API_KEY")

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        max_retries=max_retries,
        rate_limiter=_build_in_memory_limiter(rpm),
        **kwargs,
    )


def create_z_ai_llm(config: Optional[ZAIConfig] = None) -> BaseChatModel:
    """Create a Z.AI chat model via OpenAI-compatible ``ChatOpenAI``.

    Z.AI exposes an OpenAI-compatible HTTP API, so we instantiate
    ``ChatOpenAI`` against ``ZAI_BASE_URL`` instead of carrying a
    bespoke wrapper class.
    """
    from langchain_openai import ChatOpenAI

    cfg = config or ZAIConfig()

    if os.getenv("Z_AI_API_KEY"):
        cfg.api_key = os.getenv("Z_AI_API_KEY")
    if os.getenv("Z_AI_MODEL"):
        cfg.model = os.getenv("Z_AI_MODEL")
    if os.getenv("Z_AI_BASE_URL"):
        cfg.base_url = os.getenv("Z_AI_BASE_URL")
    if os.getenv("Z_AI_MAX_RETRIES"):
        try:
            cfg.max_retries = int(os.getenv("Z_AI_MAX_RETRIES"))
        except ValueError:
            pass
    if os.getenv("Z_AI_TIMEOUT"):
        try:
            cfg.timeout = int(os.getenv("Z_AI_TIMEOUT"))
        except ValueError:
            pass
    if os.getenv("Z_AI_TEMPERATURE"):
        try:
            cfg.temperature = float(os.getenv("Z_AI_TEMPERATURE"))
        except ValueError:
            pass
    if os.getenv("Z_AI_MAX_TOKENS"):
        try:
            cfg.max_tokens = int(os.getenv("Z_AI_MAX_TOKENS"))
        except ValueError:
            pass

    if not cfg.api_key:
        raise ValueError("Z.AI API key is required. Set Z_AI_API_KEY environment variable.")

    return ChatOpenAI(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        max_retries=cfg.max_retries,
        timeout=cfg.timeout,
        rate_limiter=_build_in_memory_limiter(50),
    )


def create_openai_compatible_llm(
    config: Optional[OpenAICompatibleConfig] = None,
) -> BaseChatModel:
    """Create a chat model against an OpenAI-compatible endpoint.

    Covers OpenRouter, LM Studio, vLLM, Together, etc. Returns a stock
    ``ChatOpenAI`` instance pointed at the configured ``base_url``.
    """
    from langchain_openai import ChatOpenAI
    from utils.config import Config

    cfg_obj = Config()

    if config is None:
        api_key = cfg_obj.LLM_API_KEY or cfg_obj.OPENAI_API_KEY
        model = cfg_obj.LLM_MODEL or cfg_obj.OPENAI_MODEL
        base_url = cfg_obj.LLM_BASE_URL or "https://api.openai.com/v1"
        provider = cfg_obj.LLM_PROVIDER
        cfg = OpenAICompatibleConfig(
            api_key=api_key or "",
            model=model or "gpt-4",
            base_url=base_url,
            provider=provider or "openai",
            max_retries=3,
            timeout=300,
            temperature=0.1,
            max_tokens=4000,
        )
    else:
        cfg = config

    return ChatOpenAI(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        max_retries=cfg.max_retries,
        timeout=cfg.timeout,
        rate_limiter=_build_in_memory_limiter(50),
    )


def create_ollama_llm(
    model_name: str = "llama3.2",
    base_url: Optional[str] = None,
    *,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    request_timeout: int = 300,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an Ollama chat model via stock ``langchain_ollama.ChatOllama``.

    Replaces the previous LiteLLM-based ``LiteLLMOllamaWrapper`` with the
    canonical LangChain Ollama integration. The returned object is a
    ``BaseChatModel`` and works with LangGraph nodes, ``bind_tools``, and
    ``with_structured_output`` natively.
    """
    from langchain_ollama import ChatOllama

    if base_url is None:
        base_url = (
            "http://ollama:11434" if os.getenv("DOCKER_ENVIRONMENT") else "http://localhost:11434"
        )

    # Strip the ``ollama/`` prefix if a caller passed a LiteLLM-style id.
    clean_model_name = (
        model_name.removeprefix("ollama/") if model_name.startswith("ollama/") else model_name
    )

    logger.info(f"Creating Ollama LLM model={clean_model_name!r} base_url={base_url!r}")

    return ChatOllama(
        model=clean_model_name,
        base_url=base_url,
        temperature=temperature,
        num_predict=max_tokens,
        request_timeout=request_timeout,
        rate_limiter=_build_in_memory_limiter(60),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def get_llm_backend() -> BaseChatModel:
    """Return the best available LLM backend for use with LangChain/LangGraph.

    Priority order (unchanged from the legacy implementation):
    1. OpenAI-compatible (when ``LLM_BASE_URL`` is set)
    2. Z.AI (when ``USE_Z_AI=true``)
    3. Ollama (when ``USE_OLLAMA=true``)
    4. OpenAI (when ``OPENAI_API_KEY`` is set)
    """
    from utils.config import Config

    cfg = Config()

    if cfg.LLM_BASE_URL:
        try:
            logger.info(f"Initializing OpenAI-compatible LLM backend (provider={cfg.LLM_PROVIDER})")
            return create_openai_compatible_llm()
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI-compatible backend: {e}")

    if os.getenv("USE_Z_AI", "false").lower() == "true":
        try:
            logger.info("Initializing Z.AI LLM backend")
            return create_z_ai_llm()
        except Exception as e:
            logger.warning(f"Failed to initialize Z.AI backend: {e}")

    if os.getenv("USE_OLLAMA", "true").lower() == "true":
        try:
            logger.info("Initializing Ollama LLM backend")
            return create_ollama_llm()
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama backend: {e}")

    try:
        logger.info("Initializing OpenAI LLM backend")
        return create_rate_limited_llm()
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI backend: {e}")

    raise RuntimeError(
        "No LLM backend available. Configure one of:\n"
        "- OpenAI-compatible: Set LLM_BASE_URL (and optionally LLM_API_KEY, LLM_MODEL, LLM_PROVIDER)\n"
        "- Z.AI: Set USE_Z_AI=true and Z_AI_API_KEY environment variable\n"
        "- Ollama: Set USE_OLLAMA=true and ensure the Ollama service is running\n"
        "- OpenAI: Set OPENAI_API_KEY environment variable"
    )


def get_fallback_llm() -> BaseChatModel:
    """Return an Ollama-backed fallback chat model for when OpenAI is unavailable."""
    from langchain_ollama import ChatOllama

    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
    default_base_url = (
        "http://ollama:11434" if os.getenv("DOCKER_ENVIRONMENT") else "http://localhost:11434"
    )
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", default_base_url)

    logger.info(
        f"Initializing Ollama fallback LLM model={ollama_model!r} base_url={ollama_base_url!r}"
    )

    try:
        return ChatOllama(
            model=ollama_model,
            base_url=ollama_base_url,
            temperature=0.1,
            num_predict=1024,
            top_k=40,
            top_p=0.9,
            repeat_penalty=1.1,
            request_timeout=300,
            num_ctx=4096,
            num_batch=512,
            num_thread=8,
            streaming=False,
            rate_limiter=_build_in_memory_limiter(60),
        )
    except Exception as e:
        logger.error(f"Failed to create fallback Ollama LLM: {e}")
        raise RuntimeError(
            f"No LLM available. Ollama fallback failed: {e}. "
            "Troubleshooting: 1) Ensure Ollama is running. "
            "2) Verify OLLAMA_MODEL and OLLAMA_BASE_URL. "
            "3) Check connectivity to the base URL. "
            "See https://ollama.ai/docs/setup."
        ) from e
