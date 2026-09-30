# PortKit

> ## This project is no longer developed here
>
> The hosted service at modporter.ai is **shut down**. There is no website to
> upload a mod to any more, and no API to call. What is left in this repository
> still runs if you host it yourself, but it is not being maintained and no new
> features are coming.
>
> **Development has moved to [anchapin/portkit-v2](https://github.com/anchapin/portkit-v2)**,
> a rebuild with a deterministic conversion core, a real structural validator,
> and a much smaller surface area.
>
> **If a mod failed to convert here, please tell us about it on v2.** Open an
> issue at [portkit-v2/issues](https://github.com/anchapin/portkit-v2/issues)
> with a link to the mod and what went wrong. Those reports decide which
> converters get built first, so a failure report is genuinely the most useful
> thing you can send.

AI-powered Minecraft Java to Bedrock conversion platform. Self-host only; the hosted service has been shut down.

[Documentation](docs/getting-started.md) | [API Reference](docs/api-reference.md) | [Conversion Guide](docs/conversion-guide.md)

[![codecov](https://codecov.io/gh/anchapin/PortKit/branch/main/graph/badge.svg)](https://codecov.io/gh/anchapin/PortKit)

## 🎯 Vision

Empower Minecraft creators with production-grade AI tooling that converts Java Edition content to Bedrock Edition at scale — with smart assumptions to bridge technical gaps.

## 🚀 Features

### Conversion Coverage (67%+ B2B)
| Content Type | Coverage |
|--------------|----------|
| **Textures** | Block textures, item textures, entity textures |
| **Models** | Bedrock JSON models (geometry, render controllers) |
| **Recipes** | Crafting, smelting, stonecutting, milling, crushing, cooking_pot |
| **Sounds** | Sound definitions and audio assets |
| **Lang Files** | en_US.lang translation and localization |
| **Entities** | Entity behaviors and spawn rules |

### Core Platform
- **AI-Powered Conversion**: Multi-agent LangGraph pipeline for intelligent content transformation
- **Adversarial Logic Auditor**: QA pipeline that validates conversion accuracy
- **Conversion History Dashboard**: Track and review past conversions
- **Usage Metering**: Production billing via Stripe with OAuth authentication
- **File Security**: Robust validation and malware scanning (ClamAV)
- **Fine-tuning Infrastructure**: Continuously improving AI models

### Tech Stack
- **Frontend**: React + TypeScript + Vite (Nginx in production)
- **Backend**: Python + FastAPI + SQLAlchemy + AsyncPG
- **AI Engine**: LangChain/LangGraph + LangChain + FastAPI
- **RAG System**: Vector database (pgvector) + Embedding generation
- **Database**: PostgreSQL 15 with async support
- **Cache**: Redis 7 for sessions and caching
- **Infrastructure**: Docker + Docker Compose

## 📦 Quick Start

This project offers multiple deployment options:

### Prerequisites
- **Docker & Docker Compose** (recommended - handles all dependencies)
- OR for local development:
  - Node.js 22.12+ LTS (recommended for Vite 7.2.2+)
  - Python 3.9+
  - PostgreSQL 15+
  - Redis 7+

### Option 1: Production Deployment (Docker Hub)

This option uses pre-built Docker images from Docker Hub for a production-like environment.

```bash
# Clone the repository
git clone https://github.com/anchapin/PortKit.git
cd PortKit

# Copy environment variables
cp .env.example .env
# Edit .env and add your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)

# Start all services using Docker Hub images
docker compose -f docker compose.prod.yml up -d

# Check service status
docker compose ps
```

**Service URLs:**
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8080 (or `/api/` when using frontend proxy)
- **PostgreSQL**: localhost:5433
- **Redis**: localhost:6379

**Note**: The frontend uses Nginx to proxy API requests to the backend, so you can access the API through either `http://localhost:3000/api/` or directly at `http://localhost:8080/api/`.

### Option 2: Local Development Setup (Docker)

#### Production Environment
```bash
# Clone the repository
git clone https://github.com/anchapin/PortKit.git
cd PortKit

# Copy environment variables
cp .env.example .env
# Edit .env and add your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)

# Start all services
docker compose up -d

# Check service status
docker compose ps
```

#### Development Environment
```bash
# Use development configuration with hot reload
docker compose -f docker compose.dev.yml up -d
```

#### Service URLs
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8080
- **AI Engine**: http://localhost:8001
- **PostgreSQL**: localhost:5433
- **Redis**: localhost:6379

#### Docker Management
```bash
# View logs
docker compose logs [service-name]

# Restart a service
docker compose restart [service-name]

# Stop all services
docker compose down

# Rebuild and restart
docker compose up -d --build

# View real-time logs
docker compose logs -f
```

### Option 3: Manual Local Setup (Advanced)

If you prefer to run services locally without Docker:

1. Clone the repository
2. Install dependencies: `pnpm run install-all`
3. Start development servers: `pnpm run dev`
4. Open http://localhost:3000

## 🐳 Docker Architecture

### Services Overview
PortKit uses a microservices architecture with the following containers:

| Service | Technology | Port | Purpose |
|---------|------------|------|---------|
| **Frontend** | React + Nginx | 3000 | User interface |
| **Backend** | FastAPI + Python | 8080 | Main API server |
| **AI Engine** | FastAPI + LangChain/LangGraph | 8001 | AI conversion engine |
| **PostgreSQL** | PostgreSQL 15 | 5433 | Primary database |
| **Redis** | Redis 7 | 6379 | Caching & sessions |

### Environment Variables
Required environment variables (add to `.env`):
```bash
# AI API Keys (required)
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key

# Database Configuration
# For local development (auto-configured for Docker):
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/portkit
POSTGRES_DB=portkit
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

# For Supabase (production):
DATABASE_URL=postgresql://supabase_user:supabase_password@db.your_project_id.supabase.co:5432/postgres

# Redis (auto-configured for Docker)
REDIS_URL=redis://redis:6379

# Application
LOG_LEVEL=INFO
DEBUG=false
VITE_API_URL=http://localhost:8080/api/v1
```

**Note**: Frontend environment variables (`VITE_API_URL`, `VITE_API_BASE_URL`) are set as build arguments in Docker Compose and are embedded into the built JavaScript bundle at build time.

### Health Checks
All services include health checks for monitoring:
```bash
# Check frontend health
curl http://localhost:3000/health

# Check backend health (basic liveness)
curl http://localhost:8080/health

# Check backend readiness (includes dependency checks)
curl http://localhost:8080/health/readiness

# Check backend liveness (process running)
curl http://localhost:8080/health/liveness

# Check AI engine health
curl http://localhost:8001/api/v1/health

# Check all service status
docker compose ps
```

### Health Check Endpoints

The backend provides three health check endpoints for Kubernetes probes:

| Endpoint | Purpose | Dependencies Checked |
|----------|---------|---------------------|
| `/health` | Basic health check | None |
| `/health/liveness` | Process is running | None |
| `/health/readiness` | Can serve traffic | Database, Redis |

**Response Format:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00",
  "checks": {
    "dependencies": {
      "database": {
        "status": "healthy",
        "latency_ms": 5.2,
        "message": "Database connection successful"
      },
      "redis": {
        "status": "healthy",
        "latency_ms": 1.8,
        "message": "Redis connection successful"
      }
    }
  }
}
```

**Status Values:**
- `healthy`: All checks passed
- `degraded`: Non-critical dependencies unavailable (e.g., Redis)
- `unhealthy`: Critical dependencies unavailable (e.g., Database)

### Troubleshooting

#### Common Issues
1. **Port conflicts**: If ports 3000, 8080, 8001, 5433, or 6379 are in use, modify `docker compose.yml`
2. **Missing API keys**: Ensure `.env` file contains valid `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`
3. **Database connection**: Check PostgreSQL container logs if backend fails to start
4. **WebSocket connection errors**: Ensure frontend environment variables are correctly set during Docker build
5. **CSP font errors**: Updated nginx configuration allows embedded fonts via `font-src 'self' data:`

#### Debugging Commands
```bash
# View service logs
docker compose logs backend
docker compose logs ai-engine
docker compose logs frontend

# Access container shell
docker compose exec backend bash
docker compose exec ai-engine bash

# Reset everything
docker compose down -v
docker compose up -d --build
```

## Testing

### Prerequisites for Testing
- Docker and Docker Compose (for test database)

### Setup Test Database
```bash
# Start the test PostgreSQL database
./scripts/test-db.sh start

# Or manually with docker-compose
docker-compose -f docker-compose.test.yml up -d test-postgres
```

### Run Tests

**Important:** The test suite uses a parallel/serial split architecture:
- Most tests run in **parallel** for speed (2772 tests)
- A few tests with module-level state pollution run **serially** (4 tests)

```bash
# Run all tests (parallel + serial)
pnpm run test

# Backend tests - parallel run (default, ~2772 tests)
# These run with: -n auto --dist=loadscope -m "not integration and not serial"
cd backend && pytest

# Backend tests - serial run (4 tests with module-level state issues)
# These run with: -n0 -m serial
cd backend && pytest -m serial

# Backend tests - serial mode only (for debugging)
cd backend && pytest -n0

# Frontend tests
cd frontend && pnpm test

# AI Engine and RAG tests
cd ai-engine && pytest
```

**Test Stability:** The parallel test suite runs with ZERO flaky failures. The serial tests (`-m serial`) handle tests that pollute module-level state.

### Test Markers
| Marker | Description |
|--------|-------------|
| `integration` | Integration tests (excluded from default run) |
| `serial` | Tests that must run serially (not in parallel) due to module-level state pollution |
| `unit` | Unit tests |
| `asyncio` | Async tests |

### Test Database Management
```bash
# Start test database
./scripts/test-db.sh start

# Stop test database
./scripts/test-db.sh stop

# Reset test database (clears all data)
./scripts/test-db.sh reset

# View database logs
./scripts/test-db.sh logs
```

### End-to-End Conversion Test
To run the full conversion pipeline test, validating the complete Java to Bedrock pipeline:

```bash
pytest tests/test_mvp_conversion.py
```

### Docker Tests
```bash
# Run tests in Docker containers (parallel mode - default)
docker compose exec backend pytest

# Run serial tests only
docker compose exec backend pytest -m serial

# Run tests in serial mode (for debugging)
docker compose exec backend pytest -n0

# Run tests with coverage
docker compose exec backend pytest --cov=src
docker compose exec ai-engine pytest --cov=src
```

## 🔧 Development Workflows

### Docker Development Best Practices

#### Hot Reload Development
Use the development Docker Compose configuration for active development:
```bash
# Start with hot reload enabled
docker compose -f docker compose.dev.yml up -d

# This enables:
# - Frontend: Vite dev server with hot reload
# - Backend: uvicorn with auto-reload
# - AI Engine: uvicorn with auto-reload and debug mode
```

#### Making Changes
```bash
# After code changes, rebuild specific service
docker compose build backend
docker compose up -d backend

# Or rebuild all services
docker compose up -d --build
```

#### Database Management
```bash
# Access PostgreSQL directly
docker compose exec postgres psql -U postgres -d portkit

# Run database migrations
docker compose exec backend alembic upgrade head

# Reset database (⚠️ destroys data)
docker compose down -v
docker compose up -d
```

#### Performance Monitoring
```bash
# Monitor resource usage
docker stats

# View container resource limits
docker compose config

# Check service dependencies
docker compose ps --services
```

## 🗺️ Roadmap

Current milestone: **M6 Beta Iteration** — see [GitHub Milestones](https://github.com/anchapin/PortKit/milestones) for progress.

## 📖 Documentation

- [Getting Started Guide](docs/getting-started.md) - Quick start and installation
- [API Reference](docs/api-reference.md) - Full API documentation
- [Conversion Guide](docs/conversion-guide.md) - Feature support and best practices
- [Product Requirements Document](docs/PRD.md)
- [API Documentation](docs/API.md)
- [Contributing Guidelines](CONTRIBUTING.md)

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/anchapin/PortKit/issues)
- **Discussions**: [GitHub Discussions](https://github.com/anchapin/PortKit/discussions)
- **Documentation**: [Project Wiki](https://github.com/anchapin/PortKit/wiki)

## 🏆 Acknowledgments

- **LangChain/LangGraph**: For the multi-agent AI framework
- **FastAPI**: For the high-performance API framework
- **React**: For the frontend framework
- **Docker**: For containerization
- **Minecraft Community**: For inspiration and support

---

Made with ❤️ by the PortKit team

# test
