"""Initial schema - all Neuronal SEO tables

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("target_country", sa.String(100), default="DE"),
        sa.Column("target_language", sa.String(10), default="de"),
        sa.Column("target_cities", sa.JSON, default=list),
        sa.Column("services", sa.JSON, default=list),
        sa.Column("business_value_per_service", sa.JSON, nullable=True),
        sa.Column("competitors", sa.JSON, default=list),
        sa.Column("brand_terms", sa.JSON, default=list),
        sa.Column("forbidden_terms", sa.JSON, default=list),
        sa.Column("preferred_content_style", sa.Text, nullable=True),
        sa.Column("extra_context", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # pages
    # ------------------------------------------------------------------
    op.create_table(
        "pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("meta_description", sa.Text, nullable=True),
        sa.Column("h1", sa.Text, nullable=True),
        sa.Column("h2", sa.JSON, default=list),
        sa.Column("h3", sa.JSON, default=list),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("content_cleaned", sa.Text, nullable=True),
        sa.Column("word_count", sa.Integer, default=0),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("indexable", sa.Boolean, default=True),
        sa.Column("schema_markup", sa.JSON, nullable=True),
        sa.Column("internal_links", sa.JSON, default=list),
        sa.Column("external_links", sa.JSON, default=list),
        sa.Column("images_alt_text", sa.JSON, default=list),
        sa.Column("page_type", sa.String(50), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("render_mode", sa.String(20), default="http"),
        sa.Column("crawl_depth", sa.Integer, default=0),
        sa.Column("is_own_site", sa.Boolean, default=True),
        sa.Column("last_crawled_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "url", name="uq_page_project_url"),
    )
    op.create_index("ix_pages_url", "pages", ["url"])

    # ------------------------------------------------------------------
    # page_chunks
    # ------------------------------------------------------------------
    op.create_table(
        "page_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("heading_context", sa.Text, nullable=True),
        sa.Column("chunk_type", sa.String(50), default="paragraph"),
        sa.Column("token_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # keywords
    # ------------------------------------------------------------------
    op.create_table(
        "keywords",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("language", sa.String(10), default="de"),
        sa.Column("country", sa.String(100), default="DE"),
        sa.Column("city", sa.String(200), nullable=True),
        sa.Column("source", sa.String(50), default="manual"),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("business_value", sa.Integer, default=0),
        sa.Column("cluster_id", sa.String(36), nullable=True, index=True),
        sa.Column("search_volume", sa.Integer, nullable=True),
        sa.Column("cpc", sa.Float, nullable=True),
        sa.Column("competition_index", sa.Integer, nullable=True),
        sa.Column("extra_data", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "keyword", name="uq_keyword_project_keyword"),
    )

    # ------------------------------------------------------------------
    # serp_results
    # ------------------------------------------------------------------
    op.create_table(
        "serp_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("keyword_id", sa.String(36), sa.ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("country", sa.String(100), default="DE"),
        sa.Column("city", sa.String(200), nullable=True),
        sa.Column("language", sa.String(10), default="de"),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("serp_features", sa.JSON, nullable=True),
        sa.Column("fetched_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_serp_keyword_country", "serp_results", ["keyword", "country"])
    op.create_index("ix_serp_domain", "serp_results", ["domain"])

    # ------------------------------------------------------------------
    # competitor_pages
    # ------------------------------------------------------------------
    op.create_table(
        "competitor_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("keyword_id", sa.String(36), sa.ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("meta_description", sa.Text, nullable=True),
        sa.Column("headings", sa.JSON, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("content_sections", sa.JSON, nullable=True),
        sa.Column("faqs", sa.JSON, nullable=True),
        sa.Column("entities", sa.JSON, nullable=True),
        sa.Column("word_count", sa.Integer, default=0),
        sa.Column("internal_links", sa.JSON, nullable=True),
        sa.Column("schema_types", sa.JSON, nullable=True),
        sa.Column("has_pricing", sa.Boolean, default=False),
        sa.Column("has_trust_signals", sa.Boolean, default=False),
        sa.Column("has_case_studies", sa.Boolean, default=False),
        sa.Column("has_local_refs", sa.Boolean, default=False),
        sa.Column("has_cta", sa.Boolean, default=False),
        sa.Column("serp_position", sa.Integer, nullable=True),
        sa.Column("fetched_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "url", name="uq_competitor_project_url"),
    )

    # ------------------------------------------------------------------
    # keywords_clusters (created before embedding FK ref)
    # ------------------------------------------------------------------
    op.create_table(
        "keyword_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("keywords_list", sa.JSON, default=list),
        sa.Column("primary_keyword", sa.String(500), nullable=True),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("target_page_url", sa.String(2048), nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column("centroid_embedding_id", sa.String(36), nullable=True),
        sa.Column("cluster_size", sa.Integer, default=0),
        sa.Column("silhouette_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Add FK from keywords to keyword_clusters
    op.create_foreign_key(
        "fk_keywords_cluster",
        "keywords", "keyword_clusters",
        ["cluster_id"], ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # embeddings
    # ------------------------------------------------------------------
    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("object_type", sa.String(50), nullable=False, index=True),
        sa.Column("object_id", sa.String(36), nullable=False, index=True),
        sa.Column("embedding", Vector(3072), nullable=False),
        sa.Column("model", sa.String(100), default="text-embedding-3-large"),
        sa.Column("text_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_embeddings_object", "embeddings", ["object_type", "object_id"])

    # Add FK from keyword_clusters to embeddings
    op.create_foreign_key(
        "fk_cluster_centroid",
        "keyword_clusters", "embeddings",
        ["centroid_embedding_id"], ["id"],
        ondelete="SET NULL",
    )

    # Create IVFFlat index for vector similarity search (after data is inserted)
    # op.execute(
    #     "CREATE INDEX IF NOT EXISTS ix_embeddings_vector "
    #     "ON embeddings USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)"
    # )

    # ------------------------------------------------------------------
    # content_gaps
    # ------------------------------------------------------------------
    op.create_table(
        "content_gaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("keyword_cluster_id", sa.String(36), sa.ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("gap_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20), default="medium"),
        sa.Column("suggested_fix", sa.Text, nullable=True),
        sa.Column("competitors_have", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # internal_link_suggestions
    # ------------------------------------------------------------------
    op.create_table(
        "internal_link_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("target_page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("target_url", sa.String(2048), nullable=False),
        sa.Column("suggested_anchor", sa.String(500), nullable=False),
        sa.Column("relevance_score", sa.Float, default=0.0),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), default="suggested"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "source_url", "target_url", name="uq_link_suggestion"),
    )

    # ------------------------------------------------------------------
    # seo_tasks
    # ------------------------------------------------------------------
    op.create_table(
        "seo_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("keyword_cluster_id", sa.String(36), sa.ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), default="content"),
        sa.Column("priority", sa.String(20), default="medium"),
        sa.Column("priority_score", sa.Float, default=0.0),
        sa.Column("status", sa.String(20), default="todo"),
        sa.Column("checklist", sa.JSON, nullable=True),
        sa.Column("expected_impact", sa.Text, nullable=True),
        sa.Column("assigned_to", sa.String(200), nullable=True),
        sa.Column("due_date", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # gsc_performance
    # ------------------------------------------------------------------
    op.create_table(
        "gsc_performance",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("page_url", sa.String(2048), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("device", sa.String(20), default="DESKTOP"),
        sa.Column("clicks", sa.Integer, default=0),
        sa.Column("impressions", sa.Integer, default=0),
        sa.Column("ctr", sa.Float, default=0.0),
        sa.Column("position", sa.Float, default=0.0),
        sa.Column("data_date", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_gsc_query_date", "gsc_performance", ["project_id", "query", "data_date"])

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("report_type", sa.String(50), default="weekly"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=True),
        sa.Column("content_json", sa.JSON, nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("email_sent", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    # Drop FK constraints first
    op.execute("ALTER TABLE keywords DROP CONSTRAINT IF EXISTS fk_keywords_cluster")
    op.execute("ALTER TABLE keyword_clusters DROP CONSTRAINT IF EXISTS fk_cluster_centroid")

    # Drop tables in reverse-dependency order
    op.drop_table("reports")
    op.drop_table("gsc_performance")
    op.drop_table("seo_tasks")
    op.drop_table("internal_link_suggestions")
    op.drop_table("content_gaps")
    op.drop_table("keyword_clusters")
    op.execute("DROP INDEX IF EXISTS ix_embeddings_vector")
    op.drop_table("embeddings")
    op.drop_table("competitor_pages")
    op.drop_table("serp_results")
    op.drop_table("keywords")
    op.drop_table("page_chunks")
    op.drop_table("pages")
    op.drop_table("projects")
