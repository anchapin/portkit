"""
Conversion API endpoints.

This module provides REST endpoints for managing conversion jobs:
- POST /api/v1/conversions - Start new conversion
- GET /api/v1/conversions - List conversions (paginated)
- GET /api/v1/conversions/{id} - Get conversion status
- GET /api/v1/conversions/{id}/download - Download .mcaddon file
- DELETE /api/v1/conversions/{id} - Cancel/delete conversion
- WS /api/v1/conversions/{id}/ws - WebSocket progress endpoint

Issue #1151: Conversion job timeout handling and per-user rate limiting
"""

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
    Request,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator, validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db
from db import crud
from db.models import User
from src.websocket.manager import manager
from src.websocket.progress_handler import ProgressHandler
from services.cache import CacheService
from services.celery_tasks import enqueue_task, TaskPriority
from services.celery_config import get_conversion_timeout  # Issue #1151
from services.celery_monitoring import get_celery_monitor  # Issue #1151: Queue depth monitoring
from services.conversion_service import get_conversion_service
from services.metering_service import MeteringService
from services.rate_limiter import (
    RateLimitConfig,
    conversion_rate_limiter,
)
from security.file_security import FileSecurityScanner, SecurityScanResult
from security.auth import verify_token, verify_api_key
from security.path_sanitization import (  # issue #1429
    PathSanitizationError,
    safe_join,
    sanitize_for_log,
)
from api._authz import get_current_user, assert_owner  # issue #1417

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuration
TEMP_UPLOADS_DIR = os.getenv("TEMP_UPLOADS_DIR", "temp_uploads")
CONVERSION_OUTPUTS_DIR = os.getenv("CONVERSION_OUTPUTS_DIR", "conversion_outputs")
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB chunks for chunked uploads
ALLOWED_EXTENSIONS = {".jar", ".zip"}

# Cache service
cache = CacheService()

# Security scanner instance
_security_scanner: Optional[FileSecurityScanner] = None

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)


def get_security_scanner() -> FileSecurityScanner:
    """Get or create the global security scanner instance."""
    global _security_scanner
    if _security_scanner is None:
        _security_scanner = FileSecurityScanner()
    return _security_scanner


async def get_api_key_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional API key authentication - supports both Bearer tokens and API keys."""
    if not credentials:
        return None

    # Try JWT token first
    token = credentials.credentials
    user_id = verify_token(token)
    if user_id:
        try:
            user_uuid = UUID(user_id)
            result = await db.execute(select(User).where(User.id == user_uuid))
            return result.scalar_one_or_none()
        except (ValueError, TypeError):
            return None

    # Try API key (Bearer format with mpk_ prefix)
    if credentials.scheme.lower() == "bearer" and token.startswith("mpk_"):
        return await verify_api_key(db, token)

    return None


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional authentication - returns None if no valid token provided."""
    if not credentials:
        return None

    token = credentials.credentials
    user_id = verify_token(token)
    if not user_id:
        return None

    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        return None

    result = await db.execute(select(User).where(User.id == user_uuid))
    return result.scalar_one_or_none()


# Pydantic Models
class ConversionOptions(BaseModel):
    """Options for conversion behavior."""

    assumptions: str = Field(
        default="conservative",
        description="Conversion strategy: 'conservative' or 'aggressive'",
    )
    target_version: str = Field(
        default="1.20.0",
        description="Target Minecraft Bedrock version",
    )
    notify_on_completion: bool = Field(
        default=True,
        description="Send email notification when conversion completes",
    )

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, v):
        if v not in ("conservative", "aggressive"):
            raise ValueError("assumptions must be 'conservative' or 'aggressive'")
        return v


class ConversionCreateRequest(BaseModel):
    """Request model for creating a conversion (multipart form data)."""

    options: Optional[ConversionOptions] = Field(default=None, description="Conversion options")


class ConversionCreateResponse(BaseModel):
    """Response model for conversion creation."""

    conversion_id: str = Field(..., description="UUID of the conversion job")
    status: str = Field(..., description="Initial status (queued)")
    estimated_time_seconds: int = Field(
        default=1800, description="Estimated conversion time in seconds"
    )
    created_at: datetime = Field(
        ...,
        description="ISO 8601 timestamp when conversion was created",
    )


class AssetCategoryStatus(BaseModel):
    """Per-asset category conversion status (Issue #1087)."""

    category: str = Field(..., description="Category name: textures, models, recipes, etc.")
    status: str = Field(..., description="converted, partial, failed, or pending")
    total: int = Field(default=0, description="Total items in this category")
    converted: int = Field(default=0, description="Successfully converted items")
    partial: int = Field(default=0, description="Partially converted items")
    failed: int = Field(default=0, description="Failed items")
    percentage: float = Field(default=0.0, description="Conversion percentage")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class StructuredError(BaseModel):
    """Structured error with code and retry info (Issue #1087)."""

    error_code: str = Field(..., description="Short error code: INVALID_FILE, PARSE_ERROR, etc.")
    error_type: str = Field(..., description="Error type: conversion_error, validation_error, etc.")
    message: str = Field(..., description="Error message")
    is_retryable: bool = Field(..., description="Whether client can retry this operation")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class ConversionTimeoutError(BaseModel):
    """Structured timeout response - not a 500 error (Issue #1151)."""

    error_code: str = Field(
        default="CONVERSION_TIMEOUT",
        description="Error code for timeout: CONVERSION_TIMEOUT",
    )
    error_type: str = Field(
        default="timeout_error",
        description="Error type: timeout_error",
    )
    message: str = Field(
        ...,
        description="Human-readable timeout message",
    )
    timeout_seconds: int = Field(
        ...,
        description="Configured timeout in seconds for this tier",
    )
    tier: str = Field(
        ...,
        description="User's subscription tier that determined the timeout",
    )
    can_retry: bool = Field(
        default=True,
        description="Whether client can retry with same or longer timeout",
    )
    retry_after_seconds: Optional[int] = Field(
        None,
        description="Suggested wait time before retrying",
    )


class ConversionStage(str, Enum):
    """Conversion pipeline stages for progress indicator."""

    QUEUED = "queued"
    ANALYZING = "analyzing"
    CONVERTING = "converting"
    PACKAGING = "packaging"
    COMPLETE = "complete"


class ConversionStatusResponse(BaseModel):
    """Response model for conversion status."""

    conversion_id: str = Field(..., description="UUID of the conversion job")
    status: str = Field(..., description="Current status")
    progress: int = Field(..., description="Progress percentage (0-100)")
    message: str = Field(..., description="Human-readable status message")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    result_url: Optional[str] = Field(None, description="Download URL if completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    current_stage: Optional[str] = Field(
        None,
        description="Current conversion stage: queued, analyzing, converting, packaging, complete",
    )
    # Issue #1087: Enhanced error and partial result handling
    structured_error: Optional[StructuredError] = Field(
        None, description="Structured error with code and retryability"
    )
    asset_results: Optional[List[AssetCategoryStatus]] = Field(
        None, description="Per-asset category breakdown for partial results"
    )
    overall_percentage: Optional[float] = Field(
        None, description="Overall conversion percentage across all assets"
    )
    # Issue #979: Conversion history with per-user stats
    complexity_tier: Optional[str] = Field(
        None, description="Complexity tier: simple, moderate, complex"
    )
    features_converted: Optional[List[str]] = Field(
        None, description="List of features successfully converted"
    )
    features_skipped: Optional[List[str]] = Field(
        None, description="List of features that were skipped"
    )
    warnings: Optional[List[str]] = Field(None, description="List of warnings during conversion")
    email_verified: Optional[bool] = Field(
        None, description="Whether completion email was verified/sent successfully"
    )


class ConversionListResponse(BaseModel):
    """Response model for conversion listing."""

    conversions: List[ConversionStatusResponse]
    total: int = Field(..., description="Total number of conversions")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")


class ConversionReportDownloadResponse(BaseModel):
    """Response model for conversion report download."""

    download_url: str = Field(..., description="URL to download the report")
    format: str = Field(..., description="Report format: json, html, csv")


class ConversionStep(BaseModel):
    """Individual step in the conversion pipeline."""

    step_id: str = Field(..., description="Unique step identifier (e.g., 'step_1')")
    step_name: str = Field(..., description="Human-readable step name")
    status: str = Field(..., description="Status: pending, running, completed, failed")
    started_at: Optional[datetime] = Field(None, description="Step start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Step completion timestamp")
    duration_ms: Optional[float] = Field(None, description="Step duration in milliseconds")
    message: Optional[str] = Field(None, description="Step status message")
    details: Optional[str] = Field(None, description="Detailed information about the step")
    error: Optional[str] = Field(None, description="Error message if step failed")
    error_code: Optional[str] = Field(None, description="Error code if step failed")
    artifacts: Optional[Dict[str, Any]] = Field(
        None, description="Output artifacts produced by this step"
    )


class ConversionSummaryStats(BaseModel):
    """Summary statistics for conversion report."""

    total_steps: int = Field(..., description="Total number of steps in pipeline")
    completed_steps: int = Field(..., description="Number of completed steps")
    failed_steps: int = Field(..., description="Number of failed steps")
    total_duration_ms: float = Field(..., description="Total conversion duration in ms")
    success_rate: float = Field(..., description="Success rate percentage (0-100)")
    features_total: int = Field(default=0, description="Total features analyzed")
    features_converted: int = Field(default=0, description="Features successfully converted")
    features_failed: int = Field(default=0, description="Features that failed conversion")
    features_partial: int = Field(default=0, description="Partially converted features")
    assumptions_used: int = Field(default=0, description="Number of smart assumptions applied")


class ConversionStepByStepReportResponse(BaseModel):
    """Response model for step-by-step conversion report (Issue #1548)."""

    conversion_id: str = Field(..., description="UUID of the conversion job")
    status: str = Field(..., description="Overall conversion status")
    original_filename: str = Field(..., description="Original uploaded filename")
    target_version: str = Field(..., description="Target Minecraft Bedrock version")
    created_at: datetime = Field(..., description="Conversion start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Conversion completion timestamp")
    steps: List[ConversionStep] = Field(..., description="Ordered list of conversion steps")
    summary: ConversionSummaryStats = Field(..., description="Summary statistics")
    errors: List[StructuredError] = Field(
        default_factory=list, description="List of errors encountered"
    )
    warnings: List[str] = Field(default_factory=list, description="List of warnings")


# Resumable Upload Models
class ChunkUploadInitResponse(BaseModel):
    """Response for initializing a chunked upload."""

    upload_id: str = Field(..., description="Unique identifier for this upload session")
    chunk_size: int = Field(..., description="Size of each chunk in bytes")
    total_size: int = Field(..., description="Total file size in bytes")
    filename: str = Field(..., description="Original filename")
    message: str = Field(..., description="Status message")


class ChunkUploadResponse(BaseModel):
    """Response for chunk upload."""

    upload_id: str = Field(..., description="Upload session ID")
    chunk_number: int = Field(..., description="Current chunk number (1-indexed)")
    chunks_received: int = Field(..., description="Total chunks received")
    total_chunks: int = Field(..., description="Total expected chunks")
    progress: float = Field(..., description="Upload progress (0-100)")


class UploadProgressResponse(BaseModel):
    """Response for upload progress check."""

    upload_id: str
    received_bytes: int
    total_bytes: int
    progress: float
    status: str


# Helper Functions
def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal attacks.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename with only safe characters
    """
    # Remove directory paths (handles both / and \)
    filename = os.path.basename(filename)

    # Remove any path components that might have slipped through
    # This handles any attempts to use .. or absolute paths
    filename = filename.replace("..", "")
    filename = filename.replace("\\", "")

    # Also check for URL-encoded path traversal
    filename = filename.replace("%2e%2e", "")
    filename = filename.replace("%2E%2E", "")

    # Remove dangerous characters - only allow safe characters
    # This is a whitelist approach: alphanumeric, underscore, hyphen, and period
    filename = "".join(c for c in filename if c.isalnum() or c in "._-")

    # Ensure filename is not empty
    if not filename:
        filename = "uploaded_file"

    # Additional check: verify the filename doesn't start with a period
    # (hidden files on Unix systems)
    if filename.startswith("."):
        filename = "file" + filename

    return filename


def validate_path_safe(path: str, base_dir: Path) -> bool:
    """
    Validate that a path doesn't escape the base directory.

    This is a defense-in-depth check for path traversal.

    Args:
        path: The path to validate
        base_dir: The base directory that should contain the path

    Returns:
        True if the path is safe (within base_dir), False otherwise
    """
    try:
        # Resolve the full path
        full_path = (base_dir / path).resolve()

        # Check if the resolved path is within the base directory
        full_path.relative_to(base_dir.resolve())
        return True
    except (ValueError, OSError):
        # ValueError: path escapes base_dir
        # OSError: invalid path components
        return False


def _chunks_dir_for_upload(upload_id_str: str) -> Path:
    """
    Issue #1429: return ``<TEMP_UPLOADS_DIR>/chunks/<upload_id_str>`` after
    routing the join through :func:`security.path_sanitization.safe_join`.

    Centralises path construction for every chunked-upload endpoint so each
    sink (``os.makedirs``, ``open``, ``shutil.rmtree``, ``os.listdir``, ...)
    sees a path that has been allow-list validated and proven contained
    in ``TEMP_UPLOADS_DIR``. Recognised by CodeQL as a sanitizer because
    ``safe_join`` rejects any segment that does not match
    ``[A-Za-z0-9._-]+`` and verifies containment via ``Path.resolve()``
    + ``relative_to``.

    Raises:
        HTTPException(400): if ``upload_id_str`` is malformed.
    """
    try:
        # Path is created on demand by callers that need it.
        return safe_join(Path(TEMP_UPLOADS_DIR).resolve(), "chunks", upload_id_str)
    except PathSanitizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload session",
        ) from exc


def validate_file_type(filename: str) -> tuple[bool, str]:
    """
    Validate file type is allowed.

    Args:
        filename: Name of the file to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    _, ext = os.path.splitext(filename.lower())

    if ext not in ALLOWED_EXTENSIONS:
        return (
            False,
            f"File type {ext} not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    return True, ""


async def validate_file_size(file: UploadFile) -> tuple[bool, str]:
    """
    Validate file size does not exceed maximum.

    Args:
        file: UploadFile to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Use seek/tell to get file size efficiently without reading content
    file.file.seek(0, 2)
    total_size = file.file.tell()
    await file.seek(0)

    if total_size > MAX_UPLOAD_SIZE:
        return False, f"File size exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit"

    return True, ""


async def scan_uploaded_file(file_path: Path) -> SecurityScanResult:
    """
    Perform security scan on an uploaded file.

    This function:
    - Scans for ZIP bombs and compression bombs
    - Detects path traversal attempts
    - Checks for nested archives
    - Validates file count limits
    - Checks for suspicious content

    Args:
        file_path: Path to the uploaded file

    Returns:
        SecurityScanResult with scan findings

    Raises:
        HTTPException: If critical security threats are found
    """
    scanner = get_security_scanner()
    result = scanner.scan_file(file_path)

    if result.has_critical_threats:
        logger.warning(f"Critical security threat detected in {file_path}: {result.threats}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File rejected due to security threat: {result.threats[0].message}",
        )

    if result.has_high_threats:
        logger.warning(f"High severity security threat detected in {file_path}: {result.threats}")
        # Log but don't reject for high severity - could be false positives

    return result


async def validate_and_scan_file(file: UploadFile, file_path: Path) -> SecurityScanResult:
    """
    Validate and scan an uploaded file.

    Performs both basic validation (size, type) and security scanning.

    Args:
        file: The uploaded file
        file_path: Path where the file will be saved

    Returns:
        SecurityScanResult with scan findings

    Raises:
        HTTPException: If validation or scanning fails
    """
    # Step 1: Validate file size
    is_valid_size, size_error = await validate_file_size(file)
    if not is_valid_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=size_error)

    # Step 2: Validate file type
    is_valid_type, type_error = validate_file_type(file.filename or "unknown")
    if not is_valid_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=type_error)

    # Step 3: Sanitize filename to prevent path traversal
    sanitize_filename(file.filename or "uploaded_file")

    # Step 4: Perform security scan
    result = await scan_uploaded_file(file_path)

    return result


# WebSocket Endpoint
@router.websocket("/api/v1/conversions/{conversion_id}/ws")
async def websocket_conversion_progress(websocket: WebSocket, conversion_id: str):
    """
    WebSocket endpoint for real-time conversion progress updates.

    Connect to this endpoint to receive live progress updates for a conversion job.

    Message Format (Server → Client):
    ```json
    {
      "type": "agent_progress",
      "data": {
        "agent": "JavaAnalyzerAgent",
        "status": "in_progress",
        "progress": 45,
        "message": "Analyzing Java AST...",
        "timestamp": "2025-02-12T10:30:00Z",
        "details": {}
      }
    }
    ```

    Message Types:
    - agent_progress: Individual agent progress update
    - conversion_complete: Entire conversion completed
    - conversion_failed: Entire conversion failed

    Args:
        websocket: WebSocket connection
        conversion_id: UUID of the conversion job to follow
    """
    await manager.connect(websocket, conversion_id)

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connection_established",
                "data": {
                    "conversion_id": conversion_id,
                    "message": "Connected to conversion progress stream",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

        # Keep connection alive and handle incoming messages
        while True:
            # Receive any messages from client (for future bidirectional support)
            try:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_json(
                            {
                                "type": "pong",
                                "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                            }
                        )
                        continue
                except (json.JSONDecodeError, AttributeError):
                    pass
                # Issue #1429: conversion_id (URL str) and data (WS frame)
                # are both untrusted; sanitize before logging to prevent
                # CWE-117 log forgery (CodeQL py/log-injection).
                _safe_conv_id = sanitize_for_log(conversion_id)
                logger.debug(
                    "Received WebSocket message for %s: %s",
                    _safe_conv_id,
                    sanitize_for_log(data),
                )
            except WebSocketDisconnect:
                logger.info(
                    "WebSocket disconnected for conversion %s",
                    sanitize_for_log(conversion_id),
                )
                break

    except Exception as e:
        logger.error(
            "WebSocket error for conversion %s: %s",
            sanitize_for_log(conversion_id),
            sanitize_for_log(e),
        )
    finally:
        manager.disconnect(websocket, conversion_id)


def _user_owns_job(job, current_user) -> bool:
    """Return True iff ``job`` is owned by ``current_user`` (issue #1417)."""
    if job is None:
        return False
    job_user_id = getattr(job, "user_id", None)
    if job_user_id is None:
        return False
    return str(job_user_id) == str(current_user.id)


# REST Endpoints
@router.post(
    "/api/v1/conversions",
    response_model=ConversionCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["conversions"],
)
async def create_conversion(
    file: UploadFile = File(..., description="Mod file (.jar or .zip)"),
    options: str = Form(default="{}", description="JSON string of conversion options"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user: User = Depends(get_current_user),
):
    """
    Start a new mod conversion job.

    Uploads a Java mod file and starts the conversion process to Bedrock Edition.
    Returns immediately with a conversion_id for tracking progress.

    **Security:**
    - Validates file type (.jar, .zip only)
    - Enforces 100MB file size limit
    - Sanitizes filenames to prevent path traversal
    - Rate limiting (applied at middleware level)

    **Request:** multipart/form-data
    - file: The mod file (binary)
    - options: JSON string with conversion options
      ```json
      {
        "assumptions": "conservative",
        "target_version": "1.20.0"
      }
      ```

    **Response:** 202 Accepted
    ```json
    {
      "conversion_id": "uuid-v4",
      "status": "queued",
      "estimated_time_seconds": 1800,
      "created_at": "2025-02-12T10:30:00Z"
    }
    ```

    Use the returned conversion_id with:
    - GET /api/v1/conversions/{id} - Check status
    - WS /api/v1/conversions/{id}/ws - Real-time progress
    - GET /api/v1/conversions/{id}/download - Download result
    """
    # Issue #1151: Per-user rate limiting tied to subscription tier
    # Check queue depth before accepting new conversion
    monitor = get_celery_monitor()
    queue_health = monitor.check_queue_health()

    if not queue_health["healthy"] and queue_health["alerts"]:
        for alert in queue_health["alerts"]:
            if alert["severity"] == "P0":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "service_unavailable",
                        "message": "Conversion service is temporarily unavailable due to high load. Please try again later.",
                        "retry_after": 60,
                    },
                )

    # Per-user rate limiting based on subscription tier (Issue #1151, #1486)
    # Higher tiers get more conversions per minute.
    # Use endpoint-specific base config and let _get_user_config scale by tier.
    tier = user.subscription_tier if user else "free"
    from services.rate_limiter import RateLimitConfig, conversion_rate_limiter

    # Base config for /api/v1/conversions (will be scaled by tier in check_rate_limit)
    base_config = RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=300,
        burst_size=5,
    )

    # Use the shared conversion rate limiter
    rate_limiter = conversion_rate_limiter

    # Create a mock request with user context for rate limiting check
    from starlette.datastructures import Headers

    class MockRequest:
        def __init__(self, user_id: Optional[str], user_tier: str, client_host: str = "127.0.0.1"):
            self.state = type("State", (), {"user_id": user_id, "user_tier": user_tier})()
            self.client = type("Client", (), {"host": client_host})()
            self.headers = Headers()

    user_id = str(user.id) if user else None
    mock_request = MockRequest(user_id, tier)
    is_allowed, metadata = await rate_limiter.check_rate_limit(
        mock_request, override_config=base_config
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Conversion rate limit exceeded for {tier} tier. Maximum {metadata['limit_minute']} conversions per minute.",
                "retry_after": metadata.get("retry_after", 60),
                "rate_limit": {
                    "limit": metadata["limit_minute"],
                    "remaining": metadata["remaining_minute"],
                    "reset_at": metadata["reset_at_minute"],
                },
            },
        )

    # Metering check for subscription tier limits (Issue #977)
    # Use API usage metering for API key auth, web usage metering for JWT
    is_api_key_auth = user and credentials and credentials.credentials.startswith("mpk_")
    if user:
        metering_service = MeteringService(db)
        if is_api_key_auth:
            metering_result = await metering_service.check_and_increment_api_usage(user)
        else:
            metering_result = await metering_service.check_and_increment_web_usage(user)

        if not metering_result.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "usage_limit_exceeded",
                    "message": metering_result.error_message,
                    "upgrade_cta": metering_result.upgrade_cta,
                    "usage": {
                        "tier": metering_result.usage_info.tier,
                        "web_conversions": metering_result.usage_info.web_conversions,
                        "monthly_limit": metering_result.usage_info.monthly_limit,
                        "remaining": metering_result.usage_info.remaining,
                    },
                },
            )

        if metering_result.usage_info.should_upgrade:
            logger.info(
                f"User {user.id} approaching conversion limit: "
                f"{metering_result.usage_info.web_conversions}/{metering_result.usage_info.monthly_limit}"
            )

    # Validate file was provided
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )

    # Sanitize filename
    safe_filename = sanitize_filename(file.filename)

    # Validate file type
    is_valid, error_msg = validate_file_type(safe_filename)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    # Validate file size
    is_valid, error_msg = await validate_file_size(file)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=error_msg,
        )

    # Parse options
    try:
        import json

        options_data = json.loads(options)
        conversion_options = ConversionOptions(**options_data)
    except Exception as e:
        logger.warning(f"Invalid options provided: {e}, using defaults")
        conversion_options = ConversionOptions()

    # Generate file_id and save file
    file_id = str(uuid.uuid4())
    file_ext = os.path.splitext(safe_filename)[1]
    saved_filename = f"{file_id}{file_ext}"
    uploads_root = Path(TEMP_UPLOADS_DIR).resolve()
    uploads_root.mkdir(parents=True, exist_ok=True)
    try:
        file_path = safe_join(uploads_root, saved_filename)
    except PathSanitizationError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload filename",
        ) from exc

    # Save uploaded file
    try:
        with open(file_path, "wb") as buffer:
            for chunk in file.file:
                buffer.write(chunk)
        logger.info("File saved: %s", sanitize_for_log(file_path))

        # SECURITY: Scan the uploaded file for ZIP bombs, path traversal, etc.
        try:
            security_result = await scan_uploaded_file(file_path)
            logger.info(
                "Security scan completed for %s: safe=%s, threats=%d",
                sanitize_for_log(file_path),
                security_result.is_safe,
                len(security_result.threats),
            )
        except HTTPException:
            # Re-raise HTTP exceptions from security scan (file rejected)
            if file_path.exists():
                file_path.unlink()
            raise
        except Exception as e:
            # Log but don't fail on security scan errors
            logger.error("Security scan error (continuing): %s", sanitize_for_log(e))
    except Exception as e:
        logger.error("Failed to save file: %s", sanitize_for_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file",
        )
    finally:
        await file.close()

    # Create conversion job in database
    try:
        user_id = str(user.id) if user else None
        job = await crud.create_job(
            session=db,
            file_id=file_id,
            original_filename=safe_filename,
            target_version=conversion_options.target_version,
            options=conversion_options.model_dump(),
            user_id=user_id,
            commit=True,
        )

        conversion_id = str(job.id)
        logger.info(f"Conversion job created: {conversion_id}")

    except Exception as e:
        logger.error(f"Failed to create conversion job: {e}")
        # Clean up uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversion job",
        )

    # Enqueue conversion task to async task queue for background processing
    # This enables concurrent conversions and better resource management
    # Also start the conversion processing with AI Engine integration
    try:
        timeout_seconds = get_conversion_timeout(tier)
        await enqueue_task(
            name="conversion",
            payload={
                "conversion_id": conversion_id,
                "file_id": file_id,
                "file_path": file_path,
                "original_filename": safe_filename,
                "target_version": conversion_options.target_version,
                "options": conversion_options.model_dump(),
                "subscription_tier": tier,
            },
            priority=TaskPriority.NORMAL,
            timeout_seconds=timeout_seconds,
            subscription_tier=tier,
        )
        logger.info(
            f"Conversion task enqueued for job: {conversion_id} with {timeout_seconds}s timeout"
        )

        # Start AI Engine conversion in background task for real-time progress updates
        if background_tasks:
            conversion_service = get_conversion_service()
            user_email = user.email if user else None
            background_tasks.add_task(
                conversion_service.process_conversion,
                conversion_id=conversion_id,
                file_path=file_path,
                original_filename=safe_filename,
                target_version=conversion_options.target_version,
                options=conversion_options.model_dump(),
                user_email=user_email,
                notify_on_completion=conversion_options.notify_on_completion,
            )
            logger.info(f"AI Engine conversion started in background for job: {conversion_id}")

    except Exception as e:
        # Log but don't fail - conversion is still created, can be picked up by worker
        logger.warning(f"Failed to enqueue conversion task: {e}")

    # Cache job status
    await cache.set_job_status(
        conversion_id,
        {
            "conversion_id": conversion_id,
            "status": "queued",
            "progress": 0,
            "original_filename": safe_filename,
        },
    )
    await cache.set_progress(conversion_id, 0)

    return ConversionCreateResponse(
        conversion_id=conversion_id,
        status="queued",
        estimated_time_seconds=1800,  # 30 minutes default
        created_at=job.created_at,
    )


@router.get(
    "/api/v1/conversions/{conversion_id}",
    response_model=ConversionStatusResponse,
    tags=["conversions"],
)
async def get_conversion(
    conversion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the status of a specific conversion job.

    Returns detailed status information including:
    - Current status (queued, processing, completed, failed)
    - Progress percentage
    - Human-readable message
    - Download URL (if completed)
    - Error details (if failed)

    **Response:**
    ```json
    {
      "conversion_id": "uuid-v4",
      "status": "processing",
      "progress": 45,
      "message": "JavaAnalyzerAgent is analyzing mod structure...",
      "created_at": "2025-02-12T10:30:00Z",
      "updated_at": "2025-02-12T10:35:00Z",
      "result_url": null,
      "error": null,
      "original_filename": "example_mod.jar"
    }
    ```
    """
    # Issue #1417: always load job from DB so we can verify ownership
    # before honouring the cache (cached payload omits user_id).
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        # 404 (not 403) so we do not leak the existence of other users' jobs
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    cached = await cache.get_job_status(conversion_id)
    if cached:
        return ConversionStatusResponse(**cached)

    # Build response
    progress = job.progress.progress if job.progress else 0
    result_url = None

    if job.status == "completed":
        result_url = f"/api/v1/conversions/{conversion_id}/download"

    # Build descriptive message
    status_messages = {
        "queued": "Job is queued and waiting to start",
        "preprocessing": "Preprocessing uploaded file",
        "processing": f"AI conversion in progress ({progress}%)",
        "postprocessing": "Finalizing conversion results",
        "completed": "Conversion completed successfully",
        "failed": "Conversion failed",
        "cancelled": "Job was cancelled by the user",
    }

    message = status_messages.get(job.status, f"Job status: {job.status}")

    response = ConversionStatusResponse(
        conversion_id=conversion_id,
        status=job.status,
        progress=progress,
        message=message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result_url=result_url,
        error=None,
        original_filename=job.input_data.get("original_filename"),
        structured_error=None,
        asset_results=None,
        overall_percentage=None,
        email_verified=job.input_data.get("email_verified"),
    )

    # Update cache
    await cache.set_job_status(conversion_id, response.model_dump())

    return response


@router.get(
    "/api/v1/conversions",
    response_model=ConversionListResponse,
    tags=["conversions"],
)
async def list_conversions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List conversion jobs with pagination.

    Returns a paginated list of conversions for the authenticated user.
    If not authenticated, returns only jobs without user_id (public/anonymous conversions).

    **Query Parameters:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - status: Filter by status (optional)

    **Response:**
    ```json
    {
      "conversions": [...],
      "total": 42,
      "page": 1,
      "page_size": 20
    }
    ```
    """
    user_id = str(user.id) if user else None
    jobs, total = await crud.list_jobs(
        db, skip=(page - 1) * page_size, limit=page_size, user_id=user_id
    )

    if status:
        jobs = [job for job in jobs if job.status == status]

    conversions = []
    for job in jobs:
        progress = job.progress.progress if job.progress else 0
        result_url = None

        if job.status == "completed":
            result_url = f"/api/v1/conversions/{job.id}/download"

        input_data = job.input_data or {}

        conversions.append(
            ConversionStatusResponse(
                conversion_id=str(job.id),
                status=job.status,
                progress=progress,
                message=f"Job status: {job.status}",
                created_at=job.created_at,
                updated_at=job.updated_at,
                result_url=result_url,
                error=None,
                original_filename=input_data.get("original_filename"),
                structured_error=None,
                asset_results=None,
                overall_percentage=None,
                complexity_tier=input_data.get("complexity_tier"),
                features_converted=input_data.get("features_converted", []),
                features_skipped=input_data.get("features_skipped", []),
                warnings=input_data.get("warnings", []),
            )
        )

    return ConversionListResponse(
        conversions=conversions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/api/v1/conversions/{conversion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["conversions"],
)
async def delete_conversion(
    conversion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancel or delete a conversion job.

    - If the job is in progress, it will be cancelled
    - If the job is completed, the result file will be deleted
    - The database record will be marked as deleted

    **Response:** 204 No Content (success)
    """
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        # Issue #1417: 404 to avoid leaking job existence to non-owners
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    # Update status to cancelled
    await crud.update_job_status(db, conversion_id, "cancelled")
    await cache.set_job_status(
        conversion_id,
        {
            "conversion_id": conversion_id,
            "status": "cancelled",
            "progress": 0,
            "original_filename": job.input_data.get("original_filename"),
        },
    )

    # Notify WebSocket clients
    await ProgressHandler.broadcast_conversion_failed(
        conversion_id, "Conversion was cancelled by user"
    )

    return None


@router.get(
    "/api/v1/conversions/{conversion_id}/download",
    tags=["conversions"],
)
async def download_conversion(
    conversion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download the converted .mcaddon file.

    Returns the converted add-on file for download.
    The job must have status "completed".

    **Response:** Binary file download
    - Content-Type: application/zip
    - Content-Disposition: attachment; filename="{original_name}_converted.mcaddon"

    **Error Responses:**
    - 404: Conversion not found or result file missing
    - 400: Conversion not completed
    """
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        # Issue #1417: 404 to avoid leaking job existence to non-owners
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conversion is not completed. Current status: {job.status}",
        )

    # Issue #1429: derive on-disk filenames from the *server-side*
    # job.id (a uuid.UUID, not the raw URL string) and route every join
    # through safe_join so the resolved path is provably contained in
    # CONVERSION_OUTPUTS_DIR. Defends against path-injection
    # (CWE-22/-23/-36/-73/-99).
    job_uuid_str = str(job.id)
    outputs_root = Path(CONVERSION_OUTPUTS_DIR).resolve()
    outputs_root.mkdir(parents=True, exist_ok=True)
    try:
        mcaddon_path = safe_join(outputs_root, f"{job_uuid_str}_converted.mcaddon")
        zip_path = safe_join(outputs_root, f"{job_uuid_str}_converted.zip")
    except PathSanitizationError as exc:
        logger.error(
            "Refusing to serve conversion artifact for job %s: %s",
            sanitize_for_log(job_uuid_str),
            sanitize_for_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result file not found on server",
        ) from exc

    file_path: Optional[Path] = None
    if mcaddon_path.exists():
        file_path = mcaddon_path
    elif zip_path.exists():
        file_path = zip_path

    if file_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result file not found on server",
        )

    # Generate download filename - sanitize against path components from
    # the user-supplied original_filename stored in input_data.
    original_filename = job.input_data.get("original_filename", "mod")
    base_name = os.path.splitext(os.path.basename(original_filename))[0]
    base_name = sanitize_filename(base_name) or "mod"
    download_filename = f"{base_name}_converted.mcaddon"

    return FileResponse(
        path=str(file_path),  # safe: file_path is guaranteed inside outputs_root via safe_join
        media_type="application/zip",
        filename=download_filename,
    )


@router.get(
    "/api/v1/conversions/{conversion_id}/report",
    response_model=ConversionReportDownloadResponse,
    tags=["conversions"],
)
async def download_conversion_report(
    conversion_id: str,
    format: str = Query("json", description="Report format: json, html, csv"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download conversion report in specified format.

    The job must have status "completed" and have report data available.

    **Query Parameters:**
    - format: Report format - "json", "html", or "csv" (default: json)

    **Response:**
    ```json
    {
      "download_url": "/api/v1/conversions/{id}/report/download?format=json",
      "format": "json"
    }
    ```

    **Error Responses:**
    - 404: Conversion not found or no report available
    - 400: Invalid format specified
    """
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        # Issue #1417: 404 to avoid leaking job existence to non-owners
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conversion is not completed. Current status: {job.status}",
        )

    if format not in ("json", "html", "csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid format: {format}. Allowed: json, html, csv",
        )

    download_url = f"/api/v1/conversions/{conversion_id}/report/download?format={format}"

    return ConversionReportDownloadResponse(
        download_url=download_url,
        format=format,
    )


@router.get(
    "/api/v1/conversions/{conversion_id}/report/download",
    tags=["conversions"],
)
async def get_report_file(
    conversion_id: str,
    format: str = Query("json", description="Report format: json, html, csv"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the actual report file for download.

    Returns the report content in the specified format.

    **Query Parameters:**
    - format: Report format - "json", "html", or "csv" (default: json)

    **Response:** Binary file download with appropriate Content-Type
    """
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        # Issue #1417: 404 to avoid leaking job existence to non-owners
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conversion is not completed. Current status: {job.status}",
        )

    input_data = job.input_data or {}

    original_filename = input_data.get("original_filename", "conversion_report")
    base_name = os.path.splitext(original_filename)[0]

    results = job.results[0].output_data if job.results else {}
    metadata = {
        "job_id": str(job.id),
        "original_filename": original_filename,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "status": job.status,
        "complexity_tier": input_data.get("complexity_tier", "unknown"),
        "features_converted": input_data.get("features_converted", []),
        "features_skipped": input_data.get("features_skipped", []),
        "warnings": input_data.get("warnings", []),
    }

    report_data = {
        "metadata": metadata,
        "results": results,
        "input_data": {k: v for k, v in input_data.items() if k not in ("user_id", "file_id")},
    }

    exporter = ReportExporter()

    if format == "json":
        content = exporter.export_to_json(report_data)
        media_type = "application/json"
        download_filename = f"{base_name}_report.json"
    elif format == "html":
        content = exporter.export_to_html(report_data)
        media_type = "text/html"
        download_filename = f"{base_name}_report.html"
    else:
        content = exporter.export_to_csv(report_data)
        media_type = "text/csv"
        download_filename = f"{base_name}_report.csv"

    import tempfile
    import os as os_module

    temp_dir = tempfile.gettempdir()
    temp_path = os_module.path.join(temp_dir, download_filename)

    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)

    return FileResponse(
        path=temp_path,
        media_type=media_type,
        filename=download_filename,
    )


@router.get(
    "/api/v1/conversions/{conversion_id}/report/step-by-step",
    response_model=ConversionStepByStepReportResponse,
    tags=["conversions"],
)
async def get_conversion_step_by_step_report(
    conversion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed step-by-step conversion report with failure details (Issue #1548).

    Returns a comprehensive report showing:
    - Each step of the conversion process
    - What succeeded at each step with timestamps
    - What failed at each step with reasons and error codes
    - Summary statistics including success rate

    **Response:**
    ```json
    {
      "conversion_id": "uuid-v4",
      "status": "completed",
      "original_filename": "example_mod.jar",
      "target_version": "1.20.0",
      "created_at": "2025-02-12T10:30:00Z",
      "completed_at": "2025-02-12T10:35:00Z",
      "steps": [
        {
          "step_id": "step_1",
          "step_name": "File Upload & Validation",
          "status": "completed",
          "started_at": "2025-02-12T10:30:00Z",
          "completed_at": "2025-02-12T10:30:05Z",
          "duration_ms": 5000,
          "message": "File validated successfully",
          "details": "File size: 15MB, Type: .jar"
        },
        {
          "step_id": "step_2",
          "step_name": "Java Code Analysis",
          "status": "failed",
          "started_at": "2025-02-12T10:30:05Z",
          "completed_at": "2025-02-12T10:30:25Z",
          "duration_ms": 20000,
          "message": "Analysis failed",
          "error": "Unable to parse Java class structure",
          "error_code": "PARSE_ERROR",
          "details": "Missing required dependencies detected"
        }
      ],
      "summary": {
        "total_steps": 5,
        "completed_steps": 3,
        "failed_steps": 1,
        "total_duration_ms": 125000,
        "success_rate": 60.0,
        "features_total": 25,
        "features_converted": 15,
        "features_failed": 5,
        "features_partial": 5,
        "assumptions_used": 3
      },
      "errors": [
        {
          "error_code": "PARSE_ERROR",
          "error_type": "conversion_error",
          "message": "Unable to parse Java class structure",
          "is_retryable": false,
          "details": {"step": "step_2", "file": "com/example/Mod.java"}
        }
      ],
      "warnings": [
        "Custom biome detected - may require manual review",
        "Complex redstone logic may not convert fully"
      ]
    }
    ```

    **Error Responses:**
    - 404: Conversion not found
    - 403: Not authorized to view this conversion
    """
    job = await crud.get_job(db, conversion_id)
    if not _user_owns_job(job, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversion {conversion_id} not found",
        )

    input_data = job.input_data or {}
    results = job.results[0].output_data if job.results else {}

    steps_data = results.get("steps", input_data.get("steps", []))
    steps = []

    for i, step_data in enumerate(steps_data):
        step = ConversionStep(
            step_id=step_data.get("step_id", f"step_{i+1}"),
            step_name=step_data.get("step_name", f"Step {i+1}"),
            status=step_data.get("status", "pending"),
            started_at=step_data.get("started_at"),
            completed_at=step_data.get("completed_at"),
            duration_ms=step_data.get("duration_ms"),
            message=step_data.get("message"),
            details=step_data.get("details"),
            error=step_data.get("error"),
            error_code=step_data.get("error_code"),
            artifacts=step_data.get("artifacts"),
        )
        steps.append(step)

    if not steps:
        steps = _build_steps_from_job_status(job)

    summary_data = results.get("summary", input_data.get("summary", {}))
    summary = ConversionSummaryStats(
        total_steps=summary_data.get("total_steps", len(steps) if steps else 1),
        completed_steps=summary_data.get("completed_steps", 0),
        failed_steps=summary_data.get("failed_steps", 0),
        total_duration_ms=summary_data.get("total_duration_ms", 0.0),
        success_rate=summary_data.get("success_rate", 0.0),
        features_total=summary_data.get("features_total", results.get("total_features", 0)),
        features_converted=summary_data.get(
            "features_converted", results.get("converted_features", 0)
        ),
        features_failed=summary_data.get("features_failed", results.get("failed_features", 0)),
        features_partial=summary_data.get(
            "features_partial", results.get("partially_converted_features", 0)
        ),
        assumptions_used=summary_data.get("assumptions_used", results.get("assumptions_applied_count", 0)),
    )

    errors_data = input_data.get("structured_errors", results.get("errors", []))
    errors = []
    for err in errors_data:
        if isinstance(err, dict):
            errors.append(StructuredError(
                error_code=err.get("error_code", "UNKNOWN_ERROR"),
                error_type=err.get("error_type", "conversion_error"),
                message=err.get("message", "An error occurred"),
                is_retryable=err.get("is_retryable", False),
                details=err.get("details"),
            ))

    warnings_list = input_data.get("warnings", results.get("warnings", []))

    return ConversionStepByStepReportResponse(
        conversion_id=conversion_id,
        status=job.status,
        original_filename=input_data.get("original_filename", "unknown"),
        target_version=input_data.get("target_version", "1.20.0"),
        created_at=job.created_at,
        completed_at=job.completed_at if hasattr(job, "completed_at") else None,
        steps=steps,
        summary=summary,
        errors=errors,
        warnings=warnings_list,
    )


def _build_steps_from_job_status(job) -> List[ConversionStep]:
    """Build steps list from job status when detailed steps not available."""
    steps = []
    status_flow = [
        ("step_1", "File Upload & Validation", "queued"),
        ("step_2", "Java Code Analysis", "queued"),
        ("step_3", "Feature Extraction", "queued"),
        ("step_4", "Bedrock Code Conversion", "queued"),
        ("step_5", "Output Packaging", "queued"),
    ]

    job_status = job.status
    progress = job.progress.progress if job.progress else 0

    for step_id, step_name, default_status in status_flow:
        if job_status == "completed":
            status = "completed"
        elif job_status == "failed":
            status = "failed"
        elif job_status == "processing":
            status = "running" if progress > 0 else "pending"
        elif job_status == "queued":
            status = "pending"
        else:
            status = default_status

        steps.append(ConversionStep(
            step_id=step_id,
            step_name=step_name,
            status=status,
            message=_get_step_message(step_id, status, progress),
        ))

    return steps


def _get_step_message(step_id: str, status: str, progress: int) -> str:
    """Generate appropriate message for a step based on status."""
    if status == "completed":
        return "Step completed successfully"
    elif status == "failed":
        return "Step failed - see error details"
    elif status == "running":
        return f"Step in progress ({progress}%)"
    elif status == "pending":
        return "Waiting to start"
    else:
        return "Unknown status"


# Chunked/Resumable Upload Endpoints
@router.post(
    "/api/v1/uploads/init",
    response_model=ChunkUploadInitResponse,
    tags=["uploads"],
)
async def init_chunked_upload(
    filename: str = Form(..., description="Original filename"),
    total_size: int = Form(..., description="Total file size in bytes"),
    current_user: User = Depends(get_current_user),
):
    """
    Initialize a resumable/chunked upload session.

    For large files, use this endpoint to start a chunked upload session.
    Returns an upload_id to be used in subsequent chunk upload requests.

    **Benefits:**
    - Supports resumable uploads (resume from where left off)
    - Better for large files (100MB+)
    - Progress tracking per chunk

    **Request:** multipart/form-data
    - filename: Original filename
    - total_size: Total file size in bytes

    **Response:**
    ```json
    {
      "upload_id": "uuid-v4",
      "chunk_size": 5242880,
      "total_size": 104857600,
      "filename": "large_mod.jar",
      "message": "Upload session initialized"
    }
    ```
    """
    # Validate file size
    if total_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit",
        )

    # Validate file type
    safe_filename = sanitize_filename(filename)
    is_valid, error_msg = validate_file_type(safe_filename)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    # Generate upload ID
    upload_id = str(uuid.uuid4())

    # Store upload metadata in cache
    upload_metadata = {
        "upload_id": upload_id,
        "filename": safe_filename,
        "total_size": total_size,
        "chunk_size": CHUNK_SIZE,
        "chunks_received": 0,
        "status": "in_progress",
    }

    await cache.set_job_status(f"upload:{upload_id}", upload_metadata)

    # Create temporary directory for chunks. upload_id is a server-generated
    # uuid4 string; routing through _chunks_dir_for_upload keeps every chunk
    # path under TEMP_UPLOADS_DIR and silences CodeQL py/path-injection.
    chunks_dir = _chunks_dir_for_upload(upload_id)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    return ChunkUploadInitResponse(
        upload_id=upload_id,
        chunk_size=CHUNK_SIZE,
        total_size=total_size,
        filename=safe_filename,
        message="Upload session initialized. Use upload_id in subsequent chunk requests.",
    )


@router.post(
    "/api/v1/uploads/{upload_id}/chunk",
    response_model=ChunkUploadResponse,
    tags=["uploads"],
)
async def upload_chunk(
    upload_id: UUID,
    chunk_number: int = Form(..., description="Chunk number (1-indexed)"),
    total_chunks: int = Form(..., description="Total number of chunks"),
    chunk: UploadFile = File(..., description="Chunk data"),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a single chunk of a resumable upload.

    **Request:** multipart/form-data
    - chunk_number: Current chunk number (1-indexed)
    - total_chunks: Total number of chunks expected
    - chunk: Binary chunk data

    **Response:**
    ```json
    {
      "upload_id": "uuid-v4",
      "chunk_number": 1,
      "chunks_received": 1,
      "total_chunks": 20,
      "progress": 5.0
    }
    ```
    """
    upload_id_str = str(upload_id)
    # Get upload metadata
    upload_metadata = await cache.get_job_status(f"upload:{upload_id_str}")

    if not upload_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found. Initialize with /api/v1/uploads/init first.",
        )

    if upload_metadata.get("status") != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload session is {upload_metadata.get('status')}",
        )

    # Validate chunk size
    chunk_data = await chunk.read()
    if len(chunk_data) > CHUNK_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chunk size exceeds maximum of {CHUNK_SIZE} bytes",
        )

    # SECURITY: Validate chunk_number is within reasonable bounds
    if chunk_number < 1 or chunk_number > 10000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chunk number")

    # Issue #1429: build chunks_dir + chunk_path via safe_join. The helper
    # rejects any segment that isn't ``[A-Za-z0-9._-]+`` and verifies the
    # final resolved path is contained in TEMP_UPLOADS_DIR, neutralising
    # CWE-22/-23/-36/-73/-99 (CodeQL py/path-injection).
    chunks_dir = _chunks_dir_for_upload(upload_id_str)

    # Ensure chunks directory exists
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # SECURITY: Construct chunk filename safely - only allow numeric extension
    safe_chunk_name = f"chunk_{chunk_number:04d}"
    try:
        chunk_path = safe_join(chunks_dir, safe_chunk_name)
    except PathSanitizationError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chunk name"
        ) from exc

    with open(chunk_path, "wb") as f:
        f.write(chunk_data)

    # Update chunks received count
    chunks_received = upload_metadata.get("chunks_received", 0) + 1
    upload_metadata["chunks_received"] = chunks_received
    await cache.set_job_status(f"upload:{upload_id_str}", upload_metadata)

    # Calculate progress
    progress = (chunks_received / total_chunks) * 100

    return ChunkUploadResponse(
        upload_id=upload_id_str,
        chunk_number=chunk_number,
        chunks_received=chunks_received,
        total_chunks=total_chunks,
        progress=round(progress, 2),
    )


@router.get(
    "/api/v1/uploads/{upload_id}/progress",
    response_model=UploadProgressResponse,
    tags=["uploads"],
)
async def get_upload_progress(
    upload_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """
    Get the progress of a resumable upload.

    **Response:**
    ```json
    {
      "upload_id": "uuid-v4",
      "received_bytes": 5242880,
      "total_bytes": 104857600,
      "progress": 5.0,
      "status": "in_progress"
    }
    ```
    """
    upload_id_str = str(upload_id)
    upload_metadata = await cache.get_job_status(f"upload:{upload_id_str}")

    # Issue #1417: 404 (not 403) on missing OR foreign-owned session
    if not upload_metadata or upload_metadata.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found"
        )

    # Issue #1429: chunks_dir is built via safe_join; chunk files were
    # written by the server with names matching ``chunk_NNNN``, so each
    # listdir result is allow-list re-validated to keep the sink inside
    # CONVERSION_OUTPUTS_DIR.
    chunks_dir = _chunks_dir_for_upload(upload_id_str)
    received_bytes = 0

    if chunks_dir.exists():
        for chunk_file in os.listdir(chunks_dir):
            try:
                chunk_path = safe_join(chunks_dir, chunk_file)
            except PathSanitizationError:
                # Skip stray/oddly-named files we did not create.
                continue
            if chunk_path.is_file():
                received_bytes += chunk_path.stat().st_size

    total_bytes = upload_metadata.get("total_size", 0)
    progress = (received_bytes / total_bytes * 100) if total_bytes > 0 else 0

    return UploadProgressResponse(
        upload_id=upload_id_str,
        received_bytes=received_bytes,
        total_bytes=total_bytes,
        progress=round(progress, 2),
        status=upload_metadata.get("status", "unknown"),
    )


@router.post(
    "/api/v1/uploads/{upload_id}/complete",
    response_model=ConversionCreateResponse,
    tags=["uploads"],
)
async def complete_chunked_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Complete a resumable upload by combining all chunks.

    This endpoint combines all uploaded chunks into the final file
    and creates a conversion job.
    """
    upload_id_str = str(upload_id)
    # Get upload metadata
    upload_metadata = await cache.get_job_status(f"upload:{upload_id_str}")

    # Issue #1417: 404 (not 403) on missing OR foreign-owned session
    if not upload_metadata or upload_metadata.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found"
        )

    if upload_metadata.get("status") != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload session is {upload_metadata.get('status')}",
        )

    # Issue #1429: build chunks_dir + final file_path through safe_join.
    chunks_dir = _chunks_dir_for_upload(upload_id_str)
    safe_filename = upload_metadata["filename"]
    total_size = upload_metadata["total_size"]

    # Combine chunks
    file_id = str(uuid.uuid4())
    file_ext = os.path.splitext(safe_filename)[1]
    # Re-sanitize the extension defensively: ``filename`` originally came
    # from the user and ``sanitize_filename`` was applied at init, but the
    # extension is reconstructed here from cached metadata, so we strip
    # anything other than safe characters.
    file_ext_safe = "".join(c for c in file_ext if c.isalnum() or c == ".")
    saved_filename = f"{file_id}{file_ext_safe}"
    uploads_root = Path(TEMP_UPLOADS_DIR).resolve()
    uploads_root.mkdir(parents=True, exist_ok=True)
    try:
        file_path = safe_join(uploads_root, saved_filename)
    except PathSanitizationError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload filename",
        ) from exc

    try:
        with open(file_path, "wb") as outfile:
            # Read chunks in order
            chunk_number = 1
            while True:
                # safe_join validates the chunk segment against the
                # ``[A-Za-z0-9._-]+`` allow-list, so an attacker cannot
                # influence this path even if they could mutate metadata.
                try:
                    chunk_path = safe_join(chunks_dir, f"chunk_{chunk_number:04d}")
                except PathSanitizationError:  # pragma: no cover - defensive
                    break
                if not chunk_path.exists():
                    break
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
                chunk_number += 1

        # Verify file size
        actual_size = file_path.stat().st_size
        if actual_size != total_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size mismatch. Expected {total_size}, got {actual_size}",
            )

        # SECURITY: Scan the uploaded file for ZIP bombs, path traversal, etc.
        try:
            security_result = await scan_uploaded_file(file_path)
            logger.info(
                "Security scan completed for %s: safe=%s, threats=%d",
                sanitize_for_log(file_path),
                security_result.is_safe,
                len(security_result.threats),
            )
        except HTTPException:
            # Re-raise HTTP exceptions from security scan (file rejected)
            if file_path.exists():
                file_path.unlink()
            raise
        except Exception as e:
            # Log but don't fail on security scan errors
            logger.error("Security scan error (continuing): %s", sanitize_for_log(e))

        # Update upload status
        upload_metadata["status"] = "completed"
        await cache.set_job_status(f"upload:{upload_id_str}", upload_metadata)

        # Create conversion job (record owner so subsequent reads pass ownership checks)
        job = await crud.create_job(
            session=db,
            file_id=file_id,
            original_filename=safe_filename,
            target_version="1.20.0",
            options={},
            user_id=str(current_user.id),
            commit=True,
        )

        conversion_id = str(job.id)

        # Cache job status
        await cache.set_job_status(
            conversion_id,
            {
                "conversion_id": conversion_id,
                "status": "queued",
                "progress": 0,
                "original_filename": safe_filename,
            },
        )
        await cache.set_progress(conversion_id, 0)

        # Clean up chunks
        shutil.rmtree(chunks_dir, ignore_errors=True)

        return ConversionCreateResponse(
            conversion_id=conversion_id,
            status="queued",
            estimated_time_seconds=1800,
            created_at=job.created_at,
        )

    except Exception as e:
        logger.error("Failed to complete chunked upload: %s", sanitize_for_log(e))
        # Clean up on failure - file_path/chunks_dir are safe_join outputs
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:  # pragma: no cover - best-effort cleanup
            pass
        shutil.rmtree(chunks_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete upload",
        )


@router.delete(
    "/api/v1/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["uploads"],
)
async def cancel_upload(
    upload_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """
    Cancel a resumable upload session.

    Deletes all uploaded chunks and cleans up the upload session.
    """
    upload_id_str = str(upload_id)
    upload_metadata = await cache.get_job_status(f"upload:{upload_id_str}")

    # Issue #1417: 404 (not 403) on missing OR foreign-owned session
    if not upload_metadata or upload_metadata.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found"
        )

    # Update status to cancelled
    upload_metadata["status"] = "cancelled"
    await cache.set_job_status(f"upload:{upload_id_str}", upload_metadata)

    # Issue #1429: chunks_dir resolved via safe_join → guaranteed inside
    # TEMP_UPLOADS_DIR.
    chunks_dir = _chunks_dir_for_upload(upload_id_str)
    shutil.rmtree(chunks_dir, ignore_errors=True)

    return None
