"""
Feedback API endpoints for conversion job feedback and AI training data.
"""

import uuid
import os
import sys
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from db.base import get_db
from db import crud
from db.models import CorrectionSubmission
from sqlalchemy import select

# Configure logger for this module
logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    job_id: str
    feedback_type: str  # 'thumbs_up', 'thumbs_down', 'detailed'
    user_id: Optional[str] = None
    comment: Optional[str] = None
    # Enhanced feedback fields for RL training
    quality_rating: Optional[int] = None  # 1-5 scale
    specific_issues: Optional[List[str]] = None  # List of specific problems
    suggested_improvements: Optional[str] = None
    conversion_accuracy: Optional[int] = None  # 1-5 scale
    visual_quality: Optional[int] = None  # 1-5 scale
    performance_rating: Optional[int] = None  # 1-5 scale
    ease_of_use: Optional[int] = None  # 1-5 scale
    agent_specific_feedback: Optional[Dict[str, Any]] = None  # Agent-specific ratings

    model_config = ConfigDict(
        validate_assignment=True,
        json_schema_extra={
            # Handle UUID serialization
            "examples": [
                {
                    "job_id": "123e4567-e89b-12d3-a456-426614174000",
                    "feedback_type": "thumbs_up",
                    "user_id": "user123",
                    "comment": "Great conversion!",
                    "quality_rating": 5,
                    "specific_issues": [],
                    "visual_quality": 5,
                    "performance_rating": 5,
                    "ease_of_use": 5,
                    "agent_specific_feedback": {},
                }
            ]
        },
    )


class FeedbackResponse(BaseModel):
    id: str
    job_id: str
    feedback_type: str
    user_id: Optional[str] = None
    comment: Optional[str] = None
    quality_rating: Optional[int] = None
    specific_issues: Optional[List[str]] = None
    suggested_improvements: Optional[str] = None
    conversion_accuracy: Optional[int] = None
    visual_quality: Optional[int] = None
    performance_rating: Optional[int] = None
    ease_of_use: Optional[int] = None
    agent_specific_feedback: Optional[Dict[str, Any]] = None
    created_at: str


class TrainingDataResponse(BaseModel):
    """Enhanced training data response with quality metrics"""

    job_id: str
    input_file_path: str
    output_file_path: str
    feedback: Dict[str, Any]
    quality_metrics: Optional[Dict[str, Any]] = None
    conversion_metadata: Optional[Dict[str, Any]] = None
    agent_performance_data: Optional[Dict[str, Any]] = None


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit feedback for a conversion job."""
    logger.info(f"Receiving feedback for job {feedback.job_id}")

    # Validate job ID format
    try:
        job_uuid = uuid.UUID(feedback.job_id)
    except ValueError:
        logger.warning(f"Invalid job ID format: {feedback.job_id}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Validate feedback type
    valid_feedback_types = ["thumbs_up", "thumbs_down", "detailed"]
    if feedback.feedback_type not in valid_feedback_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback type. Must be one of: {', '.join(valid_feedback_types)}",
        )

    # Validate rating scales (1-5)
    rating_fields = [
        "quality_rating",
        "conversion_accuracy",
        "visual_quality",
        "performance_rating",
        "ease_of_use",
    ]
    for field in rating_fields:
        value = getattr(feedback, field, None)
        if value is not None and (value < 1 or value > 5):
            raise HTTPException(status_code=400, detail=f"{field} must be between 1 and 5")

    # Check if job exists
    try:
        job = await crud.get_job(db, feedback.job_id)
        if not job:
            logger.warning(f"Job not found: {feedback.job_id}")
            raise HTTPException(
                status_code=404, detail=f"Conversion job with ID '{feedback.job_id}' not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        # Check if it's a "not found" exception from crud
        if "not found" in str(e).lower():
            logger.warning(f"Job not found via exception: {feedback.job_id}")
            raise HTTPException(
                status_code=404, detail=f"Conversion job with ID '{feedback.job_id}' not found"
            )
        logger.error(f"Database error checking job {feedback.job_id}: {e}")
        raise HTTPException(status_code=500, detail="Error validating job ID")

    # Create enhanced feedback with RL training data
    db_feedback = await crud.create_enhanced_feedback(
        db,
        job_id=job_uuid,
        feedback_type=feedback.feedback_type,
        user_id=feedback.user_id,
        comment=feedback.comment,
        quality_rating=feedback.quality_rating,
        specific_issues=feedback.specific_issues,
        suggested_improvements=feedback.suggested_improvements,
        conversion_accuracy=feedback.conversion_accuracy,
        visual_quality=feedback.visual_quality,
        performance_rating=feedback.performance_rating,
        ease_of_use=feedback.ease_of_use,
        agent_specific_feedback=feedback.agent_specific_feedback,
    )

    return FeedbackResponse(
        id=str(db_feedback.id),
        job_id=str(db_feedback.job_id),
        feedback_type=db_feedback.feedback_type,
        user_id=db_feedback.user_id,
        comment=db_feedback.comment,
        quality_rating=db_feedback.quality_rating,
        specific_issues=db_feedback.specific_issues,
        suggested_improvements=db_feedback.suggested_improvements,
        conversion_accuracy=db_feedback.conversion_accuracy,
        visual_quality=db_feedback.visual_quality,
        performance_rating=db_feedback.performance_rating,
        ease_of_use=db_feedback.ease_of_use,
        agent_specific_feedback=db_feedback.agent_specific_feedback,
        created_at=db_feedback.created_at.isoformat(),
    )


@router.get("/ai/training_data")
async def get_training_data(
    skip: int = 0,
    limit: int = 100,
    include_quality_metrics: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get enhanced feedback data for RL training."""
    logger.info(
        f"Fetching training data: skip={skip}, limit={limit}, include_quality_metrics={include_quality_metrics}"
    )

    # Validate parameters
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be non-negative")
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

    try:
        feedback_list = await crud.list_all_feedback(
            db, skip=skip, limit=limit, is_anonymized=True
        )
    except Exception as e:
        logger.error(f"Database error fetching feedback: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving training data")

    training_data = []
    for feedback in feedback_list:
        # Get job details for file paths
        job = await crud.get_job(db, str(feedback.job_id))

        feedback_dict = {
            "id": str(feedback.id),
            "job_id": str(feedback.job_id),
            "input_file_path": job.input_data.get("file_path", "") if job else "",
            "output_file_path": f"conversion_outputs/{feedback.job_id}_converted.mcaddon"
            if job
            else "",
            "feedback": {
                "feedback_type": feedback.feedback_type,
                "user_id": feedback.user_id,
                "comment": feedback.comment,
                "quality_rating": getattr(feedback, "quality_rating", None),
                "specific_issues": getattr(feedback, "specific_issues", None),
                "suggested_improvements": getattr(feedback, "suggested_improvements", None),
                "conversion_accuracy": getattr(feedback, "conversion_accuracy", None),
                "visual_quality": getattr(feedback, "visual_quality", None),
                "performance_rating": getattr(feedback, "performance_rating", None),
                "ease_of_use": getattr(feedback, "ease_of_use", None),
                "agent_specific_feedback": getattr(feedback, "agent_specific_feedback", None),
                "created_at": feedback.created_at.isoformat(),
            },
        }

        # Add conversion metadata if available
        if job:
            feedback_dict["conversion_metadata"] = {
                "job_id": str(job.id),
                "status": job.status,
                "processing_time_seconds": 30.0,  # Could be calculated from timestamps
                "target_version": job.input_data.get("target_version", "1.20.0"),
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
            }

        training_data.append(feedback_dict)

    return {"data": training_data, "total": len(training_data), "skip": skip, "limit": limit}


@router.post("/ai/training/trigger")
async def trigger_rl_training():
    """Manually trigger RL training cycle."""
    try:
        logger.info("Starting manual RL training trigger")

        # Dynamic import with better error handling
        ai_engine_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "ai-engine", "src"
        )
        if ai_engine_path not in sys.path:
            sys.path.append(ai_engine_path)

        try:
            from training_manager import fetch_training_data_from_backend, train_model_with_feedback
        except ImportError as ie:
            logger.error(f"Failed to import RL training components: {ie}")
            raise HTTPException(status_code=503, detail="RL training system is not available")

        # Fetch training data
        backend_url = os.getenv("PORTKIT_BACKEND_URL", "http://localhost:8000")
        logger.info(f"Fetching training data from {backend_url}")

        training_data = await fetch_training_data_from_backend(backend_url, skip=0, limit=50)

        if training_data:
            logger.info(f"Found {len(training_data)} training items, starting RL training")
            # Run RL training
            result = await train_model_with_feedback(training_data)
            logger.info("RL training completed successfully")

            return {
                "status": "success",
                "message": "RL training completed successfully",
                "training_result": result,
                "training_data_count": len(training_data),
            }
        else:
            logger.warning("No training data available for RL training")
            return {"status": "warning", "message": "No training data available for RL training"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RL training failed with error: {e}", exc_info=True)
        logger.error(f"RL training failed: {str(e)}", exc_info=True)

        raise HTTPException(status_code=500, detail="RL training failed: Please try again.")


@router.get("/ai/performance/agents")
async def get_agent_performance():
    """Get performance metrics for all AI agents."""
    try:
        logger.info("Fetching agent performance metrics")

        # Dynamic import with better error handling
        ai_engine_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "ai-engine", "src"
        )
        if ai_engine_path not in sys.path:
            sys.path.append(ai_engine_path)

        try:
            from rl.agent_optimizer import create_agent_optimizer
        except ImportError as ie:
            logger.error(f"Failed to import RL optimizer components: {ie}")
            raise HTTPException(
                status_code=503, detail="Agent performance monitoring is not available"
            )

        optimizer = create_agent_optimizer()
        system_metrics = optimizer.get_system_wide_metrics()

        logger.info(f"Retrieved metrics for {system_metrics.get('total_agents', 0)} agents")

        return {"status": "success", "metrics": system_metrics}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve agent performance")


@router.get("/ai/performance/agents/{agent_type}")
async def get_specific_agent_performance(agent_type: str):
    """Get detailed performance metrics for a specific agent type."""
    # Dynamic import with better error handling
    # Do this BEFORE validating agent_type so import errors are caught first
    ai_engine_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ai-engine", "src")
    if ai_engine_path not in sys.path:
        sys.path.append(ai_engine_path)

    try:
        from rl.agent_optimizer import create_agent_optimizer
    except ImportError as ie:
        logger.error(f"Failed to import RL optimizer components: {ie}")
        raise HTTPException(status_code=503, detail="Agent performance monitoring is not available")

    try:
        logger.info(f"Fetching performance metrics for agent: {agent_type}")

        # Validate agent_type
        valid_agent_types = [
            "java_analyzer",
            "asset_converter",
            "behavior_translator",
            "conversion_planner",
            "qa_validator",
        ]
        if agent_type not in valid_agent_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent type. Must be one of: {', '.join(valid_agent_types)}",
            )

        optimizer = create_agent_optimizer()

        # Check if we have performance history for this agent
        if (
            agent_type in optimizer.performance_history
            and optimizer.performance_history[agent_type]
        ):
            latest_metrics = optimizer.performance_history[agent_type][-1]
            logger.info(f"Found performance data for {agent_type}")

            # Convert to dict safely
            metrics_dict = latest_metrics.__dict__ if hasattr(latest_metrics, "__dict__") else {}

            return {"status": "success", "agent_type": agent_type, "metrics": metrics_dict}
        else:
            logger.warning(f"No performance data available for agent type: {agent_type}")
            return {
                "status": "warning",
                "message": f"No performance data available for agent type: {agent_type}",
                "agent_type": agent_type,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get performance for agent {agent_type}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve performance for agent",
        )


@router.post("/ai/performance/compare")
async def compare_agent_performance(agent_types: List[str]):
    """Compare performance between multiple agent types."""
    try:
        logger.info(f"Comparing performance for agents: {agent_types}")

        # Validate input
        if not agent_types or len(agent_types) < 2:
            raise HTTPException(
                status_code=400, detail="At least 2 agent types are required for comparison"
            )

        valid_agent_types = [
            "java_analyzer",
            "asset_converter",
            "behavior_translator",
            "conversion_planner",
            "qa_validator",
        ]
        invalid_agents = [agent for agent in agent_types if agent not in valid_agent_types]
        if invalid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent types: {invalid_agents}. Must be one of: {', '.join(valid_agent_types)}",
            )

        # Dynamic import with better error handling
        ai_engine_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "ai-engine", "src"
        )
        if ai_engine_path not in sys.path:
            sys.path.append(ai_engine_path)

        try:
            from rl.agent_optimizer import create_agent_optimizer
        except ImportError as ie:
            logger.error(f"Failed to import RL optimizer components: {ie}")
            raise HTTPException(
                status_code=503, detail="Agent performance comparison is not available"
            )

        optimizer = create_agent_optimizer()
        comparison_report = optimizer.compare_agents(agent_types)

        logger.info(f"Generated comparison report for {len(agent_types)} agents")

        # Convert to dict safely
        report_dict = comparison_report.__dict__ if hasattr(comparison_report, "__dict__") else {}

        return {"status": "success", "comparison_report": report_dict}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compare agents {agent_types}: {e}", exc_info=True)
        logger.error(f"Failed to compare agents: {str(e)}", exc_info=True)

        raise HTTPException(status_code=500, detail="Failed to compare agents: Please try again.")


# Correction Submission Models and Endpoints


class CorrectionSubmissionRequest(BaseModel):
    job_id: str
    original_output: str
    corrected_output: str
    correction_rationale: Optional[str] = None
    original_chunk_id: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(
        validate_assignment=True,
        json_schema_extra={
            "examples": [
                {
                    "job_id": "123e4567-e89b-12d3-a456-426614174000",
                    "original_output": "player.getWorld().spawnEntity(...)",
                    "corrected_output": "player.getDimension().spawnEntity(...)",
                    "correction_rationale": "Bedrock uses getDimension() instead of getWorld()",
                    "user_id": "user123",
                }
            ]
        },
    )


class CorrectionSubmissionResponse(BaseModel):
    id: str
    job_id: str
    original_output: str
    corrected_output: str
    correction_rationale: Optional[str] = None
    original_chunk_id: Optional[str] = None
    status: str
    submitted_at: str

    model_config = ConfigDict(from_attributes=True)


class CorrectionReviewRequest(BaseModel):
    status: str
    review_notes: Optional[str] = None

    model_config = ConfigDict(
        validate_assignment=True,
        json_schema_extra={
            "examples": [{"status": "approved", "review_notes": "Valid correction for Bedrock API"}]
        },
    )


class CorrectionListResponse(BaseModel):
    data: List[CorrectionSubmissionResponse]
    total: int
    skip: int
    limit: int

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/feedback/corrections",
    response_model=CorrectionSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_correction(
    correction: CorrectionSubmissionRequest, db: AsyncSession = Depends(get_db)
):
    """Submit a correction for a conversion output."""
    from datetime import datetime, timezone

    logger.info(f"Receiving correction for job {correction.job_id}")

    try:
        job_uuid = uuid.UUID(correction.job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    try:
        job = await crud.get_job(db, correction.job_id)
        if not job:
            raise HTTPException(
                status_code=404, detail=f"Conversion job with ID '{correction.job_id}' not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error checking job {correction.job_id}: {e}")
        raise HTTPException(status_code=500, detail="Error validating job ID")

    original_chunk_uuid = None
    if correction.original_chunk_id:
        try:
            original_chunk_uuid = uuid.UUID(correction.original_chunk_id)
        except ValueError:
            pass

    db_correction = CorrectionSubmission(
        job_id=job_uuid,
        user_id=correction.user_id,
        original_output=correction.original_output,
        corrected_output=correction.corrected_output,
        correction_rationale=correction.correction_rationale,
        original_chunk_id=original_chunk_uuid,
        status="pending",
    )
    db.add(db_correction)
    await db.commit()
    await db.refresh(db_correction)

    return CorrectionSubmissionResponse(
        id=str(db_correction.id),
        job_id=str(db_correction.job_id),
        original_output=db_correction.original_output,
        corrected_output=db_correction.corrected_output,
        correction_rationale=db_correction.correction_rationale,
        original_chunk_id=str(db_correction.original_chunk_id)
        if db_correction.original_chunk_id
        else None,
        status=db_correction.status,
        submitted_at=db_correction.submitted_at.isoformat(),
    )


@router.get("/feedback/corrections", response_model=CorrectionListResponse)
async def list_corrections(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List corrections with optional filters."""
    from sqlalchemy import func

    logger.info(f"Fetching corrections: job_id={job_id}, status={status}, user_id={user_id}")

    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")

    query = select(CorrectionSubmission)
    count_query = select(func.count()).select_from(CorrectionSubmission)

    if job_id:
        try:
            job_uuid = uuid.UUID(job_id)
            query = query.where(CorrectionSubmission.job_id == job_uuid)
            count_query = count_query.where(CorrectionSubmission.job_id == job_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid job_id format")

    if status:
        if status not in ["pending", "approved", "rejected", "applied"]:
            raise HTTPException(status_code=400, detail="Invalid status value")
        query = query.where(CorrectionSubmission.status == status)
        count_query = count_query.where(CorrectionSubmission.status == status)

    if user_id:
        query = query.where(CorrectionSubmission.user_id == user_id)
        count_query = count_query.where(CorrectionSubmission.user_id == user_id)

    query = query.order_by(CorrectionSubmission.submitted_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    corrections = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    data = [
        CorrectionSubmissionResponse(
            id=str(c.id),
            job_id=str(c.job_id),
            original_output=c.original_output,
            corrected_output=c.corrected_output,
            correction_rationale=c.correction_rationale,
            original_chunk_id=str(c.original_chunk_id) if c.original_chunk_id else None,
            status=c.status,
            submitted_at=c.submitted_at.isoformat(),
        )
        for c in corrections
    ]

    return CorrectionListResponse(data=data, total=total, skip=offset, limit=limit)


@router.get("/feedback/corrections/{correction_id}", response_model=CorrectionSubmissionResponse)
async def get_correction(correction_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single correction by ID."""
    from db.models import CorrectionSubmission

    try:
        correction_uuid = uuid.UUID(correction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid correction ID format")

    query = select(CorrectionSubmission).where(CorrectionSubmission.id == correction_uuid)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()

    if not correction:
        raise HTTPException(status_code=404, detail="Correction not found")

    return CorrectionSubmissionResponse(
        id=str(correction.id),
        job_id=str(correction.job_id),
        original_output=correction.original_output,
        corrected_output=correction.corrected_output,
        correction_rationale=correction.correction_rationale,
        original_chunk_id=str(correction.original_chunk_id)
        if correction.original_chunk_id
        else None,
        status=correction.status,
        submitted_at=correction.submitted_at.isoformat(),
    )


@router.put(
    "/feedback/corrections/{correction_id}/review", response_model=CorrectionSubmissionResponse
)
async def review_correction(
    correction_id: str, review: CorrectionReviewRequest, db: AsyncSession = Depends(get_db)
):
    """Review a correction (approve or reject)."""
    from datetime import datetime, timezone

    if review.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    try:
        correction_uuid = uuid.UUID(correction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid correction ID format")

    query = select(CorrectionSubmission).where(CorrectionSubmission.id == correction_uuid)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()

    if not correction:
        raise HTTPException(status_code=404, detail="Correction not found")

    correction.status = review.status
    correction.review_notes = review.review_notes
    correction.reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(correction)

    logger.info(f"Correction {correction_id} reviewed: {review.status}")

    return CorrectionSubmissionResponse(
        id=str(correction.id),
        job_id=str(correction.job_id),
        original_output=correction.original_output,
        corrected_output=correction.corrected_output,
        correction_rationale=correction.correction_rationale,
        original_chunk_id=str(correction.original_chunk_id)
        if correction.original_chunk_id
        else None,
        status=correction.status,
        submitted_at=correction.submitted_at.isoformat(),
    )


@router.post("/feedback/corrections/{correction_id}/apply")
async def apply_correction(correction_id: str, db: AsyncSession = Depends(get_db)):
    """Manually apply a correction to the knowledge base."""
    from datetime import datetime, timezone

    try:
        correction_uuid = uuid.UUID(correction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid correction ID format")

    query = select(CorrectionSubmission).where(CorrectionSubmission.id == correction_uuid)
    result = await db.execute(query)
    correction = result.scalar_one_or_none()

    if not correction:
        raise HTTPException(status_code=404, detail="Correction not found")

    if correction.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved corrections can be applied")

    correction.status = "applied"
    correction.applied_at = datetime.now(timezone.utc)
    correction.embedding_updated = True

    await db.commit()
    await db.refresh(correction)

    logger.info(f"Correction {correction_id} applied to knowledge base")

    return {
        "status": "success",
        "message": "Correction applied to knowledge base",
        "correction_id": str(correction.id),
        "applied_at": correction.applied_at.isoformat(),
    }


class IssueReportRequest(BaseModel):
    job_id: str
    mod_name: str
    version: str
    conversion_score: float
    failing_categories: List[str] = []
    description: str
    severity: str = "medium"
    contact_email: Optional[str] = None

    model_config = ConfigDict(
        validate_assignment=True,
        json_schema_extra={
            "examples": [
                {
                    "job_id": "123e4567-e89b-12d3-a456-426614174000",
                    "mod_name": "My Awesome Mod",
                    "version": "3.2.1",
                    "conversion_score": 72.5,
                    "failing_categories": ["Custom Rendering", "Network Packets"],
                    "description": "Entities are not spawning correctly in Bedrock edition.",
                    "severity": "high",
                    "contact_email": "user@example.com",
                }
            ]
        },
    )


class IssueReportResponse(BaseModel):
    message: str
    report_id: str
    severity: str
    expected_response_time: str


@router.post(
    "/feedback/issues",
    response_model=IssueReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_issue_report(report: IssueReportRequest, db: AsyncSession = Depends(get_db)):
    """Submit an issue report for a conversion job (beta feedback)."""
    from datetime import datetime, timezone
    from db.models import IssueReport

    logger.info(f"Receiving issue report for job {report.job_id}")

    try:
        job_uuid = uuid.UUID(report.job_id)
    except ValueError:
        logger.warning(f"Invalid job ID format: {report.job_id}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    valid_severities = ["low", "medium", "high", "critical"]
    if report.severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity. Must be one of: {', '.join(valid_severities)}",
        )

    try:
        job = await crud.get_job(db, report.job_id)
        if not job:
            logger.warning(f"Job not found: {report.job_id}")
            raise HTTPException(
                status_code=404, detail=f"Conversion job with ID '{report.job_id}' not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(f"Job not found via exception: {report.job_id}")
            raise HTTPException(
                status_code=404, detail=f"Conversion job with ID '{report.job_id}' not found"
            )
        logger.error(f"Database error checking job {report.job_id}: {e}")
        raise HTTPException(status_code=500, detail="Error validating job ID")

    failing_categories_str = (
        ", ".join(report.failing_categories) if report.failing_categories else None
    )

    db_report = IssueReport(
        job_id=job_uuid,
        mod_name=report.mod_name,
        version=report.version,
        conversion_score=report.conversion_score,
        description=report.description,
        severity=report.severity,
        failing_categories=failing_categories_str,
        contact_email=report.contact_email,
        status="pending",
    )
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    response_times = {
        "critical": "< 2 hours",
        "high": "< 24 hours",
        "medium": "< 3 days",
        "low": "< 1 week",
    }
    expected_response = response_times.get(report.severity, "< 1 week")

    logger.info(f"Issue report created: {db_report.id} for job {report.job_id}")

    return IssueReportResponse(
        message="Thank you for your report! Our team will investigate this issue.",
        report_id=str(db_report.id),
        severity=report.severity,
        expected_response_time=expected_response,
    )
