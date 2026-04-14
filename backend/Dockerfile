FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

# Runtime dependencies: libpq for PostgreSQL, curl for healthcheck,
# nodejs + npm for MCP server (@modelcontextprotocol/server-postgres via npx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

# ChromaDB persistence directory (mount as volume in docker-compose)
RUN mkdir -p /data/chromadb

ENV PORT=8000
ENV CHROMADB_PERSIST_DIRECTORY=/data/chromadb

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
