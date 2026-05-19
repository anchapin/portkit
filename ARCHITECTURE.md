# PortKit — Architecture Overview
<!-- AUTO-GENERATED section markers present. Update static sections manually; module map regenerates weekly. -->

## Vision
AI-powered "conversion accelerator" that converts Minecraft Java Edition mods to Bedrock Edition add-ons.
Target: automate 60-80% of a mod creator's conversion effort (B2B positioning).

---

## System Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │                   User / Client                      │
                        └────────────────────┬────────────────────────────────┘
                                             │ HTTPS
                        ┌────────────────────▼────────────────────────────────┐
                        │           Frontend  (React + TypeScript + Vite)      │
                        │           Nginx proxy — localhost:3000               │
                        └────────────────────┬────────────────────────────────┘
                                             │ REST API
                        ┌────────────────────▼────────────────────────────────┐
                        │           Backend  (FastAPI + Python 3.12+)          │
                        │           localhost:8080                             │
                        │  ┌──────────────────────────────────────────────┐   │
                        │  │  src/api/          HTTP route handlers        │   │
                        │  │  src/services/     Business logic             │   │
                        │  │  src/models/       Pydantic schemas           │   │
                        │  │  src/db/           SQLAlchemy async ORM       │   │
                        │  │  src/security/     Upload sandbox, rate limits│   │
                        │  └──────────────────────────────────────────────┘   │
                        └───┬────────────────────┬───────────────────────┬────┘
                            │ HTTP               │ Celery                │
               ┌────────────▼──────┐  ┌─────────▼────────┐  ┌──────────▼────────┐
               │   AI Engine        │  │   PostgreSQL 15   │  │    Redis 7         │
               │   FastAPI:8001     │  │   + pgvector      │  │    Celery broker  │
               │   CrewAI + RAG    │  │   port:5433       │  │    port:6379      │
               └────────────────────┘  └──────────────────┘  └───────────────────┘
```

---

## Service Directory

| Service | Technology | Port | Key Files |
|---------|-----------|------|-----------|
| **Frontend** | React 18 + TypeScript + Vite + Nginx | 3000 | `frontend/src/` |
| **Backend** | FastAPI + SQLAlchemy (async) + Celery | 8080 | `backend/src/` |
| **AI Engine** | FastAPI + CrewAI + LangChain | 8001 | `ai-engine/` |
| **PostgreSQL** | PostgreSQL 15 + pgvector | 5433 | `database/` |
| **Redis** | Redis 7 | 6379 | Celery broker + session cache |

---

## AI Engine — Module Map

```
ai-engine/
├── main.py                    # FastAPI app entrypoint (port 8001)
├── agents/                    # Conversion agent implementations
│   ├── java_analyzer/         # Java mod parsing (tree-sitter, AST analysis)
│   ├── logic_translator/      # Java→Bedrock logic translation
│   ├── texture_converter/     # Texture atlas + image conversion
│   ├── model_converter/       # 3D model format conversion
│   ├── recipe_converter.py    # Crafting/custom recipe conversion
│   ├── entity_converter.py    # Entity behavior + spawn rules
│   ├── bedrock_builder.py     # Bedrock add-on package assembly
│   ├── bedrock_architect.py   # Manifest + structure generation
│   └── ...                    # 20+ specialized agents
├── converters/                # Standalone converter utilities
│   ├── advancement_converter.py
│   ├── loot_table_generator.py
│   ├── sound_converter.py
│   └── ...
├── crew/                      # CrewAI crew definitions
│   ├── conversion_crew.py     # Main PortkitConversionCrew
│   └── rag_crew.py
├── orchestration/             # Parallel task orchestration
│   ├── orchestrator.py        # ParallelOrchestrator (main entry)
│   ├── strategy_selector.py   # Chooses sequential/parallel/hybrid
│   ├── task_graph.py          # DAG of conversion tasks
│   └── worker_pool.py
├── search/                    # RAG + hybrid search
│   ├── rag_pipeline.py        # Main RAG pipeline
│   ├── hybrid_search_engine.py # BM25 + vector hybrid
│   ├── reranking_engine.py    # Cross-encoder reranking
│   └── ...
├── qa/                        # Quality assurance pipeline
│   ├── orchestrator.py        # QA workflow coordinator
│   ├── multi_candidate.py     # DPC-style consistency selection
│   ├── validators.py
│   └── logic_auditor_agent.py # Adversarial functional testing
├── knowledge/                 # Domain knowledge base
│   ├── cross_reference.py
│   └── schema.py
└── models/                    # Pydantic models + ML model wrappers
    └── smart_assumptions.py   # SmartAssumptionEngine
```

### Conversion Data Flow

```
JAR Upload
    │
    ▼
java_analyzer/ ──── tree-sitter AST ──→ JavaModAnalysis
    │                                        │
    ▼                                        ▼
PortkitConversionCrew (CrewAI)          RAG Pipeline
    │  Agents run in parallel:          (pgvector + hybrid search)
    │  - entity_converter                    │
    │  - recipe_converter               Bedrock pattern retrieval
    │  - texture_converter/                  │
    │  - logic_translator/              ◄────┘
    │  - model_converter/
    │  - sound_converter
    │  - ...
    ▼
bedrock_builder → .mcaddon package
    │
    ▼
QA Pipeline (multi_candidate + logic_auditor)
    │
    ▼
ConversionReport → Frontend
```

---

## Backend — Module Map

```
backend/src/
├── main.py                    # FastAPI app entrypoint (port 8080)
├── api/                       # Route handlers (thin layer, delegates to services)
│   ├── conversions.py         # POST /api/v1/convert, GET /api/v1/conversions/{id}
│   ├── auth.py                # OAuth routes (Discord/GitHub/Google)
│   ├── billing.py             # Stripe webhook + subscription routes
│   ├── analytics.py           # Usage analytics endpoints
│   └── ...
├── services/                  # Business logic
│   ├── celery_tasks.py        # Async task definitions
│   ├── celery_config.py       # Celery + Redis configuration
│   ├── ai_engine_client.py    # HTTP client for AI Engine (port 8001)
│   ├── asset_conversion_service.py  # Coordinates asset conversion
│   ├── comprehensive_report_generator.py
│   └── ...
├── models/                    # Pydantic request/response schemas
│   ├── addon_models.py
│   └── embedding_models.py
├── db/                        # Database layer
│   ├── models.py              # SQLAlchemy ORM models
│   ├── crud.py                # CRUD operations
│   ├── base.py                # async engine + get_db dependency
│   └── init_db.py
├── security/                  # Security hardening
│   └── ...                    # Upload sandbox, ClamAV, rate limiting
└── errors/                    # Centralized error handling package
```

---

## Frontend — Module Map

```
frontend/src/
├── App.tsx                    # Root component, router setup
├── main.tsx                   # Vite entrypoint
├── api/                       # API client functions (axios/fetch wrappers)
├── components/                # Reusable UI components
├── pages/                     # Route-level page components
├── hooks/                     # Custom React hooks
├── contexts/                  # React context providers
├── services/                  # Frontend business logic
├── types/                     # TypeScript type definitions
└── utils/                     # Utility functions
```

---

## Key Design Patterns

| Pattern | Where Used | Notes |
|---------|-----------|-------|
| **Async-first** | Backend + AI Engine | All I/O is `async def` + `await` |
| **CrewAI agents** | `ai-engine/crew/` | Each converter is a CrewAI agent with tools |
| **RAG retrieval** | `ai-engine/search/` | pgvector + BM25 hybrid; reranked by cross-encoder |
| **Smart assumptions** | `ai-engine/models/smart_assumptions.py` | Fills Java→Bedrock gaps automatically |
| **Celery queuing** | `backend/src/services/celery_tasks.py` | Long conversions run async; Redis broker |
| **Dependency injection** | Backend | `Depends(get_db)` for DB sessions |
| **Per-segment confidence** | `ai-engine/qa/` | Each converted segment gets a conformal reliability score |

---

## Critical "Do Not Touch" Zones

| File/Module | Reason |
|-------------|--------|
| `ai-engine/search/rag_pipeline.py` | Tightly coupled with CrewAI + Minecraft knowledge; LangChain/LlamaIndex swap would break agent tool interfaces |
| `ai-engine/knowledge/patterns/` | Domain-specific Java→Bedrock pattern mappings; no external library covers these |
| `ai-engine/orchestration/strategy_selector.py` | PortKit-specific orchestration logic; not generic |
| `backend/src/db/models.py` | Core ORM models; schema changes require migrations |

---

## Environment Variables (Required)

```bash
OPENAI_API_KEY=           # Required for embeddings + LLM
ANTHROPIC_API_KEY=        # Required for Claude-based agents
DATABASE_URL=             # postgresql+asyncpg://...
REDIS_URL=redis://redis:6379
STRIPE_SECRET_KEY=        # Billing
STRIPE_WEBHOOK_SECRET=    # Billing webhook validation
```

---

## Development Commands

```bash
# Start all services
docker compose up -d

# Dev mode (hot reload)
docker compose -f docker-compose.dev.yml up -d

# Run tests
pnpm run test                          # All tests
cd backend && pytest src/tests/unit/ -q  # Backend unit (fast)
cd ai-engine && pytest                 # AI engine tests

# Linting / formatting
pnpm run lint
pnpm run format

# Code quality
cd backend && ruff check src/
cd ai-engine && ruff check .
```

---

## Auto-Generated Skeleton Files

The following files are **auto-generated weekly** by `scripts/portkit_skeletonize.py`.
Do not edit them manually — commit the generator script changes instead.

- `ai-engine/SKELETON.md`
- `backend/SKELETON.md`
- `frontend/SKELETON.md`

*Last generated: 2026-05-18*
