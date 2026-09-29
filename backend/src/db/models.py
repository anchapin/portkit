import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    String,
    Integer,
    ForeignKey,
    DateTime,
    func,
    text,
    Column,
    Text,
    VARCHAR,
    DECIMAL,
    TIMESTAMP,
    TypeDecorator,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.orm import relationship, Mapped, mapped_column
from db.declarative_base import Base


# Custom type that automatically chooses the right JSON type based on the database
class JSONType(TypeDecorator):
    impl = JSONB  # Default to JSONB for PostgreSQL
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(SQLiteJSON)
        else:
            return dialect.type_descriptor(JSONB)


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'queued'"),
    )
    input_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship: one job -> many results and progress
    results = relationship("ConversionResult", back_populates="job", cascade="all, delete-orphan")
    progress = relationship(
        "JobProgress", back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    # Relationship to comparison_results
    comparison_results = relationship("ComparisonResultDb", back_populates="conversion_job")
    # Relationship to feedback
    feedback = relationship(
        "ConversionFeedback", back_populates="job", cascade="all, delete-orphan"
    )
    # Relationship to assets
    assets = relationship("Asset", back_populates="conversion", cascade="all, delete-orphan")


class ConversionResult(Base):
    __tablename__ = "conversion_results"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    job = relationship("ConversionJob", back_populates="results")


class JobProgress(Base):
    __tablename__ = "job_progress"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_update: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    job = relationship("ConversionJob", back_populates="progress")


# Addon Management Models


class Addon(Base):
    __tablename__ = "addons"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Assuming user_id is a string for now
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    blocks = relationship("AddonBlock", back_populates="addon", cascade="all, delete-orphan")
    assets = relationship("AddonAsset", back_populates="addon", cascade="all, delete-orphan")
    recipes = relationship("AddonRecipe", back_populates="addon", cascade="all, delete-orphan")


class AddonBlock(Base):
    __tablename__ = "addon_blocks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    addon_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addons.id", ondelete="CASCADE"), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    properties: Mapped[dict] = mapped_column(JSONType, nullable=True, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    addon = relationship("Addon", back_populates="blocks")
    behavior = relationship(
        "AddonBehavior",
        back_populates="block",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AddonAsset(Base):
    __tablename__ = "addon_assets"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    addon_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addons.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)  # E.g., "texture", "sound", "script"
    path: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Relative path within the addon structure
    original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    addon = relationship("Addon", back_populates="assets")


class AddonBehavior(Base):
    __tablename__ = "addon_behaviors"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    block_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("addon_blocks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default={}
    )  # Behavior components, events, etc.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    block = relationship("AddonBlock", back_populates="behavior")


class AddonRecipe(Base):
    __tablename__ = "addon_recipes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    addon_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addons.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default={}
    )  # Crafting recipe definition
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    addon = relationship("Addon", back_populates="recipes")


# Behavior File Model for Post-Conversion Editor


class BehaviorFile(Base):
    __tablename__ = "behavior_files"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'entity_behavior', 'block_behavior', 'script', 'recipe', etc.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    conversion = relationship("ConversionJob", backref="behavior_files")


# Feedback Models


class ConversionFeedback(Base):
    __tablename__ = "conversion_feedback"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversion_jobs.id"), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_anonymized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("'false'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job = relationship("ConversionJob", back_populates="feedback")


class CorrectionSubmission(Base):
    __tablename__ = "correction_submissions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversion_jobs.id"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    original_output: Mapped[str] = mapped_column(Text, nullable=False)
    original_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    corrected_output: Mapped[str] = mapped_column(Text, nullable=False)
    correction_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'"), index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_updated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("'false'")
    )

    job = relationship("ConversionJob", backref="correction_submissions")


class IssueReport(Base):
    __tablename__ = "issue_reports"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversion_jobs.id"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    mod_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    conversion_score: Mapped[float] = mapped_column(nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'medium'")
    )  # 'low', 'medium', 'high', 'critical'
    failing_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )  # 'pending', 'acknowledged', 'investigating', 'resolved', 'wont_fix'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    job = relationship("ConversionJob", backref="issue_reports")


# Asset Management Models


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'texture', 'model', 'sound', 'script', etc.
    original_path: Mapped[str] = mapped_column(String, nullable=False)
    converted_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )  # 'pending', 'processing', 'converted', 'failed'
    asset_metadata: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True, default={})
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    conversion = relationship("ConversionJob", back_populates="assets")


# Comparison Models


class ComparisonResultDb(Base):
    __tablename__ = "comparison_results"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversion_id = Column(UUID(as_uuid=True), ForeignKey("conversion_jobs.id"), nullable=False)
    structural_diff = Column(JSONType)
    code_diff = Column(JSONType)
    asset_diff = Column(JSONType)
    assumptions_applied = Column(JSONType)
    confidence_scores = Column(JSONType)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    feature_mappings = relationship(
        "FeatureMappingDb",
        back_populates="comparison_result",
        cascade="all, delete-orphan",
    )
    conversion_job = relationship("ConversionJob", back_populates="comparison_results")


class FeatureMappingDb(Base):
    __tablename__ = "feature_mappings"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comparison_id = Column(UUID(as_uuid=True), ForeignKey("comparison_results.id"), nullable=False)
    java_feature = Column(Text)
    bedrock_equivalent = Column(Text)
    mapping_type = Column(VARCHAR(50))
    confidence_score = Column(DECIMAL(3, 2))

    comparison_result = relationship("ComparisonResultDb", back_populates="feature_mappings")


# Document Embedding Models


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    embedding = Column(
        VECTOR(3072), nullable=True
    )  # Nullable to support parent documents without embeddings
    document_source = Column(String, nullable=False, index=True)
    content_hash = Column(
        String, nullable=True, unique=True, index=True
    )  # Nullable for parent documents
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Hierarchical indexing fields
    parent_document_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True, index=True)
    hierarchy_level = Column(
        Integer, nullable=False, server_default=text("2")
    )  # 0=document, 1=section, 2=chunk
    title = Column(String, nullable=True, index=True)

    # Metadata storage - use JSONType to support both SQLite and PostgreSQL
    metadata_json = Column(JSONType, nullable=True)


# A/B Testing Models


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft, active, paused, completed
    traffic_allocation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )  # Percentage (0-100)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    variants = relationship(
        "ExperimentVariant", back_populates="experiment", cascade="all, delete-orphan"
    )
    # Note: Access to results can be achieved via experiment.variants
    # then iterating through variant.results for each variant


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strategy_config: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    experiment = relationship("Experiment", back_populates="variants")
    results = relationship(
        "ExperimentResult", back_populates="variant", cascade="all, delete-orphan"
    )


class ExperimentResult(Base):
    __tablename__ = "experiment_results"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiment_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    kpi_quality: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), nullable=True
    )  # Quality score (0.00 to 100.00)
    kpi_speed: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Execution time in milliseconds
    kpi_cost: Mapped[Optional[float]] = mapped_column(
        DECIMAL(10, 2), nullable=True
    )  # Computational cost
    user_feedback_score: Mapped[Optional[float]] = mapped_column(
        DECIMAL(3, 2), nullable=True
    )  # User feedback score (1.0 to 5.0)
    user_feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_asset_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONType, nullable=True, name="result_metadata"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    variant = relationship("ExperimentVariant", back_populates="results")
    # Note: Access to experiment can be achieved via result.variant.experiment


class BehaviorTemplate(Base):
    __tablename__ = "behavior_templates"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    template_type: Mapped[str] = mapped_column(String(100), nullable=False)
    template_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    tags: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    created_by: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# Product Analytics Models


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # e.g., "page_view", "conversion_start", "conversion_complete", "button_click"
    event_category: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # e.g., "navigation", "conversion", "feedback", "export"
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    conversion_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )  # Link to conversion job if applicable
    event_properties: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    # Properties like: { "button_id": "upload_mod", "page": "/", "target_version": "1.20.0" }
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # Hashed IP for privacy
    referrer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # "desktop", "mobile", "tablet"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


# Community Pattern Submission Models


class PatternSubmission(Base):
    __tablename__ = "pattern_submissions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    java_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    bedrock_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    upvotes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    downvotes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    tags: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=list,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )


# ============================================
# Authentication Models
# ============================================


class User(Base):
    """User model for authentication"""

    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("'false'"),
    )
    conversion_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("'0'"),
    )
    # Email verification
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    verification_token_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Password reset
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # OAuth fields (Issue #980)
    # Primary OAuth provider (discord, github, google)
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # OAuth provider's user ID
    oauth_provider_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Store OAuth access token (encrypted) for API calls if needed
    oauth_access_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Store OAuth refresh token (encrypted) for token refresh
    oauth_refresh_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Subscription / Billing fields (Issue #970)
    subscription_tier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'free'"),
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    subscription_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    byok_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("'false'"),
    )
    llm_api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    llm_api_key_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")
    credit_balance = relationship("UserCredits", back_populates="user", uselist=False)

    # OAuth account linking
    oauth_accounts = relationship(
        "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
    )


class OAuthAccount(Base):
    """OAuth account linking for users (Issue #980)"""

    __tablename__ = "oauth_accounts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    oauth_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    oauth_provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    oauth_access_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    oauth_refresh_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    oauth_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    oauth_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oauth_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship
    user = relationship("User", back_populates="oauth_accounts")

    __table_args__ = (
        Index(
            "ix_oauth_accounts_provider_user",
            "oauth_provider",
            "oauth_provider_user_id",
            unique=True,
        ),
    )


class APIKey(Base):
    """API Key model for programmatic access"""

    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="API Key")
    prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("'true'"),
    )
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", back_populates="api_keys")


class UsageRecord(Base):
    """Tracks monthly usage for conversion limits per subscription tier (Issue #977)"""

    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    web_conversions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("'0'"),
    )
    api_conversions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("'0'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", back_populates="usage_records")

    __table_args__ = (
        Index("ix_usage_user_period", "user_id", "period_year", "period_month", unique=True),
    )


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserCredits(Base):
    """PAYG credit balance for users (Issue #1226)"""

    __tablename__ = "user_credits"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # user_id: explicit unique index defined below in __table_args__ (avoids
    # SQLAlchemy auto-generating a duplicate index named "ix_user_credits_user_id")
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("'0'"),
    )
    lifetime_purchased: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("'0'"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user = relationship("User", back_populates="credit_balance")

    __table_args__ = (Index("ix_user_credits_user_id", "user_id", unique=True),)
