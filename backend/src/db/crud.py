from typing import Optional, List
from uuid import UUID as PyUUID  # For type hinting UUID objects
import uuid
import os
import re
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from db import models
from db.models import DocumentEmbedding
from datetime import datetime, timezone

BASE_ASSET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon_assets")

_ANONYMIZATION_SALT = os.environ.get("FEEDBACK_ANONYMIZATION_SALT", "portkit-feedback-salt")


def _anonymize_feedback_pii(
    user_id: Optional[str], comment: Optional[str]
) -> tuple[Optional[str], Optional[str], bool]:
    """
    Anonymize personal data in feedback before storage for GDPR compliance.

    Args:
        user_id: Self-reported user identifier (may be None for anonymous feedback).
        comment: Free-text comment (may contain personal data).

    Returns:
        Tuple of (anonymized_user_id, anonymized_comment, is_anonymized).
        - user_id is hashed with SHA256 + salt to allow grouping without identification
        - comment has personal data patterns (email, phone, names) redacted
    """
    anonymized_user_id = None
    anonymized_comment = None

    if user_id:
        anonymized_user_id = hashlib.sha256(
            f"{_ANONYMIZATION_SALT}:{user_id}".encode()
        ).hexdigest()[:16]

    if comment:
        anonymized_comment = comment
        email_pattern = r"[\w.+-]+@[\w-]+\.[\w.-]+"
        anonymized_comment = re.sub(email_pattern, "[EMAIL_REDACTED]", anonymized_comment)
        phone_pattern = r"\+?[\d\s\-\(\)]{10,}"
        anonymized_comment = re.sub(phone_pattern, "[PHONE_REDACTED]", anonymized_comment)

    is_anonymized = anonymized_user_id is not None or anonymized_comment is not None
    return anonymized_user_id, anonymized_comment, is_anonymized


async def create_job(
    session: AsyncSession,
    *,
    file_id: str,
    original_filename: str,
    target_version: str,
    options: Optional[dict] = None,
    user_id: Optional[str] = None,
    commit: bool = True,
) -> models.ConversionJob:
    input_data = {
        "file_id": file_id,
        "original_filename": original_filename,
        "target_version": target_version,
        "options": options or {},
    }
    if user_id:
        input_data["user_id"] = user_id
    job = models.ConversionJob(
        status="queued",
        input_data=input_data,
    )
    # By using the relationship, SQLAlchemy will handle creating both
    # records and linking them in a single transaction.
    job.progress = models.JobProgress(progress=0)
    session.add(job)
    if commit:
        try:
            await session.commit()
            await session.refresh(job)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()  # Flush to get the ID without committing
    return job


def _to_uuid(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))


async def get_job(session: AsyncSession, job_id: str) -> Optional[models.ConversionJob]:
    try:
        job_uuid = _to_uuid(job_id)
    except (ValueError, AttributeError):
        return None
    stmt = (
        select(models.ConversionJob)
        .where(models.ConversionJob.id == job_uuid)
        .options(
            selectinload(models.ConversionJob.results),
            selectinload(models.ConversionJob.progress),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_job_status(
    session: AsyncSession, job_id: str, status: str, commit: bool = True
) -> Optional[models.ConversionJob]:
    try:
        job_uuid = _to_uuid(job_id)
    except (ValueError, AttributeError):
        return None

    stmt = (
        update(models.ConversionJob)
        .where(models.ConversionJob.id == job_uuid)
        .values(status=status)
    )
    await session.execute(stmt)
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Refresh the job object
    stmt = select(models.ConversionJob).where(models.ConversionJob.id == job_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_job_progress(
    session: AsyncSession, job_id: str, progress: int, commit: bool = True
) -> Optional[models.JobProgress]:
    try:
        job_uuid = _to_uuid(job_id)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid job_id format: {job_id}")

    # Use PostgreSQL's ON CONFLICT DO UPDATE for an atomic upsert operation

    stmt = (
        pg_insert(models.JobProgress)
        .values(job_id=job_uuid, progress=progress)
        .on_conflict_do_update(
            index_elements=["job_id"],
            set_={"progress": progress, "last_update": func.now()},
        )
        .returning(models.JobProgress)
    )

    result = await session.execute(stmt)
    prog = result.scalar_one()
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return prog


async def get_job_progress(session: AsyncSession, job_id: str) -> Optional[models.JobProgress]:
    try:
        job_uuid = _to_uuid(job_id)
    except (ValueError, AttributeError):
        return None

    stmt = select(models.JobProgress).where(models.JobProgress.job_id == job_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_result(
    session: AsyncSession,
    *,
    job_id: str,
    output_data: dict,
    commit: bool = True,
) -> models.ConversionResult:
    try:
        job_uuid = _to_uuid(job_id)
    except (ValueError, AttributeError):
        raise ValueError("Invalid job_id format")

    result = models.ConversionResult(
        job_id=job_uuid,
        output_data=output_data,
    )
    session.add(result)
    if commit:
        try:
            await session.commit()
            await session.refresh(result)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return result


# Feedback CRUD operations (enhanced for RL training)


async def create_enhanced_feedback(
    session: AsyncSession,
    *,
    job_id: PyUUID,
    feedback_type: str,
    user_id: Optional[str] = None,
    comment: Optional[str] = None,
    quality_rating: Optional[int] = None,
    specific_issues: Optional[List[str]] = None,
    suggested_improvements: Optional[str] = None,
    conversion_accuracy: Optional[int] = None,
    visual_quality: Optional[int] = None,
    performance_rating: Optional[int] = None,
    ease_of_use: Optional[int] = None,
    agent_specific_feedback: Optional[dict] = None,
    commit: bool = True,
) -> models.ConversionFeedback:
    anon_user_id, anon_comment, is_anonymized = _anonymize_feedback_pii(user_id, comment)
    feedback = models.ConversionFeedback(
        job_id=job_id,
        feedback_type=feedback_type,
        user_id=anon_user_id,
        comment=anon_comment,
        is_anonymized=is_anonymized,
    )
    session.add(feedback)
    if commit:
        try:
            await session.commit()
            await session.refresh(feedback)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return feedback


async def get_feedback(
    session: AsyncSession, feedback_id: PyUUID
) -> Optional[models.ConversionFeedback]:
    stmt = select(models.ConversionFeedback).where(models.ConversionFeedback.id == feedback_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_feedback_by_job_id(
    session: AsyncSession, job_id: PyUUID
) -> List[models.ConversionFeedback]:
    stmt = select(models.ConversionFeedback).where(models.ConversionFeedback.job_id == job_id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def list_all_feedback(
    session: AsyncSession, skip: int = 0, limit: int = 100, is_anonymized: Optional[bool] = None
) -> List[models.ConversionFeedback]:
    stmt = select(models.ConversionFeedback)
    if is_anonymized is not None:
        stmt = stmt.where(models.ConversionFeedback.is_anonymized == is_anonymized)
    stmt = stmt.offset(skip).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


# Document Embedding CRUD operations


async def create_document_embedding(
    db: AsyncSession,
    *,
    embedding: list[float],
    document_source: str,
    content_hash: str,
    commit: bool = True,
) -> DocumentEmbedding:
    db_embedding = DocumentEmbedding(
        embedding=embedding,
        document_source=document_source,
        content_hash=content_hash,
    )
    db.add(db_embedding)
    if commit:
        try:
            await db.commit()
            await db.refresh(db_embedding)
        except Exception:
            await db.rollback()
            raise
    else:
        await db.flush()
    return db_embedding


async def get_document_embedding_by_id(
    db: AsyncSession, embedding_id: PyUUID
) -> Optional[DocumentEmbedding]:
    stmt = select(DocumentEmbedding).where(DocumentEmbedding.id == embedding_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_document_embedding_by_hash(
    db: AsyncSession, content_hash: str
) -> Optional[DocumentEmbedding]:
    stmt = select(DocumentEmbedding).where(DocumentEmbedding.content_hash == content_hash)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_document_embedding(
    db: AsyncSession,
    embedding_id: PyUUID,
    *,
    embedding: Optional[list[float]] = None,
    document_source: Optional[str] = None,
) -> Optional[DocumentEmbedding]:
    db_embedding = await get_document_embedding_by_id(db, embedding_id)
    if db_embedding is None:
        return None

    update_data = {}
    if embedding is not None:
        update_data["embedding"] = embedding
    if document_source is not None:
        update_data["document_source"] = document_source

    if not update_data:  # Nothing to update
        return db_embedding

    stmt = (
        update(DocumentEmbedding).where(DocumentEmbedding.id == embedding_id).values(**update_data)
    )
    await db.execute(stmt)
    try:
        await db.commit()
        await db.refresh(db_embedding)
    except Exception:
        await db.rollback()
        raise
    return db_embedding


async def delete_document_embedding(db: AsyncSession, embedding_id: PyUUID) -> bool:
    """
    Deletes a document embedding by its ID.
    Returns True if deleted, False otherwise.
    """
    db_embedding = await get_document_embedding_by_id(db, embedding_id)
    if db_embedding is None:
        return False

    stmt = delete(DocumentEmbedding).where(DocumentEmbedding.id == embedding_id)
    await db.execute(stmt)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True


# Hierarchical Document Indexing CRUD


async def create_document_with_chunks(
    db: AsyncSession,
    *,
    chunks: list[dict],  # List of {content, embedding, metadata}
    document_source: str,
    title: Optional[str] = None,
    parent_document_id: Optional[PyUUID] = None,
) -> tuple[DocumentEmbedding, list[DocumentEmbedding]]:
    """
    Create a document with multiple chunks.

    Returns tuple of (parent_document, chunks)
    """
    from uuid import uuid4

    # Create parent document
    parent_id = parent_document_id or uuid4()
    parent_doc = DocumentEmbedding(
        id=parent_id,
        embedding=None,  # No embedding for document level
        document_source=document_source,
        content_hash="",  # Will be calculated from chunks
        parent_document_id=None,
        chunk_index=None,
        hierarchy_level=0,  # Document level
        title=title,
        metadata_json={"chunk_count": len(chunks)},
    )
    db.add(parent_doc)
    await db.flush()

    # Create chunks
    created_chunks = []
    for i, chunk_data in enumerate(chunks):
        chunk = DocumentEmbedding(
            embedding=chunk_data["embedding"],
            document_source=document_source,
            content_hash=chunk_data.get("content_hash", ""),
            parent_document_id=parent_id,
            chunk_index=i,
            hierarchy_level=2,  # Chunk level
            title=title,
            metadata_json=chunk_data.get("metadata"),
        )
        db.add(chunk)
        created_chunks.append(chunk)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    for chunk in created_chunks:
        await db.refresh(chunk)
    await db.refresh(parent_doc)

    return parent_doc, created_chunks


async def get_document_with_chunks(
    db: AsyncSession, document_id: PyUUID
) -> tuple[Optional[DocumentEmbedding], list[DocumentEmbedding]]:
    """
    Get a document with all its chunks.

    Returns tuple of (parent_document, list of chunks)
    """
    # Get parent document
    parent = await get_document_embedding_by_id(db, document_id)
    if parent is None:
        return None, []

    # Get all chunks for this document
    stmt = (
        select(DocumentEmbedding)
        .where(DocumentEmbedding.parent_document_id == document_id)
        .order_by(DocumentEmbedding.chunk_index)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    return parent, list(chunks)


async def get_chunks_by_parent(
    db: AsyncSession, parent_document_id: PyUUID
) -> list[DocumentEmbedding]:
    """
    Get all chunks for a parent document.
    """
    stmt = (
        select(DocumentEmbedding)
        .where(DocumentEmbedding.parent_document_id == parent_document_id)
        .order_by(DocumentEmbedding.chunk_index)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def search_similar_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    limit: int = 10,
    parent_document_id: Optional[PyUUID] = None,
) -> list[DocumentEmbedding]:
    """
    Search for similar chunks, optionally within a specific document.
    """
    from sqlalchemy import and_

    # Simple similarity search (cosine similarity via dot product)
    # For pgvector, we use the <=> operator for cosine distance
    stmt = (
        select(DocumentEmbedding)
        .where(DocumentEmbedding.embedding.isnot(None))
        .order_by(DocumentEmbedding.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    if parent_document_id:
        stmt = stmt.where(DocumentEmbedding.parent_document_id == parent_document_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_similar_embeddings(
    db: AsyncSession, query_embedding: list[float], limit: int = 5
) -> List[DocumentEmbedding]:
    """
    Finds document embeddings similar to the query_embedding using L2 distance.
    """
    stmt = (
        select(DocumentEmbedding)
        .order_by(DocumentEmbedding.embedding.l2_distance(query_embedding))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# A/B Testing CRUD operations


async def create_experiment(
    session: AsyncSession,
    *,
    name: str,
    description: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: str = "draft",
    traffic_allocation: int = 100,
    commit: bool = True,
) -> models.Experiment:
    experiment = models.Experiment(
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
        status=status,
        traffic_allocation=traffic_allocation,
    )
    session.add(experiment)
    if commit:
        try:
            await session.commit()
            await session.refresh(experiment)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return experiment


async def get_experiment(
    session: AsyncSession, experiment_id: PyUUID
) -> Optional[models.Experiment]:
    stmt = select(models.Experiment).where(models.Experiment.id == experiment_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_experiments(
    session: AsyncSession,
    *,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Experiment]:
    stmt = select(models.Experiment)
    if status:
        stmt = stmt.where(models.Experiment.status == status)
    stmt = stmt.offset(skip).limit(limit).order_by(models.Experiment.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_experiment(
    session: AsyncSession,
    experiment_id: PyUUID,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    traffic_allocation: Optional[int] = None,
    commit: bool = True,
) -> Optional[models.Experiment]:
    experiment = await get_experiment(session, experiment_id)
    if not experiment:
        return None

    update_data = {}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if start_date is not None:
        update_data["start_date"] = start_date
    if end_date is not None:
        update_data["end_date"] = end_date
    if status is not None:
        update_data["status"] = status
    if traffic_allocation is not None:
        update_data["traffic_allocation"] = traffic_allocation

    if not update_data:  # Nothing to update
        return experiment

    stmt = (
        update(models.Experiment).where(models.Experiment.id == experiment_id).values(**update_data)
    )
    await session.execute(stmt)
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Refresh the experiment object
    stmt = select(models.Experiment).where(models.Experiment.id == experiment_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_experiment(session: AsyncSession, experiment_id: PyUUID) -> bool:
    experiment = await get_experiment(session, experiment_id)
    if not experiment:
        return False

    stmt = delete(models.Experiment).where(models.Experiment.id == experiment_id)
    await session.execute(stmt)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return True


async def create_experiment_variant(
    session: AsyncSession,
    *,
    experiment_id: PyUUID,
    name: str,
    description: Optional[str] = None,
    is_control: bool = False,
    strategy_config: Optional[dict] = None,
    commit: bool = True,
) -> models.ExperimentVariant:
    # If this is a control variant, make sure no other control variant exists for this experiment
    if is_control:
        # Use SELECT ... FOR UPDATE to prevent race conditions
        stmt = (
            select(models.ExperimentVariant)
            .where(
                models.ExperimentVariant.experiment_id == experiment_id,
                models.ExperimentVariant.is_control,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        existing_control = result.scalar_one_or_none()
        if existing_control:
            # Update the existing control variant to not be control
            update_stmt = (
                update(models.ExperimentVariant)
                .where(models.ExperimentVariant.id == existing_control.id)
                .values(is_control=False)
            )
            await session.execute(update_stmt)

    variant = models.ExperimentVariant(
        experiment_id=experiment_id,
        name=name,
        description=description,
        is_control=is_control,
        strategy_config=strategy_config,
    )
    session.add(variant)
    if commit:
        try:
            await session.commit()
            await session.refresh(variant)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return variant


async def get_experiment_variant(
    session: AsyncSession, variant_id: PyUUID
) -> Optional[models.ExperimentVariant]:
    stmt = select(models.ExperimentVariant).where(models.ExperimentVariant.id == variant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_experiment_variants(
    session: AsyncSession, experiment_id: PyUUID
) -> List[models.ExperimentVariant]:
    stmt = (
        select(models.ExperimentVariant)
        .where(models.ExperimentVariant.experiment_id == experiment_id)
        .order_by(models.ExperimentVariant.created_at)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_experiment_variant(
    session: AsyncSession,
    variant_id: PyUUID,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_control: Optional[bool] = None,
    strategy_config: Optional[dict] = None,
    commit: bool = True,
) -> Optional[models.ExperimentVariant]:
    variant = await get_experiment_variant(session, variant_id)
    if not variant:
        return None

    # If this is being set as a control variant, make sure no other control variant exists for this experiment
    if is_control and is_control != variant.is_control:
        # Use SELECT ... FOR UPDATE to prevent race conditions
        stmt = (
            select(models.ExperimentVariant)
            .where(
                models.ExperimentVariant.experiment_id == variant.experiment_id,
                models.ExperimentVariant.is_control,
                models.ExperimentVariant.id != variant_id,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        existing_control = result.scalar_one_or_none()
        if existing_control:
            # Update the existing control variant to not be control
            update_stmt = (
                update(models.ExperimentVariant)
                .where(models.ExperimentVariant.id == existing_control.id)
                .values(is_control=False)
            )
            await session.execute(update_stmt)

    update_data = {}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if is_control is not None:
        update_data["is_control"] = is_control
    if strategy_config is not None:
        update_data["strategy_config"] = strategy_config

    if not update_data:  # Nothing to update
        return variant

    stmt = (
        update(models.ExperimentVariant)
        .where(models.ExperimentVariant.id == variant_id)
        .values(**update_data)
    )
    await session.execute(stmt)
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Refresh the variant object
    stmt = select(models.ExperimentVariant).where(models.ExperimentVariant.id == variant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_experiment_variant(session: AsyncSession, variant_id: PyUUID) -> bool:
    variant = await get_experiment_variant(session, variant_id)
    if not variant:
        return False

    stmt = delete(models.ExperimentVariant).where(models.ExperimentVariant.id == variant_id)
    await session.execute(stmt)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return True


async def create_experiment_result(
    session: AsyncSession,
    *,
    variant_id: PyUUID,
    session_id: PyUUID,
    kpi_quality: Optional[float] = None,
    kpi_speed: Optional[int] = None,
    kpi_cost: Optional[float] = None,
    user_feedback_score: Optional[float] = None,
    user_feedback_text: Optional[str] = None,
    result_metadata: Optional[dict] = None,
    commit: bool = True,
) -> models.ExperimentResult:
    result = models.ExperimentResult(
        variant_id=variant_id,
        session_id=session_id,
        kpi_quality=kpi_quality,
        kpi_speed=kpi_speed,
        kpi_cost=kpi_cost,
        user_feedback_score=user_feedback_score,
        user_feedback_text=user_feedback_text,
        result_asset_metadata=result_metadata,
    )
    session.add(result)
    if commit:
        try:
            await session.commit()
            await session.refresh(result)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return result


async def get_experiment_result(
    session: AsyncSession, result_id: PyUUID
) -> Optional[models.ExperimentResult]:
    stmt = select(models.ExperimentResult).where(models.ExperimentResult.id == result_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_experiment_results(
    session: AsyncSession,
    *,
    variant_id: Optional[PyUUID] = None,
    session_id: Optional[PyUUID] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.ExperimentResult]:
    stmt = select(models.ExperimentResult)
    if variant_id:
        stmt = stmt.where(models.ExperimentResult.variant_id == variant_id)
    if session_id:
        stmt = stmt.where(models.ExperimentResult.session_id == session_id)
    stmt = stmt.offset(skip).limit(limit).order_by(models.ExperimentResult.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


# Behavior File CRUD operations for post-conversion editor


async def create_behavior_file(
    session: AsyncSession,
    *,
    conversion_id: str,
    file_path: str,
    file_type: str,
    content: str,
    commit: bool = True,
) -> models.BehaviorFile:
    """Create a new behavior file entry."""
    try:
        conversion_uuid = _to_uuid(conversion_id)
    except ValueError:
        raise ValueError("Invalid conversion_id format")

    # Prevent path traversal attacks
    if ".." in file_path or file_path.startswith("/") or file_path.startswith("\\"):
        raise ValueError("Invalid file path: path traversal detected or absolute path used")

    behavior_file = models.BehaviorFile(
        conversion_id=conversion_uuid,
        file_path=file_path,
        file_type=file_type,
        content=content,
    )
    session.add(behavior_file)
    if commit:
        try:
            await session.commit()
            await session.refresh(behavior_file)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return behavior_file


async def get_behavior_file(session: AsyncSession, file_id: str) -> Optional[models.BehaviorFile]:
    """Get a specific behavior file by ID."""
    try:
        file_uuid = _to_uuid(file_id)
    except ValueError:
        return None

    stmt = select(models.BehaviorFile).where(models.BehaviorFile.id == file_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_behavior_files_by_conversion(
    session: AsyncSession, conversion_id: str
) -> List[models.BehaviorFile]:
    """Get all behavior files for a specific conversion."""
    try:
        conversion_uuid = _to_uuid(conversion_id)
    except ValueError:
        return []

    stmt = (
        select(models.BehaviorFile)
        .where(models.BehaviorFile.conversion_id == conversion_uuid)
        .order_by(models.BehaviorFile.file_path)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_behavior_file_content(
    session: AsyncSession,
    file_id: str,
    content: str,
    commit: bool = True,
) -> Optional[models.BehaviorFile]:
    """Update the content of a behavior file."""
    try:
        file_uuid = _to_uuid(file_id)
    except ValueError:
        return None

    stmt = (
        update(models.BehaviorFile)
        .where(models.BehaviorFile.id == file_uuid)
        .values(content=content)
        .returning(models.BehaviorFile)
    )
    result = await session.execute(stmt)
    updated_file = result.scalar_one_or_none()

    if commit and updated_file:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return updated_file


async def delete_behavior_file(session: AsyncSession, file_id: str) -> bool:
    """Delete a behavior file by ID."""
    try:
        file_uuid = _to_uuid(file_id)
    except ValueError:
        return False

    stmt = delete(models.BehaviorFile).where(models.BehaviorFile.id == file_uuid)
    result = await session.execute(stmt)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result.rowcount > 0


async def get_behavior_files_by_type(
    session: AsyncSession, conversion_id: str, file_type: str
) -> List[models.BehaviorFile]:
    """Get behavior files of a specific type for a conversion."""
    try:
        conversion_uuid = _to_uuid(conversion_id)
    except ValueError:
        return []

    stmt = (
        select(models.BehaviorFile)
        .where(
            models.BehaviorFile.conversion_id == conversion_uuid,
            models.BehaviorFile.file_type == file_type,
        )
        .order_by(models.BehaviorFile.file_path)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# Alias for update_job_progress to maintain compatibility
async def upsert_progress(
    session: AsyncSession, job_id: str, progress: int, commit: bool = True
) -> Optional[models.JobProgress]:
    """Alias for update_job_progress to maintain backward compatibility."""
    return await update_job_progress(session, job_id, progress, commit)


async def list_jobs(
    session: AsyncSession, skip: int = 0, limit: int = 100, user_id: Optional[str] = None
) -> tuple[List[models.ConversionJob], int]:
    """List conversion jobs with pagination, optionally filtered by user_id.

    Returns tuple of (jobs list, total count).
    When user_id is None, returns jobs without user_id (public/anonymous).
    When user_id is provided, returns jobs for that specific user.
    """
    from sqlalchemy import cast, Text, func

    stmt = select(models.ConversionJob).options(
        selectinload(models.ConversionJob.results),
        selectinload(models.ConversionJob.progress),
    )

    count_stmt = select(func.count(models.ConversionJob.id))

    if user_id:
        stmt = stmt.where(models.ConversionJob.input_data["user_id"].astext == user_id)
        count_stmt = count_stmt.where(models.ConversionJob.input_data["user_id"].astext == user_id)
    else:
        stmt = stmt.where(models.ConversionJob.input_data["user_id"].is_(None))
        count_stmt = count_stmt.where(models.ConversionJob.input_data["user_id"].is_(None))

    stmt = stmt.offset(skip).limit(limit).order_by(models.ConversionJob.created_at.desc())

    result = await session.execute(stmt)
    jobs = result.scalars().all()

    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    return jobs, total


async def update_addon_details(
    session: AsyncSession,
    addon_id: object,
    addon_data: object,
    commit: bool = True,
) -> Optional[models.Addon]:
    addon_uuid = _to_uuid(addon_id)

    stmt = select(models.Addon).where(models.Addon.id == addon_uuid)
    result = await session.execute(stmt)
    addon = result.scalar_one_or_none()

    if addon is None:
        addon = models.Addon(
            id=addon_uuid,
            name=getattr(addon_data, "name", "Unnamed Addon"),
            description=getattr(addon_data, "description", None),
            user_id=getattr(addon_data, "user_id", "anonymous"),
        )
        session.add(addon)
    else:
        addon.name = getattr(addon_data, "name", addon.name)
        addon.description = getattr(addon_data, "description", addon.description)
        addon.user_id = getattr(addon_data, "user_id", addon.user_id)

    for block_model in list(addon.blocks):
        await session.delete(block_model)
    for recipe_model in list(addon.recipes):
        await session.delete(recipe_model)
    await session.flush()

    for block_data in getattr(addon_data, "blocks", []):
        block = models.AddonBlock(
            addon_id=addon_uuid,
            identifier=block_data.identifier,
            properties=getattr(block_data, "properties", {}),
        )
        session.add(block)
        await session.flush()

        behavior_data = getattr(block_data, "behavior", None)
        if behavior_data:
            behavior = models.AddonBehavior(
                block_id=block.id,
                data=getattr(behavior_data, "data", {}),
            )
            session.add(behavior)

    for recipe_data in getattr(addon_data, "recipes", []):
        recipe = models.AddonRecipe(
            addon_id=addon_uuid,
            data=getattr(recipe_data, "data", {}),
        )
        session.add(recipe)

    if commit:
        try:
            await session.commit()
            await session.refresh(addon)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()

    return addon


# Addon CRUD operations
async def get_addon_details(session: AsyncSession, addon_id: uuid.UUID) -> Optional[models.Addon]:
    """Get addon details with all blocks, assets, and recipes."""
    stmt = (
        select(models.Addon)
        .options(
            selectinload(models.Addon.blocks).selectinload(models.AddonBlock.behavior),
            selectinload(models.Addon.assets),
            selectinload(models.Addon.recipes),
        )
        .where(models.Addon.id == addon_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# Addon Asset CRUD operations
async def get_addon_asset(session: AsyncSession, asset_id: str) -> Optional[models.AddonAsset]:
    """Get an addon asset by ID."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    stmt = select(models.AddonAsset).where(models.AddonAsset.id == asset_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_addon_asset(
    session: AsyncSession,
    *,
    addon_id: str,
    asset_type: str,
    file_path: str,
    original_filename: str,
    commit: bool = True,
) -> models.AddonAsset:
    """Create a new addon asset."""
    try:
        addon_uuid = _to_uuid(addon_id)
    except ValueError:
        raise ValueError(f"Invalid addon ID format: {addon_id}")

    # Prevent path traversal attacks
    if ".." in file_path or file_path.startswith("/"):
        raise ValueError("Invalid file path: path traversal detected")

    asset = models.AddonAsset(
        addon_id=addon_uuid,
        type=asset_type,
        path=file_path,
        original_filename=original_filename,
    )
    session.add(asset)
    if commit:
        try:
            await session.commit()
            await session.refresh(asset)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return asset


async def create_addon_asset_from_local_path(
    session: AsyncSession,
    *,
    addon_id: object,
    source_file_path: str,
    asset_type: str,
    original_filename: str,
    commit: bool = True,
) -> models.AddonAsset:
    rel_path = (
        os.path.relpath(source_file_path, BASE_ASSET_PATH)
        if os.path.isabs(source_file_path)
        else source_file_path
    )
    return await create_addon_asset(
        session,
        addon_id=str(addon_id),
        asset_type=asset_type,
        file_path=rel_path,
        original_filename=original_filename,
        commit=commit,
    )


async def update_addon_asset(
    session: AsyncSession,
    asset_id: str,
    *,
    asset_type: Optional[str] = None,
    file_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    commit: bool = True,
) -> Optional[models.AddonAsset]:
    """Update an addon asset."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    # Check if asset exists
    asset = await get_addon_asset(session, asset_id)
    if not asset:
        return None

    # Update fields if provided
    update_data = {}
    if asset_type is not None:
        update_data["type"] = asset_type
    if file_path is not None:
        # Prevent path traversal attacks
        if ".." in file_path or file_path.startswith("/"):
            raise ValueError("Invalid file path: path traversal detected")
        update_data["path"] = file_path
    if original_filename is not None:
        update_data["original_filename"] = original_filename

    if update_data:
        stmt = (
            update(models.AddonAsset)
            .where(models.AddonAsset.id == asset_uuid)
            .values(**update_data)
            .returning(models.AddonAsset)
        )
        result = await session.execute(stmt)
        if commit:
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        asset = result.scalar_one_or_none()

    return asset


async def delete_addon_asset(session: AsyncSession, asset_id: str) -> bool:
    """Delete an addon asset."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    # Check if asset exists
    asset = await get_addon_asset(session, asset_id)
    if not asset:
        return False

    stmt = delete(models.AddonAsset).where(models.AddonAsset.id == asset_uuid)
    result = await session.execute(stmt)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result.rowcount > 0


async def list_addon_assets(
    session: AsyncSession,
    addon_id: str,
    *,
    asset_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.AddonAsset]:
    """List addon assets for a given addon."""
    try:
        addon_uuid = _to_uuid(addon_id)
    except ValueError:
        raise ValueError(f"Invalid addon ID format: {addon_id}")

    stmt = (
        select(models.AddonAsset)
        .where(models.AddonAsset.addon_id == addon_uuid)
        .offset(skip)
        .limit(limit)
        .order_by(models.AddonAsset.created_at.desc())
    )

    if asset_type:
        stmt = stmt.where(models.AddonAsset.type == asset_type)

    result = await session.execute(stmt)
    return result.scalars().all()


# Asset CRUD operations
async def get_asset(session: AsyncSession, asset_id: str) -> Optional[models.Asset]:
    """Get an asset by ID."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    stmt = select(models.Asset).where(models.Asset.id == asset_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_asset(
    session: AsyncSession,
    *,
    conversion_id: str,
    asset_type: str,
    original_path: str,
    original_filename: str,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    asset_metadata: Optional[dict] = None,
    commit: bool = True,
) -> models.Asset:
    """Create a new asset."""
    try:
        conversion_uuid = _to_uuid(conversion_id)
    except ValueError:
        raise ValueError(f"Invalid conversion ID format: {conversion_id}")

    asset = models.Asset(
        conversion_id=conversion_uuid,
        asset_type=asset_type,
        original_path=original_path,
        original_filename=original_filename,
        file_size=file_size,
        mime_type=mime_type,
        asset_metadata=asset_metadata or {},
        status="pending",
    )
    session.add(asset)
    if commit:
        try:
            await session.commit()
            await session.refresh(asset)
        except Exception:
            await session.rollback()
            raise
    else:
        await session.flush()
    return asset


async def update_asset_status(
    session: AsyncSession,
    asset_id: str,
    status: str,
    *,
    converted_path: Optional[str] = None,
    error_message: Optional[str] = None,
    commit: bool = True,
) -> Optional[models.Asset]:
    """Update asset status, optionally setting converted_path or error_message."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    asset = await get_asset(session, asset_id)
    if not asset:
        return None

    values: dict = {"status": status}
    if converted_path is not None:
        values["converted_path"] = converted_path
    if error_message is not None:
        values["error_message"] = error_message

    stmt = (
        update(models.Asset)
        .where(models.Asset.id == asset_uuid)
        .values(**values)
        .returning(models.Asset)
    )
    result = await session.execute(stmt)
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return result.scalar_one_or_none()


async def update_asset_metadata(
    session: AsyncSession,
    asset_id: str,
    asset_metadata: dict,
    commit: bool = True,
) -> Optional[models.Asset]:
    """Update asset metadata."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    # Check if asset exists
    asset = await get_asset(session, asset_id)
    if not asset:
        return None

    stmt = (
        update(models.Asset)
        .where(models.Asset.id == asset_uuid)
        .values(asset_metadata=asset_metadata)
        .returning(models.Asset)
    )
    result = await session.execute(stmt)
    if commit:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return result.scalar_one_or_none()


async def delete_asset(session: AsyncSession, asset_id: str) -> bool:
    """Delete an asset."""
    try:
        asset_uuid = _to_uuid(asset_id)
    except ValueError:
        raise ValueError(f"Invalid asset ID format: {asset_id}")

    # Check if asset exists
    asset = await get_asset(session, asset_id)
    if not asset:
        return False

    stmt = delete(models.Asset).where(models.Asset.id == asset_uuid)
    result = await session.execute(stmt)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result.rowcount > 0


async def list_assets_for_conversion(
    session: AsyncSession,
    conversion_id: str,
    *,
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Asset]:
    """List assets for a given conversion."""
    try:
        conversion_uuid = _to_uuid(conversion_id)
    except ValueError:
        raise ValueError(f"Invalid conversion ID format: {conversion_id}")

    stmt = (
        select(models.Asset)
        .where(models.Asset.conversion_id == conversion_uuid)
        .offset(skip)
        .limit(limit)
        .order_by(models.Asset.created_at.desc())
    )

    if asset_type:
        stmt = stmt.where(models.Asset.asset_type == asset_type)

    if status:
        stmt = stmt.where(models.Asset.status == status)

    result = await session.execute(stmt)
    return result.scalars().all()


# ============================================================================
# Pattern Submission CRUD Functions
# ============================================================================


async def create_pattern_submission(
    session: AsyncSession,
    java_pattern: str,
    bedrock_pattern: str,
    description: str,
    contributor_id: str,
    tags: List[str],
    category: str,
) -> models.PatternSubmission:
    """
    Create a new pattern submission.

    Args:
        session: Database session
        java_pattern: Java code example
        bedrock_pattern: Bedrock code example
        description: Pattern description
        contributor_id: User submitting the pattern
        tags: List of tags
        category: Pattern category

    Returns:
        Created PatternSubmission
    """
    submission = models.PatternSubmission(
        java_pattern=java_pattern,
        bedrock_pattern=bedrock_pattern,
        description=description,
        contributor_id=contributor_id,
        tags=tags,
        category=category,
        status="pending",
    )
    session.add(submission)
    try:
        await session.commit()
        await session.refresh(submission)
    except Exception:
        await session.rollback()
        raise
    return submission


async def get_pattern_submission(
    session: AsyncSession,
    submission_id: str,
) -> Optional[models.PatternSubmission]:
    """
    Get a pattern submission by ID.

    Args:
        session: Database session
        submission_id: Submission UUID

    Returns:
        PatternSubmission if found, None otherwise
    """
    try:
        submission_uuid = _to_uuid(submission_id)
    except ValueError:
        raise ValueError(f"Invalid submission ID format: {submission_id}")

    stmt = select(models.PatternSubmission).where(models.PatternSubmission.id == submission_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pending_submissions(
    session: AsyncSession,
    limit: int = 50,
) -> List[models.PatternSubmission]:
    """
    Get pending pattern submissions.

    Args:
        session: Database session
        limit: Maximum number of submissions to return

    Returns:
        List of pending submissions, ordered by created_at DESC
    """
    stmt = (
        select(models.PatternSubmission)
        .where(models.PatternSubmission.status == "pending")
        .order_by(models.PatternSubmission.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_pattern_submission_status(
    session: AsyncSession,
    submission_id: str,
    status: str,
    reviewed_by: str,
    notes: Optional[str] = None,
) -> models.PatternSubmission:
    """
    Update pattern submission status (review workflow).

    Args:
        session: Database session
        submission_id: Submission UUID
        status: New status ("approved" or "rejected")
        reviewed_by: Reviewer user ID
        notes: Optional review notes

    Returns:
        Updated PatternSubmission

    Raises:
        ValueError: If submission not found
    """
    try:
        submission_uuid = _to_uuid(submission_id)
    except ValueError:
        raise ValueError(f"Invalid submission ID format: {submission_id}")

    # Get submission
    submission = await get_pattern_submission(session, submission_id)
    if not submission:
        raise ValueError(f"Submission {submission_id} not found")

    # Update fields
    submission.status = status
    submission.reviewed_by = reviewed_by
    submission.review_notes = notes
    submission.reviewed_at = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(submission)
    except Exception:
        await session.rollback()
        raise
    return submission


async def vote_on_pattern(
    session: AsyncSession,
    submission_id: str,
    upvote: bool,
) -> models.PatternSubmission:
    """
    Vote on a pattern submission.

    Args:
        session: Database session
        submission_id: Submission UUID
        upvote: True for upvote, False for downvote

    Returns:
        Updated PatternSubmission

    Raises:
        ValueError: If submission not found
    """
    try:
        submission_uuid = _to_uuid(submission_id)
    except ValueError:
        raise ValueError(f"Invalid submission ID format: {submission_id}")

    # Get submission
    submission = await get_pattern_submission(session, submission_id)
    if not submission:
        raise ValueError(f"Submission {submission_id} not found")

    # Update vote counts
    if upvote:
        submission.upvotes += 1
    else:
        submission.downvotes += 1

    try:
        await session.commit()
        await session.refresh(submission)
    except Exception:
        await session.rollback()
        raise
    return submission
