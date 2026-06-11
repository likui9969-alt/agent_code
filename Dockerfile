# ============================================================================
# AI Code Assistant — Production Docker image
# ============================================================================
#
# Build:
#   docker build -t ai-code-assistant:latest .
#
# Run (standalone, Redis must be reachable):
#   docker run -p 8000:8000 --env-file .env.production ai-code-assistant:latest
#
# Run (with compose — recommended):
#   docker compose up -d
# ============================================================================

# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps (if any C extensions are added later)
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a venv
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="AI Code Assistant"
LABEL org.opencontainers.image.description="LangGraph + FastAPI + Redis AI Code Assistant"
LABEL org.opencontainers.image.version="1.0.0"

# ── Create non-root user ──
RUN groupadd -r codeagent && useradd -r -g codeagent -d /app codeagent

# ── Copy venv from builder ──
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ── Application ──
WORKDIR /app
COPY app/ ./app/
COPY run.py .

# ── Entrypoint ──
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# ── Security ──
RUN chown -R codeagent:codeagent /app
USER codeagent

# ── Runtime ──
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

EXPOSE 8000

# Healthcheck — calls the /health endpoint every 30 s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${APP_PORT}/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
