# Neuronal SEO - Automated SEO Intelligence Pipeline

An automated SEO analysis pipeline using a **competitor-first, SERP-optional** approach. Crawls your website, discovers competitor pages via sitemaps, extracts entities and topics, generates semantic embeddings, clusters keywords, classifies search intent, detects content gaps, suggests internal links, scores SEO opportunities, and produces actionable task reports.

## Architecture Philosophy

**No heavy Google SERP scraping.** The system avoids building core logic around automated Google queries, which are against Google's ToS and fragile.

Instead, it uses:

```text
self-crawl + competitor-crawl + sitemap discovery + entity extraction + embeddings + clustering + gap analysis
```

This gives 80-90% of SEO intelligence without paid SERP APIs or anti-bot headaches.

## Architecture

```text
┌───────────────────────────────────────────────────┐
│                   Docker Compose                   │
│                                                    │
│  ┌──────────┐ ┌───────┐ ┌──────────┐             │
│  │ Postgres │ │ Redis │ │ FastAPI  │             │
│  │ +pgvector│ │       │ │ API      │             │
│  └──────────┘ └───────┘ └──────────┘             │
│                           │                        │
│                    ┌──────┴──────┐                │
│                    │  RQ Worker  │                │
│                    └─────────────┘                │
└───────────────────────────────────────────────────┘
```

## Pipeline Flow (15 Steps)

```text
1.  Generate seed keywords from project context (city×service×intent combos)
2.  Crawl own website (httpx + Trafilatura + selectolax)
3.  Extract own sitemap (XML sitemap + robots.txt discovery)
4.  Crawl competitors via sitemap-first discovery
5.  Classify all pages (service, blog, FAQ, landing, etc.)
6.  Extract entities (services, tech, pricing, trust, FAQs, CTAs)
7.  Build competitor topic maps
8.  Generate embeddings (OpenAI or local sentence-transformers)
9.  Cluster keywords semantically (HDBSCAN + cosine similarity)
10. Classify search intent (pattern + SERP + LLM)
11. Map clusters to pages (create/improve/merge/noindex)
12. Detect content gaps against competitor topic maps
13. Generate internal link suggestions (vector similarity)
14. Score SEO opportunities (bv × intent × opportunity × feasibility)
15. Generate Markdown report with actionable task tickets

Optional (not blocking):
  - Manual SERP seeding (user provides top URLs per keyword)
  - Bing Webmaster Tools keyword data (free)
  - Light SERP sampling for validation
  - Search Console feedback loop (future)
```

## Features

### MVP (v0.1)

| Module | Description |
|--------|-------------|
| **Keyword Seed Engine** | Generates keywords from services, cities, intent patterns, competitor seeds |
| **Website Crawler** | Crawls own site with httpx + Trafilatura + selectolax for speed |
| **Sitemap Extractor** | Discovers all pages via XML sitemaps, sitemap indexes, and robots.txt |
| **Competitor Crawler** | Sitemap-first discovery → classify → prioritize → crawl → extract |
| **Page Classifier** | Classifies pages as service/landing/blog/FAQ/comparison/case study/thin |
| **Entity Extractor** | Extracts services, technologies, pricing terms, trust signals, FAQs, CTAs, cities |
| **Bing Webmaster Tools** | Free keyword ideas and site scan (optional, works without API key) |
| **Embedding Layer** | OpenAI text-embedding-3-large with local sentence-transformers fallback |
| **Semantic Clustering** | HDBSCAN + cosine similarity with text-based fallback |
| **Intent Classifier** | Pattern-based + SERP feature + LLM classification |
| **Page Mapper** | Maps keyword clusters to target pages (create/improve/merge actions) |
| **Content Gap Detector** | Compares own pages vs competitors, finds missing sections/FAQs/trust/schema |
| **Internal Linking Engine** | Vector similarity-based link suggestions |
| **Opportunity Scorer** | Priority = business_value × intent × opportunity × feasibility |
| **Report Generator** | Markdown + JSON reports with task tickets and priority roadmap |
| **Email Delivery** | SMTP sender with styled HTML emails from Markdown reports |
| **Weekly Scheduler** | APScheduler-based automatic weekly report generation and delivery |
| **CLI Tool** | Typer-based CLI for project management, pipeline execution, and email |
| **REST API** | FastAPI endpoints for all operations |

### SERP Data Strategy

| Approach | Use Case | Status |
|----------|----------|--------|
| Self-crawl | Own website | ✅ Primary |
| Sitemap discovery | Competitor pages | ✅ Primary |
| Competitor crawl | Content/entity analysis | ✅ Primary |
| Manual SERP seeding | Key page validation | ✅ Supported |
| Bing Webmaster Tools | Keyword ideas | ✅ Optional |
| DataForSEO / SerpAPI | Automated SERP data | ⚠️ Optional, off by default |
| Google Search Console | Performance data | 📋 Future |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 16 + pgvector |
| Queue | Redis + RQ |
| Crawler | httpx, Trafilatura, selectolax, BeautifulSoup, Playwright |
| Sitemap | XML parsing (ElementTree), gzip, robots.txt |
| NLP/ML | sentence-transformers, scikit-learn, HDBSCAN |
| Embeddings | OpenAI text-embedding-3-large (local fallback) |
| LLM | OpenAI GPT-4o (optional) |
| SERP Data | DataForSEO / SerpAPI (optional, off by default) |
| Extras | extruct (schema.org), advertools (SEO utilities) |
| Reports | Markdown |
| Infrastructure | Docker Compose |

## Quick Start

### 1. Configure

```bash
cp .env.example .env
# Edit .env - only OPENAI_API_KEY is needed for embeddings
# DATAFORSEO and SERPAPI keys are OPTIONAL
```

### 2. Start Services

```bash
# Start core services
docker-compose up -d

# Start with weekly scheduler (auto-generates + emails reports)
docker-compose --profile scheduler up -d
```

Services: PostgreSQL:5432, Redis:6379, FastAPI:8000, RQ Worker, Scheduler (optional)

### 3. Run Migrations

```bash
docker-compose exec api alembic upgrade head
```

### 4. Create a Project

```bash
python cli.py create-project \
  --domain "appagentur-koeln.com" \
  --country DE \
  --language de \
  --cities "Köln,Bonn,Düsseldorf" \
  --services "App Entwicklung,Flutter Entwicklung,MVP Entwicklung" \
  --competitors "competitor1.de,competitor2.de"
```

### 5. Generate Seed Keywords

```bash
python cli.py seed-keywords --project-id <uuid>
```

### 6. (Optional) Manual SERP Seeding

For your most important keywords, manually seed the top-ranking URLs:

```bash
curl -X POST http://localhost:8000/api/v1/serp/<project_id>/seed-manual \
  -H "Content-Type: application/json" \
  -d '{"keyword": "app entwicklung köln", "urls": ["https://competitor1.de/app", "https://competitor2.de/entwicklung"]}'
```

### 7. Run the Full Pipeline

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/pipeline/run/<project_id>

# Via CLI
python cli.py run-pipeline --project-id <project_id>
```

### 8. View Results

```bash
curl http://localhost:8000/api/v1/reports/<project_id>/list
curl http://localhost:8000/api/v1/analysis/<project_id>/tasks
python cli.py stats --project-id <project_id>
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/projects/` | Project CRUD |
| POST | `/api/v1/crawler/{id}` | Crawl own website |
| POST | `/api/v1/keywords/{id}/batch` | Add keywords in batch |
| POST | `/api/v1/keywords/{id}/generate-seeds` | Generate seed keywords |
| POST | `/api/v1/serp/{id}/seed-manual` | **Manual SERP seeding** (no API needed) |
| POST | `/api/v1/serp/{id}/fetch` | Fetch SERPs (requires API key) |
| POST | `/api/v1/serp/{id}/crawl-competitors` | Crawl competitors (sitemap-first) |
| POST | `/api/v1/embeddings/{id}/generate` | Generate embeddings |
| POST | `/api/v1/embeddings/{id}/search` | Vector similarity search |
| POST | `/api/v1/analysis/{id}/cluster` | Cluster keywords |
| POST | `/api/v1/analysis/{id}/classify-intent` | Classify search intent |
| POST | `/api/v1/analysis/{id}/map-pages` | Map clusters to pages |
| POST | `/api/v1/analysis/{id}/detect-gaps` | Detect content gaps |
| POST | `/api/v1/analysis/{id}/suggest-links` | Internal link suggestions |
| POST | `/api/v1/analysis/{id}/score-opportunities` | Score SEO opportunities |
| GET | `/api/v1/analysis/{id}/tasks` | List prioritized SEO tasks |
| POST | `/api/v1/reports/{id}/generate` | Generate report |
| POST | `/api/v1/reports/{id}/send-email` | Generate + email a report |
| POST | `/api/v1/reports/test-email` | Test SMTP configuration |
| POST | `/api/v1/reports/schedule/weekly/start` | Start weekly scheduler |
| POST | `/api/v1/reports/schedule/weekly/stop` | Stop weekly scheduler |
| POST | `/api/v1/reports/schedule/run-now` | Run all weekly reports now |
| POST | `/api/v1/pipeline/run/{id}` | Run full 15-step pipeline |
| POST | `/api/v1/sitemaps/extract/{domain}` | Extract sitemap from any domain |
| POST | `/api/v1/entities/extract` | Extract entities from text |
| GET | `/api/v1/bing/keyword-ideas` | Bing keyword ideas (free) |

## Database Schema

```
projects              - SEO project configuration
pages                 - Crawled page data
page_chunks           - Semantic content chunks
keywords              - Target keywords
serp_results          - Google SERP data (optional)
competitor_pages      - Competitor analysis with entities
embeddings            - Vector embeddings (pgvector)
keyword_clusters      - Semantic keyword groups
content_gaps          - Detected content gaps
internal_link_suggestions - Link recommendations
seo_tasks             - Prioritized action items
gsc_performance       - Google Search Console data (future)
reports               - Generated reports
```

## Directory Structure

```
neuronal_seo/
├── seeds/              # Project seed configurations (YAML)
│   ├── appagentur-koeln.yml
│   ├── hypnosetherapie-koeln.yml
│   └── udonthanilawyer-en.yml
├── app/
│   ├── api/            # FastAPI route handlers (7 modules)
│   ├── core/           # Config, database engine
│   ├── models/         # SQLAlchemy ORM models (13 tables)
│   ├── services/       # Business logic (15 services)
│   │   ├── crawler.py           # Own-site crawler (selectolax)
│   │   ├── keyword_engine.py    # Seed keyword generator
│   │   ├── sitemap_extractor.py # XML sitemap discovery
│   │   ├── competitor_crawler.py# Sitemap-first competitor analysis
│   │   ├── page_classifier.py   # Page type classification
│   │   ├── entity_extractor.py  # Topic/entity extraction
│   │   ├── serp_fetcher.py      # SERP API (optional)
│   │   ├── bing_webmaster.py    # Bing Webmaster Tools (free)
│   │   ├── embedding_service.py # OpenAI + local embeddings
│   │   ├── clustering.py        # HDBSCAN keyword clustering
│   │   ├── intent_classifier.py # Intent classification
│   │   ├── page_mapper.py       # Cluster→Page mapping
│   │   ├── content_gap.py       # Gap detection
│   │   ├── internal_linking.py  # Link suggestions
│   │   ├── opportunity_scorer.py# Priority scoring
│   │   ├── report_generator.py  # Markdown/JSON reports
│   │   ├── email_sender.py      # SMTP email delivery (HTML styled)
│   │   ├── scheduler.py         # Weekly report scheduler (APScheduler)
│   │   └── pipeline.py          # 15-step orchestrator
│   ├── workers/        # RQ background tasks
│   └── main.py         # FastAPI application
├── alembic/            # Database migrations
├── docker/             # Docker init scripts
├── reports/            # Generated reports
├── cli.py              # Typer CLI
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

## Priority Scoring Formula

```
priority_score = business_value × intent_score × opportunity × feasibility

business_value:   0-10 (manual per service)
intent_score:     local_transactional=1.0, commercial=0.9, informational=0.4
opportunity:      based on competitor weakness, gap size
feasibility:      how easy to implement

Result:
  ≥ 70 → critical
  ≥ 40 → high
  ≥ 20 → medium
  < 20 → low
```

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
rq worker --url redis://localhost:6379/0 neuronal_seo_tasks
python cli.py --help
```

## Running Tests

All tests run inside Docker against the live database:

```bash
# Start services
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head

# Run all tests (24 tests: migrations, API, crawler, Playwright, reports)
docker-compose exec api pytest tests/ -v

# Run specific test file
docker-compose exec api pytest tests/test_migrations.py -v

# Run with verbose output
docker-compose exec api pytest tests/ -v --tb=long
```

Test coverage:
- **Migrations**: Validates `alembic upgrade head` creates all 14 tables with correct columns and foreign keys
- **API**: 12 endpoint tests (CRUD, keywords, analysis, health)
- **Crawler**: Static crawling, render_mode tracking, crawl policy
- **Playwright**: Real JS-rendered page crawling + mock-based fallback tests
- **Reports**: Report generation with Markdown output
