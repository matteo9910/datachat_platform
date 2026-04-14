# Railway.app Deployment Guide — DataChat BI (FastAPI + ChromaDB)

> **Last updated:** 2026-03-04  
> **Target stack:** FastAPI 0.115 · ChromaDB 0.5.18 · PostgreSQL 15+ · Python 3.11

---

## 1. Railway Platform Overview

### 1.1 Pricing (2025-2026)

| Plan | Cost | Included Resources |
|------|------|--------------------|
| **Trial** | Free for 30 days | $5 one-time credit, up to 5 projects, 3 services/project |
| **Hobby** | $5/month | $5 included usage, 1 vCPU, 8 GB RAM/service, 50 GB volume storage |
| **Pro** | $20/month | $20 included usage, 32 vCPU, 32 GB RAM/service, 500 GB volume storage |
| **Enterprise** | Custom | Dedicated infra, SLA, priority support |

**Free / Trial tier limits:**
- 1 vCPU per service, 0.5 GB RAM per service
- 0.5 GB volume storage
- 7-day log retention
- Single region
- Community support only
- After trial: $1/month non-rollover credit (enough for a small idle app)

**Usage-based billing** (all plans after credits):
- vCPU: ~$0.000231/min ($10/mo for 1 vCPU)
- RAM: ~$0.000231/GB/min ($10/mo for 1 GB)
- Egress: $0.10/GB after free allowance

**Recommendation:** Use the **Hobby plan ($5/month)** for POC. Estimated monthly cost for FastAPI + PostgreSQL + ChromaDB volume: **$5-$12/month**.

---

## 2. Account Creation — Step by Step

1. Go to [railway.app](https://railway.app) and click **"Start a New Project"**
2. Sign up with **GitHub** (recommended for auto-deploy) or email
3. Verify your email address
4. *Optional:* Add a credit card to unlock Hobby tier (removes trial limits)
5. Create a new **Project** — this is the top-level container
6. Inside the project, you will add **Services** (FastAPI backend, PostgreSQL, etc.)

---

## 3. Dockerfile for FastAPI + ChromaDB

Create `backend/Dockerfile` at the backend root:

```dockerfile
# ============================================================
# DataChat BI — FastAPI + ChromaDB Production Dockerfile
# ============================================================

# ---------- Stage 1: Build ----------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system deps required by psycopg2 and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim

WORKDIR /app

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# ChromaDB persistent storage directory (will be mounted as Railway volume)
RUN mkdir -p /data/chroma_db

# Expose port — Railway injects $PORT at runtime
ENV PORT=8000
EXPOSE ${PORT}

# Health-check endpoint (Railway uses this)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run with uvicorn — bind to 0.0.0.0 on $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

### Key Dockerfile Decisions

| Decision | Rationale |
|----------|-----------|
| Multi-stage build | Reduces final image by ~400 MB (no gcc/build tools) |
| `python:3.11-slim` | Smaller than full image, larger than alpine but avoids musl compat issues with ChromaDB native deps |
| `libpq5` at runtime | Required by psycopg2-binary |
| `$PORT` env var | Railway injects the port; we default to 8000 for local dev |
| `/data/chroma_db` directory | Mount point for Railway persistent volume |
| HEALTHCHECK | Railway uses health checks before routing traffic |

---

## 4. Railway Configuration (`railway.toml`)

Create `backend/railway.toml`:

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 5
```

> **Note:** If your Dockerfile already has a `CMD`, the `startCommand` in `railway.toml` will **override** it. You can omit `startCommand` to use the Dockerfile's CMD instead.

### Alternative: Nixpacks (no Dockerfile)

If you prefer Railway's auto-builder instead of Docker, create `railway.toml`:

```toml
[build]
builder = "nixpacks"
buildCommand = "pip install -r requirements.txt"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
healthcheckPath = "/health"
healthcheckTimeout = 300
```

Nixpacks will auto-detect Python and install dependencies. **However, Docker is recommended** for ChromaDB because it needs specific system libraries.

---

## 5. Environment Variable Management

### 5.1 Setting Variables in Dashboard

1. Open your Railway project → click on the FastAPI service
2. Go to the **Variables** tab
3. Click **"New Variable"** or **"RAW Editor"** for bulk paste

### 5.2 Required Variables

```env
# --- App ---
PORT=8000
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info

# --- Database (auto-populated if using Railway PostgreSQL) ---
DATABASE_URL=${{Postgres.DATABASE_URL}}
# Railway supports variable references — ${{ServiceName.VAR}}

# --- ChromaDB ---
CHROMA_DB_PATH=/data/chroma_db
CHROMA_PERSIST_DIRECTORY=/data/chroma_db

# --- OpenAI / LLM ---
OPENAI_API_KEY=sk-...your-key...

# --- CORS ---
FRONTEND_URL=https://your-frontend.railway.app
ALLOWED_ORIGINS=https://your-frontend.railway.app,https://yourdomain.com

# --- Supabase (if used) ---
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

### 5.3 Setting Variables via CLI

```bash
railway variable set OPENAI_API_KEY=sk-xxx
railway variable set CHROMA_DB_PATH=/data/chroma_db
railway variable set ENVIRONMENT=production

# List all variables
railway variable list

# Delete a variable
railway variable delete DEBUG
```

### 5.4 Variable References

Railway supports **cross-service variable references**:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```
This auto-injects connection strings from other services in the same project.

### 5.5 Shared Variables

Use **Shared Variables** in project settings to define variables available to all services (e.g., `ENVIRONMENT=production`).

---

## 6. Persistent Storage / Volumes

ChromaDB requires persistent storage to retain vector embeddings across deployments.

### 6.1 Create a Volume

**Via Dashboard:**
1. Open your project canvas
2. Press `Cmd+K` (or `Ctrl+K`) → type "Volume" → select "Create Volume"
3. Attach it to your FastAPI service
4. Set mount path: `/data/chroma_db`

**Via CLI:**
```bash
railway volume add --mount-path /data/chroma_db
```

### 6.2 Important Volume Notes

| Aspect | Detail |
|--------|--------|
| **Mount timing** | Volumes mount at container **start**, not during build |
| **Permissions** | Mounted as root; set `RAILWAY_RUN_UID=0` if using non-root user |
| **Provided env vars** | `RAILWAY_VOLUME_NAME`, `RAILWAY_VOLUME_MOUNT_PATH` auto-set |
| **Size limits** | Trial: 0.5 GB; Hobby: 50 GB; Pro: 500 GB |
| **Live resize** | Available on Pro plan and above |
| **Backups** | Manual and automated backups supported |
| **Data on build** | Data written during `docker build` does NOT persist on volume |

### 6.3 Application Configuration

Ensure your FastAPI app reads the ChromaDB path from environment:

```python
import os
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "/data/chroma_db")
```

---

## 7. PostgreSQL Database

### 7.1 Add PostgreSQL via Dashboard

1. Inside your project, press `Cmd+K` → "Database" → select **PostgreSQL**
2. Railway deploys the official PostgreSQL Docker image
3. Connection variables are auto-created: `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`

### 7.2 Add PostgreSQL via CLI

```bash
railway add --database postgres
```

### 7.3 Connect from FastAPI Service

Use a variable reference in your FastAPI service:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Or manually copy the connection string from the PostgreSQL service's Variables tab.

### 7.4 PostgreSQL Features on Railway

- **SSL enabled** by default
- **TCP Proxy** for external connections (additional cost)
- **Extensions:** PostGIS, pgvector, TimescaleDB available
- **Backups:** Native backup support
- **Monitoring:** Grafana + Prometheus templates available
- **Version:** PostgreSQL 15/16/17 available

### 7.5 Running Migrations

```bash
# Via CLI (runs command with Railway env vars)
railway run alembic upgrade head

# Or set as pre-deploy command in railway.toml:
# [deploy]
# preDeployCommand = ["alembic upgrade head"]
```

---

## 8. GitHub Auto-Deploy Setup

### 8.1 Connect Repository

1. In Railway dashboard, create a **New Service** → **Deploy from GitHub Repo**
2. Select your repository (Railway requests GitHub permissions)
3. Choose the branch to deploy from (default: `main`)

### 8.2 Auto-Deploy Behavior

- **Every push** to the configured branch triggers a new deployment
- Railway builds the Docker image and deploys automatically
- Zero-downtime deployments (new container starts, health check passes, traffic switches)

### 8.3 Configure Deploy Branch

In Service Settings → **Source** section → set the trigger branch.

### 8.4 Wait for CI

Enable **"Wait for CI"** in Service Settings to ensure Railway only deploys after GitHub Actions pass:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/
```

### 8.5 Disable Auto-Deploy

In Service Settings → disconnect the GitHub repo, then use manual deploy via CLI:
```bash
railway up
```

### 8.6 PR Preview Environments

Enable **PR Environments** in Project Settings → Environments to get automatic preview deployments for pull requests.

---

## 9. Railway CLI Reference

### 9.1 Installation

```bash
# Windows (Scoop)
scoop install railway

# macOS (Homebrew)
brew install railway

# npm (cross-platform)
npm i -g @railway/cli

# Shell script (macOS/Linux/WSL)
bash <(curl -fsSL cli.new)
```

### 9.2 Authentication

```bash
railway login              # Opens browser for OAuth
railway login --browserless  # Prints code for manual auth
railway whoami             # Verify logged-in user
```

### 9.3 Project Setup

```bash
railway init               # Create new project
railway link               # Link existing directory to project
railway status             # Show project/service info
```

### 9.4 Deployment

```bash
railway up                 # Deploy current directory
railway up --detach        # Deploy without streaming logs
railway redeploy           # Redeploy latest
railway down               # Remove latest deployment
railway logs               # Stream live logs
railway logs --build       # View build logs
```

### 9.5 CI/CD Token Auth

For automated pipelines, use tokens instead of interactive login:

```bash
# Project-level token (set in Railway dashboard → project settings)
RAILWAY_TOKEN=xxx railway up

# Account-level token
RAILWAY_API_TOKEN=xxx railway up
```

### 9.6 SSH into Container

```bash
railway ssh                # Interactive shell in running container
```

### 9.7 Connect to Database

```bash
railway connect            # Opens database shell (psql for PostgreSQL)
```

---

## 10. Custom Domains

### 10.1 Railway-Generated Domain

1. Open service → **Settings** → **Networking**
2. Click **"Generate Domain"**
3. You get a URL like `your-service-abc123.up.railway.app`

### 10.2 Custom Domain Setup

1. In service **Settings** → **Networking** → **Custom Domain**
2. Enter your domain: `api.yourdomain.com`
3. Railway provides a **CNAME** target (e.g., `your-service.railway.app`)
4. At your DNS provider, add:
   ```
   Type: CNAME
   Name: api
   Value: your-service.railway.app
   ```
5. Railway automatically provisions **SSL/TLS** (Let's Encrypt)

**Via CLI:**
```bash
railway domain api.yourdomain.com
```

### 10.3 Notes

- SSL certificates are auto-provisioned and renewed
- DNS propagation can take up to 48 hours
- Both root domains and subdomains are supported
- Multiple custom domains can be added to one service

---

## 11. Complete Deployment Workflow

### 11.1 First-Time Setup (Dashboard)

```
1. Sign up at railway.app with GitHub
2. Create New Project
3. Add PostgreSQL database service
4. Add FastAPI service (Deploy from GitHub → select repo)
5. Set root directory to /backend (if monorepo)
6. Railway auto-detects Dockerfile and builds
7. Configure environment variables (see Section 5)
8. Create volume mounted at /data/chroma_db
9. Set RAILWAY_RUN_UID=0 (for volume permissions)
10. Generate public domain or add custom domain
11. Verify /health endpoint responds
12. Run migrations: railway run alembic upgrade head
```

### 11.2 First-Time Setup (CLI)

```bash
# 1. Install and login
npm i -g @railway/cli
railway login

# 2. Create project
cd backend
railway init

# 3. Add PostgreSQL
railway add --database postgres

# 4. Set variables
railway variable set OPENAI_API_KEY=sk-xxx
railway variable set CHROMA_DB_PATH=/data/chroma_db
railway variable set ENVIRONMENT=production
railway variable set RAILWAY_RUN_UID=0

# 5. Add volume
railway volume add --mount-path /data/chroma_db

# 6. Deploy
railway up

# 7. Generate domain
railway domain

# 8. Run migrations
railway run alembic upgrade head

# 9. Check logs
railway logs
```

### 11.3 Ongoing Deployment (after GitHub connected)

```
git add .
git commit -m "feat: add new endpoint"
git push origin main
# → Railway auto-builds and deploys (zero-downtime)
```

---

## 12. Project Structure for Railway

```
ai_engineer_poc_orchestrator/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # Settings (reads env vars)
│   │   ├── api/               # Route handlers
│   │   ├── models/            # SQLAlchemy models
│   │   ├── services/          # Business logic + Vanna/ChromaDB
│   │   └── utils/             # Helpers
│   ├── tests/
│   ├── Dockerfile             # ← Production Dockerfile
│   ├── railway.toml           # ← Railway config-as-code
│   ├── requirements.txt
│   └── alembic/               # Database migrations
├── frontend/                  # Separate Railway service
├── database/
└── .github/
    └── workflows/
        └── ci.yml             # CI pipeline (Wait for CI)
```

---

## 13. Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails on ChromaDB | Ensure `build-essential`, `gcc` are in build stage |
| Volume data lost on deploy | Data must be written at **runtime**, not build time |
| Permission denied on volume | Set `RAILWAY_RUN_UID=0` in env vars |
| Database connection refused | Use `${{Postgres.DATABASE_URL}}` variable reference |
| Port not accessible | Ensure app binds to `0.0.0.0:${PORT}` |
| Health check failing | Verify `/health` endpoint returns 200 within timeout |
| DNS not resolving | Allow 24-48h for propagation; verify CNAME record |
| Internal hostname not resolving | Use `.railway.internal` hostnames only at runtime, not in build |

---

## 14. Cost Estimate for DataChat BI POC

| Service | Estimated Monthly Cost |
|---------|----------------------|
| FastAPI backend (0.5 vCPU, 512 MB RAM) | ~$5 |
| PostgreSQL (0.25 vCPU, 256 MB RAM) | ~$3 |
| ChromaDB volume (1 GB) | ~$0.25 |
| Network egress (light usage) | ~$0 |
| **Total (Hobby plan)** | **~$5-$10/month** |

The Hobby plan's $5 included usage covers most of this for a low-traffic POC.