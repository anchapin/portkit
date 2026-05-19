# Multi-stage Dockerfile for Portkit
# This builds all components: backend, ai-engine, and frontend

# ============================================
# Stage 1: Backend builder
# ============================================
FROM python:3.14-slim AS backend-builder

WORKDIR /app/backend

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip>=26.1" setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: AI Engine builder
# ============================================
FROM python:3.14-slim AS ai-engine-builder

WORKDIR /app/ai-engine

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install ai-engine dependencies
COPY ai-engine/requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip>=26.1" setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 3: Production backend
# ============================================
FROM python:3.14-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builders
COPY --from=backend-builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Create non-root user
RUN groupadd -r portkit && useradd -r -g portkit portkit

# Copy backend source
WORKDIR /app/backend
COPY --chown=portkit:portkit backend/ .

# Create required directories
RUN mkdir -p /app/backend/temp_uploads /app/backend/conversion_outputs && \
    chown -R portkit:portkit /app/backend/temp_uploads /app/backend/conversion_outputs

USER portkit

# Health check for backend
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Default command runs backend
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--access-log"]