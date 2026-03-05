"""
Database API endpoints - Gestione connessione e schema database
Supporta PostgreSQL locale e Supabase cloud
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

from app.services.mcp_manager import mcp_postgres_client
from app.services.mcp_supabase_client import mcp_supabase_client
from app.services.supabase_oauth import supabase_oauth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database", tags=["database"])

# Tipo di sorgente dati
DataSourceType = Literal["postgres", "supabase"]

# Stato connessione globale - memorizza i parametri usati per connettersi
_current_connection = {
    "source_type": None,  # "postgres" o "supabase"
    "host": None,
    "port": None,
    "username": None,
    "password": None,
    "connected": False,
    "active_database": None,
    "enabled_databases": [],
    # Supabase specific
    "project_ref": None,
    "service_role_key": None
}

# Configurazioni salvate per switch rapido
_saved_connections = {
    "postgres": None,
    "supabase": None
}


# ============================================================
# MODELS
# ============================================================

class ConnectionParams(BaseModel):
    """Parametri per connessione PostgreSQL locale"""
    host: str = Field(..., description="Host PostgreSQL", example="localhost")
    port: int = Field(5432, description="Porta PostgreSQL")
    username: str = Field(..., description="Username", example="datachat_user")
    password: str = Field(..., description="Password")


class SupabaseConnectionParams(BaseModel):
    """Parametri per connessione Supabase"""
    project_ref: str = Field(..., description="Project Reference Supabase", example="vdtdizltnesotxbbdjpq")
    service_role_key: Optional[str] = Field(None, description="Service Role Key (per REST API)")
    personal_access_token: Optional[str] = Field(None, description="Personal Access Token (per MCP nativo)")


class SupabasePasswordConnectionParams(BaseModel):
    """Parametri per connessione Supabase con password database"""
    project_ref: str = Field(..., description="Project Reference Supabase")
    db_password: str = Field(..., description="Password del database Supabase")
    region: Optional[str] = Field(None, description="Regione del progetto (es. eu-west-1)")


class ConnectionStringParams(BaseModel):
    """Parametri per connessione con connection string diretta"""
    connection_string: str = Field(..., description="Connection string PostgreSQL completa")
    project_ref: Optional[str] = Field(None, description="Project Reference (opzionale, per identificazione)")


class SelectDatabaseRequest(BaseModel):
    """Request per selezionare database attivo"""
    database: str = Field(..., description="Nome database da attivare")


class ConnectionStatus(BaseModel):
    connected: bool
    source_type: Optional[str] = None  # "postgres" o "supabase"
    active_database: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    project_ref: Optional[str] = None  # Per Supabase
    message: str
    using_mcp: bool = False
    enabled_databases: List[str] = []


class DataSourceInfo(BaseModel):
    """Info su una sorgente dati disponibile"""
    type: str
    name: str
    description: str
    icon: str
    configured: bool = False
    connected: bool = False


class DatabaseInfo(BaseModel):
    name: str
    size: Optional[str] = None
    tables_count: int = 0


class TableInfo(BaseModel):
    name: str
    schema_name: str = "public"
    row_count: Optional[int] = None
    columns: List[Dict[str, Any]] = []
    type: str = "table"  # "table" or "view"


class SchemaResponse(BaseModel):
    database: str
    tables: List[TableInfo]


class TablePreviewResponse(BaseModel):
    table_name: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int
    preview_limit: int = 50


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/sources", response_model=List[DataSourceInfo])
async def get_available_sources():
    """Lista le sorgenti dati disponibili"""
    global _current_connection, _saved_connections
    
    sources = [
        DataSourceInfo(
            type="postgres",
            name="PostgreSQL",
            description="Database PostgreSQL locale o remoto",
            icon="database",
            configured=_saved_connections.get("postgres") is not None,
            connected=_current_connection.get("source_type") == "postgres" and _current_connection.get("connected", False)
        ),
        DataSourceInfo(
            type="supabase",
            name="Supabase",
            description="PostgreSQL cloud su Supabase",
            icon="cloud",
            configured=_saved_connections.get("supabase") is not None,
            connected=_current_connection.get("source_type") == "supabase" and _current_connection.get("connected", False)
        )
    ]
    return sources


@router.get("/status", response_model=ConnectionStatus)
async def get_connection_status():
    """Verifica stato connessione al database"""
    global _current_connection
    
    try:
        source_type = _current_connection.get("source_type")
        is_connected = _current_connection.get("connected", False)
        
        # Check if mcp_postgres_client is connected (used for both postgres and supabase via connection-string)
        postgres_connected = mcp_postgres_client._connected if hasattr(mcp_postgres_client, '_connected') else False
        
        # Check PostgreSQL connection
        if source_type == "postgres" and postgres_connected and is_connected:
            return ConnectionStatus(
                connected=True,
                source_type="postgres",
                active_database=_current_connection.get("active_database"),
                host=_current_connection.get("host"),
                port=_current_connection.get("port"),
                username=_current_connection.get("username"),
                message="PostgreSQL - " + (f"Database: {_current_connection.get('active_database')}" if _current_connection.get('active_database') else "Seleziona un database"),
                using_mcp=not mcp_postgres_client._use_fallback if hasattr(mcp_postgres_client, '_use_fallback') else False,
                enabled_databases=_current_connection.get("enabled_databases", [])
            )
        # Check Supabase connection (via connection-string uses mcp_postgres_client)
        elif source_type == "supabase" and postgres_connected and is_connected:
            return ConnectionStatus(
                connected=True,
                source_type="supabase",
                active_database=_current_connection.get("active_database", "postgres"),
                host=_current_connection.get("host"),
                port=_current_connection.get("port"),
                username=_current_connection.get("username"),
                project_ref=_current_connection.get("project_ref"),
                message=f"Supabase - Database: {_current_connection.get('active_database', 'postgres')}",
                using_mcp=not mcp_postgres_client._use_fallback if hasattr(mcp_postgres_client, '_use_fallback') else False,
                enabled_databases=_current_connection.get("enabled_databases", ["postgres"])
            )
        else:
            return ConnectionStatus(
                connected=False,
                message="Non connesso. Seleziona una sorgente dati nelle Impostazioni."
            )
    except Exception as e:
        logger.error(f"Connection status error: {e}")
        _current_connection["connected"] = False
        return ConnectionStatus(connected=False, message=f"Errore: {str(e)}")


@router.post("/connect", response_model=ConnectionStatus)
async def connect_with_params(params: ConnectionParams):
    """Connetti a PostgreSQL locale"""
    global _current_connection, _saved_connections
    
    try:
        # Disconnetti eventuali connessioni esistenti
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        connection_string = f"postgresql://{params.username}:{params.password}@{params.host}:{params.port}/postgres"
        
        logger.info(f"Connecting to PostgreSQL at {params.host}:{params.port}")
        
        mcp_postgres_client.connect_with_string(connection_string)
        result = mcp_postgres_client.execute_query("SELECT version() as ver")
        
        _current_connection = {
            "source_type": "postgres",
            "host": params.host,
            "port": params.port,
            "username": params.username,
            "password": params.password,
            "connected": True,
            "active_database": None,
            "enabled_databases": [],
            "project_ref": None,
            "service_role_key": None
        }
        
        # Salva configurazione per switch rapido
        _saved_connections["postgres"] = {
            "host": params.host,
            "port": params.port,
            "username": params.username,
            "password": params.password
        }
        
        logger.info(f"Connected to PostgreSQL at {params.host}:{params.port}")
        
        return ConnectionStatus(
            connected=True,
            source_type="postgres",
            active_database=None,
            host=params.host,
            port=params.port,
            username=params.username,
            message="Connesso a PostgreSQL! Seleziona i database da abilitare.",
            using_mcp=not mcp_postgres_client._use_fallback,
            enabled_databases=[]
        )
    except Exception as e:
        logger.error(f"PostgreSQL connection error: {e}")
        _current_connection["connected"] = False
        raise HTTPException(status_code=500, detail=f"Connessione PostgreSQL fallita: {str(e)}")


@router.post("/connect/connection-string", response_model=ConnectionStatus)
async def connect_with_connection_string(params: ConnectionStringParams):
    """
    Connetti usando una connection string PostgreSQL diretta.
    Approccio UNIVERSALE - funziona con qualsiasi database PostgreSQL.
    L'utente copia la connection string dalla dashboard del suo provider.
    """
    global _current_connection, _saved_connections
    
    try:
        # Disconnetti eventuali connessioni esistenti
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        # Valida formato base
        if not params.connection_string.startswith("postgresql://"):
            raise HTTPException(status_code=400, detail="La connection string deve iniziare con postgresql://")
        
        logger.info(f"Connecting with direct connection string: {params.connection_string[:50]}...")
        
        # Decodifica la connection string se contiene caratteri URL-encoded
        from urllib.parse import unquote
        decoded_connection_string = unquote(params.connection_string)
        logger.info(f"Decoded connection string: {decoded_connection_string[:50]}...")
        
        # Connetti usando la connection string decodificata
        mcp_postgres_client.connect_with_string(decoded_connection_string)
        tables = mcp_postgres_client.list_tables()
        using_mcp = not mcp_postgres_client._use_fallback
        
        # Estrai info dalla connection string decodificata
        from urllib.parse import urlparse
        parsed = urlparse(decoded_connection_string)
        username = parsed.username or "unknown"
        password = parsed.password or ""
        host = parsed.hostname or "unknown"
        port = parsed.port or 5432
        database = parsed.path.lstrip('/') or "postgres"
        
        _current_connection = {
            "source_type": "supabase",
            "host": host,
            "port": int(port) if isinstance(port, str) else port,
            "username": username,
            "password": password,
            "connected": True,
            "active_database": database,
            "enabled_databases": [database],
            "project_ref": params.project_ref,
            "using_mcp": using_mcp
        }
        
        _saved_connections["supabase"] = {
            "connection_string": params.connection_string,
            "project_ref": params.project_ref
        }
        
        logger.info(f"Connected via connection string: {len(tables)} tables found")
        
        return ConnectionStatus(
            connected=True,
            source_type="supabase",
            active_database=database,
            project_ref=params.project_ref,
            host=host,
            port=int(port) if isinstance(port, str) else port,
            username=username,
            message=f"Connesso! {len(tables)} tabelle trovate",
            using_mcp=using_mcp,
            enabled_databases=[database]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection string error: {e}")
        _current_connection["connected"] = False
        raise HTTPException(status_code=500, detail=f"Connessione fallita: {str(e)}")


@router.post("/connect/supabase-password", response_model=ConnectionStatus)
async def connect_supabase_with_password(params: SupabasePasswordConnectionParams):
    """Connetti a Supabase usando project_ref e password database (via pooler)"""
    global _current_connection, _saved_connections
    
    try:
        # Disconnetti eventuali connessioni esistenti
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        # Determina la regione del pooler
        region = params.region or "eu-central-1"
        pooler_host = f"aws-0-{region}.pooler.supabase.com"
        pooler_user = f"postgres.{params.project_ref}"
        connection_string = f"postgresql://{pooler_user}:{params.db_password}@{pooler_host}:6543/postgres"
        
        logger.info(f"Connecting to Supabase pooler for project: {params.project_ref} in region: {region}")
        
        mcp_postgres_client.connect_with_string(connection_string)
        tables = mcp_postgres_client.list_tables()
        using_mcp = not mcp_postgres_client._use_fallback
        
        _current_connection = {
            "source_type": "supabase",
            "host": pooler_host,
            "port": 6543,
            "username": pooler_user,
            "password": params.db_password,
            "connected": True,
            "active_database": "postgres",
            "enabled_databases": ["postgres"],
            "project_ref": params.project_ref,
            "using_mcp": using_mcp
        }
        
        _saved_connections["supabase"] = {
            "project_ref": params.project_ref,
            "db_password": params.db_password,
            "region": region
        }
        
        logger.info(f"Connected to Supabase via pooler: {len(tables)} tables found")
        
        return ConnectionStatus(
            connected=True,
            source_type="supabase",
            active_database="postgres",
            project_ref=params.project_ref,
            host=pooler_host,
            port=6543,
            username=pooler_user,
            message=f"Connesso a Supabase! {len(tables)} tabelle trovate",
            using_mcp=using_mcp,
            enabled_databases=["postgres"]
        )
    except Exception as e:
        logger.error(f"Supabase password connection error: {e}")
        _current_connection["connected"] = False
        raise HTTPException(status_code=500, detail=f"Connessione fallita: {str(e)}")


@router.post("/connect/supabase", response_model=ConnectionStatus)
async def connect_supabase(params: SupabaseConnectionParams):
    """Connetti a Supabase via MCP nativo (PAT) o REST API (service_role_key)"""
    global _current_connection, _saved_connections
    
    try:
        # Disconnetti eventuali connessioni esistenti
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        logger.info(f"Connecting to Supabase project: {params.project_ref}")
        
        supabase_host = f"{params.project_ref}.supabase.co"
        connection_type = ""
        
        # Priorita' a Personal Access Token (MCP nativo)
        if params.personal_access_token:
            logger.info("Using Personal Access Token for MCP native connection")
            mcp_supabase_client.connect_with_pat(params.project_ref, params.personal_access_token)
            connection_type = "MCP nativo"
        elif params.service_role_key:
            logger.info("Using Service Role Key for REST API connection")
            mcp_supabase_client.connect_with_service_key(params.project_ref, params.service_role_key)
            connection_type = "REST API"
        else:
            raise HTTPException(status_code=400, detail="Richiesto personal_access_token o service_role_key")
        
        # Verifica connessione listando le tabelle
        tables = mcp_supabase_client.list_tables()
        using_mcp = mcp_supabase_client.is_using_mcp
        logger.info(f"Connected to Supabase via {connection_type}: {len(tables)} tables found")
        
        _current_connection = {
            "source_type": "supabase",
            "host": supabase_host,
            "port": 5432,
            "username": "postgres",
            "connected": True,
            "active_database": "postgres",
            "enabled_databases": ["postgres"],
            "project_ref": params.project_ref,
            "using_mcp": using_mcp
        }
        
        # Salva configurazione per switch rapido
        _saved_connections["supabase"] = {
            "project_ref": params.project_ref,
            "personal_access_token": params.personal_access_token,
            "service_role_key": params.service_role_key
        }
        
        return ConnectionStatus(
            connected=True,
            source_type="supabase",
            active_database="postgres",
            project_ref=params.project_ref,
            host=supabase_host,
            port=5432,
            username="postgres",
            message=f"Connesso a Supabase via {connection_type}! Project: {params.project_ref} ({len(tables)} tabelle)",
            using_mcp=using_mcp,
            enabled_databases=["postgres"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Supabase connection error: {e}")
        _current_connection["connected"] = False
        raise HTTPException(status_code=500, detail=f"Connessione Supabase fallita: {str(e)}")


# ============================================================
# OAUTH ENDPOINTS per connessione Supabase
# ============================================================

class OAuthInitResponse(BaseModel):
    """Risposta inizializzazione OAuth"""
    auth_url: str = Field(..., description="URL per autorizzazione OAuth")
    state: str = Field(..., description="State per verifica CSRF")


@router.get("/oauth/init")
async def init_oauth():
    """
    Inizia il flusso OAuth per connessione a Supabase.
    Restituisce l'URL dove reindirizzare l'utente per l'autorizzazione.
    """
    try:
        oauth_data = supabase_oauth.get_authorization_url()
        return OAuthInitResponse(**oauth_data)
    except Exception as e:
        logger.error(f"OAuth init failed: {e}")
        raise HTTPException(status_code=500, detail=f"Inizializzazione OAuth fallita: {str(e)}")


class OAuthCallbackRequest(BaseModel):
    """Richiesta callback OAuth"""
    code: str = Field(..., description="Authorization code")
    state: str = Field(..., description="State per verifica CSRF")


@router.post("/oauth/callback")
async def oauth_callback(request: OAuthCallbackRequest):
    """
    Callback OAuth - scambia il codice per i token.
    Chiamato dal frontend dopo il redirect da Supabase.
    """
    try:
        logger.info(f"OAuth callback with state: {request.state}")
        tokens = supabase_oauth.exchange_code(request.code, request.state)
        
        return {
            "status": "success",
            "message": "Autenticazione completata! Seleziona un progetto.",
            "authenticated": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth fallito: {str(e)}")


class SupabaseProject(BaseModel):
    """Progetto Supabase"""
    id: str
    name: str
    ref: str = Field(..., alias="project_ref")
    region: str
    organization_id: str


@router.get("/oauth/projects")
async def list_oauth_projects():
    """Lista i progetti Supabase dell'utente autenticato via OAuth"""
    if not supabase_oauth.is_authenticated:
        raise HTTPException(status_code=401, detail="Non autenticato. Completa prima il flusso OAuth.")
    
    try:
        projects = supabase_oauth.list_projects()
        return {
            "projects": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "ref": p.get("id"),  # project_ref e' l'id
                    "region": p.get("region"),
                    "organization_id": p.get("organization_id")
                }
                for p in projects
            ]
        }
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero progetti: {str(e)}")


class SelectProjectRequest(BaseModel):
    """Richiesta selezione progetto"""
    project_ref: str = Field(..., description="Project reference da connettere")


@router.post("/oauth/select-project")
async def select_oauth_project(request: SelectProjectRequest):
    """Seleziona un progetto e stabilisce la connessione usando OAuth token"""
    global _current_connection, _saved_connections
    
    if not supabase_oauth.is_authenticated:
        raise HTTPException(status_code=401, detail="Non autenticato")
    
    try:
        # Disconnetti connessioni esistenti
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        supabase_host = f"{request.project_ref}.supabase.co"
        service_role_key = None
        connection_type = ""
        tables = []
        using_mcp = False
        
        # Strategia 1: Prova a ottenere le API keys dal progetto
        try:
            logger.info(f"Trying to fetch API keys for project {request.project_ref}")
            api_keys = supabase_oauth.get_project_api_keys(request.project_ref)
            service_role_key = api_keys.get("service_role")
            
            if service_role_key:
                logger.info("Got service_role key, connecting via REST API")
                mcp_supabase_client.connect_with_service_key(request.project_ref, service_role_key)
                tables = mcp_supabase_client.list_tables()
                using_mcp = False
                connection_type = "REST API (service_role)"
        except Exception as api_err:
            logger.warning(f"Could not fetch API keys (403 is normal for OAuth apps without api-keys scope): {api_err}")
        
        # Strategia 2: Se non abbiamo service_role, prova connessione diretta via pooler
        if not service_role_key:
            logger.info("Trying direct database connection via Supabase pooler")
            try:
                # Usa la password del database se disponibile nel .env
                from app.config import settings
                db_password = getattr(settings, "supabase_database_password", None)
                
                if db_password:
                    # Connessione diretta via pooler Supabase
                    pooler_host = "aws-0-eu-central-1.pooler.supabase.com"
                    pooler_user = f"postgres.{request.project_ref}"
                    connection_string = f"postgresql://{pooler_user}:{db_password}@{pooler_host}:6543/postgres"
                    
                    logger.info(f"Connecting via Supabase pooler: {pooler_host}")
                    mcp_postgres_client.connect_with_string(connection_string)
                    tables = mcp_postgres_client.list_tables()
                    using_mcp = not mcp_postgres_client._use_fallback
                    connection_type = "Pooler diretto"
                    
                    _current_connection = {
                        "source_type": "supabase",
                        "host": pooler_host,
                        "port": 6543,
                        "username": pooler_user,
                        "connected": True,
                        "active_database": "postgres",
                        "enabled_databases": ["postgres"],
                        "project_ref": request.project_ref,
                        "using_mcp": using_mcp
                    }
                    
                    _saved_connections["supabase"] = {
                        "project_ref": request.project_ref,
                        "pooler_connection": True
                    }
                    
                    return ConnectionStatus(
                        connected=True,
                        source_type="supabase",
                        active_database="postgres",
                        project_ref=request.project_ref,
                        host=pooler_host,
                        port=6543,
                        username=pooler_user,
                        message=f"Connesso a Supabase via {connection_type}! {len(tables)} tabelle trovate",
                        using_mcp=using_mcp,
                        enabled_databases=["postgres"]
                    )
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail="OAuth app non ha permesso 'api-keys'. Configura SUPABASE_DATABASE_PASSWORD nel .env o usa connessione manuale con service_role_key."
                    )
            except HTTPException:
                raise
            except Exception as pool_err:
                logger.error(f"Pooler connection failed: {pool_err}")
                raise HTTPException(
                    status_code=500, 
                    detail=f"Connessione pooler fallita: {str(pool_err)}. Prova la connessione manuale."
                )
        
        # Se siamo qui, abbiamo usato service_role_key
        _current_connection = {
            "source_type": "supabase",
            "host": supabase_host,
            "port": 5432,
            "username": "postgres",
            "connected": True,
            "active_database": "postgres",
            "enabled_databases": ["postgres"],
            "project_ref": request.project_ref,
            "using_mcp": using_mcp
        }
        
        _saved_connections["supabase"] = {
            "project_ref": request.project_ref,
            "service_role_key": service_role_key
        }
        
        return ConnectionStatus(
            connected=True,
            source_type="supabase",
            active_database="postgres",
            project_ref=request.project_ref,
            host=supabase_host,
            port=5432,
            username="postgres",
            message=f"Connesso a Supabase via {connection_type}! {len(tables)} tabelle trovate",
            using_mcp=using_mcp,
            enabled_databases=["postgres"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Select project failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connessione fallita: {str(e)}")


@router.get("/oauth/callback")
async def oauth_callback_redirect(code: str, state: str):
    """
    Callback OAuth GET - redirect dal browser.
    Reindirizza al frontend per completare l'OAuth.
    """
    from fastapi.responses import RedirectResponse
    # Reindirizza al frontend con i parametri
    redirect_url = f"http://localhost:5173/oauth/callback?code={code}&state={state}"
    return RedirectResponse(url=redirect_url)


@router.post("/switch/{source_type}", response_model=ConnectionStatus)
async def switch_data_source(source_type: str):
    """Switch rapido tra sorgenti dati salvate"""
    global _current_connection, _saved_connections
    
    if source_type not in ["postgres", "supabase"]:
        raise HTTPException(status_code=400, detail="Sorgente dati non valida. Usa 'postgres' o 'supabase'")
    
    saved = _saved_connections.get(source_type)
    if not saved:
        raise HTTPException(status_code=400, detail=f"Nessuna configurazione salvata per {source_type}")
    
    try:
        if source_type == "postgres":
            return await connect_with_params(ConnectionParams(**saved))
        else:
            return await connect_supabase(SupabaseConnectionParams(**saved))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Switch fallito: {str(e)}")


@router.post("/disconnect")
async def disconnect_database():
    """Disconnetti dalla sorgente dati attiva"""
    global _current_connection
    
    try:
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        if mcp_supabase_client.is_connected:
            mcp_supabase_client.disconnect()
        
        _current_connection = {
            "source_type": None,
            "host": None,
            "port": None,
            "username": None,
            "password": None,
            "connected": False,
            "active_database": None,
            "enabled_databases": [],
            "project_ref": None,
            "service_role_key": None
        }
        
        return {"success": True, "message": "Disconnesso"}
    except Exception as e:
        logger.error(f"Disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enable-databases")
async def enable_databases(databases: List[str]):
    """Abilita i database selezionati dall'utente"""
    global _current_connection
    
    if not _current_connection["connected"]:
        raise HTTPException(status_code=400, detail="Non connesso a PostgreSQL")
    
    _current_connection["enabled_databases"] = databases
    
    # Se c'è almeno un database abilitato e nessuno è attivo, attiva il primo
    if databases and not _current_connection["active_database"]:
        await select_active_database(SelectDatabaseRequest(database=databases[0]))
    
    return {
        "success": True, 
        "enabled_databases": databases,
        "message": f"{len(databases)} database abilitati"
    }


@router.post("/select-database", response_model=ConnectionStatus)
async def select_active_database(request: SelectDatabaseRequest):
    """Seleziona il database attivo per le query"""
    global _current_connection
    
    if not _current_connection["connected"]:
        raise HTTPException(status_code=400, detail="Non connesso a PostgreSQL")
    
    try:
        # Riconnetti al database selezionato
        connection_string = f"postgresql://{_current_connection['username']}:{_current_connection['password']}@{_current_connection['host']}:{_current_connection['port']}/{request.database}"
        
        logger.info(f"Switching to database: {request.database}")
        
        # Disconnetti e riconnetti al nuovo database
        if mcp_postgres_client._connected:
            mcp_postgres_client.shutdown()
        
        mcp_postgres_client.connect_with_string(connection_string)
        
        # Verifica connessione
        result = mcp_postgres_client.execute_query("SELECT current_database() as db")
        db_name = result[0].get("db") if result else request.database
        
        _current_connection["active_database"] = db_name
        
        # Aggiungi ai database abilitati se non già presente
        if db_name not in _current_connection["enabled_databases"]:
            _current_connection["enabled_databases"].append(db_name)
        
        logger.info(f"Now using database: {db_name}")
        
        return ConnectionStatus(
            connected=True,
            active_database=db_name,
            host=_current_connection["host"],
            port=_current_connection["port"],
            username=_current_connection["username"],
            message=f"Database attivo: {db_name}",
            using_mcp=not mcp_postgres_client._use_fallback,
            enabled_databases=_current_connection["enabled_databases"]
        )
    except Exception as e:
        logger.error(f"Select database error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore selezione database: {str(e)}")


@router.post("/connect")
async def connect_database():
    """Stabilisce connessione al database"""
    try:
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        return {"success": True, "message": "Connessione stabilita"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases", response_model=List[DatabaseInfo])
async def list_databases():
    """Lista tutti i database disponibili"""
    try:
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        
        sql = """
            SELECT datname as name, pg_size_pretty(pg_database_size(datname)) as size
            FROM pg_database 
            WHERE datistemplate = false AND datname NOT IN ('postgres')
            ORDER BY datname
        """
        result = mcp_postgres_client.execute_query(sql)
        
        databases = []
        current_db = mcp_postgres_client.execute_query("SELECT current_database() as db")
        current_db_name = current_db[0].get("db") if current_db else None
        
        for row in result:
            db_name = row.get("name")
            tables_count = 0
            if current_db_name == db_name:
                tables = mcp_postgres_client.list_tables()
                tables_count = len(tables)
            
            databases.append(DatabaseInfo(
                name=db_name,
                size=row.get("size"),
                tables_count=tables_count
            ))
        
        return databases
    except Exception as e:
        logger.error(f"List databases error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema", response_model=SchemaResponse)
async def get_database_schema():
    """Recupera lo schema completo del database usando connessione diretta"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    global _current_connection
    
    if not _current_connection["connected"] or not _current_connection["active_database"]:
        raise HTTPException(status_code=400, detail="Database non connesso o non selezionato")
    
    try:
        logger.info(f"Loading schema for database: {_current_connection['active_database']}")
        
        # Usa connessione diretta psycopg2 per velocita'
        conn_string = f"postgresql://{_current_connection['username']}:{_current_connection['password']}@{_current_connection['host']}:{_current_connection['port']}/{_current_connection['active_database']}"
        
        conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
        conn.autocommit = True
        
        try:
            with conn.cursor() as cur:
                db_name = _current_connection["active_database"]
                
                # Lista tabelle
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name")
                tables_list = [row["table_name"] for row in cur.fetchall()]
                
                tables = []
                for table_name in tables_list:
                    columns_sql = f"""
                        SELECT 
                            c.column_name, c.data_type, c.is_nullable,
                            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_pk,
                            CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_fk,
                            fk.foreign_table_name as fk_references
                        FROM information_schema.columns c
                        LEFT JOIN (
                            SELECT ku.column_name FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
                            WHERE tc.table_name = '{table_name}' AND tc.constraint_type = 'PRIMARY KEY'
                        ) pk ON c.column_name = pk.column_name
                        LEFT JOIN (
                            SELECT kcu.column_name, ccu.table_name as foreign_table_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                            WHERE tc.table_name = '{table_name}' AND tc.constraint_type = 'FOREIGN KEY'
                        ) fk ON c.column_name = fk.column_name
                        WHERE c.table_name = '{table_name}' AND c.table_schema = 'public'
                        ORDER BY c.ordinal_position
                    """
                    cur.execute(columns_sql)
                    columns_result = [dict(row) for row in cur.fetchall()]
                    
                    columns = []
                    for col in columns_result:
                        columns.append({
                            "name": col.get("column_name"),
                            "type": col.get("data_type", "").upper(),
                            "nullable": col.get("is_nullable") == "YES",
                            "isPK": col.get("is_pk", False),
                            "isFK": col.get("is_fk", False),
                            "fkReferences": col.get("fk_references")
                        })
                    
                    # Count righe
                    cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
                    count_result = cur.fetchone()
                    row_count = count_result.get("cnt", 0) if count_result else 0
                    
                    tables.append(TableInfo(name=table_name, row_count=row_count, columns=columns))
                
                # Also load views
                cur.execute("SELECT table_name FROM information_schema.views WHERE table_schema = 'public' ORDER BY table_name")
                views_list = [row["table_name"] for row in cur.fetchall()]
                
                for view_name in views_list:
                    view_columns_sql = f"""
                        SELECT 
                            c.column_name, c.data_type, c.is_nullable
                        FROM information_schema.columns c
                        WHERE c.table_name = '{view_name}' AND c.table_schema = 'public'
                        ORDER BY c.ordinal_position
                    """
                    cur.execute(view_columns_sql)
                    view_columns_result = [dict(row) for row in cur.fetchall()]
                    
                    view_columns = []
                    for col in view_columns_result:
                        view_columns.append({
                            "name": col.get("column_name"),
                            "type": col.get("data_type", "").upper(),
                            "nullable": col.get("is_nullable") == "YES",
                            "isPK": False,
                            "isFK": False,
                            "fkReferences": None
                        })
                    
                    tables.append(TableInfo(name=view_name, row_count=None, columns=view_columns, type="view"))
                
                logger.info(f"Schema loaded: {len(tables)} items ({len(tables_list)} tables, {len(views_list)} views)")
                return SchemaResponse(database=db_name, tables=tables)
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Get schema error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{table_name}/preview", response_model=TablePreviewResponse)
async def get_table_preview(table_name: str, limit: int = 50):
    """Recupera anteprima dati di una tabella usando connessione diretta"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    global _current_connection
    
    if not _current_connection["connected"] or not _current_connection["active_database"]:
        raise HTTPException(status_code=400, detail="Database non connesso o non selezionato")
    
    try:
        logger.info(f"Loading preview for table: {table_name}, limit: {limit}")
        
        # Usa connessione diretta psycopg2 per evitare timeout MCP
        conn_string = f"postgresql://{_current_connection['username']}:{_current_connection['password']}@{_current_connection['host']}:{_current_connection['port']}/{_current_connection['active_database']}"
        
        conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
        conn.autocommit = True
        
        try:
            with conn.cursor() as cur:
                # Query dati
                cur.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
                rows = [dict(row) for row in cur.fetchall()]
                
                if not rows:
                    # Verifica se tabella esiste
                    cur.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (table_name,))
                    exists = cur.fetchone()
                    if not exists or not exists.get("exists"):
                        raise HTTPException(status_code=404, detail=f"Tabella '{table_name}' non trovata")
                    return TablePreviewResponse(
                        table_name=table_name, columns=[], rows=[],
                        total_rows=0, preview_limit=limit
                    )
                
                columns = list(rows[0].keys()) if rows else []
                
                # Count totale
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
                count_result = cur.fetchone()
                total_rows = count_result.get("cnt", 0) if count_result else 0
                
                logger.info(f"Preview loaded: {len(rows)} rows, {len(columns)} columns")
                
                return TablePreviewResponse(
                    table_name=table_name, columns=columns, rows=rows,
                    total_rows=total_rows, preview_limit=limit
                )
        finally:
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Table preview error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables")
async def list_tables():
    """Lista tutte le tabelle del database corrente"""
    try:
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        
        tables = mcp_postgres_client.list_tables()
        result = []
        for table_name in tables:
            count_result = mcp_postgres_client.execute_query(f"SELECT COUNT(*) as cnt FROM {table_name}")
            row_count = count_result[0].get("cnt", 0) if count_result else 0
            result.append({"name": table_name, "row_count": row_count})
        
        return {"tables": result}
    except Exception as e:
        logger.error(f"List tables error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationships")
async def get_relationships():
    """
    Recupera tutte le relazioni (Foreign Keys) tra le tabelle.
    Questo endpoint e' UNIVERSALE - funziona con qualsiasi database PostgreSQL connesso via MCP.
    Le relazioni vengono lette direttamente dal catalogo di sistema del database.
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    global _current_connection
    
    if not _current_connection["connected"] or not _current_connection["active_database"]:
        raise HTTPException(status_code=400, detail="Database non connesso o non selezionato")
    
    try:
        logger.info(f"Loading relationships for database: {_current_connection['active_database']}")
        
        conn_string = f"postgresql://{_current_connection['username']}:{_current_connection['password']}@{_current_connection['host']}:{_current_connection['port']}/{_current_connection['active_database']}"
        
        conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
        conn.autocommit = True
        
        try:
            with conn.cursor() as cur:
                # Query universale per recuperare tutte le FK dal catalogo PostgreSQL
                relationships_sql = """
                    SELECT 
                        tc.table_name as from_table,
                        kcu.column_name as from_column,
                        ccu.table_name as to_table,
                        ccu.column_name as to_column,
                        tc.constraint_name,
                        -- Determina il tipo di relazione basandosi su vincoli UNIQUE
                        CASE 
                            WHEN EXISTS (
                                SELECT 1 FROM information_schema.table_constraints tc2
                                JOIN information_schema.key_column_usage kcu2 
                                    ON tc2.constraint_name = kcu2.constraint_name
                                WHERE tc2.table_name = tc.table_name 
                                AND kcu2.column_name = kcu.column_name
                                AND tc2.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
                            ) THEN '1:1'
                            ELSE '1:N'
                        END as relationship_type
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu 
                        ON tc.constraint_name = kcu.constraint_name 
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu 
                        ON tc.constraint_name = ccu.constraint_name 
                        AND tc.table_schema = ccu.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    ORDER BY tc.table_name, kcu.column_name
                """
                cur.execute(relationships_sql)
                relationships = [dict(row) for row in cur.fetchall()]
                
                logger.info(f"Found {len(relationships)} relationships")
                
                return {
                    "database": _current_connection["active_database"],
                    "relationships": relationships,
                    "count": len(relationships)
                }
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Get relationships error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DATABASE ANALYSIS ENDPOINTS
# ============================================================

@router.post("/analyze")
async def analyze_database(schema: str = "public"):
    """
    Genera analisi completa del database con report strutturato.
    Usa LLM per analisi semantica delle tabelle e dei dati.
    """
    if not _current_connection["connected"]:
        raise HTTPException(status_code=400, detail="Non connesso al database")
    
    try:
        from app.services.database_analyzer import get_database_analyzer, set_cached_report
        
        analyzer = get_database_analyzer()
        report = analyzer.analyze_database(schema=schema)
        
        if report.get("success"):
            set_cached_report(report)
        
        return report
        
    except Exception as e:
        logger.error(f"Database analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis-report")
async def get_analysis_report():
    """
    Recupera l'ultimo report di analisi del database (se disponibile).
    """
    from app.services.database_analyzer import get_cached_report
    
    report = get_cached_report()
    
    if report is None:
        return {
            "success": False,
            "message": "Nessun report disponibile. Esegui prima l'analisi con POST /api/database/analyze"
        }
    
    return report