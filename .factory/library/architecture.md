# Architecture

Architectural decisions, patterns, and conventions discovered during the mission.

**What belongs here:** Design decisions, module responsibilities, data flow patterns, integration points.

---

## CRITICAL: Database-Agnostic Client DB

The application is fully database-agnostic regarding the client database. Supabase with dim_products/fact_orders/inventory_snapshot is ONLY a test database used during development.

**Rules:**
- NO hardcoded references to specific table names, column names, or schema structures in application code
- All features (text-to-SQL, charts, KB, views, write operations, dashboard filters) dynamically discover and adapt to whatever schema the connected DB has
- The Setup Wizard handles DB connection + table selection — all features use this dynamic schema discovery
- Write operations whitelist is dynamically populated from connected DB schema
- Dashboard filters are dynamically generated from query result column types

## Two-Database Architecture

- **System DB (Neon)**: All application metadata — users, roles, sessions, audit_log, brand_config, write_whitelist, kb_pairs, instructions, view_metadata, dashboard_metadata. FIXED schema controlled by us via Alembic migrations.
- **Client DB (any PostgreSQL)**: Customer's business data with UNKNOWN schema. Connected via Setup Wizard. Accessed via MCP or direct connection. NEVER polluted with system tables.

System tables MUST NOT be created in the client DB to avoid polluting the schema browser.

## Backend Architecture

Pattern: Layered (API → Services → Data Access)
- `backend/app/api/` — FastAPI routers (endpoints)
- `backend/app/services/` — Business logic (chat_orchestrator, vanna_service, llm_provider, chart_service, mcp_manager)
- `backend/app/config.py` — Pydantic settings loaded from .env
- `backend/app/main.py` — App factory, CORS, middleware, router registration

## Frontend Architecture

Pattern: Component-based SPA with Zustand state
- `frontend/src/components/` — UI components organized by feature (Chat, Charts, Dashboard, Schema, Settings, SetupWizard)
- `frontend/src/api/` — API clients (chatApi.ts, chartsApi.ts, databaseApi.ts)
- `frontend/src/store/` — Zustand stores (appStore.ts)
- `frontend/src/pages/` — Page-level components

## LLM Provider Abstraction

Strategy pattern in `llm_provider.py`:
- `LLMProviderManager` manages provider instances
- Each provider implements common interface for SQL generation
- Providers: Claude (OpenRouter), GPT-4.1 (Azure), GPT-5.2 (Azure)
- All new features that generate SQL MUST work with all providers

## Deployment Architecture

- Frontend → Vercel (static build, `npm run build` → dist/)
- Backend → Railway (Docker container, Dockerfile in backend/)
- System DB → Neon PostgreSQL (free tier, pooled connection)
- Client DB → Supabase PostgreSQL (existing, pooler port 6543)
- ChromaDB → Embedded in Railway container (volume /data/chroma_db)

## Testing Patterns

### System DB Tests with SQLite
Backend tests use SQLite in-memory database with a JSONB→TEXT compilation override for testing PostgreSQL-specific system models without a live Neon connection. The pattern is in `backend/tests/test_system_db.py`:
```python
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"
```
Future workers building on system DB models should reuse this test fixture pattern.

### Auth Middleware
Auth dependencies (`get_current_user`, `require_role`) are implemented as FastAPI dependencies in `backend/app/services/auth_middleware.py` (not ASGI middleware). This is the correct pattern for FastAPI — use Depends() injection rather than ASGI middleware for request-level auth.

## Known Technical Debt
- `backend/app/models/database.py` uses deprecated `from sqlalchemy.ext.declarative import declarative_base`. The newer system models in `system.py` correctly use `from sqlalchemy.orm import declarative_base`. Should be updated when touching that file.
- `backend/app/config.py` mixes type hint styles: `str | None` (PEP 604) and `Optional[str]` (typing module). Both work on Python 3.14.2 but inconsistent.
