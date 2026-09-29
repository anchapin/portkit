"""
Configuration settings for the AI Engine.
"""

import os
from typing import Optional


class Config:
    """
    Configuration class for AI Engine settings.
    All settings can be overridden via environment variables.
    """

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:password@localhost:5432/portkit_ai"
    )

    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    # OpenAI-Compatible Provider Configuration (OpenRouter, LM Studio, etc.)
    # When LLM_BASE_URL is set, OPENAI_API_KEY is used as the bearer token
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai, openrouter, lmstudio, custom
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")  # e.g., https://openrouter.ai/api/v1
    LLM_MODEL: Optional[str] = os.getenv(
        "LLM_MODEL"
    )  # e.g., anthropic/claude-3.5-sonnet, will fallback to OPENAI_MODEL
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")  # Will fallback to OPENAI_API_KEY

    # Vector DB Configuration
    VECTOR_DB_URL: str = os.getenv("VECTOR_DB_URL", "http://localhost:19530")
    VECTOR_DB_API_KEY: Optional[str] = os.getenv("VECTOR_DB_API_KEY", "your_vector_db_api_key")

    # AI Engine Configuration
    MOCK_AI_RESPONSES: bool = os.getenv("MOCK_AI_RESPONSES", "false").lower() == "true"
    BACKEND_API_URL: str = os.getenv(
        "BACKEND_API_URL", "http://localhost:8000/api/v1"
    )  # Default for local backend

    # RAG Configuration
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "openai/text-embedding-3-large")
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.7"))
    RAG_MAX_RESULTS: int = int(os.getenv("RAG_MAX_RESULTS", "10"))

    # Search Tool Fallback Configuration
    # Enable/disable fallback mechanism when primary search returns insufficient results
    SEARCH_FALLBACK_ENABLED: bool = os.getenv("SEARCH_FALLBACK_ENABLED", "true").lower() == "true"

    # Specifies which fallback tool to use (e.g., 'web_search_tool', 'api_search_tool')
    # The tool name should match the filename without extension in tools/
    FALLBACK_SEARCH_TOOL: str = os.getenv("FALLBACK_SEARCH_TOOL", "web_search_tool")

    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Performance Configuration
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
    TASK_TIMEOUT: int = int(os.getenv("TASK_TIMEOUT", "300"))  # 5 minutes

    # File Processing Configuration
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "100").replace("MB", ""))  # MB
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/portkit")

    # Java Analysis Configuration
    JAVA_ANALYSIS_TIMEOUT: int = int(os.getenv("JAVA_ANALYSIS_TIMEOUT", "60"))  # seconds

    # Asset Processing Configuration
    MAX_TEXTURE_SIZE: int = int(os.getenv("MAX_TEXTURE_SIZE", "1024"))  # pixels
    SUPPORTED_FORMATS: list[str] = ["png", "jpg", "jpeg", "ogg", "wav"]

    # Bedrock Scraper Configuration
    BEDROCK_SCRAPER_ENABLED: bool = os.getenv("BEDROCK_SCRAPER_ENABLED", "true").lower() == "true"
    BEDROCK_SCRAPER_RATE_LIMIT: float = float(
        os.getenv("BEDROCK_SCRAPER_RATE_LIMIT", "1.0")
    )  # requests per second
    BEDROCK_DOCS_CACHE_TTL: int = int(os.getenv("BEDROCK_DOCS_CACHE_TTL", "86400"))  # 24 hours

    # GPU Configuration
    GPU_TYPE: str = os.getenv("GPU_TYPE", "cpu").lower()  # nvidia, amd, cpu
    GPU_ENABLED: bool = os.getenv("GPU_ENABLED", "false").lower() == "true"
    MODEL_CACHE_SIZE: str = os.getenv("MODEL_CACHE_SIZE", "2GB")
    MAX_TOKENS_PER_REQUEST: int = int(os.getenv("MAX_TOKENS_PER_REQUEST", "4000"))

    # Self-hosted Inference Configuration (Issue #1203)
    # INFERENCE_MODE: cloud (default) | self_hosted | hybrid (self-hosted with cloud fallback)
    INFERENCE_MODE: str = os.getenv("INFERENCE_MODE", "cloud")
    # INFERENCE_PROVIDER: openrouter (default) | runpod_flash | sglang | vllm | ollama
    INFERENCE_PROVIDER: str = os.getenv("INFERENCE_PROVIDER", "openrouter")

    # Self-hosted endpoint configuration
    SELF_HOSTED_ENDPOINT: Optional[str] = os.getenv("SELF_HOSTED_ENDPOINT")
    SELF_HOSTED_API_KEY: Optional[str] = os.getenv("SELF_HOSTED_API_KEY")
    SELF_HOSTED_MODEL: str = os.getenv("SELF_HOSTED_MODEL", "Qwen3-Coder-7B")

    # RunPod Flash configuration (Phase 2)
    RUNPOD_ENDPOINT_ID: Optional[str] = os.getenv("RUNPOD_ENDPOINT_ID")
    RUNPOD_API_KEY: Optional[str] = os.getenv("RUNPOD_API_KEY")
    RUNPOD_ENDPOINT: Optional[str] = os.getenv("RUNPOD_ENDPOINT")

    # SGLang configuration (Phase 3)
    SGLANG_URL: Optional[str] = os.getenv("SGLANG_URL")
    VLLM_URL: Optional[str] = os.getenv("VLLM_URL")

    # Inference performance tuning
    INFERENCE_TIMEOUT: int = int(os.getenv("INFERENCE_TIMEOUT", "120"))
    INFERENCE_SCALE_TO_ZERO: bool = os.getenv("SCALE_TO_ZERO", "true").lower() == "true"
    INFERENCE_WARMUP_REQUESTS: int = int(os.getenv("INFERENCE_WARMUP_REQUESTS", "1"))
    INFERENCE_KEEP_ALIVE: int = int(os.getenv("INFERENCE_KEEP_ALIVE", "300"))
