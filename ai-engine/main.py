"""
Portkit Engine
FastAPI service for AI-powered mod conversion using LangGraph + LangChain
"""

import json
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging using centralized configuration
from utils.logging_config import configure_structlog, get_agent_logger, setup_logging

# Load environment variables
load_dotenv()

# Setup logging with environment-based configuration
debug_mode = os.getenv("DEBUG", "false").lower() == "true"

# Also configure structlog for structured JSON logging in production
configure_structlog(
    debug_mode=debug_mode, json_format=os.getenv("LOG_JSON_FORMAT", "false").lower() == "true"
)

setup_logging(
    debug_mode=debug_mode,
    enable_file_logging=os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true",
)

logger = get_agent_logger("main")

from models.smart_assumptions import SmartAssumptionEngine
from utils.gpu_config import get_gpu_config, optimize_for_inference, print_gpu_info

# Import RAG evaluation components
try:
    from evaluation.rag_evaluator import EvaluationResult, GoldenDatasetItem, RAGEvaluator

    RAG_EVALUATOR_AVAILABLE = True
except ImportError:
    RAG_EVALUATOR_AVAILABLE = False
    RAGEvaluator = None
    GoldenDatasetItem = None
    EvaluationResult = None

# Import token budget estimator for B2B cost transparency (Issue #1188)
try:
    from agent_metrics.token_budget_estimator import (
        TokenBudgetEstimator,
        estimate_conversion_cost,
        ModMetadata,
    )

    TOKEN_BUDGET_AVAILABLE = True
except ImportError:
    TOKEN_BUDGET_AVAILABLE = False
    TokenBudgetEstimator = None
    estimate_conversion_cost = None
    ModMetadata = None

# Import progress callback for real-time updates
try:
    from utils.progress_callback import cleanup_progress_callback, create_progress_callback

    PROGRESS_CALLBACK_AVAILABLE = True
except ImportError:
    PROGRESS_CALLBACK_AVAILABLE = False
    create_progress_callback = None
    cleanup_progress_callback = None

# Import tracing
from tracing import init_tracing, get_trace_id

# Initialize GPU configuration
gpu_config = get_gpu_config()
optimize_for_inference()
logger.info(f"GPU Configuration initialized: {gpu_config.gpu_type.value}")

# Print GPU info if debug mode is enabled
if debug_mode:
    print_gpu_info()


# Status enumeration for conversion states
class ConversionStatusEnum(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# FastAPI app configuration
app = FastAPI(
    title="Portkit Engine",
    description="AI-powered conversion engine for Minecraft Java to Bedrock mod conversion",
    version="1.0.0",
    contact={
        "name": "Portkit Team",
        "url": "https://github.com/anchapin/portkit",
        "email": "support@portkit.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# CORS middleware - Restrict to portkit.cloud domains in production
# Use ALLOWED_ORIGINS env var (Fly.io secrets) for production
if os.getenv("ENVIRONMENT") == "production":
    allowed_origins = os.getenv(
        "ALLOWED_ORIGINS", "https://portkit.cloud,https://www.portkit.cloud"
    ).split(",")
else:
    allowed_origins = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080"
    ).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Global instances
assumption_engine = None
redis_client = None


# Redis job state management
class RedisJobManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.available = True

    async def set_job_status(self, job_id: str, status: "ConversionStatus") -> None:
        """Store job status in Redis with error handling"""
        try:
            if not self.available:
                raise HTTPException(status_code=503, detail="Job state storage unavailable")

            status_dict = status.model_dump()
            status_dict["started_at"] = (
                status_dict["started_at"].isoformat() if status_dict["started_at"] else None
            )
            status_dict["completed_at"] = (
                status_dict["completed_at"].isoformat() if status_dict["completed_at"] else None
            )

            await self.redis.set(
                f"ai_engine:jobs:{job_id}",
                json.dumps(status_dict),
                ex=3600,  # Expire after 1 hour
            )
        except Exception as e:
            logger.error(f"Failed to store job status in Redis: {e}", exc_info=True)
            self.available = False
            raise HTTPException(status_code=503, detail="Job state storage failed")

    async def get_job_status(self, job_id: str) -> Optional["ConversionStatus"]:
        """Retrieve job status from Redis with error handling"""
        try:
            if not self.available:
                return None

            data = await self.redis.get(f"ai_engine:jobs:{job_id}")
            if not data:
                return None

            status_dict = json.loads(data)
            # Convert ISO strings back to datetime
            if status_dict.get("started_at"):
                status_dict["started_at"] = datetime.fromisoformat(status_dict["started_at"])
            if status_dict.get("completed_at"):
                status_dict["completed_at"] = datetime.fromisoformat(status_dict["completed_at"])

            return ConversionStatus(**status_dict)
        except Exception as e:
            logger.error(f"Failed to retrieve job status from Redis: {e}", exc_info=True)
            self.available = False
            return None

    async def delete_job(self, job_id: str) -> None:
        """Remove job from Redis"""
        try:
            if self.available:
                await self.redis.delete(f"ai_engine:jobs:{job_id}")
        except Exception as e:
            logger.error(f"Failed to delete job from Redis: {e}", exc_info=True)


class InMemoryJobManager:
    """Fallback job manager using in-memory dict when Redis is unavailable."""

    def __init__(self):
        self._jobs: Dict[str, "ConversionStatus"] = {}

    async def set_job_status(self, job_id: str, status: "ConversionStatus") -> None:
        """Store job status in memory."""
        self._jobs[job_id] = status

    async def get_job_status(self, job_id: str) -> Optional["ConversionStatus"]:
        """Retrieve job status from memory."""
        return self._jobs.get(job_id)

    async def delete_job(self, job_id: str) -> None:
        """Remove job from memory."""
        self._jobs.pop(job_id, None)


job_manager = None


# Pydantic models
class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    version: str
    timestamp: str
    services: Dict[str, str]


class DependencyHealth(BaseModel):
    """Individual dependency health status"""

    name: str
    status: str
    latency_ms: float = 0.0
    message: str = ""


class HealthStatus(BaseModel):
    """Health check response model for readiness/liveness"""

    status: str = Field(..., description="Overall health status: healthy, degraded, or unhealthy")
    timestamp: str = Field(..., description="ISO timestamp of the health check")
    checks: Dict[str, Any] = Field(..., description="Individual check results")


class ConversionRequest(BaseModel):
    """Conversion request model"""

    job_id: str = Field(..., description="Unique job identifier")
    mod_file_path: str = Field(..., description="Path to the mod file")
    conversion_options: Optional[Dict[str, Any]] = Field(
        default={}, description="Conversion options"
    )
    experiment_variant: Optional[str] = Field(
        default=None, description="Experiment variant ID for A/B testing"
    )


class ConversionResponse(BaseModel):
    """Conversion response model"""

    job_id: str
    status: str
    message: str
    estimated_time: Optional[int] = None


class ConversionStatus(BaseModel):
    """Conversion status model"""

    job_id: str
    status: str
    progress: int
    current_stage: str
    message: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# Job storage is now handled by RedisJobManager - no global dict


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global assumption_engine, redis_client, job_manager

    logger.info("Starting Portkit Engine...")

    try:
        # Initialize Redis connection
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = aioredis.from_url(redis_url, decode_responses=True)

        # Test Redis connection
        await redis_client.ping()
        logger.info("Redis connection established")

        # Initialize job manager
        job_manager = RedisJobManager(redis_client)
        logger.info("RedisJobManager initialized")

        # Initialize SmartAssumptionEngine
        assumption_engine = SmartAssumptionEngine()
        logger.info("SmartAssumptionEngine initialized")

        # Initialize OpenTelemetry tracing (OTLP exporters)
        init_tracing(app)
        logger.info("OpenTelemetry tracing initialized")

        logger.info("Portkit Engine startup complete")

    except Exception as e:
        logger.warning(f"Redis not available for AI Engine startup: {e}. Using in-memory fallback.")
        redis_client = None
        job_manager = InMemoryJobManager()
        logger.info("AI Engine started with in-memory job manager (Redis unavailable)")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Check the health status of the AI Engine"""
    services = {
        "assumption_engine": "healthy" if assumption_engine else "unavailable",
    }

    # Conversion crew is now initialized per request, so we don't check it here

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
    )


# Simple health endpoint for load balancers
@app.get("/health")
async def simple_health_check():
    """Simple health check for load balancers and monitoring"""
    return {"status": "healthy"}


async def check_redis_health() -> DependencyHealth:
    """
    Check Redis connectivity and return health status.
    """
    start_time = time.time()

    try:
        if not redis_client:
            return DependencyHealth(
                name="redis",
                status="unhealthy",
                latency_ms=0.0,
                message="Redis client not initialized",
            )

        # Try a simple Redis operation
        await redis_client.ping()

        latency_ms = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="redis",
            status="healthy",
            latency_ms=latency_ms,
            message="Redis connection successful",
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"Redis health check failed: {e}")

        return DependencyHealth(
            name="redis",
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Redis connection failed: {str(e)}",
        )


@app.get("/health/readiness", response_model=HealthStatus, tags=["health"])
async def readiness_check():
    """
    Readiness probe - checks if the application can serve traffic.

    This endpoint verifies that all required dependencies (Redis) are available.
    The application should only receive traffic when this endpoint returns healthy.
    """
    checks = []

    # Check Redis
    redis_health = await check_redis_health()
    checks.append(redis_health)

    # Determine overall status
    unhealthy_checks = [c for c in checks if c.status == "unhealthy"]

    if unhealthy_checks:
        status = "unhealthy"
    else:
        status = "healthy"

    return HealthStatus(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks={
            "dependencies": {
                c.name: {"status": c.status, "latency_ms": c.latency_ms, "message": c.message}
                for c in checks
            }
        },
    )


@app.get("/health/liveness", response_model=HealthStatus, tags=["health"])
async def liveness_check():
    """
    Liveness probe - checks if the application is running and doesn't need restart.

    This endpoint verifies that the application process is running and can handle requests.
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks={"application": {"status": "running", "message": "Application process is running"}},
    )


@app.post("/api/v1/convert", response_model=ConversionResponse, tags=["conversion"])
async def start_conversion(request: ConversionRequest, background_tasks: BackgroundTasks):
    """Start a new mod conversion job"""
    trace_id = get_trace_id()
    logger.info(f"Received conversion request for job {request.job_id}, trace_id={trace_id}")

    if not job_manager or not job_manager.available:
        raise HTTPException(status_code=503, detail="Job state storage unavailable")

    # Initialize conversion crew with variant if specified
    # The crew is now initialized in the background task to avoid blocking the request

    # Create job status
    job_status = ConversionStatus(
        job_id=request.job_id,
        status="queued",
        progress=0,
        current_stage="initialization",
        message="Conversion job queued",
        started_at=datetime.now(timezone.utc),
    )

    # Store in Redis instead of global dict
    await job_manager.set_job_status(request.job_id, job_status)

    # Start conversion in background
    background_tasks.add_task(
        process_conversion,
        request.job_id,
        request.mod_file_path,
        request.conversion_options,
        request.experiment_variant,  # Pass variant to process_conversion
    )

    logger.info(f"Started conversion job {request.job_id}")

    return ConversionResponse(
        job_id=request.job_id,
        status="queued",
        message="Conversion job started",
        estimated_time=120,  # Placeholder - would be calculated based on mod size
    )


@app.get("/api/v1/status/{job_id}", response_model=ConversionStatus, tags=["conversion"])
async def get_conversion_status(job_id: str):
    """Get the status of a conversion job"""

    if not job_manager:
        raise HTTPException(status_code=503, detail="Job state storage unavailable")

    job_status = await job_manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")

    return job_status


@app.get("/api/v1/jobs", response_model=List[ConversionStatus], tags=["conversion"])
async def list_jobs():
    """List all active conversion jobs"""
    if not job_manager or not job_manager.available:
        raise HTTPException(status_code=503, detail="Job state storage unavailable")

    # Note: In production, implement pagination and filtering
    # For now, return empty list as Redis doesn't have easy "list all" without keys
    logger.warning("list_jobs endpoint returns empty - implement Redis SCAN for production")
    return []


async def process_conversion(
    job_id: str,
    mod_file_path: str,
    options: Dict[str, Any],
    experiment_variant: Optional[str] = None,
):
    """Process a conversion job through the LangGraph pipeline (issue #1201).

    The ``experiment_variant`` parameter is accepted for API compatibility
    with the legacy variant-aware crew; it is currently advisory only and
    forwarded into the pipeline options dict for downstream consumers.
    """

    progress_callback = None

    try:
        # Get current job status
        job_status = await job_manager.get_job_status(job_id)
        if not job_status:
            logger.error(f"Job {job_id} not found during processing")
            return

        # Update job status
        job_status.status = "processing"
        job_status.current_stage = "analysis"
        job_status.message = "Analyzing mod structure"
        job_status.progress = 10
        await job_manager.set_job_status(job_id, job_status)

        logger.info(f"Processing conversion for job {job_id} (engine=langgraph)")

        # Create progress callback for real-time updates if available
        if PROGRESS_CALLBACK_AVAILABLE and create_progress_callback:
            try:
                progress_callback = await create_progress_callback(job_id)
                logger.info(f"Progress callback created for job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to create progress callback: {e}")

        # Prepare output path
        output_path = options.get("output_path")
        if not output_path:
            # Default output path using job_id pattern that backend expects
            # Use the mounted volume path inside the container
            output_path = os.path.join(
                os.getenv("CONVERSION_OUTPUT_DIR", "/app/conversion_outputs"),
                f"{job_id}_converted.mcaddon",
            )

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Forward variant for downstream telemetry / A-B observability
        if experiment_variant:
            options = {**options, "experiment_variant": experiment_variant}

        await _process_with_langgraph_pipeline(
            job_id, mod_file_path, output_path, options, job_manager, progress_callback
        )

    except Exception as e:
        logger.error(f"Conversion failed for job {job_id}: {e}", exc_info=True)

        # Update job status to failed
        job_status = await job_manager.get_job_status(job_id)
        if job_status:
            job_status.status = "failed"
            job_status.message = f"Conversion failed: {str(e)}"
            try:
                await job_manager.set_job_status(job_id, job_status)
            except Exception as status_error:
                logger.error(
                    f"Failed to update job status after error: {status_error}", exc_info=True
                )
    finally:
        # Clean up progress callback
        if progress_callback and PROGRESS_CALLBACK_AVAILABLE and cleanup_progress_callback:
            try:
                await cleanup_progress_callback(job_id)
                logger.info(f"Cleaned up progress callback for job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup progress callback: {e}")


async def _process_with_langgraph_pipeline(
    job_id: str,
    mod_file_path: str,
    output_path: str,
    options: Dict[str, Any],
    job_manager: Any,
    progress_callback: Optional[Any],
) -> None:
    """Process conversion using the LangGraph pipeline."""
    try:
        from orchestration.langgraph import ConversionPipeline

        logger.info(f"Initializing LangGraph pipeline for job {job_id}")

        # Update status for pipeline initialization
        job_status = await job_manager.get_job_status(job_id)
        if job_status:
            job_status.current_stage = "pipeline_init"
            job_status.message = "Initializing LangGraph conversion pipeline"
            job_status.progress = 15
            await job_manager.set_job_status(job_id, job_status)

        # Initialize the LangGraph pipeline
        pipeline = ConversionPipeline(
            job_id=job_id,
            mod_path=mod_file_path,
            output_path=output_path,
            enable_checkpointing=os.getenv("LANGGRAPH_CHECKPOINTING", "true").lower() == "true",
            enable_langsmith=os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY"),
        )

        # Build and compile the graph
        pipeline.build_graph()
        pipeline.compile()

        # Update progress
        job_status = await job_manager.get_job_status(job_id)
        if job_status:
            job_status.current_stage = "analysis"
            job_status.message = "Analyzing Java mod structure"
            job_status.progress = 20
            await job_manager.set_job_status(job_id, job_status)

        # Execute the pipeline
        result = await pipeline.execute()

        # Check for errors in result
        if result.get("errors"):
            logger.error(f"LangGraph pipeline errors: {result.get('errors')}")

        # Update progress through conversion stages
        stages = [
            ("planning", "Creating conversion plan", 40),
            ("translation", "Translating logic to Bedrock", 60),
            ("assets", "Converting assets", 80),
            ("packaging", "Packaging Bedrock addon", 90),
            ("validation", "Validating conversion", 95),
        ]

        for stage, message, progress in stages:
            job_status = await job_manager.get_job_status(job_id)
            if job_status:
                job_status.current_stage = stage
                job_status.message = message
                job_status.progress = progress
                await job_manager.set_job_status(job_id, job_status)

            import asyncio
            await asyncio.sleep(0.5)

        # Check if output was produced
        bedrock_json = result.get("bedrock_json", {})
        if not bedrock_json and not os.path.exists(output_path):
            logger.error(f"LangGraph pipeline did not produce output: {output_path}")
            job_status = await job_manager.get_job_status(job_id)
            if job_status:
                job_status.status = "failed"
                job_status.message = "LangGraph pipeline failed to produce output"
                await job_manager.set_job_status(job_id, job_status)
            return

        logger.info(f"LangGraph conversion completed successfully: {output_path}")

        # Mark as completed
        job_status = await job_manager.get_job_status(job_id)
        if job_status:
            job_status.status = "completed"
            job_status.message = "Conversion completed successfully"
            job_status.completed_at = datetime.now(timezone.utc)
            await job_manager.set_job_status(job_id, job_status)

        logger.info(f"Completed LangGraph conversion for job {job_id}")

    except Exception as conversion_error:
        logger.error(f"LangGraph pipeline failed for job {job_id}: {conversion_error}", exc_info=True)
        # Mark job as failed
        job_status = await job_manager.get_job_status(job_id)
        if job_status:
            job_status.status = "failed"
            job_status.message = f"LangGraph pipeline failed: {str(conversion_error)}"
            await job_manager.set_job_status(job_id, job_status)


# RAG Evaluation Models


class RAGEvaluationRequest(BaseModel):
    """Request model for RAG evaluation."""

    query: str = Field(..., description="The query that was asked")
    retrieved_docs: List[str] = Field(..., description="List of retrieved document IDs")
    relevant_docs: List[str] = Field(..., description="List of relevant document IDs")
    answer: str = Field(..., description="The generated answer")
    required_keywords: Optional[List[str]] = Field(
        default=[], description="Keywords that should be in answer"
    )
    prohibited_keywords: Optional[List[str]] = Field(
        default=[], description="Keywords that should not be in answer"
    )
    query_type: Optional[str] = Field(
        default="general", description="Type of query (explanation, how_to, example, etc.)"
    )
    relevance_scores: Optional[Dict[str, float]] = Field(
        default=None, description="Relevance scores for retrieved docs"
    )


class RAGEvaluationResponse(BaseModel):
    """Response model for RAG evaluation."""

    query: str
    overall_score: float
    retrieval_metrics: Dict[str, float]
    generation_metrics: Dict[str, float]
    diversity_metrics: Dict[str, float]
    evaluation_timestamp: datetime


@app.post(
    "/api/v1/rag/evaluate",
    response_model=RAGEvaluationResponse,
    tags=["evaluation"],
    summary="Evaluate RAG system performance",
    description="Evaluate a RAG query against retrieved documents and generated answer",
)
async def evaluate_rag_query(request: RAGEvaluationRequest):
    """
    Evaluate RAG system performance for a single query.

    Computes:
    - Retrieval metrics: precision, recall, MRR, NDCG, hit rate
    - Generation metrics: keyword coverage, coherence, answer length
    - Diversity metrics: content type diversity, source diversity
    """
    if not RAG_EVALUATOR_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="RAG evaluation not available - evaluation module not loaded"
        )

    try:
        # Create evaluator and compute metrics
        evaluator = RAGEvaluator()

        # Build evaluation input
        evaluation_input = {
            "query": request.query,
            "retrieved_docs": request.retrieved_docs,
            "relevant_docs": request.relevant_docs,
            "answer": request.answer,
            "required_keywords": request.required_keywords,
            "prohibited_keywords": request.prohibited_keywords,
            "query_type": request.query_type,
            "relevance_scores": request.relevance_scores,
        }

        # Run evaluation
        result = await evaluator.evaluate_query(**evaluation_input)

        # Extract metrics
        metrics = result.metrics

        # Build response
        retrieval_metrics = {
            "precision_at_5": metrics.get("precision_at_5", 0.0),
            "recall_at_5": metrics.get("recall_at_5", 0.0),
            "mrr": metrics.get("mrr", 0.0),
            "ndcg": metrics.get("ndcg", 0.0),
            "hit_rate": metrics.get("hit_rate", 0.0),
        }

        generation_metrics = {
            "keyword_coverage": metrics.get("keyword_coverage", 0.0),
            "coherence_score": metrics.get("coherence_score", 0.0),
            "answer_length_score": metrics.get("answer_length_score", 0.0),
        }

        diversity_metrics = {
            "content_type_diversity": metrics.get("content_type_diversity", 0.0),
            "source_diversity": metrics.get("source_diversity", 0.0),
        }

        # Calculate overall score (weighted average)
        overall_score = (
            0.4 * retrieval_metrics["precision_at_5"]
            + 0.3 * generation_metrics["keyword_coverage"]
            + 0.2 * generation_metrics["coherence_score"]
            + 0.1 * diversity_metrics["source_diversity"]
        )

        return RAGEvaluationResponse(
            query=request.query,
            overall_score=overall_score,
            retrieval_metrics=retrieval_metrics,
            generation_metrics=generation_metrics,
            diversity_metrics=diversity_metrics,
            evaluation_timestamp=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"RAG evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Evaluation failed.")


class TokenEstimateRequest(BaseModel):
    """Request model for token cost estimation"""

    mod_file_path: str = Field(..., description="Path to the mod file")
    model: Optional[str] = Field(None, description="Model to use for estimation")
    budget_limit: Optional[float] = Field(None, description="Optional budget cap in USD")


class TokenEstimateResponse(BaseModel):
    """Response model for token cost estimation"""

    estimated_tokens: int = Field(..., description="Total estimated tokens")
    input_tokens: int = Field(..., description="Estimated input tokens")
    output_tokens: int = Field(..., description="Estimated output tokens")
    estimated_cost_usd: float = Field(..., description="Estimated cost in USD")
    confidence_interval: tuple[float, float] = Field(..., description="Low and high confidence bounds")
    complexity_tier: str = Field(..., description="Complexity tier: simple, moderate, complex, very_complex")
    model_used: str = Field(..., description="Model used for pricing")
    budget_check: Dict[str, Any] = Field(..., description="Budget cap check result")
    phases: Dict[str, Dict[str, int]] = Field(..., description="Per-phase token breakdown")


@app.post(
    "/api/v1/estimate",
    response_model=TokenEstimateResponse,
    tags=["estimation"],
    summary="Estimate conversion cost before running",
    description="Pre-conversion token and cost estimation for B2B transparency. "
    "Provides token budget prediction based on mod metadata before conversion runs.",
)
async def estimate_conversion_cost_endpoint(request: TokenEstimateRequest):
    """
    Estimate the token usage and cost for a conversion before running it.

    This endpoint enables B2B cost transparency by allowing customers to:
    - See estimated token consumption before conversion starts
    - Check if estimated cost fits within their budget
    - Make informed decisions about which mods to convert

    Based on regression model using: file count, LOC, class count, max class depth,
    and dependency count. Confidence intervals account for model variability.

    The estimation follows findings from "How Do AI Agents Spend Your Money?"
    (Bai et al., 2026): context tokens dominate in agentic tasks, and pre-task
    prediction is feasible with reasonable accuracy.
    """
    if not TOKEN_BUDGET_AVAILABLE or estimate_conversion_cost is None:
        raise HTTPException(
            status_code=503,
            detail="Token budget estimation not available",
        )

    try:
        result = estimate_conversion_cost(
            mod_path=request.mod_file_path,
            model=request.model,
            budget_limit=request.budget_limit,
        )

        estimate = result["estimate"]
        budget_check = result["budget_check"]

        return TokenEstimateResponse(
            estimated_tokens=estimate["total_tokens"],
            input_tokens=estimate["total_input_tokens"],
            output_tokens=estimate["total_output_tokens"],
            estimated_cost_usd=estimate["estimated_cost_usd"],
            confidence_interval=estimate["confidence_interval"],
            complexity_tier=estimate["complexity_tier"],
            model_used=estimate["model_used"],
            budget_check=budget_check,
            phases=estimate["by_phase"],
        )

    except Exception as e:
        logger.error(f"Token estimation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Estimation failed: {str(e)}")


@app.get(
    "/api/v1/rag/health",
    tags=["evaluation"],
    summary="Check RAG evaluation service health",
)
async def evaluation_health_check():
    """Check if RAG evaluation service is available."""
    return {
        "status": "healthy" if RAG_EVALUATOR_AVAILABLE else "unavailable",
        "evaluator_available": RAG_EVALUATOR_AVAILABLE,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8001)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
