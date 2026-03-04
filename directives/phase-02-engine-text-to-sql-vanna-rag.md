# Fase 02: Engine Text-to-SQL con Vanna 2.0 e RAG ChromaDB

## Panoramica
- **Obiettivo**: Integrare Vanna 2.0 come motore text-to-SQL con RAG ChromaDB embedded e MCP PostgreSQL per query execution
- **Dipendenza**: Fase 01 (Database operativo con schema e dati Kaggle)
- **Complessità stimata**: Alta
- **Componenti coinvolti**: Backend, AI

## Contesto
La Fase 01 ha creato l'infrastruttura database con dati Kaggle Superstore Sales. Ora costruiamo il cuore del sistema: il motore text-to-SQL che converte domande in linguaggio naturale in query SQL eseguibili.

Vanna 2.0 è una libreria specializzata per text-to-SQL con RAG built-in. A differenza di LangChain (generico) o implementazioni custom, Vanna offre:
- Accuracy 94% su benchmark BIRD con Claude Sonnet 4.5
- RAG automatico con ChromaDB per learning da esempi (few-shot)
- Multi-LLM support (prepara terreno per Fase 3)
- Row-level security (future-proof)

In questa fase creiamo `vanna_service.py` che orchestra:
1. **Schema inspection** via MCP PostgreSQL (DDL tabelle, colonne, relazioni)
2. **RAG retrieval** da ChromaDB (query simili passate, k=5)
3. **LLM generation** SQL via Vanna → Claude Sonnet 4.5 (temporaneo, Fase 3 generalizza)
4. **SQL execution** via MCP PostgreSQL
5. **Training loop** feedback utente per migliorare accuracy

Useremo MCP PostgreSQL Server (Anthropic official) invece di connessione diretta psycopg2 per future-proofing (swap database facile in fasi successive).

## Obiettivi Specifici
1. Installare Vanna 2.0, ChromaDB, MCP client Python
2. Configurare ChromaDB embedded mode con persistent storage SQLite
3. Configurare MCP PostgreSQL Server e testare comunicazione subprocess Python
4. Creare `backend/app/services/vanna_service.py` con classe `VannaService`
5. Implementare schema inspection automatico (lettura DDL da PostgreSQL)
6. Seed ChromaDB con 15-20 coppie (NL question, SQL query) validate manualmente
7. Implementare workflow text-to-SQL completo: NL → RAG → LLM → SQL → execute
8. Creare endpoint FastAPI `/api/internal/test-vanna` per testing isolato
9. Testare accuracy su 10 query di test (target >90%)
10. Implementare logging SQL generated + execution time per analytics

## Specifiche Tecniche Dettagliate

### Area 1: Installazione Dipendenze

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\requirements.txt`

```txt
# ============================================================
# DATACHAT BI PLATFORM - BACKEND DEPENDENCIES
# ============================================================

# --- Web Framework ---
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-multipart==0.0.9

# --- Database ---
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
alembic==1.13.3

# --- Data Validation ---
pydantic==2.9.2
pydantic-settings==2.5.2

# --- Environment ---
python-dotenv==1.0.1

# --- Text-to-SQL (Vanna 2.0) ---
vanna==0.8.1
chromadb==0.5.18

# --- LLM Providers (temporaneo per questa fase, generalizzato in Fase 3) ---
openai==1.54.3  # Supporta OpenRouter + Azure OpenAI

# --- MCP Client ---
# MCP servers sono subprocess Node.js, comunicazione via stdio
# Usiamo subprocess + json per comunicazione
# No package Python specifico necessario in questa fase

# --- Data Processing ---
pandas==2.2.0
numpy==1.26.4

# --- HTTP Client ---
httpx==0.27.2
requests==2.32.3

# --- Utilities ---
python-dateutil==2.9.0

# --- Logging ---
structlog==24.4.0

# --- Testing (dev) ---
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2  # Per TestClient FastAPI
```

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\requirements-dev.txt`

```txt
# Development dependencies
-r requirements.txt

black==24.10.0
flake8==7.1.1
mypy==1.13.0
pytest-cov==6.0.0
```

**Installazione:**

```bash
# Dalla root del progetto
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend

# Creare virtual environment
python -m venv venv

# Attivare venv (Windows)
venv\Scripts\activate

# Installare dipendenze
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

### Area 2: Configurazione ChromaDB Embedded

ChromaDB userà SQLite backend per persistenza embeddings. No server separato necessario.

**Directory ChromaDB:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\data\chromadb`

Questa directory viene creata automaticamente da ChromaDB al primo utilizzo. Configurazione in `.env`:

```bash
CHROMADB_PERSIST_DIRECTORY=./data/chromadb
CHROMADB_COLLECTION_NAME=vanna_training
```

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\config.py`

```python
"""
Configurazione applicazione - carica variabili d'ambiente
"""

import os
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Settings applicazione caricate da .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Database
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # LLM Provider (generalizzato in Fase 3, temporaneo Claude)
    default_llm_provider: Literal["claude", "azure"] = "claude"
    openrouter_api_key: str | None = None
    openrouter_model: str = "anthropic/claude-sonnet-4.5"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str = "2024-02-15-preview"

    # LLM Parameters
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 30

    # MCP Configuration
    mcp_postgres_read_only: bool = True
    mcp_postgres_connection_string: str

    # Vanna 2.0
    vanna_model: str = "datachat_superstore"
    vanna_training_auto_save: bool = True
    vanna_rag_top_k: int = 5

    # ChromaDB
    chromadb_persist_directory: str = "./data/chromadb"
    chromadb_collection_name: str = "vanna_training"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True
    api_workers: int = 1
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Performance
    sql_query_timeout_seconds: int = 30

    @property
    def cors_origins_list(self) -> list[str]:
        """Converte CORS_ORIGINS string in lista"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Singleton settings
settings = Settings()
```

---

### Area 3: MCP PostgreSQL Server Setup

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\mcp-config\postgres-config.json`

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres",
        "postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db"
      ],
      "env": {
        "POSTGRES_READ_ONLY": "true"
      }
    }
  }
}
```

**IMPORTANTE:** In produzione, connection string deve venire da `.env`, non hardcoded. Per POC, accettabile hardcode in config JSON.

**Test MCP Server manualmente:**

```bash
# Installare MCP PostgreSQL server globalmente
npx @modelcontextprotocol/server-postgres

# Test comunicazione (da terminale separato)
npx -y @modelcontextprotocol/server-postgres "postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db"

# Output atteso: server avviato, listening su stdio
# Ctrl+C per terminare
```

**Gestione MCP in Python:**

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\mcp_manager.py`

```python
"""
MCP Manager - Gestione lifecycle MCP servers (PostgreSQL)
Comunicazione via subprocess stdio + JSON-RPC 2.0
"""

import subprocess
import json
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class MCPPostgreSQLClient:
    """Client MCP PostgreSQL Server"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    def start(self):
        """Avvia MCP PostgreSQL server subprocess"""
        try:
            self.process = subprocess.Popen(
                [
                    "npx",
                    "-y",
                    "@modelcontextprotocol/server-postgres",
                    settings.mcp_postgres_connection_string
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"POSTGRES_READ_ONLY": str(settings.mcp_postgres_read_only).lower()},
                text=False  # Binary mode per controllo encoding
            )
            logger.info("MCP PostgreSQL server avviato")
        except Exception as e:
            logger.error(f"Errore avvio MCP PostgreSQL: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chiama tool MCP PostgreSQL

        Tools disponibili:
        - query: esegue SQL SELECT
        - list_tables: lista tabelle/viste
        - describe_table: schema tabella dettagliato
        """
        if not self.process:
            raise RuntimeError("MCP server non avviato")

        self.request_id += 1

        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": self.request_id
        }

        try:
            # Invia richiesta
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json.encode("utf-8"))
            self.process.stdin.flush()

            # Leggi risposta
            response_line = self.process.stdout.readline()
            response = json.loads(response_line.decode("utf-8"))

            if "error" in response:
                raise Exception(f"MCP error: {response['error']}")

            return response.get("result", {})

        except Exception as e:
            logger.error(f"Errore chiamata MCP tool '{tool_name}': {e}")
            raise

    def execute_query(self, sql: str) -> list[dict]:
        """
        Esegue query SQL via MCP
        Returns: lista di righe come dizionari
        """
        result = self.call_tool("query", {"sql": sql})
        # MCP PostgreSQL restituisce: {"rows": [...], "fields": [...]}
        return result.get("rows", [])

    def list_tables(self, schema: str = "public") -> list[str]:
        """Lista tabelle in schema"""
        result = self.call_tool("list_tables", {"schema": schema})
        return result.get("tables", [])

    def describe_table(self, table_name: str, schema: str = "public") -> Dict[str, Any]:
        """Recupera DDL/schema tabella"""
        result = self.call_tool("describe_table", {
            "table": table_name,
            "schema": schema
        })
        return result

    def shutdown(self):
        """Termina MCP server subprocess"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            logger.info("MCP PostgreSQL server terminato")


# Singleton MCP client
mcp_postgres_client = MCPPostgreSQLClient()
```

---

### Area 4: Vanna Service - Core Text-to-SQL

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\vanna_service.py`

```python
"""
Vanna Service - Text-to-SQL engine con RAG ChromaDB
Wrapper Vanna 2.0 + integrazione MCP PostgreSQL
"""

import logging
from typing import Dict, Any, Optional
from vanna.chromadb import ChromaDB_VectorStore
from vanna.openai import OpenAI_Chat
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.mcp_manager import mcp_postgres_client

logger = logging.getLogger(__name__)


class VannaChromaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
    """
    Vanna custom class: ChromaDB vector store + OpenAI-compatible LLM
    Supporta OpenRouter (Claude via OpenAI API format)
    """
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)


class VannaService:
    """
    Service orchestrazione Vanna 2.0 per text-to-SQL

    Workflow:
    1. User NL query → generate_sql()
    2. RAG retrieval da ChromaDB (k=5 query simili)
    3. Schema inspection PostgreSQL (DDL tabelle)
    4. LLM generation SQL (Vanna + Claude Sonnet 4.5)
    5. SQL execution via MCP PostgreSQL
    6. Results + metadata return
    """

    def __init__(self):
        self.vanna_model: Optional[VannaChromaOpenAI] = None
        self._initialize_vanna()

    def _initialize_vanna(self):
        """Inizializza Vanna con ChromaDB + OpenAI/OpenRouter"""
        try:
            # ChromaDB client embedded
            chroma_client = chromadb.PersistentClient(
                path=settings.chromadb_persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False)
            )

            # Configurazione Vanna
            vanna_config = {
                "client": chroma_client,
                "model": settings.vanna_model,
                "api_key": settings.openrouter_api_key,
                "api_base": "https://openrouter.ai/api/v1",  # OpenRouter endpoint
                "model": settings.openrouter_model,  # anthropic/claude-sonnet-4.5
                "temperature": settings.llm_temperature,
                "max_tokens": settings.llm_max_tokens
            }

            self.vanna_model = VannaChromaOpenAI(config=vanna_config)

            logger.info(f"Vanna initialized: model={settings.vanna_model}, LLM={settings.openrouter_model}")

        except Exception as e:
            logger.error(f"Errore inizializzazione Vanna: {e}")
            raise

    def train_on_ddl(self, ddl: str):
        """
        Aggiungi DDL schema a training Vanna (embedding in ChromaDB)
        Es: CREATE TABLE orders (...)
        """
        try:
            self.vanna_model.train(ddl=ddl)
            logger.info(f"DDL training added: {len(ddl)} chars")
        except Exception as e:
            logger.error(f"Errore training DDL: {e}")
            raise

    def train_on_sql(self, question: str, sql: str):
        """
        Aggiungi coppia (NL question, SQL) a training (few-shot learning)
        """
        try:
            self.vanna_model.train(question=question, sql=sql)
            logger.info(f"SQL training added: '{question[:50]}...'")
        except Exception as e:
            logger.error(f"Errore training SQL: {e}")
            raise

    def generate_sql(self, question: str) -> Dict[str, Any]:
        """
        Genera SQL da domanda NL

        Returns:
            {
                "sql": str,              # SQL generato
                "explanation": str,      # Spiegazione LLM (opzionale)
                "similar_questions": [], # RAG k=5 query simili
                "success": bool
            }
        """
        try:
            logger.info(f"Generating SQL for: '{question}'")

            # Vanna genera SQL (RAG + LLM automatico)
            sql = self.vanna_model.generate_sql(question=question)

            logger.info(f"SQL generated: {sql[:100]}...")

            return {
                "sql": sql,
                "explanation": "",  # Vanna 0.8.1 non espone explanation direttamente
                "similar_questions": [],  # TODO: implementare retrieval esplicito
                "success": True
            }

        except Exception as e:
            logger.error(f"Errore generazione SQL: {e}")
            return {
                "sql": "",
                "explanation": str(e),
                "similar_questions": [],
                "success": False,
                "error": str(e)
            }

    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        Esegue SQL via MCP PostgreSQL

        Returns:
            {
                "rows": list[dict],      # Risultati query
                "row_count": int,
                "execution_time_ms": float,
                "success": bool
            }
        """
        import time

        try:
            start_time = time.time()

            # Execute via MCP
            rows = mcp_postgres_client.execute_query(sql)

            execution_time_ms = (time.time() - start_time) * 1000

            logger.info(f"SQL executed: {len(rows)} rows, {execution_time_ms:.2f}ms")

            return {
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": execution_time_ms,
                "success": True
            }

        except Exception as e:
            logger.error(f"Errore esecuzione SQL: {e}")
            return {
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "success": False,
                "error": str(e)
            }

    def generate_and_execute(self, question: str) -> Dict[str, Any]:
        """
        Workflow completo: NL → SQL → execute

        Returns:
            {
                "question": str,
                "sql": str,
                "rows": list[dict],
                "row_count": int,
                "execution_time_ms": float,
                "success": bool
            }
        """
        # Generate SQL
        sql_result = self.generate_sql(question)

        if not sql_result["success"]:
            return {
                "question": question,
                "sql": "",
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "success": False,
                "error": sql_result.get("error", "SQL generation failed")
            }

        sql = sql_result["sql"]

        # Execute SQL
        exec_result = self.execute_sql(sql)

        return {
            "question": question,
            "sql": sql,
            "rows": exec_result["rows"],
            "row_count": exec_result["row_count"],
            "execution_time_ms": exec_result["execution_time_ms"],
            "success": exec_result["success"],
            "error": exec_result.get("error")
        }


# Singleton service
vanna_service = VannaService()
```

---

### Area 5: Seed Training Data

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\training_seed.py`

```python
"""
Seed training data Vanna - 15-20 coppie (NL, SQL) validate
Dataset: Superstore Sales
"""

from app.services.vanna_service import vanna_service
from app.services.mcp_manager import mcp_postgres_client
import logging

logger = logging.getLogger(__name__)

# Training data: (question_NL, sql_query)
TRAINING_DATA = [
    # Query semplici aggregazione
    (
        "Mostra le vendite totali per ogni regione",
        "SELECT region, SUM(sales) as total_sales FROM public.orders GROUP BY region ORDER BY total_sales DESC"
    ),
    (
        "Qual è il profitto totale per categoria di prodotto?",
        "SELECT category, SUM(profit) as total_profit FROM public.orders GROUP BY category ORDER BY total_profit DESC"
    ),
    (
        "Conta quanti ordini abbiamo per ogni segmento cliente",
        "SELECT segment, COUNT(DISTINCT order_id) as order_count FROM public.orders GROUP BY segment ORDER BY order_count DESC"
    ),

    # Query temporali
    (
        "Mostra le vendite mensili negli ultimi 12 mesi",
        "SELECT DATE_TRUNC('month', order_date) as month, SUM(sales) as monthly_sales FROM public.orders WHERE order_date >= CURRENT_DATE - INTERVAL '12 months' GROUP BY month ORDER BY month"
    ),
    (
        "Vendite totali per ogni anno",
        "SELECT EXTRACT(YEAR FROM order_date) as year, SUM(sales) as yearly_sales FROM public.orders GROUP BY year ORDER BY year"
    ),
    (
        "Mostra le vendite trimestrali per categoria",
        "SELECT DATE_TRUNC('quarter', order_date) as quarter, category, SUM(sales) as sales FROM public.orders GROUP BY quarter, category ORDER BY quarter, category"
    ),

    # Query con filtri
    (
        "Vendite nella regione West nel 2016",
        "SELECT SUM(sales) as total_sales FROM public.orders WHERE region = 'West' AND EXTRACT(YEAR FROM order_date) = 2016"
    ),
    (
        "Top 10 prodotti per profitto",
        "SELECT product_name, SUM(profit) as total_profit FROM public.orders GROUP BY product_name ORDER BY total_profit DESC LIMIT 10"
    ),
    (
        "Ordini con sconto maggiore del 20%",
        "SELECT order_id, customer_name, discount, sales FROM public.orders WHERE discount > 0.20 ORDER BY discount DESC"
    ),

    # Query multi-dimensione
    (
        "Vendite per categoria e sottocategoria",
        "SELECT category, sub_category, SUM(sales) as total_sales FROM public.orders GROUP BY category, sub_category ORDER BY category, total_sales DESC"
    ),
    (
        "Profitto medio per stato e segmento cliente",
        "SELECT state, segment, AVG(profit) as avg_profit FROM public.orders GROUP BY state, segment ORDER BY avg_profit DESC"
    ),
    (
        "Top 5 clienti per vendite totali",
        "SELECT customer_name, SUM(sales) as total_sales FROM public.orders GROUP BY customer_name ORDER BY total_sales DESC LIMIT 5"
    ),

    # Query con JOIN (self-join simulato per POC)
    (
        "Numero di prodotti distinti ordinati per regione",
        "SELECT region, COUNT(DISTINCT product_id) as product_count FROM public.orders GROUP BY region ORDER BY product_count DESC"
    ),

    # Query analitiche
    (
        "Tasso sconto medio per categoria",
        "SELECT category, AVG(discount) as avg_discount FROM public.orders GROUP BY category ORDER BY avg_discount DESC"
    ),
    (
        "Quantità media venduta per modalità di spedizione",
        "SELECT ship_mode, AVG(quantity) as avg_quantity FROM public.orders GROUP BY ship_mode ORDER BY avg_quantity DESC"
    ),

    # Query temporali complesse
    (
        "Confronto vendite anno corrente vs anno precedente",
        "SELECT EXTRACT(YEAR FROM order_date) as year, SUM(sales) as total_sales FROM public.orders GROUP BY year ORDER BY year DESC LIMIT 2"
    ),
    (
        "Vendite giornaliere nell'ultimo mese",
        "SELECT DATE(order_date) as day, SUM(sales) as daily_sales FROM public.orders WHERE order_date >= CURRENT_DATE - INTERVAL '30 days' GROUP BY day ORDER BY day"
    ),

    # Query geografiche
    (
        "Vendite per stato nella regione East",
        "SELECT state, SUM(sales) as total_sales FROM public.orders WHERE region = 'East' GROUP BY state ORDER BY total_sales DESC"
    ),
    (
        "Top 10 città per numero di ordini",
        "SELECT city, COUNT(DISTINCT order_id) as order_count FROM public.orders GROUP BY city ORDER BY order_count DESC LIMIT 10"
    ),

    # Query prodotti
    (
        "Sottocategoria con profitto più alto nella categoria Technology",
        "SELECT sub_category, SUM(profit) as total_profit FROM public.orders WHERE category = 'Technology' GROUP BY sub_category ORDER BY total_profit DESC LIMIT 1"
    ),
]


def seed_training_data():
    """
    Seed ChromaDB con training data
    Eseguire una volta dopo setup iniziale
    """
    logger.info("=== SEED VANNA TRAINING DATA ===")

    # 1. Train su DDL schema
    logger.info("Step 1: Training DDL schema...")

    try:
        # Recupera DDL da MCP PostgreSQL
        tables = mcp_postgres_client.list_tables(schema="public")

        for table in tables:
            table_info = mcp_postgres_client.describe_table(table, schema="public")
            # Construct DDL string
            ddl = f"-- Table: {table}\n"
            ddl += str(table_info)  # MCP restituisce struttura dettagliata
            vanna_service.train_on_ddl(ddl)

        logger.info(f"✓ DDL training completato: {len(tables)} tabelle")

    except Exception as e:
        logger.warning(f"DDL training fallito (continuare con SQL): {e}")

    # 2. Train su coppie (NL, SQL)
    logger.info(f"Step 2: Training {len(TRAINING_DATA)} SQL examples...")

    for question, sql in TRAINING_DATA:
        try:
            vanna_service.train_on_sql(question=question, sql=sql)
        except Exception as e:
            logger.error(f"Errore training '{question[:30]}...': {e}")

    logger.info(f"✓ SQL training completato: {len(TRAINING_DATA)} esempi")
    logger.info("=== SEED COMPLETATO ===")


if __name__ == "__main__":
    # Esecuzione standalone per seed
    logging.basicConfig(level=logging.INFO)
    from app.services.mcp_manager import mcp_postgres_client

    # Avvia MCP client
    mcp_postgres_client.start()

    # Seed
    seed_training_data()

    # Cleanup
    mcp_postgres_client.shutdown()
```

---

### Area 6: FastAPI Endpoint Test

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\main.py`

```python
"""
FastAPI main application - DataChat BI Platform
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.services.mcp_manager import mcp_postgres_client

# Setup logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: startup + shutdown"""
    # Startup
    logger.info("=== DATACHAT BI PLATFORM STARTUP ===")
    logger.info(f"Environment: {settings.log_level}")

    # Avvia MCP PostgreSQL server
    mcp_postgres_client.start()
    logger.info("MCP PostgreSQL client started")

    yield

    # Shutdown
    logger.info("=== SHUTDOWN ===")
    mcp_postgres_client.shutdown()


app = FastAPI(
    title="DataChat BI Platform API",
    description="Natural Language Business Intelligence POC",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTES (Fase 2: endpoint test interno)
# ============================================================

from fastapi import HTTPException
from pydantic import BaseModel
from app.services.vanna_service import vanna_service


class TestVannaRequest(BaseModel):
    question: str


class TestVannaResponse(BaseModel):
    question: str
    sql: str
    rows: list[dict]
    row_count: int
    execution_time_ms: float
    success: bool
    error: str | None = None


@app.post("/api/internal/test-vanna", response_model=TestVannaResponse)
async def test_vanna_endpoint(request: TestVannaRequest):
    """
    Endpoint test interno Vanna (Fase 2)
    Genera SQL da NL query ed esegue
    """
    try:
        result = vanna_service.generate_and_execute(request.question)
        return TestVannaResponse(**result)

    except Exception as e:
        logger.error(f"Errore test-vanna: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "datachat-bi-platform",
        "version": "0.1.0"
    }
```

**Script avvio backend:**

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\scripts\start_backend.sh`

```bash
#!/bin/bash

# Start backend FastAPI server
# Usage: bash scripts/start_backend.sh

cd "$(dirname "$0")/.."

echo "=== Starting DataChat BI Platform Backend ==="

# Activate venv
source backend/venv/Scripts/activate

# Run uvicorn
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Note: --reload auto-reloads on code changes (dev only)
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `backend/requirements.txt` | Creare | Dipendenze Python backend (Vanna, ChromaDB, FastAPI, etc.) |
| `backend/requirements-dev.txt` | Creare | Dipendenze sviluppo (pytest, black, mypy) |
| `backend/app/config.py` | Creare | Configurazione app (Pydantic Settings, carica .env) |
| `backend/app/main.py` | Creare | FastAPI app principale con lifecycle MCP |
| `backend/app/services/mcp_manager.py` | Creare | Client MCP PostgreSQL (subprocess + JSON-RPC) |
| `backend/app/services/vanna_service.py` | Creare | Vanna 2.0 wrapper, text-to-SQL orchestration |
| `backend/app/services/training_seed.py` | Creare | Seed 15-20 training examples ChromaDB |
| `mcp-config/postgres-config.json` | Creare | Configurazione MCP PostgreSQL server |
| `scripts/start_backend.sh` | Creare | Script avvio backend FastAPI |
| `.env` | Modificare | Aggiungere `OPENROUTER_API_KEY` reale |

## Dipendenze da Installare

### Backend (Python)

```bash
# Dalla directory backend/
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend

# Creare venv
python -m venv venv

# Attivare venv (Windows)
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Installare dipendenze
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### MCP PostgreSQL Server (Node.js)

```bash
# Installazione globale (eseguita automaticamente da npx, ma test manuale utile)
npx @modelcontextprotocol/server-postgres

# Output atteso: server in ascolto
# Ctrl+C per terminare
```

## Variabili d'Ambiente

Aggiungere a `.env`:

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `OPENROUTER_API_KEY` | API key OpenRouter per Claude Sonnet 4.5 | `sk-or-v1-xxxxx...` |
| `OPENROUTER_MODEL` | Modello LLM OpenRouter | `anthropic/claude-sonnet-4.5` |
| `VANNA_MODEL` | Nome modello Vanna (ChromaDB collection) | `datachat_superstore` |
| `VANNA_RAG_TOP_K` | Numero query simili RAG retrieval | `5` |
| `CHROMADB_PERSIST_DIRECTORY` | Path storage ChromaDB SQLite | `./data/chromadb` |
| `CHROMADB_COLLECTION_NAME` | Nome collection ChromaDB | `vanna_training` |
| `MCP_POSTGRES_CONNECTION_STRING` | Connection string PostgreSQL per MCP | `postgresql://datachat_user:...@localhost:5432/datachat_db` |

## Criteri di Completamento

- [ ] File `requirements.txt` e `requirements-dev.txt` creati con versioni specificate
- [ ] Virtual environment Python creato in `backend/venv/`
- [ ] Tutte le dipendenze installate senza errori (`pip list` mostra vanna, chromadb, fastapi)
- [ ] ChromaDB directory `data/chromadb/` esiste (creata automaticamente al primo run)
- [ ] File `config.py` carica correttamente variabili da `.env` (testare import)
- [ ] MCP PostgreSQL server si avvia manualmente senza errori
- [ ] `mcp_manager.py` comunica con MCP server (test `list_tables()` restituisce `['orders']`)
- [ ] `vanna_service.py` inizializza Vanna + ChromaDB senza errori
- [ ] Script `training_seed.py` esegue seed di 20 esempi senza errori
- [ ] Endpoint `/api/internal/test-vanna` risponde correttamente a query test
- [ ] Test accuracy: almeno 9/10 query test generano SQL corretto (>90%)
- [ ] Backend FastAPI si avvia su `http://localhost:8000` senza errori
- [ ] Health check `/health` restituisce `{"status": "healthy"}`
- [ ] Swagger docs disponibili su `http://localhost:8000/docs`

## Test di Verifica

### Test 1: Installazione Dipendenze

```bash
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend

# Attivare venv
venv\Scripts\activate

# Verificare vanna installato
python -c "import vanna; print(vanna.__version__)"
# Output atteso: 0.8.1

# Verificare chromadb
python -c "import chromadb; print(chromadb.__version__)"
# Output atteso: 0.5.18
```

### Test 2: Seed Training Data

```bash
# Dalla root progetto
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator

# Assicurarsi .env con OPENROUTER_API_KEY configurato

# Eseguire seed
cd backend
python -m app.services.training_seed

# Output atteso:
# === SEED VANNA TRAINING DATA ===
# Step 1: Training DDL schema...
# ✓ DDL training completato: 1 tabelle
# Step 2: Training 20 SQL examples...
# ✓ SQL training completato: 20 esempi
# === SEED COMPLETATO ===
```

### Test 3: Avvio Backend FastAPI

```bash
# Dalla root progetto
bash scripts/start_backend.sh

# Output atteso:
# === Starting DataChat BI Platform Backend ===
# INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
# INFO:     Started reloader process
# === DATACHAT BI PLATFORM STARTUP ===
# MCP PostgreSQL client started

# Aprire browser: http://localhost:8000/docs
# Swagger UI deve mostrare endpoint /api/internal/test-vanna e /health
```

### Test 4: Endpoint Test Vanna

```bash
# Da terminale separato (con backend running)
curl -X POST http://localhost:8000/api/internal/test-vanna \
  -H "Content-Type: application/json" \
  -d '{"question": "Mostra le vendite totali per ogni regione"}'

# Output atteso (JSON):
# {
#   "question": "Mostra le vendite totali per ogni regione",
#   "sql": "SELECT region, SUM(sales) as total_sales FROM public.orders GROUP BY region ORDER BY total_sales DESC",
#   "rows": [
#     {"region": "West", "total_sales": 725457.82},
#     {"region": "East", "total_sales": 678781.24},
#     ...
#   ],
#   "row_count": 4,
#   "execution_time_ms": 145.23,
#   "success": true,
#   "error": null
# }
```

### Test 5: Accuracy Test Set

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\tests\test_vanna_accuracy.py`

```python
"""
Test accuracy Vanna su 10 query di test
Target: >90% (almeno 9/10 corrette)
"""

import pytest
from app.services.vanna_service import vanna_service

# Test queries (question, expected_keywords_in_sql)
TEST_QUERIES = [
    ("Vendite totali per regione", ["SELECT", "region", "SUM(sales)", "GROUP BY"]),
    ("Profitto per categoria", ["SELECT", "category", "SUM(profit)", "GROUP BY"]),
    ("Top 5 prodotti", ["SELECT", "product", "LIMIT 5", "ORDER BY"]),
    ("Vendite nel 2016", ["WHERE", "2016", "order_date"]),
    ("Ordini con sconto maggiore 10%", ["WHERE", "discount", ">", "0.1"]),
    ("Media vendite per stato", ["SELECT", "state", "AVG(sales)", "GROUP BY"]),
    ("Numero ordini per segmento", ["SELECT", "segment", "COUNT", "GROUP BY"]),
    ("Vendite mensili ultimi 6 mesi", ["DATE_TRUNC", "month", "INTERVAL"]),
    ("Clienti con vendite maggiori 1000", ["customer", "SUM(sales)", ">", "1000"]),
    ("Sottocategoria più profittevole", ["sub_category", "SUM(profit)", "ORDER BY", "DESC"]),
]

@pytest.mark.parametrize("question,expected_keywords", TEST_QUERIES)
def test_vanna_generates_valid_sql(question, expected_keywords):
    """Test che Vanna generi SQL con keywords attese"""
    result = vanna_service.generate_sql(question)

    assert result["success"], f"SQL generation failed: {result.get('error')}"

    sql = result["sql"].upper()

    for keyword in expected_keywords:
        assert keyword.upper() in sql, f"Keyword '{keyword}' not found in SQL: {sql}"

def test_accuracy_overall():
    """Test accuracy complessiva (almeno 9/10 corrette)"""
    correct = 0
    total = len(TEST_QUERIES)

    for question, expected_keywords in TEST_QUERIES:
        result = vanna_service.generate_sql(question)

        if result["success"]:
            sql = result["sql"].upper()
            if all(kw.upper() in sql for kw in expected_keywords):
                correct += 1

    accuracy = (correct / total) * 100
    print(f"\nAccuracy: {accuracy:.1f}% ({correct}/{total})")

    assert accuracy >= 90, f"Accuracy {accuracy:.1f}% < 90% target"
```

Eseguire test:

```bash
cd backend
pytest tests/test_vanna_accuracy.py -v

# Output atteso:
# test_vanna_accuracy.py::test_vanna_generates_valid_sql[...] PASSED (x10)
# test_vanna_accuracy.py::test_accuracy_overall PASSED
# Accuracy: 95.0% (9.5/10)  # Esempio
```

### Test 6: MCP Communication Test

```python
# Test interattivo Python
from app.services.mcp_manager import mcp_postgres_client

# Start MCP
mcp_postgres_client.start()

# List tables
tables = mcp_postgres_client.list_tables(schema="public")
print(tables)  # ['orders']

# Describe table
schema = mcp_postgres_client.describe_table("orders", schema="public")
print(schema)

# Execute query
rows = mcp_postgres_client.execute_query("SELECT COUNT(*) as cnt FROM public.orders")
print(rows)  # [{'cnt': 9994}]

# Shutdown
mcp_postgres_client.shutdown()
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **Vanna initialization:** Sempre in singleton service, non reinizializzare per ogni richiesta
2. **MCP communication:** Subprocess stdio è blocking, usare timeout se necessario
3. **ChromaDB persistent client:** Path relativo `./data/chromadb` risolto da root progetto
4. **Error handling:** Tutte le funzioni Vanna/MCP wrappate in try/except con logging
5. **LLM API calls:** Vanna gestisce retry interno, ma aggiungere timeout global 30s

### Convenzioni Naming

- **Vanna model name:** `datachat_superstore` (identifica dataset)
- **ChromaDB collection:** `vanna_training` (coerente con training data)
- **Logging:** Usare logger module-level `logger = logging.getLogger(__name__)`
- **Endpoint test:** Prefisso `/api/internal/*` per endpoint non production-ready

### Errori Comuni da Evitare

1. **OpenRouter API key mancante:** Verificare `.env` prima di avviare backend
2. **MCP server già running:** Terminare processi `npx` esistenti prima di nuovo start
3. **ChromaDB lock:** Se processo crashes, eliminare `data/chromadb/*.lock` files
4. **SQL injection:** Vanna genera SQL parametrizzato, ma validare input NL (max 500 chars)
5. **DDL training duplicati:** ChromaDB gestisce dedup automatico, ma evitare re-seed multipli
6. **Timeout LLM:** Claude Sonnet può richiedere 5-10s per SQL complesso, aumentare timeout se necessario

### Troubleshooting

**Errore: "MCP server not responding"**
```bash
# Verificare MCP server manualmente
npx -y @modelcontextprotocol/server-postgres "postgresql://datachat_user:password@localhost:5432/datachat_db"
# Testare connessione PostgreSQL separatamente
psql -U datachat_user -d datachat_db
```

**Errore: "Vanna training failed"**
```python
# Verificare ChromaDB path writable
import os
os.makedirs("./data/chromadb", exist_ok=True)
# Re-run seed con logging DEBUG
```

**Errore: "OpenRouter API rate limit"**
- OpenRouter free tier: 200 req/min
- Aggiungere exponential backoff o ridurre test queries

**SQL generation accuracy <90%**
- Aumentare training examples (target 30-50)
- Migliorare DDL descriptions (comments su colonne)
- Aumentare `VANNA_RAG_TOP_K` a 10

**ChromaDB "collection not found"**
```python
# Reset ChromaDB (WARNING: perde training data)
import shutil
shutil.rmtree("./data/chromadb")
# Re-run seed
```

## Riferimenti

- **BRIEFING.md**: Sezione "Framework, Librerie e Tool Rilevanti" (Vanna 2.0, MCP Servers)
- **PRD.md**: Sezione 3.2 "Componenti del Sistema" (Vanna service, MCP integration), Sezione 3.4 "Flusso 1: Chat con i Dati"
- **Fase precedente**: `phase-01-fondamenta-infrastrutturali-database.md` (database operativo, dataset importato)
- **Vanna 2.0 Docs**: https://vanna.ai/docs/
- **ChromaDB Docs**: https://docs.trychroma.com/
- **MCP PostgreSQL Server**: https://github.com/modelcontextprotocol/servers
- **OpenRouter API**: https://openrouter.ai/docs
