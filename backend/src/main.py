from contextlib import asynccontextmanager
from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    BackgroundTasks,
    Path,
    Depends,
    Form,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db, AsyncSessionLocal
from db import crud
from services.cache import CacheService
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator
from services import addon_exporter  # For .mcaddon export
from services import conversion_parser  # For parsing converted pack output
from services.asset_conversion_service import asset_conversion_service
import shutil  # For directory operations
from typing import List, Optional, Dict
from datetime import datetime, timezone
import uvicorn
import os
import uuid
import asyncio  # Added for simulated AI conversion
import httpx  # Add for AI Engine communication
import json  # For JSON operations
from dotenv import load_dotenv
import logging
from db.init_db import init_db
from uuid import UUID as PyUUID  # For addon_id path parameter
from models import addon_models as pydantic_addon_models  # For addon Pydantic models
from services.report_models import (
    InteractiveReport,
    FullConversionReport,
)  # For conversion report model
from services.report_generator import ConversionReportGenerator
from errors import register_exception_handlers
from services.rate_limiter import (
    RateLimitMiddleware,
    init_rate_limiter,
    close_rate_limiter,
    create_global_limiter,
)
from services.security_headers import SecurityHeadersMiddleware, HTTPSRedirectMiddleware
from services.logging_middleware import LoggingMiddleware, RequestContextMiddleware
from services.sentry_config import (
    init_sentry,
    capture_conversion_error,
    capture_conversion_success,
    track_conversion_failure_rate,
    flush,
)
from services.tracing import init_tracing

# Import API routers
from api import (
    performance,
    behavioral_testing,
    validation,
    comparison,
    embeddings,
    feedback,
    experiments,
    behavior_files,
    behavior_templates,
    behavior_export,
    advanced_events,
    conversions,
    mod_imports,
    analytics,
    health,
    rag,
    billing,
    auth,
    email_webhooks,
    webhooks,
    waitlist,
    assets,
    mode_classification,
    automation_metrics,
    version_info,
    status,
    plugins,
    pre_conversion_scan,
)
from api.rate_limit_dashboard import router as rate_limit_dashboard_router

# Import mock data from report_generator
from services.report_generator import (
    MOCK_CONVERSION_RESULT_SUCCESS,
    MOCK_CONVERSION_RESULT_FAILURE,
)
from services.metrics import get_metrics
from services.structured_logging import configure_structlog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# AI Engine settings
AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")

TEMP_UPLOADS_DIR = "temp_uploads"
CONVERSION_OUTPUTS_DIR = "conversion_outputs"  # Added
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

# Conversion job status is stored in Redis via CacheService (scales across instances)


@asynccontextmanager
async def lifespan(app: FastAPI):
    testing_env = os.getenv("TESTING", "false").lower()
    if testing_env != "true":
        await init_db()
        logger.info("Database initialized")
        cleanup_result = await asset_conversion_service.cleanup_stale_assets(max_age_hours=24)
        if cleanup_result.get("cleaned", 0) > 0:
            logger.info(f"Startup cleanup: removed {cleanup_result['cleaned']} stale assets")
    yield
    logger.info("Application shutdown initiated")
    await close_rate_limiter()
    logger.info("Rate limiter closed")
    logger.info("Application shutdown complete")


# Cache service instance
cache = CacheService()

# Report generator instance
report_generator = ConversionReportGenerator()

# FastAPI app with OpenAPI configuration
app = FastAPI(
    title="Portkit Backend",
    description="AI-powered tool for converting Minecraft Java Edition mods to Bedrock Edition add-ons",
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "Portkit Team",
        "url": "https://github.com/anchapin/portkit",
        "email": "support@portkit.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "conversion",
            "description": "Mod conversion operations",
        },
        {
            "name": "files",
            "description": "File upload and management",
        },
        {
            "name": "health",
            "description": "Health check endpoints",
        },
        {
            "name": "addons",
            "description": "Addon data management",
        },
        {
            "name": "behavior-files",
            "description": "Post-conversion behavior file editing",
        },
    ],
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# Rate limiting middleware (Issue #456)
# Create rate limiter instance and add middleware synchronously
# Initialization (Redis connection) happens in startup
# Skip rate limiting in test mode to avoid 429 errors during test runs
if os.getenv("TESTING", "false").lower() != "true":
    # UserContextMiddleware must be added BEFORE RateLimitMiddleware
    # to extract user info from JWT before rate limiting checks
    from services.rate_limiter import UserContextMiddleware

    app.add_middleware(UserContextMiddleware)

    rate_limiter = create_global_limiter()
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

# Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# HTTPS Redirect Middleware - Issue #1535
# Must be added first (outermost) to catch HTTP requests before processing
# Only activates in production or when FORCE_HTTPS=true
if os.getenv("TESTING", "false").lower() != "true":
    app.add_middleware(HTTPSRedirectMiddleware)

# Request/Response Logging Middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.on_event("startup")
async def startup_event():
    """Initialize rate limiter and structured logging on startup"""
    # Initialize Sentry for error monitoring
    init_sentry()
    logger.info("Sentry error monitoring initialized")

    # Initialize OpenTelemetry tracing with Jaeger/OTLP exporters
    init_tracing(app)
    logger.info("OpenTelemetry tracing initialized")

    # Configure structured logging
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    configure_structlog(debug_mode=debug_mode)
    logger.info("Structured logging configured")

    await init_rate_limiter()
    logger.info("Rate limiting middleware initialized")


# Include API routers
app.include_router(performance.router, prefix="/api/v1/performance", tags=["performance"])
app.include_router(behavioral_testing.router, prefix="/api/v1", tags=["behavioral-testing"])
app.include_router(validation.router, prefix="/api/v1/validation", tags=["validation"])
app.include_router(comparison.router, prefix="/api/v1/comparison", tags=["comparison"])
app.include_router(embeddings.router, prefix="/api/v1/embeddings", tags=["embeddings"])
app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])
app.include_router(experiments.router, prefix="/api/v1/experiments", tags=["experiments"])
app.include_router(behavior_files.router, prefix="/api/v1", tags=["behavior-files"])
app.include_router(behavior_templates.router, prefix="/api/v1", tags=["behavior-templates"])
app.include_router(behavior_export.router, prefix="/api/v1", tags=["behavior-export"])
app.include_router(advanced_events.router, prefix="/api/v1", tags=["advanced-events"])
app.include_router(conversions.router)  # Conversions API + WebSocket
app.include_router(assets.router, prefix="/api/v1", tags=["assets"])
app.include_router(mod_imports.router, prefix="/api/v1/mods", tags=["mod-imports"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(rate_limit_dashboard_router, prefix="/api/v1/rate-limit", tags=["rate-limiting"])
app.include_router(rag.router, prefix="/api/v1/search", tags=["rag-search"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(email_webhooks.router, prefix="/api/v1/webhooks", tags=["Email Webhooks"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["Webhook Management"])
app.include_router(waitlist.router, prefix="/api/v1", tags=["waitlist"])
app.include_router(mode_classification.router, tags=["mode-classification"])
app.include_router(automation_metrics.router, prefix="/api/v1", tags=["automation-metrics"])
app.include_router(version_info.router, prefix="/api/v1", tags=["version-info"])

# Health check endpoints (no prefix - used for Kubernetes probes)
app.include_router(health.router)

# Status page endpoint (public status page)
app.include_router(status.router, prefix="/api/v1", tags=["status"])

# Plugin endpoints
app.include_router(plugins.router, prefix="/api/v1/plugins", tags=["plugins"])

# Pre-conversion scan endpoint
app.include_router(
    pre_conversion_scan.router, prefix="/api/v1/pre-conversion-scan", tags=["pre-conversion-scan"]
)

# Register exception handlers for comprehensive error handling
register_exception_handlers(app)


# Pydantic models for API documentation
class ConversionRequest(BaseModel):
    """Request model for mod conversion"""

    # Legacy
    file_name: Optional[str] = None
    # New
    file_id: Optional[str] = None
    original_filename: Optional[str] = None
    target_version: str = Field(
        default="1.20.0", description="Target Minecraft version for the conversion."
    )
    options: Optional[dict] = Field(default=None, description="Optional conversion settings.")

    @property
    def resolved_file_id(self) -> str:
        # Use file_id if provided, else generate a new UUID string (should only happen for tests)
        return self.file_id or str(uuid.uuid4())

    @property
    def resolved_original_name(self) -> str:
        return self.original_filename or self.file_name or ""


class UploadResponse(BaseModel):
    """Response model for file upload"""

    file_id: str = Field(..., description="Unique identifier assigned to the uploaded file.")
    original_filename: str = Field(..., description="The original name of the uploaded file.")
    saved_filename: str = Field(
        ...,
        description="The name under which the file is saved on the server (job_id + extension).",
    )
    size: int = Field(..., description="Size of the uploaded file in bytes.")
    content_type: Optional[str] = Field(
        default=None, description="Detected content type of the uploaded file."
    )
    message: str = Field(..., description="Status message confirming the upload.")
    filename: str = Field(..., description="The uploaded filename (matches original_filename)")


class ConversionResponse(BaseModel):
    """Response model for mod conversion"""

    job_id: str
    status: str
    message: str
    estimated_time: Optional[int] = None


class ConversionStatus(BaseModel):
    """Status model for conversion job"""

    job_id: str
    status: str
    progress: int
    message: str
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


class ConversionJob(BaseModel):
    """Detailed model for a conversion job"""

    job_id: str
    file_id: str
    original_filename: str
    status: str
    progress: int
    target_version: str
    options: Optional[dict] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("job_id", "file_id", "original_filename", mode="before")
    @classmethod
    def coerce_uuid_to_str(cls, v: object) -> str:
        if isinstance(v, uuid.UUID):
            return str(v)
        return v


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    version: str
    timestamp: str


# Health check endpoint
@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Check the health status of the API"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# Simple health endpoint for load balancers
@app.get("/health")
async def simple_health_check():
    """Simple health check for load balancers and monitoring"""
    return {"status": "healthy"}


# File upload endpoint
@app.post("/api/v1/upload", response_model=UploadResponse, tags=["files"])
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a mod file (.jar, .zip, .mcaddon) for conversion.

    - Validates file type and size (max 100MB).
    - Saves the file to a temporary location.
    - Returns a unique file identifier and other file details.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Create temporary uploads directory if it doesn't exist
    os.makedirs(TEMP_UPLOADS_DIR, exist_ok=True)

    # Note: file.size is not always available in FastAPI UploadFile
    # We'll validate size during the actual file reading process

    # Validate file type
    allowed_extensions = [".jar", ".zip", ".mcaddon"]
    original_filename = file.filename
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not supported. Allowed: {', '.join(allowed_extensions)}",
        )

    # Generate unique file identifier
    file_id = str(uuid.uuid4())
    saved_filename = f"{file_id}{file_ext}"
    file_path = os.path.join(TEMP_UPLOADS_DIR, saved_filename)

    # Save the uploaded file
    try:
        real_file_size = 0
        with open(file_path, "wb") as buffer:
            for chunk in file.file:
                real_file_size += len(chunk)
                if real_file_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size exceeds the limit of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
                    )
                buffer.write(chunk)
    except (OSError, IOError) as e:
        # File system error during upload
        raise HTTPException(status_code=500, detail="Could not save file")
    finally:
        file.file.close()

    return UploadResponse(
        file_id=file_id,
        original_filename=original_filename,
        saved_filename=saved_filename,  # The name with job_id and extension
        size=real_file_size,  # Use the actual size we read
        content_type=file.content_type,
        message=f"File '{original_filename}' saved successfully as '{saved_filename}'",
        filename=original_filename,
    )


# Simulated AI Conversion Engine (DB + Redis + mirror)
async def simulate_ai_conversion(job_id: str):
    from src.websocket.progress_handler import ProgressHandler

    logger.info(f"Starting AI simulation for job_id: {job_id}")

    # Broadcast initial queued status
    await ProgressHandler.broadcast_progress(
        conversion_id=job_id,
        agent="ConversionWorkflow",
        status="queued",
        progress=0,
        message="Job queued, waiting to start",
    )

    # Temporary directory for simulated pack output
    # Base temp dir for all simulated packs by this job
    base_simulated_pack_dir = os.path.join(TEMP_UPLOADS_DIR, "simulated_packs")
    os.makedirs(base_simulated_pack_dir, exist_ok=True)
    # Specific pack dir for this job_id
    simulated_pack_output_path = os.path.join(base_simulated_pack_dir, job_id)
    if os.path.exists(simulated_pack_output_path):  # Clean up from previous run if any
        shutil.rmtree(simulated_pack_output_path)
    os.makedirs(simulated_pack_output_path)

    try:
        async with AsyncSessionLocal() as session:
            job = await crud.get_job(session, job_id)
            if not job:
                logger.error(f"Job not found for AI simulation: {job_id}")
                return

            original_mod_name = job.input_data.get("original_filename", "ConvertedAddon").split(
                "."
            )[0]
            # Attempt to get user_id from job input_data, fall back to a default if not found
            # This field might not exist in older job records.
            user_id_for_addon = str(
                job.input_data.get("user_id", conversion_parser.DEFAULT_USER_ID)
            )

            def mirror_dict_from_job(
                current_job, progress_val=None, result_url=None, error_message=None
            ):
                return ConversionJob(
                    job_id=str(current_job.id),
                    file_id=str(current_job.input_data.get("file_id", "")),
                    original_filename=current_job.input_data.get("original_filename"),
                    status=current_job.status,
                    progress=(
                        progress_val
                        if progress_val is not None
                        else (current_job.progress.progress if current_job.progress else 0)
                    ),
                    target_version=current_job.input_data.get("target_version"),
                    options=current_job.input_data.get("options"),
                    result_url=result_url,
                    error_message=error_message,
                    created_at=current_job.created_at,
                    updated_at=current_job.updated_at,
                )

            try:
                # Stage 1: JavaAnalyzerAgent (0-25%)
                await ProgressHandler.broadcast_agent_start(
                    job_id,
                    "JavaAnalyzerAgent",
                    "Analyzing Java mod structure and dependencies",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_update(
                    job_id, "JavaAnalyzerAgent", 10, "Parsing Java AST..."
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_complete(
                    job_id, "JavaAnalyzerAgent", "Java analysis complete"
                )

                # Stage 2: Preprocessing -> Processing
                job = await crud.update_job_status(session, job_id, "processing")
                await crud.upsert_progress(session, job_id, 25)
                mirror = mirror_dict_from_job(job, 25)
                await cache.set_job_status(job_id, mirror.model_dump())
                await cache.set_progress(job_id, 25)
                logger.info(f"Job {job_id}: Status updated to {job.status}, Progress: 25%")

                # Stage 3: BedrockArchitectAgent (25-50%)
                await ProgressHandler.broadcast_agent_start(
                    job_id,
                    "BedrockArchitectAgent",
                    "Designing Bedrock conversion architecture",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_update(
                    job_id,
                    "BedrockArchitectAgent",
                    35,
                    "Mapping Java components to Bedrock equivalents...",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_complete(
                    job_id, "BedrockArchitectAgent", "Architecture design complete"
                )

                # Stage 4: Processing -> Postprocessing
                await asyncio.sleep(1)
                job = await crud.get_job(session, job_id)

                # Stage 4: Postprocessing -> Validating
                job = await crud.update_job_status(session, job_id, "postprocessing")
                await crud.upsert_progress(session, job_id, 50)
                mirror = mirror_dict_from_job(job, 50)
                await cache.set_job_status(job_id, mirror.model_dump())
                await cache.set_progress(job_id, 50)
                logger.info(f"Job {job_id}: Status updated to {job.status}, Progress: 50%")

                # Stage 5: LogicTranslatorAgent (50-75%)
                await ProgressHandler.broadcast_agent_start(
                    job_id,
                    "LogicTranslatorAgent",
                    "Translating Java logic to JavaScript",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_update(
                    job_id,
                    "LogicTranslatorAgent",
                    60,
                    "Converting game logic and behaviors...",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_complete(
                    job_id, "LogicTranslatorAgent", "Logic translation complete"
                )

                # Stage 6: AssetConverterAgent (75-90%)
                await ProgressHandler.broadcast_agent_start(
                    job_id,
                    "AssetConverterAgent",
                    "Converting assets (textures, models, sounds)",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_update(
                    job_id, "AssetConverterAgent", 80, "Processing texture files..."
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_complete(
                    job_id, "AssetConverterAgent", "Asset conversion complete"
                )

                # Update to 75% progress
                await crud.upsert_progress(session, job_id, 75)
                await cache.set_progress(job_id, 75)
                mirror = mirror_dict_from_job(job, 75)
                await cache.set_job_status(job_id, mirror.model_dump())
                logger.info(f"Job {job_id}: Progress: 75%")

                # Stage 7: Postprocessing -> Completed
                await asyncio.sleep(1)
                job = await crud.get_job(session, job_id)
                if job.status == "cancelled":
                    logger.info(f"Job {job_id} was cancelled. Stopping AI simulation.")
                    return

                # Stage 8: PackagingAgent (90-100%)
                await ProgressHandler.broadcast_agent_start(
                    job_id, "PackagingAgent", "Packaging add-on into .mcaddon file"
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_update(
                    job_id,
                    "PackagingAgent",
                    95,
                    "Creating manifest and packaging files...",
                )
                await asyncio.sleep(1)
                await ProgressHandler.broadcast_agent_complete(
                    job_id, "PackagingAgent", "Packaging complete"
                )

                # --- Simulate creating pack structure ---
                bp_name = f"{original_mod_name} BP"
                rp_name = f"{original_mod_name} RP"
                bp_dir = os.path.join(simulated_pack_output_path, bp_name)
                rp_dir = os.path.join(simulated_pack_output_path, rp_name)
                os.makedirs(os.path.join(bp_dir, "blocks"), exist_ok=True)
                os.makedirs(os.path.join(bp_dir, "recipes"), exist_ok=True)
                os.makedirs(os.path.join(rp_dir, "textures", "blocks"), exist_ok=True)
                os.makedirs(os.path.join(rp_dir, "textures", "items"), exist_ok=True)

                # BP Manifest
                with open(os.path.join(bp_dir, "manifest.json"), "w") as f:
                    json.dump(
                        {
                            "format_version": 2,
                            "header": {
                                "name": bp_name,
                                "description": "Simulated BP",
                                "uuid": str(uuid.uuid4()),
                                "version": [1, 0, 0],
                            },
                            "modules": [
                                {
                                    "type": "data",
                                    "uuid": str(uuid.uuid4()),
                                    "version": [1, 0, 0],
                                }
                            ],
                        },
                        f,
                    )
                # RP Manifest
                with open(os.path.join(rp_dir, "manifest.json"), "w") as f:
                    json.dump(
                        {
                            "format_version": 2,
                            "header": {
                                "name": rp_name,
                                "description": "Simulated RP",
                                "uuid": str(uuid.uuid4()),
                                "version": [1, 0, 0],
                            },
                            "modules": [
                                {
                                    "type": "resources",
                                    "uuid": str(uuid.uuid4()),
                                    "version": [1, 0, 0],
                                }
                            ],
                        },
                        f,
                    )
                # Dummy block behavior
                with open(os.path.join(bp_dir, "blocks", "simulated_block.json"), "w") as f:
                    json.dump(
                        {
                            "minecraft:block": {
                                "description": {"identifier": "sim:simulated_block"},
                                "components": {
                                    "minecraft:loot": "loot_tables/blocks/simulated_block.json"
                                },
                            }
                        },
                        f,
                    )
                # Dummy recipe
                with open(os.path.join(bp_dir, "recipes", "simulated_recipe.json"), "w") as f:
                    json.dump(
                        {
                            "minecraft:recipe_shaped": {
                                "description": {"identifier": "sim:simulated_recipe"},
                                "tags": ["crafting_table"],
                                "pattern": ["#"],
                                "key": {"#": {"item": "minecraft:stick"}},
                                "result": {"item": "sim:simulated_block"},
                            }
                        },
                        f,
                    )
                # Dummy texture
                dummy_texture_path = os.path.join(
                    rp_dir, "textures", "blocks", "simulated_block_tex.png"
                )
                with open(dummy_texture_path, "w") as f:
                    f.write("dummy png content")
                # --- End of pack simulation ---

                addon_data_upload, identified_assets_info = (
                    conversion_parser.transform_pack_to_addon_data(
                        pack_root_path=simulated_pack_output_path,
                        addon_name_fallback=original_mod_name,
                        addon_id_override=job_id,
                        user_id=user_id_for_addon,
                    )
                )

                # Save Addon, Blocks, Recipes (assets list in addon_data_upload is empty)
                await crud.update_addon_details(session, job_id, addon_data_upload)
                logger.info(
                    f"Job {job_id}: Addon core data (metadata, blocks, recipes) saved to DB."
                )

                # Save AddonAssets (linked to addon) and Assets (linked to conversion job)
                for asset_info in identified_assets_info:
                    await crud.create_addon_asset_from_local_path(
                        session=session,
                        addon_id=job_id,
                        source_file_path=asset_info["source_tmp_path"],
                        asset_type=asset_info["type"],
                        original_filename=asset_info["original_filename"],
                    )
                    try:
                        file_size = os.path.getsize(asset_info["source_tmp_path"])
                    except OSError:
                        file_size = None
                    await crud.create_asset(
                        session=session,
                        conversion_id=job_id,
                        asset_type=asset_info["type"],
                        original_path=asset_info["source_tmp_path"],
                        original_filename=asset_info["original_filename"],
                        file_size=file_size,
                    )
                logger.info(
                    f"Job {job_id}: {len(identified_assets_info)} assets processed and saved."
                )

                # Asset conversion integration - convert uploaded assets using AI engine
                try:
                    logger.info(f"Job {job_id}: Starting asset conversion for conversion job")
                    asset_conversion_result = (
                        await asset_conversion_service.convert_assets_for_conversion(job_id)
                    )

                    if asset_conversion_result.get("success"):
                        converted_count = asset_conversion_result.get("converted_count", 0)
                        failed_count = asset_conversion_result.get("failed_count", 0)
                        logger.info(
                            f"Job {job_id}: Asset conversion completed - {converted_count} converted, {failed_count} failed"
                        )
                    else:
                        logger.warning(f"Job {job_id}: Asset conversion batch had issues")

                except Exception as asset_error:
                    logger.error(f"Asset conversion error: {asset_error}")
                    # Don't fail the entire job for asset conversion errors

                # Original ZIP creation (can be retained or removed)
                os.makedirs(CONVERSION_OUTPUTS_DIR, exist_ok=True)
                mock_output_filename_internal = f"{job.id}_converted.zip"  # Original ZIP name
                mock_output_filepath = os.path.join(
                    CONVERSION_OUTPUTS_DIR, mock_output_filename_internal
                )
                result_url = f"/api/v1/convert/{job.id}/download"

                # Create a simple zip for download endpoint if needed, or remove if export is primary
                shutil.make_archive(
                    os.path.splitext(mock_output_filepath)[0],
                    "zip",
                    simulated_pack_output_path,
                )
                logger.info(f"Job {job_id}: Original ZIP archive created at {mock_output_filepath}")

                job = await crud.update_job_status(session, job_id, "completed")
                await crud.upsert_progress(session, job_id, 100)

                mirror = mirror_dict_from_job(job, 100, result_url)
                await cache.set_job_status(job_id, mirror.model_dump())
                await cache.set_progress(job_id, 100)
                logger.info(
                    f"Job {job_id}: AI Conversion COMPLETED. Output processed into addon DB. Original ZIP at: {mock_output_filepath}"
                )

                # Broadcast completion to WebSocket clients
                await ProgressHandler.broadcast_conversion_complete(job_id, result_url)

                # Delete input JAR file after conversion completes (data retention policy)
                # Issue: #1156
                try:
                    from services.celery_tasks import delete_input_file

                    file_id = str(job.input_data.get("file_id", ""))
                    if file_id:
                        delete_input_file.delay(job_id, file_id)
                except Exception as del_err:
                    logger.warning(f"Could not schedule input file deletion: {del_err}")

            except Exception as e_inner:
                logger.error(
                    f"Error during AI simulation processing for job {job_id}: {e_inner}",
                    exc_info=True,
                )
                job = await crud.update_job_status(session, job_id, "failed")
                mirror = mirror_dict_from_job(job, 0, None, str(e_inner))
                await cache.set_job_status(job_id, mirror.model_dump())
                await cache.set_progress(job_id, 0)
                logger.error(f"Job status updated to FAILED due to processing error: {job_id}")

                # Broadcast failure to WebSocket clients
                await ProgressHandler.broadcast_conversion_failed(job_id, str(e_inner))
            finally:
                # Clean up the temporary simulated pack directory
                if os.path.exists(simulated_pack_output_path):
                    shutil.rmtree(simulated_pack_output_path)
                    logger.info(
                        f"Cleaned up simulated pack directory: {simulated_pack_output_path}"
                    )

    except Exception as e_outer:
        logger.error(
            f"Critical database or setup failure during AI simulation for job {job_id}: {e_outer}",
            exc_info=True,
        )
        try:
            # Update cache status to failed
            failed_status = {
                "status": "failed",
                "progress": 0,
                "error_message": "Critical simulation error: " + str(e_outer),
            }
            await cache.set_job_status(job_id, failed_status)

        except Exception as cache_error:
            logger.error(
                f"Failed to update cache after critical simulation error for job {job_id}: {cache_error}",
                exc_info=True,
            )
        return


async def call_ai_engine_conversion(job_id: str):
    """Call the actual AI Engine for conversion instead of simulation"""
    async with AsyncSessionLocal() as session:
        job = await crud.get_job(session, job_id)
        if not job:
            return

        def mirror_dict_from_job(job, progress_val=None, result_url=None, error_message=None):
            return ConversionJob(
                job_id=str(job.id),
                file_id=str(job.input_data.get("file_id", "")),
                original_filename=job.input_data.get("original_filename"),
                status=job.status,
                progress=(
                    progress_val
                    if progress_val is not None
                    else (job.progress.progress if job.progress else 0)
                ),
                target_version=job.input_data.get("target_version"),
                options=job.input_data.get("options"),
                result_url=result_url if result_url is not None else None,
                error_message=error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )

        try:
            # Prepare the output path for AI Engine
            os.makedirs(CONVERSION_OUTPUTS_DIR, exist_ok=True)
            output_filename = f"{job.id}_converted.mcaddon"
            output_path = os.path.join(CONVERSION_OUTPUTS_DIR, output_filename)

            # Get the input file path
            input_file_path = os.path.join(
                TEMP_UPLOADS_DIR, f"{str(job.input_data.get('file_id', ''))}.jar"
            )

            # Call AI Engine
            conversion_options = job.input_data.get("options", {})
            conversion_options["output_path"] = output_path

            ai_request = {
                "job_id": job_id,
                "mod_file_path": input_file_path,
                "conversion_options": conversion_options,
            }

            async with httpx.AsyncClient(timeout=600.0) as client:  # 10 minute timeout
                # Start AI Engine conversion
                response = await client.post(f"{AI_ENGINE_URL}/api/v1/convert", json=ai_request)

                if response.status_code != 200:
                    raise Exception(
                        f"AI Engine failed to start conversion: {response.status_code} - {response.text}"
                    )

                # Poll AI Engine for status updates
                while True:
                    await asyncio.sleep(2)

                    # Check if job was cancelled
                    current_job = await crud.get_job(session, job_id)
                    if current_job.status == "cancelled":
                        return

                    # Get status from AI Engine
                    status_response = await client.get(f"{AI_ENGINE_URL}/api/v1/status/{job_id}")

                    if status_response.status_code != 200:
                        continue

                    ai_status = status_response.json()

                    # Map AI Engine status to backend status
                    backend_status = ai_status["status"]
                    if backend_status == "processing":
                        backend_status = "processing"
                    elif backend_status == "completed":
                        backend_status = "completed"
                    elif backend_status == "failed":
                        backend_status = "failed"

                    # Update database and cache
                    progress = ai_status.get("progress", 0)
                    job = await crud.update_job_status(session, job_id, backend_status)
                    await crud.upsert_progress(session, job_id, progress)

                    # Update in-memory mirror and cache
                    if backend_status == "completed":
                        result_url = f"/api/v1/convert/{job.id}/download"
                        mirror = mirror_dict_from_job(job, progress, result_url)
                    else:
                        mirror = mirror_dict_from_job(job, progress)

                    await cache.set_job_status(job_id, mirror.model_dump())
                    await cache.set_progress(job_id, progress)

                    if backend_status in ["completed", "failed"]:
                        break

                if backend_status == "completed":
                    # Verify the file exists
                    if not os.path.exists(output_path):
                        pass
                else:
                    pass

        except Exception as e:
            job = await crud.update_job_status(session, job_id, "failed")
            mirror = mirror_dict_from_job(job, 0, None, str(e))
            await cache.set_job_status(job_id, mirror.model_dump())
            await cache.set_progress(job_id, 0)


# Conversion endpoints
@app.post("/api/v1/convert", response_model=ConversionResponse, tags=["conversion"])
async def start_conversion(
    request: ConversionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new mod conversion job.
    Handles both legacy (file_name) and new (file_id+original_filename) fields.
    Validates that a file_id and original_filename are resolved.
    """
    # Legacy support: if file_id or original_filename missing, try to resolve from file_name
    file_id = request.file_id
    original_filename = request.original_filename

    if not file_id or not original_filename:
        # Try to resolve from legacy 'file_name'
        if request.file_name:
            # Try to extract file_id from a file_name pattern like "{file_id}.{ext}"
            parts = os.path.splitext(request.file_name)
            maybe_file_id = parts[0]
            # maybe_ext = parts[1]  # unused variable
            if not file_id:
                file_id = maybe_file_id
            if not original_filename:
                original_filename = request.file_name
        else:
            raise HTTPException(
                status_code=422,
                detail="Must provide either (file_id and original_filename) or legacy file_name.",
            )

    # Persist job to DB (status 'queued', progress 0) in a single transaction
    job = await crud.create_job(
        db,
        file_id=file_id,
        original_filename=original_filename,
        target_version=request.target_version,
        options=request.options,
        commit=False,
    )
    # Update job status to 'queued' in the same transaction
    job = await crud.update_job_status(db, str(job.id), "queued", commit=False)
    # Commit the entire transaction at once
    await db.commit()
    await db.refresh(job)

    # Build legacy-mirror dict for in-memory compatibility (ConversionJob pydantic)
    # Set mirror status to 'preprocessing', but leave DB as 'queued'
    mirror = ConversionJob(
        job_id=str(job.id),
        file_id=file_id,
        original_filename=original_filename,
        status="preprocessing",
        progress=0,
        target_version=request.target_version,
        options=request.options,
        result_url=None,
        error_message=None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
    await cache.set_job_status(str(job.id), mirror.model_dump())
    await cache.set_progress(str(job.id), 0)

    # Try AI Engine first, fallback to simulation if it fails
    background_tasks.add_task(try_ai_engine_or_fallback, str(job.id))

    return ConversionResponse(
        job_id=str(job.id),
        status="preprocessing",
        message="Conversion job started and is now preprocessing.",
        estimated_time=35,
    )


@app.get(
    "/api/v1/convert/{job_id}/status",
    response_model=ConversionStatus,
    tags=["conversion"],
)
async def get_conversion_status(
    job_id: str = Path(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="Unique identifier for the conversion job (standard UUID format).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of a specific conversion job.
    """
    # Try Redis first (for speed/freshness)
    cached = await cache.get_job_status(job_id)
    if cached:
        # Compose descriptive message
        status = cached.get("status")
        progress = cached.get("progress", 0)
        error_message = cached.get("error_message")
        result_url = cached.get("result_url")
        descriptive_message = ""
        if status == "queued":
            descriptive_message = "Job is queued and waiting to start."
        elif status == "preprocessing":
            descriptive_message = "Preprocessing uploaded file."
        elif status == "processing":
            descriptive_message = f"AI conversion in progress ({progress}%)."
        elif status == "postprocessing":
            descriptive_message = "Finalizing conversion results."
        elif status == "completed":
            descriptive_message = "Conversion completed successfully."
        elif status == "failed":
            descriptive_message = (
                f"Conversion failed: {error_message}" if error_message else "Conversion failed."
            )
        elif status == "cancelled":
            descriptive_message = "Job was cancelled by the user."
        else:
            descriptive_message = f"Job status: {status}."
        return ConversionStatus(
            job_id=job_id,
            status=status,
            progress=progress,
            message=descriptive_message,
            result_url=result_url,
            error=error_message,
            created_at=(
                cached.get("created_at", datetime.now(timezone.utc))
                if cached
                else datetime.now(timezone.utc)
            ),
        )
    # Fallback: load from DB
    job = await crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Conversion job with ID '{job_id}' not found.")
    progress = job.progress.progress if job.progress else 0
    error_message = None
    result_url = None
    status = job.status
    # Compose descriptive message
    if status == "queued":
        descriptive_message = "Job is queued and waiting to start."
    elif status == "preprocessing":
        descriptive_message = "Preprocessing uploaded file."
    elif status == "processing":
        descriptive_message = f"AI conversion in progress ({progress}%)."
    elif status == "postprocessing":
        descriptive_message = "Finalizing conversion results."
    elif status == "completed":
        descriptive_message = "Conversion completed successfully."
        # Only set result_url if job is completed
        result_url = f"/api/v1/convert/{job_id}/download"  # Updated result_url
    elif status == "failed":
        error_message = "Conversion failed."
        descriptive_message = error_message
    elif status == "cancelled":
        descriptive_message = "Job was cancelled by the user."
    else:
        descriptive_message = f"Job status: {status}."
    # Mirror for legacy tests
    mirror = ConversionJob(
        job_id=str(job.id),
        file_id=str(job.input_data.get("file_id", "")),
        original_filename=job.input_data.get("original_filename"),
        status=job.status,
        progress=progress,
        target_version=job.input_data.get("target_version"),
        options=job.input_data.get("options"),
        result_url=result_url,
        error_message=error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
    return ConversionStatus(
        job_id=job_id,
        status=status,
        progress=progress,
        message=descriptive_message,
        result_url=result_url,
        error=error_message,
        created_at=job.created_at,
    )


@app.get("/api/v1/conversions", response_model=List[ConversionStatus], tags=["conversion"])
async def list_conversions(db: AsyncSession = Depends(get_db)):
    """
    List all current and past conversion jobs.
    """
    jobs = await crud.list_jobs(db)
    statuses = []
    for job in jobs:
        try:
            progress = (
                job.progress.progress if job.progress and hasattr(job.progress, "progress") else 0
            )
        except Exception:
            progress = 0
        error_message = None
        result_url = None
        status = job.status
        message = f"Job status: {status}"
        if status == "failed":
            error_message = "Conversion failed."
            message = error_message
        elif status == "completed":
            result_url = f"/api/download/{job.id}"
        mirror = ConversionJob(
            job_id=str(job.id),
            file_id=str(job.input_data.get("file_id", "")),
            original_filename=job.input_data.get("original_filename"),
            status=status,
            progress=progress,
            target_version=job.input_data.get("target_version"),
            options=job.input_data.get("options"),
            result_url=result_url,
            error_message=error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        statuses.append(
            ConversionStatus(
                job_id=str(job.id),
                status=status,
                progress=progress,
                message=message,
                result_url=result_url,
                error=error_message,
                created_at=job.created_at,
            )
        )
    return statuses


@app.delete("/api/v1/convert/{job_id}", tags=["conversion"])
async def cancel_conversion(
    job_id: str = Path(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="Unique identifier for the conversion job to be cancelled (standard UUID format).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel an ongoing conversion job.
    """
    job = await crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Conversion job with ID '{job_id}' not found.")
    if job.status == "cancelled":
        return {"message": f"Conversion job {job_id} is already cancelled."}
    job = await crud.update_job_status(db, job_id, "cancelled")
    await crud.upsert_progress(db, job_id, 0)
    mirror = ConversionJob(
        job_id=str(job.id),
        file_id=str(job.input_data.get("file_id", "")),
        original_filename=job.input_data.get("original_filename"),
        status="cancelled",
        progress=0,
        target_version=job.input_data.get("target_version"),
        options=job.input_data.get("options"),
        result_url=None,
        error_message=None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
    await cache.set_job_status(job_id, mirror.model_dump())
    await cache.set_progress(job_id, 0)
    return {"message": f"Conversion job {job_id} has been cancelled."}


# Download endpoint
@app.get("/api/v1/convert/{job_id}/download", tags=["files"])
async def download_converted_mod(
    job_id: str = Path(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="Unique identifier for the conversion job whose output is to be downloaded (standard UUID format).",
    ),
):
    """
    Download the converted mod file.

    This endpoint allows downloading the output of a successfully completed conversion job.
    The job must have a status of "completed" and a valid result file available.
    """
    job_data = await cache.get_job_status(job_id)
    job = ConversionJob(**job_data) if job_data else None

    if not job:
        raise HTTPException(status_code=404, detail=f"Conversion job with ID '{job_id}' not found.")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not yet completed. Current status: {job.status}.",
        )

    if not job.result_url:  # Should be set if status is completed and file was made
        # This indicates an internal inconsistency if the job is 'completed'.
        raise HTTPException(
            status_code=404,
            detail=f"Result for job '{job_id}' not available or URL is missing.",
        )

    # Construct the path to the mock output file
    # The actual filename stored on server uses job_id for uniqueness
    internal_filename = f"{job.job_id}_converted.mcaddon"
    file_path = os.path.join(CONVERSION_OUTPUTS_DIR, internal_filename)

    if not os.path.exists(file_path):
        file_path = os.path.join(CONVERSION_OUTPUTS_DIR, f"{job.job_id}_converted.zip")

    if not os.path.exists(file_path):
        # This case might indicate an issue post-completion or if the file was manually removed.
        raise HTTPException(status_code=404, detail="Converted file not found on server.")

    # Determine a user-friendly download filename
    original_filename_base = os.path.splitext(job.original_filename)[0]
    download_filename = f"{original_filename_base}_converted.mcaddon"

    return FileResponse(
        path=file_path,
        media_type="application/zip",  # Still ZIP format internally
        filename=download_filename,
    )

    try:
        await init_db()
    except Exception as e:
        logger.warning(f"Database initialization failed during startup: {e}")
        logger.info("Application will continue without database initialization")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )


async def try_ai_engine_or_fallback(job_id: str):
    """Try AI Engine first, fallback to simulation if it fails"""
    try:
        # Check if AI Engine is available
        async with httpx.AsyncClient(timeout=5.0) as client:
            health_response = await client.get(f"{AI_ENGINE_URL}/api/v1/health")
            if health_response.status_code == 200:
                await call_ai_engine_conversion(job_id)
                return
    except Exception as e:
        # This catches errors when trying to connect to AI Engine
        logger.error(f"Failed to connect to AI Engine: {e}")

    # Fallback to simulation when AI Engine is unavailable
    logger.info(f"Falling back to AI simulation for job {job_id}")
    await simulate_ai_conversion(job_id)


@app.get(
    "/api/v1/jobs/{job_id}/report",
    response_model=InteractiveReport,
    tags=["conversion"],
)
async def get_conversion_report(job_id: str):
    mock_data_source = None
    if job_id == MOCK_CONVERSION_RESULT_SUCCESS["job_id"]:
        mock_data_source = MOCK_CONVERSION_RESULT_SUCCESS
    elif job_id == MOCK_CONVERSION_RESULT_FAILURE["job_id"]:
        mock_data_source = MOCK_CONVERSION_RESULT_FAILURE
    elif "success" in job_id:
        mock_data_source = MOCK_CONVERSION_RESULT_SUCCESS
    elif "failure" in job_id:
        mock_data_source = MOCK_CONVERSION_RESULT_FAILURE

    if mock_data_source:
        report = report_generator.create_interactive_report(mock_data_source, job_id)
        return report

    job_mirror_data = await cache.get_job_status(job_id)
    if job_mirror_data and job_mirror_data.get("status") == "completed":
        from datetime import datetime, timezone

        return {
            "job_id": job_id,
            "report_generation_date": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "overall_success_rate": 100.0,
                "total_features": 1,
                "converted_features": 1,
                "partially_converted_features": 0,
                "failed_features": 0,
                "assumptions_applied_count": 0,
                "processing_time_seconds": 0.0,
                "download_url": f"/api/v1/convert/{job_id}/download",
                "quick_statistics": {},
            },
            "converted_mods": [
                {
                    "name": job_mirror_data.get("original_filename") or "Unknown",
                    "version": "1.0.0",
                    "status": "Converted",
                    "warnings": None,
                    "errors": None,
                }
            ],
            "failed_mods": [],
            "feature_analysis": None,
            "smart_assumptions_report": None,
            "developer_log": None,
        }

    raise HTTPException(
        status_code=404,
        detail=f"Job ID {job_id} not found or no report available.",
    )


@app.get(
    "/api/v1/jobs/{job_id}/report/prd",
    response_model=FullConversionReport,
    tags=["conversion"],
)
async def get_conversion_report_prd(job_id: str):
    mock_data_source = None
    if job_id == MOCK_CONVERSION_RESULT_SUCCESS["job_id"]:
        mock_data_source = MOCK_CONVERSION_RESULT_SUCCESS
    elif job_id == MOCK_CONVERSION_RESULT_FAILURE["job_id"]:
        mock_data_source = MOCK_CONVERSION_RESULT_FAILURE
    elif "success" in job_id:  # Generic fallback
        mock_data_source = MOCK_CONVERSION_RESULT_SUCCESS
    elif "failure" in job_id:  # Generic fallback
        mock_data_source = MOCK_CONVERSION_RESULT_FAILURE
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Job ID {job_id} not found or no mock data available.",
        )

    report = report_generator.create_full_conversion_report_prd_style(mock_data_source)
    return report


# Addon Data Management Endpoints
@app.get(
    "/api/v1/addons/{addon_id}",
    response_model=pydantic_addon_models.AddonDetails,
    tags=["addons"],
)
async def read_addon_details(addon_id: PyUUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve an addon and its associated blocks, assets, behaviors, and recipes.
    """
    db_addon = await crud.get_addon_details(session=db, addon_id=addon_id)
    if db_addon is None:
        raise HTTPException(status_code=404, detail="Addon not found")
    return db_addon


@app.put(
    "/api/v1/addons/{addon_id}",
    response_model=pydantic_addon_models.AddonDetails,
    tags=["addons"],
)
async def upsert_addon_details(
    addon_id: PyUUID,
    addon_data: pydantic_addon_models.AddonDataUpload,
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update an addon with its full details.
    This endpoint accepts addon data (including blocks, assets, behaviors, recipes)
    and will create the addon if it doesn't exist, or update it if it does.
    For child collections (blocks, assets, recipes), this performs a full replacement.
    """
    db_addon = await crud.update_addon_details(session=db, addon_id=addon_id, addon_data=addon_data)
    if db_addon is None:  # Should not happen if crud.update_addon_details works as expected
        raise HTTPException(status_code=500, detail="Error processing addon data")
    return db_addon


# Addon Asset Endpoints


@app.post(
    "/api/v1/addons/{addon_id}/assets",
    response_model=pydantic_addon_models.AddonAsset,
    tags=["addons"],
)
async def create_addon_asset_endpoint(
    addon_id: PyUUID,
    asset_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a new asset for a given addon.
    """
    # First, verify the addon exists to avoid orphaned assets or errors
    addon = await crud.get_addon_details(
        session=db, addon_id=addon_id
    )  # Using get_addon_details to ensure addon exists
    if not addon:
        raise HTTPException(status_code=404, detail=f"Addon with id {addon_id} not found.")

    try:
        db_asset = await crud.create_addon_asset(
            session=db, addon_id=addon_id, file=file, asset_type=asset_type
        )
    except ValueError as e:  # Catch errors like Addon not found from CRUD (though checked above)
        logger.error(f"Failed to create addon asset: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=404, detail="Failed to create addon asset: Resource not found"
        )
    except Exception as e:
        logger.error(f"Failed to create addon asset: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to create addon asset: Please try again."
        )
    return db_asset


@app.get(
    "/api/v1/addons/{addon_id}/assets/{asset_id}",
    response_class=FileResponse,
    tags=["addons"],
)
async def get_addon_asset_file(
    addon_id: PyUUID,  # Included for path consistency and ownership check
    asset_id: PyUUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Download/serve an addon asset file.
    """
    db_asset = await crud.get_addon_asset(session=db, asset_id=asset_id)
    if not db_asset or db_asset.addon_id != addon_id:  # Check ownership
        raise HTTPException(
            status_code=404, detail="Asset not found or does not belong to this addon."
        )

    file_full_path = os.path.join(crud.BASE_ASSET_PATH, db_asset.path)

    if not os.path.exists(file_full_path):
        logger.error(f"Asset file not found on disk: {file_full_path} for asset_id {asset_id}")
        raise HTTPException(status_code=404, detail="Asset file not found on server.")

    return FileResponse(
        path=file_full_path,
        filename=db_asset.original_filename or os.path.basename(db_asset.path),
        media_type="application/octet-stream",  # Generic, can be improved with mimetypes library
    )


@app.put(
    "/api/v1/addons/{addon_id}/assets/{asset_id}",
    response_model=pydantic_addon_models.AddonAsset,
    tags=["addons"],
)
async def update_addon_asset_endpoint(
    addon_id: PyUUID,  # Validate addon ownership of asset
    asset_id: PyUUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace an existing asset file and its metadata.
    """
    # Verify asset exists and belongs to the addon
    existing_asset = await crud.get_addon_asset(session=db, asset_id=asset_id)
    if not existing_asset or existing_asset.addon_id != addon_id:  # Check ownership
        raise HTTPException(
            status_code=404, detail="Asset not found or does not belong to this addon."
        )

    try:
        updated_asset = await crud.update_addon_asset(session=db, asset_id=asset_id, file=file)
    except Exception as e:
        logger.error(f"Failed to update addon asset {asset_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to update addon asset. Please try again."
        )

    if not updated_asset:  # Should be caught by prior check or raise exception in CRUD
        raise HTTPException(status_code=404, detail="Asset not found after update attempt.")
    return updated_asset


@app.delete("/api/v1/addons/{addon_id}/assets/{asset_id}", status_code=204, tags=["addons"])
async def delete_addon_asset_endpoint(
    addon_id: PyUUID,  # Validate addon ownership of asset
    asset_id: PyUUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an addon asset (file and database record).
    """
    # Verify asset exists and belongs to the addon
    existing_asset = await crud.get_addon_asset(session=db, asset_id=asset_id)
    if not existing_asset or existing_asset.addon_id != addon_id:  # Check ownership
        raise HTTPException(
            status_code=404, detail="Asset not found or does not belong to this addon."
        )

    deleted_asset_info = await crud.delete_addon_asset(session=db, asset_id=asset_id)
    if not deleted_asset_info:  # Should be caught by prior check
        raise HTTPException(status_code=404, detail="Asset not found during delete operation.")

    # Return 204 No Content by default for DELETE operations
    # FastAPI will automatically handle returning no body if status_code is 204
    return


@app.get(
    "/api/v1/addons/{addon_id}/export",
    response_class=StreamingResponse,
    tags=["addons"],
)
async def export_addon_mcaddon(addon_id: PyUUID, db: AsyncSession = Depends(get_db)):
    """
    Exports the addon as a .mcaddon file.
    """
    addon_details = await crud.get_addon_details(session=db, addon_id=addon_id)
    if not addon_details:
        raise HTTPException(status_code=404, detail="Addon not found")

    try:
        # asset_base_path is where actual asset files are stored
        # This path is defined in crud.py as crud.BASE_ASSET_PATH
        zip_bytes_io = addon_exporter.create_mcaddon_zip(
            addon_pydantic=addon_details, asset_base_path=crud.BASE_ASSET_PATH
        )
    except Exception as e:
        logger.error(f"Error creating .mcaddon package for addon {addon_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export addon. Please try again.")

    # Sanitize addon name for filename
    safe_filename = "".join(c if c.isalnum() else "_" for c in addon_details.name)
    if not safe_filename:
        safe_filename = "addon"
    download_filename = f"{safe_filename}.mcaddon"

    return StreamingResponse(
        content=zip_bytes_io,
        media_type="application/zip",  # Standard for .mcaddon which is a zip file
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


# Metrics endpoint for Prometheus scraping
@app.get("/api/v1/metrics", tags=["monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint.
    """
    return Response(content=get_metrics(), media_type="text/plain")
