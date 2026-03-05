"""
FastAPI main application - DataChat BI Platform
Hybrid Architecture: Vanna RAG + MCP Server + Multi-Provider LLM
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    logger.info("=== DATACHAT BI PLATFORM STARTUP ===")
    logger.info(f"Architecture: Hybrid (Vanna RAG + MCP Server + Multi-Provider LLM)")
    logger.info(f"Default LLM Provider: {settings.default_llm_provider}")
    logger.info("Database: Awaiting manual connection from Settings page")
    
    # Reset any stale DB connection state from previous runs
    from app.services.mcp_manager import mcp_postgres_client
    if mcp_postgres_client._connected:
        try:
            mcp_postgres_client.shutdown()
        except Exception:
            pass
    mcp_postgres_client._connected = False
    mcp_postgres_client._use_fallback = False
    mcp_postgres_client._direct_conn = None
    
    from app.api.database import _current_connection
    _current_connection.update({
        "source_type": None, "host": None, "port": None,
        "username": None, "password": None, "connected": False,
        "active_database": None, "enabled_databases": [],
        "project_ref": None, "service_role_key": None
    })
    logger.info("Database connection state reset - awaiting manual setup")
    
    # Initialize LLM providers
    try:
        from app.services.llm_provider import get_llm_provider_manager
        llm_manager = get_llm_provider_manager()
        logger.info(f"LLM Providers available: {llm_manager.list_available_providers()}")
    except Exception as e:
        logger.error(f"LLM Provider initialization failed: {e}")

    # Seed admin account on startup (if users table is empty)
    try:
        if settings.system_database_url:
            from app.database import get_system_session_factory
            from app.services.auth_service import seed_admin_user
            SessionFactory = get_system_session_factory()
            db = SessionFactory()
            try:
                seed_admin_user(db)
            finally:
                db.close()
        else:
            logger.info("SYSTEM_DATABASE_URL not configured — skipping seed admin")
    except Exception as e:
        logger.error(f"Seed admin creation failed: {e}")

    yield
    
    logger.info("=== SHUTDOWN ===")
    from app.services.mcp_manager import mcp_postgres_client
    if mcp_postgres_client._connected:
        mcp_postgres_client.shutdown()


app = FastAPI(
    title="DataChat BI Platform API",
    description="Natural Language to SQL - Hybrid Architecture with Multi-Provider LLM",
    version="0.5.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Chat Router (Fase 03)
from app.api.chat import router as chat_router
app.include_router(chat_router)

# Include Charts Router (Fase 05)
from app.api.charts import router as charts_router
app.include_router(charts_router)

# Include Database Router
from app.api.database import router as database_router
app.include_router(database_router)

# Include Auth Router
from app.api.auth import router as auth_router
app.include_router(auth_router)

# Include Admin Router
from app.api.admin import router as admin_router
app.include_router(admin_router)

# Include Knowledge Base Router
from app.api.knowledge import router as knowledge_router
app.include_router(knowledge_router)

# Include Views Router
from app.api.views import router as views_router
app.include_router(views_router)

# Include Brand Config Router
from app.api.brand import router as brand_router
app.include_router(brand_router)


# ============================================================
# MODELS
# ============================================================

class QueryRequest(BaseModel):
    question: str
    llm_provider: Optional[str] = None

class QueryResponse(BaseModel):
    question: str
    sql: str
    rows: List[Dict[str, Any]]
    row_count: int
    execution_time_ms: float
    success: bool
    error: Optional[str] = None
    schema_source: Optional[str] = None
    examples_source: Optional[str] = None
    executed_via: Optional[str] = None
    llm_provider: Optional[str] = None

class SeedResponse(BaseModel):
    success: bool
    examples_trained: int
    message: str


# ============================================================
# ROUTES
# ============================================================

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "datachat-bi-platform", "version": "0.5.0"}


@app.get("/api/internal/architecture")
async def architecture_info():
    """Mostra architettura del sistema"""
    from app.services.mcp_manager import mcp_postgres_client
    from app.services.vanna_service import get_vanna_service
    from app.services.llm_provider import get_llm_provider_manager
    
    service = get_vanna_service()
    stats = service.get_training_stats()
    llm_manager = get_llm_provider_manager()
    
    return {
        "architecture": "Hybrid Vanna RAG + MCP Server + Multi-Provider LLM",
        "version": "0.3.0",
        "components": {
            "schema_provider": "MCP PostgreSQL Server (LIVE schema)",
            "rag_examples": "ChromaDB Vector Store",
            "embeddings": "Azure OpenAI text-embedding-3-large",
            "llm_providers": llm_manager.list_available_providers(),
            "default_llm": settings.default_llm_provider,
            "sql_executor": "MCP PostgreSQL Server"
        },
        "mcp_server": {
            "active": not mcp_postgres_client._use_fallback,
            "mode": "MCP Server" if not mcp_postgres_client._use_fallback else "Direct psycopg2 (fallback)"
        },
        "training_stats": stats,
        "api_endpoints": {
            "chat": "/api/chat/query (POST) - Main chat endpoint",
            "history": "/api/chat/history/{session_id} (GET) - Get session history",
            "providers": "/api/chat/providers (GET) - List LLM providers"
        },
        "flow": [
            "1. User question arrives at /api/chat/query",
            "2. Select LLM provider (claude/azure)",
            "3. Get LIVE schema from MCP Server",
            "4. Search similar examples in ChromaDB (RAG)",
            "5. Build prompt with schema + examples",
            "6. LLM generates SQL",
            "7. Execute SQL via MCP Server",
            "8. Generate NL response",
            "9. Return results to user"
        ]
    }


@app.get("/api/internal/mcp-status")
async def mcp_status():
    """Stato del server MCP"""
    from app.services.mcp_manager import mcp_postgres_client
    
    if not mcp_postgres_client._connected:
        mcp_postgres_client.start()
    
    tables = mcp_postgres_client.list_tables()
    
    return {
        "connected": mcp_postgres_client._connected,
        "mode": "MCP Server" if not mcp_postgres_client._use_fallback else "Direct (fallback)",
        "tables": tables,
        "capabilities": ["query", "list_tables", "describe_table", "get_schema_ddl"]
    }


@app.get("/api/internal/schema")
async def get_live_schema():
    """Ottieni schema LIVE dal database via MCP"""
    from app.services.vanna_service import get_vanna_service
    
    service = get_vanna_service()
    tables = service.get_tables_from_mcp()
    schema_ddl = service.get_schema_from_mcp()
    
    return {
        "source": "MCP Server (LIVE)",
        "tables": tables,
        "ddl": schema_ddl
    }


@app.get("/api/internal/db-status")
async def db_status():
    """Check database status"""
    from app.services.mcp_manager import mcp_postgres_client
    
    try:
        tables = mcp_postgres_client.list_tables()
        row_count = 0
        if "orders" in tables:
            result = mcp_postgres_client.execute_query("SELECT COUNT(*) as cnt FROM public.orders")
            row_count = int(result[0]["cnt"]) if result else 0
        
        return {
            "status": "connected",
            "connection_type": "MCP Server" if not mcp_postgres_client._use_fallback else "Direct",
            "tables": tables,
            "orders_row_count": row_count
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/internal/seed-training", response_model=SeedResponse)
async def seed_training():
    """Popola ChromaDB con esempi di training"""
    try:
        from app.services.training_seed import seed_training_data
        count = seed_training_data()
        return SeedResponse(success=True, examples_trained=count, message=f"Training completato: {count} esempi")
    except Exception as e:
        logger.error(f"Seed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/internal/test-vanna", response_model=QueryResponse)
async def test_vanna(request: QueryRequest):
    """
    Text-to-SQL endpoint (legacy, usa /api/chat/query per production)
    """
    try:
        from app.services.vanna_service import get_vanna_service
        
        provider = request.llm_provider or settings.default_llm_provider
        service = get_vanna_service(llm_provider=provider)
        
        if not service.is_initialized():
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        result = service.generate_and_execute(request.question, llm_provider=provider)
        return QueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/internal/vanna-status")
async def vanna_status():
    """Stato del servizio Vanna ibrido"""
    try:
        from app.services.vanna_service import get_vanna_service
        from app.services.llm_provider import get_llm_provider_manager
        
        service = get_vanna_service()
        stats = service.get_training_stats()
        llm_manager = get_llm_provider_manager()
        
        return {
            "initialized": service.is_initialized(),
            "type": "Hybrid (Vanna RAG + MCP + Multi-Provider LLM)",
            "training_stats": stats,
            "llm_providers": llm_manager.list_available_providers()
        }
    except Exception as e:
        return {"initialized": False, "error": str(e)}