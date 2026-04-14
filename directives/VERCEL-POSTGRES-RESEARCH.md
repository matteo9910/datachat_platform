# Vercel Postgres / Neon Setup – Technical Research Report

> **Date:** 2026-03-04  
> **Purpose:** System database for auth/sessions/audit in DataChat BI Platform  
> **Backend:** FastAPI on Railway  
> **Target:** Free tier, minimal ops

---

## 1. Current State: Vercel Postgres → Neon

**Vercel Postgres no longer exists as a standalone service.** In December 2024, all Vercel Postgres databases were migrated to **Neon** (neon.tech). New projects must use **Neon directly** or via the **Vercel Marketplace integration**.

**Recommendation:** Sign up directly at [neon.tech](https://neon.tech) for a free account. This gives full control over the database and avoids Vercel marketplace intermediation. The Vercel Marketplace integration is mainly useful for auto-injecting env vars into Vercel-hosted frontends — not needed for a Railway backend.

---

## 2. Neon Free Tier Limits (2026)

| Resource | Free Tier Limit |
|---|---|
| **Projects** | Up to 20 |
| **Storage per project** | 0.5 GB |
| **Total storage** | 5 GB across projects |
| **Compute** | 100 CU-hours/month per project |
| **Autoscaling** | Up to 2 CU (8 GB RAM) |
| **Branches per project** | Up to 10 |
| **Monitoring retention** | 1 day |
| **Network transfer** | 5 GB public |
| **Scale-to-zero** | Yes (suspends when idle) |
| **Point-in-time recovery** | 6 hours |

**Assessment for system DB (auth/sessions/audit):**
- 0.5 GB storage is sufficient for auth tables, session tokens, and audit logs for a POC
- 100 CU-hours/month ≈ ~416 hours at 0.25 CU, or ~100 hours at 1 CU — adequate for dev/POC workloads
- Scale-to-zero means the DB sleeps when idle; first connection after sleep has ~500ms cold start
- **Connection limit:** Neon's `max_connections` depends on compute size. At minimum (0.25 CU): ~112 connections. With PgBouncer pooling: up to 10,000 concurrent connections.

---

## 3. Connection String Format and SSL Requirements

### Connection String Format

Neon provides two types of connection strings:

**Direct connection (for migrations):**
```
postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
```

**Pooled connection (for application runtime — via PgBouncer):**
```
postgresql://<user>:<password>@<endpoint>-pooler.neon.tech/<dbname>?sslmode=require
```

The `-pooler` suffix in the hostname routes through PgBouncer.

### SSL Requirements

- **Neon requires SSL for ALL connections** — non-SSL connections are rejected
- Minimum: `sslmode=require` (encrypts connection, no cert verification)
- Recommended: `sslmode=require&channel_binding=require` (adds SCRAM-SHA-256-PLUS protection)
- For maximum security: `sslmode=verify-full` (requires root CA cert)
- **No client certificates needed** — Neon uses password-based auth over SSL

### Example Connection String

```
postgresql://alex:AbC123dEf@ep-cool-darkness-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
```

---

## 4. Connecting from Railway-Hosted FastAPI Backend

### Environment Variables

In your Railway service, set these environment variables:

```env
# For application runtime (pooled — higher concurrency)
DATABASE_URL=postgresql://<user>:<password>@<endpoint>-pooler.neon.tech/<dbname>?sslmode=require

# For migrations (direct — avoids PgBouncer issues with DDL)
DATABASE_URL_DIRECT=postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
```

### SQLAlchemy Configuration (Synchronous)

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Handles Neon scale-to-zero reconnection
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```

### SQLAlchemy Configuration (Async with asyncpg)

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

# Convert postgresql:// to postgresql+asyncpg://
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()
```

**Note on asyncpg + sslmode:** asyncpg does not support the `sslmode` query parameter directly in the URL. You may need to strip `?sslmode=require` from the URL and instead pass `ssl="require"` via `connect_args`:

```python
import ssl as ssl_module

ssl_context = ssl_module.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl_module.CERT_NONE

engine = create_async_engine(
    ASYNC_DATABASE_URL.split("?")[0],  # strip query params
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": ssl_context},
)
```

### psycopg2 Direct Connection (Simple)

```python
import os
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
```

This works out of the box since psycopg2 natively supports `sslmode=require` in the connection string.

---

## 5. Migration Strategy with Alembic

### Setup

```bash
pip install sqlalchemy alembic psycopg2-binary python-dotenv
alembic init alembic
```

### Configure alembic/env.py

```python
# alembic/env.py
import os
import dotenv
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load .env
dotenv.load_dotenv()

config = context.config

# Use DIRECT connection for migrations (not pooled)
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL_DIRECT", ""))

# Import your models' Base
from app.models import Base
target_metadata = Base.metadata
```

### Key Migration Commands

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current migration state
alembic current

# Show migration history
alembic history
```

### Critical: Use Direct Connection for Migrations

**Always use the direct (non-pooled) connection string for running migrations.** PgBouncer in transaction pooling mode can cause issues with DDL statements, advisory locks, and multi-statement transactions that Alembic relies on.

### Running Migrations in Railway

Option A — **Run on deploy (recommended for POC):**
Add to Railway start command:
```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Option B — **Run manually via Railway CLI:**
```bash
railway run alembic upgrade head
```

Option C — **Run on FastAPI startup (lifespan event):**
```python
from contextlib import asynccontextmanager
from alembic.config import Config
from alembic import command

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on startup
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield

app = FastAPI(lifespan=lifespan)
```

---

## 6. Neon vs Regular PostgreSQL: Key Differences

| Feature | Neon | Regular PostgreSQL |
|---|---|---|
| **Architecture** | Serverless, separates compute and storage | Single-server, coupled |
| **Scale-to-zero** | Yes — computes suspend on idle | No — always running |
| **Cold start** | ~300-500ms on first connection after sleep | None |
| **Branching** | Instant copy-on-write DB branches | Manual pg_dump/restore |
| **Storage** | Bottomless (object-storage backed) | Disk-limited |
| **Connection pooling** | Built-in PgBouncer | Must self-manage |
| **Extensions** | Most common ones supported | All extensions |
| **Replication** | Logical replication supported | Full replication options |
| **Backups** | Automatic PITR (6h free, 30d+ paid) | Manual pg_dump |
| **PostgreSQL versions** | 14, 15, 16 | Any version |
| **Max connections** | 112-4000 (compute dependent) + pooling | Configurable |

**Practical Implications for this POC:**
- Cold start on first connection after idle is a real consideration — use `pool_pre_ping=True` in SQLAlchemy
- Branching is extremely useful for testing migrations before applying to main
- Connection pooling is built-in, reducing backend complexity
- Standard PostgreSQL syntax/features work — no proprietary SQL dialect

---

## 7. Step-by-Step Setup Instructions

### A. Create the Neon Database

1. Go to [console.neon.tech](https://console.neon.tech/) and sign up (GitHub/Google/email)
2. Click **"New Project"**
3. Set:
   - **Project name:** `datachat-system-db`
   - **Region:** `us-east-2` (or closest to your Railway deployment)
   - **PostgreSQL version:** `16`
4. A default database `neondb` with role `neondb_owner` is created automatically
5. Copy both connection strings from the **Connect** dialog:
   - **Pooled** (for app runtime)
   - **Direct** (for migrations)

### B. Configure Railway Backend

1. In Railway project settings → Variables, add:
   ```
   DATABASE_URL=postgresql://neondb_owner:<password>@<endpoint>-pooler.<region>.aws.neon.tech/neondb?sslmode=require
   DATABASE_URL_DIRECT=postgresql://neondb_owner:<password>@<endpoint>.<region>.aws.neon.tech/neondb?sslmode=require
   ```

2. Also add to your local `.env` file for development

### C. Set Up Alembic in Backend Project

```bash
cd backend
pip install sqlalchemy alembic psycopg2-binary python-dotenv
alembic init alembic
```

Edit `alembic/env.py` to load `DATABASE_URL_DIRECT` (see section 5 above).

### D. Define System Models

Create models for auth/sessions/audit:

```python
# app/models/system.py
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(255))
    details = Column(JSON)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### E. Generate and Apply Initial Migration

```bash
alembic revision --autogenerate -m "create_system_tables"
alembic upgrade head
```

### F. Verify Connection

```python
# Quick test script
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone())
cur.close()
conn.close()
```

---

## 8. Cost Summary

| Component | Cost |
|---|---|
| Neon Free Tier | $0 |
| Railway (if on free tier) | $0 |
| SSL | Included (mandatory) |
| **Total** | **$0** |

Free tier is sufficient for POC/development. If the project goes to production, Neon's Launch plan starts at $19/month with 10 GB storage and 300 CU-hours.

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Cold start latency (~500ms) | Use `pool_pre_ping=True`; accept for POC |
| 0.5 GB storage limit | Monitor via Neon dashboard; vacuum regularly; sufficient for system tables |
| 100 CU-hours/month | Reduce compute to 0.25 CU to extend hours; scale-to-zero helps |
| Pooled connection + DDL | Always use direct connection for migrations |
| asyncpg sslmode incompatibility | Strip sslmode from URL, use `connect_args={"ssl": ssl_context}` |
| Neon downtime | Accept for POC; Neon has 99.95% SLA on paid plans |