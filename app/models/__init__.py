"""
SQLAlchemy ORM models for the Neuronal SEO database.
Uses pgvector for embedding storage and similarity search.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Enum as SAEnum,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.models.enums import (
    IntentType,
    PageType,
    TaskPriority,
    TaskStatus,
    ClusterAction,
    GapSeverity,
)


# ---------------------------------------------------------------------------
# Helper: generate UUID primary keys
# ---------------------------------------------------------------------------
def _uuid_pk() -> Mapped[str]:
    return mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


def _timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime, default=datetime.utcnow)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = _uuid_pk()
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    target_country: Mapped[str] = mapped_column(String(100), default="DE")
    target_language: Mapped[str] = mapped_column(String(10), default="de")
    target_cities: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    services: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    business_value_per_service: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    competitors: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    brand_terms: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    forbidden_terms: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    preferred_content_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    pages: Mapped[list["Page"]] = relationship("Page", back_populates="project", cascade="all, delete-orphan")
    keywords: Mapped[list["Keyword"]] = relationship("Keyword", back_populates="project", cascade="all, delete-orphan")
    serp_results: Mapped[list["SerpResult"]] = relationship("SerpResult", back_populates="project", cascade="all, delete-orphan")
    seo_tasks: Mapped[list["SeoTask"]] = relationship("SeoTask", back_populates="project", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="project", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    h1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    h2: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    h3: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_cleaned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    indexable: Mapped[bool] = mapped_column(Boolean, default=True)
    schema_markup: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    internal_links: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    external_links: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    images_alt_text: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    page_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    render_mode: Mapped[str] = mapped_column(String(20), default="http")  # http or playwright
    crawl_depth: Mapped[int] = mapped_column(Integer, default=0)
    is_own_site: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="pages")
    chunks: Mapped[list["PageChunk"]] = relationship("PageChunk", back_populates="page", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_page_project_url"),
        Index("ix_pages_url", "url"),
    )


# ---------------------------------------------------------------------------
# Page Chunk
# ---------------------------------------------------------------------------
class PageChunk(Base):
    """Semantic chunks of page content for embedding."""
    __tablename__ = "page_chunks"

    id: Mapped[str] = _uuid_pk()
    page_id: Mapped[str] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    heading_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_type: Mapped[str] = mapped_column(String(50), default="paragraph")  # paragraph, heading, faq, list
    token_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _timestamp()

    # Relationships
    page: Mapped["Page"] = relationship("Page", back_populates="chunks")


# ---------------------------------------------------------------------------
# Keyword
# ---------------------------------------------------------------------------
class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="de")
    country: Mapped[str] = mapped_column(String(100), default="DE")
    city: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual, competitor, serp_api, gsc, autocomplete
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    business_value: Mapped[int] = mapped_column(Integer, default=0)  # 0-10
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cpc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    competition_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="keywords")
    cluster: Mapped[Optional["KeywordCluster"]] = relationship("KeywordCluster", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("project_id", "keyword", name="uq_keyword_project_keyword"),
    )


# ---------------------------------------------------------------------------
# SERP Result
# ---------------------------------------------------------------------------
class SerpResult(Base):
    __tablename__ = "serp_results"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True, index=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    country: Mapped[str] = mapped_column(String(100), default="DE")
    city: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="de")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    serp_features: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = _timestamp()

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="serp_results")

    __table_args__ = (
        Index("ix_serp_keyword_country", "keyword", "country"),
        Index("ix_serp_domain", "domain"),
    )


# ---------------------------------------------------------------------------
# Competitor Page
# ---------------------------------------------------------------------------
class CompetitorPage(Base):
    __tablename__ = "competitor_pages"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_sections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    faqs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    entities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    internal_links: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    schema_types: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    has_pricing: Mapped[bool] = mapped_column(Boolean, default=False)
    has_trust_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    has_case_studies: Mapped[bool] = mapped_column(Boolean, default=False)
    has_local_refs: Mapped[bool] = mapped_column(Boolean, default=False)
    has_cta: Mapped[bool] = mapped_column(Boolean, default=False)
    serp_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_competitor_project_url"),
    )


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = _uuid_pk()
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # keyword, page, chunk, competitor_page
    object_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    embedding = mapped_column(Vector, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-large")
    text_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256 for dedup
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        Index("ix_embeddings_object", "object_type", "object_id"),
        Index(
            "ix_embeddings_vector",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_l2_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Keyword Cluster
# ---------------------------------------------------------------------------
class KeywordCluster(Base):
    __tablename__ = "keyword_clusters"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    keywords_list: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    primary_keyword: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_page_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # create_new, improve_existing, merge, noindex
    centroid_embedding_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("embeddings.id", ondelete="SET NULL"), nullable=True)
    cluster_size: Mapped[int] = mapped_column(Integer, default=0)
    silhouette_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    keywords: Mapped[list["Keyword"]] = relationship("Keyword", back_populates="cluster")


# ---------------------------------------------------------------------------
# Content Gap
# ---------------------------------------------------------------------------
class ContentGap(Base):
    __tablename__ = "content_gaps"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True)
    keyword_cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    gap_type: Mapped[str] = mapped_column(String(50), nullable=False)  # missing_section, missing_entity, missing_faq, missing_trust, thin_content
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # high, medium, low
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    competitors_have: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, fixed, ignored
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()


# ---------------------------------------------------------------------------
# Internal Link Suggestion
# ---------------------------------------------------------------------------
class InternalLinkSuggestion(Base):
    __tablename__ = "internal_link_suggestions"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    suggested_anchor: Mapped[str] = mapped_column(String(500), nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested, implemented, rejected
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_url", "target_url",
            name="uq_link_suggestion",
        ),
    )


# ---------------------------------------------------------------------------
# SEO Task
# ---------------------------------------------------------------------------
class SeoTask(Base):
    __tablename__ = "seo_tasks"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True)
    keyword_cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="content")  # content, technical, on_page, internal_linking, schema, local_seo
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    checklist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="seo_tasks")


# ---------------------------------------------------------------------------
# GSC Performance
# ---------------------------------------------------------------------------
class GscPerformance(Base):
    __tablename__ = "gsc_performance"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    page_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device: Mapped[str] = mapped_column(String(20), default="DESKTOP")
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    data_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        Index("ix_gsc_query_date", "project_id", "query", "data_date"),
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = _uuid_pk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(50), default="weekly")  # weekly, on_demand, content_brief
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="reports")
