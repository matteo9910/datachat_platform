# Fase 01: Fondamenta Infrastrutturali e Database Multi-Schema

## Panoramica
- **Obiettivo**: Setup completo ambiente di sviluppo (Python, PostgreSQL, Node.js) e database multi-schema con dati Kaggle Superstore Sales
- **Dipendenza**: Nessuna (prima fase)
- **Complessità stimata**: Media
- **Componenti coinvolti**: Database, Infra

## Contesto
Questa è la prima fase del progetto DataChat BI Platform. Non esiste ancora alcuna infrastruttura. Dobbiamo creare le fondamenta su cui costruire l'intero sistema: database PostgreSQL con schema dati utente (`public`) e schema metadata POC (`poc_metadata`), importare dataset Kaggle Superstore Sales, configurare variabili d'ambiente, preparare struttura cartelle progetto backend e frontend.

Il database avrà un ruolo centrale: conterrà sia i dati di business che l'utente interrogherà tramite NL, sia i metadata dei chart salvati e la query history. ChromaDB (fase 2) userà SQLite separato per RAG embeddings.

## Obiettivi Specifici
1. Installare e configurare PostgreSQL 16 con user `datachat_user` e database `datachat_db`
2. Creare schema `public` (dati Kaggle) e schema `poc_metadata` (metadata POC)
3. Scaricare e importare dataset Kaggle Superstore Sales (>10k righe) in tabella `public.orders`
4. Creare indici PostgreSQL su colonne chiave (date, category, region) per performance query
5. Creare struttura cartelle progetto backend e frontend
6. Generare file `.env.example` completo con tutte le variabili necessarie
7. Creare script `init_schema.sql` per creazione schemi e tabelle metadata
8. Creare script Python `import_kaggle_dataset.py` per import CSV → PostgreSQL
9. Validare connessione database e conteggio righe importate

## Specifiche Tecniche Dettagliate

### Area 1: Installazione e Configurazione PostgreSQL 16

**Prerequisiti software:**
- PostgreSQL 16.x scaricato da https://www.postgresql.org/download/windows/
- Durante installazione, annotare password utente `postgres` (superuser)
- Port default: 5432
- Locale: Italian_Italy.1252 (o UTF-8)

**Creazione database e user:**

Dopo installazione, aprire **pgAdmin 4** o **psql** e eseguire:

```sql
-- Connessione come postgres superuser
CREATE USER datachat_user WITH PASSWORD 'DataChat2026!Secure';

CREATE DATABASE datachat_db
  OWNER datachat_user
  ENCODING 'UTF8'
  LC_COLLATE = 'Italian_Italy.1252'
  LC_CTYPE = 'Italian_Italy.1252'
  TEMPLATE template0;

-- Grant privilegi
GRANT ALL PRIVILEGES ON DATABASE datachat_db TO datachat_user;

-- Connessione a datachat_db come postgres
\c datachat_db postgres

-- Creare extension per UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant usage su schema public
GRANT ALL ON SCHEMA public TO datachat_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO datachat_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO datachat_user;
```

**Connection string risultante:**
```
postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db
```

---

### Area 2: Creazione Schemi Database

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\database\init_schema.sql`

Questo script SQL crea:
1. Schema `poc_metadata` per metadata POC
2. Tabelle metadata: `saved_charts`, `query_history`, `vanna_training_data`
3. Indici per performance
4. Grant privilegi a `datachat_user`

```sql
-- ============================================================
-- DATACHAT BI PLATFORM - DATABASE SCHEMA INITIALIZATION
-- ============================================================
-- Eseguire come utente postgres dopo creazione database
-- Usage: psql -U postgres -d datachat_db -f init_schema.sql
-- ============================================================

-- Connessione a datachat_db
\c datachat_db

-- ============================================================
-- SCHEMA POC_METADATA (Metadata POC)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS poc_metadata AUTHORIZATION datachat_user;

GRANT ALL ON SCHEMA poc_metadata TO datachat_user;

-- ============================================================
-- TABELLA: poc_metadata.saved_charts
-- ============================================================

CREATE TABLE IF NOT EXISTS poc_metadata.saved_charts (
    chart_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(100), -- Future multi-user (nullable per POC)
    title VARCHAR(200) NOT NULL,
    description TEXT,
    sql_template TEXT NOT NULL, -- SQL con placeholder {param_name}
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb, -- Schema parametri modificabili
    plotly_config JSONB NOT NULL, -- Config Plotly completa
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Indici saved_charts
CREATE INDEX idx_saved_charts_created ON poc_metadata.saved_charts(created_at DESC);
CREATE INDEX idx_saved_charts_user ON poc_metadata.saved_charts(user_id) WHERE user_id IS NOT NULL;

COMMENT ON TABLE poc_metadata.saved_charts IS 'Chart salvati con metadata parametrica per modifica post-creazione';
COMMENT ON COLUMN poc_metadata.saved_charts.sql_template IS 'SQL con placeholder tipo {time_granularity} per parametrizzazione';
COMMENT ON COLUMN poc_metadata.saved_charts.parameters IS 'JSONB: {param_name: {type, current, options, label}}';

-- ============================================================
-- TABELLA: poc_metadata.query_history
-- ============================================================

CREATE TABLE IF NOT EXISTS poc_metadata.query_history (
    query_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(100) NOT NULL,
    nl_query TEXT NOT NULL, -- Domanda linguaggio naturale
    sql_generated TEXT, -- SQL generato da Vanna/LLM
    llm_provider VARCHAR(20), -- 'claude' | 'azure'
    success BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT,
    execution_time_ms INTEGER, -- Latency totale
    result_rows INTEGER, -- Numero righe risultato
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indici query_history
CREATE INDEX idx_query_history_session ON poc_metadata.query_history(session_id, created_at DESC);
CREATE INDEX idx_query_history_success ON poc_metadata.query_history(success, created_at DESC);
CREATE INDEX idx_query_history_created ON poc_metadata.query_history(created_at DESC);

COMMENT ON TABLE poc_metadata.query_history IS 'Storico query NL → SQL per analytics e debugging';

-- ============================================================
-- TABELLA: poc_metadata.vanna_training_data
-- ============================================================

CREATE TABLE IF NOT EXISTS poc_metadata.vanna_training_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nl_question TEXT NOT NULL, -- Domanda NL esempio
    sql_query TEXT NOT NULL, -- SQL corretto corrispondente
    ddl_context TEXT, -- DDL schema (opzionale, Vanna lo recupera da MCP)
    approved BOOLEAN NOT NULL DEFAULT true, -- User-approved per training
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indici vanna_training_data
CREATE INDEX idx_vanna_training_approved ON poc_metadata.vanna_training_data(approved, created_at DESC);

COMMENT ON TABLE poc_metadata.vanna_training_data IS 'Training data Vanna 2.0 (backup PostgreSQL, embeddings in ChromaDB)';

-- ============================================================
-- GRANT PRIVILEGI FINALI
-- ============================================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA poc_metadata TO datachat_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA poc_metadata TO datachat_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA poc_metadata GRANT ALL ON TABLES TO datachat_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA poc_metadata GRANT ALL ON SEQUENCES TO datachat_user;

-- ============================================================
-- VERIFICA CREAZIONE
-- ============================================================

\dt poc_metadata.*

SELECT 'Schema poc_metadata creato con successo' AS status;
```

---

### Area 3: Dataset Kaggle Superstore Sales

**Download dataset:**
1. Accedere a Kaggle: https://www.kaggle.com/datasets/vivek468/superstore-dataset-final
2. Scaricare `Sample - Superstore.csv` (~10 MB, ~9994 righe)
3. Salvare in `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\database\data\Sample-Superstore.csv`

**Schema tabella `public.orders`:**

```sql
-- Eseguire come datachat_user
CREATE TABLE IF NOT EXISTS public.orders (
    row_id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    order_date DATE NOT NULL,
    ship_date DATE,
    ship_mode VARCHAR(50),
    customer_id VARCHAR(50) NOT NULL,
    customer_name VARCHAR(100),
    segment VARCHAR(50),
    country VARCHAR(50),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    region VARCHAR(50),
    product_id VARCHAR(50) NOT NULL,
    category VARCHAR(50),
    sub_category VARCHAR(50),
    product_name VARCHAR(200),
    sales DECIMAL(10,2) NOT NULL,
    quantity INTEGER NOT NULL,
    discount DECIMAL(5,2),
    profit DECIMAL(10,2)
);

-- Indici per performance query
CREATE INDEX idx_orders_order_date ON public.orders(order_date);
CREATE INDEX idx_orders_category ON public.orders(category);
CREATE INDEX idx_orders_sub_category ON public.orders(sub_category);
CREATE INDEX idx_orders_region ON public.orders(region);
CREATE INDEX idx_orders_state ON public.orders(state);
CREATE INDEX idx_orders_segment ON public.orders(segment);
CREATE INDEX idx_orders_customer_id ON public.orders(customer_id);

COMMENT ON TABLE public.orders IS 'Dataset Kaggle Superstore Sales - dati di business per demo POC';
```

**Script import Python:**

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\scripts\import_kaggle_dataset.py`

```python
"""
Script import dataset Kaggle Superstore Sales in PostgreSQL.
Usage: python scripts/import_kaggle_dataset.py
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Load .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
CSV_PATH = "database/data/Sample-Superstore.csv"

def create_orders_table(conn):
    """Crea tabella public.orders se non esiste"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS public.orders (
        row_id SERIAL PRIMARY KEY,
        order_id VARCHAR(50) NOT NULL,
        order_date DATE NOT NULL,
        ship_date DATE,
        ship_mode VARCHAR(50),
        customer_id VARCHAR(50) NOT NULL,
        customer_name VARCHAR(100),
        segment VARCHAR(50),
        country VARCHAR(50),
        city VARCHAR(100),
        state VARCHAR(50),
        postal_code VARCHAR(20),
        region VARCHAR(50),
        product_id VARCHAR(50) NOT NULL,
        category VARCHAR(50),
        sub_category VARCHAR(50),
        product_name VARCHAR(200),
        sales DECIMAL(10,2) NOT NULL,
        quantity INTEGER NOT NULL,
        discount DECIMAL(5,2),
        profit DECIMAL(10,2)
    );
    """

    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        conn.commit()
    print("✓ Tabella public.orders creata (se non esisteva)")

def create_indexes(conn):
    """Crea indici per performance"""
    indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_orders_order_date ON public.orders(order_date);",
        "CREATE INDEX IF NOT EXISTS idx_orders_category ON public.orders(category);",
        "CREATE INDEX IF NOT EXISTS idx_orders_sub_category ON public.orders(sub_category);",
        "CREATE INDEX IF NOT EXISTS idx_orders_region ON public.orders(region);",
        "CREATE INDEX IF NOT EXISTS idx_orders_state ON public.orders(state);",
        "CREATE INDEX IF NOT EXISTS idx_orders_segment ON public.orders(segment);",
        "CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON public.orders(customer_id);",
    ]

    with conn.cursor() as cur:
        for idx_sql in indexes_sql:
            cur.execute(idx_sql)
        conn.commit()
    print("✓ Indici creati")

def import_csv_data(conn, csv_path):
    """Importa dati CSV in PostgreSQL"""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV non trovato: {csv_path}")

    print(f"Lettura CSV: {csv_path}")
    df = pd.read_csv(csv_path, encoding='utf-8')

    # Rinomina colonne per match schema PostgreSQL
    column_mapping = {
        "Row ID": "row_id",
        "Order ID": "order_id",
        "Order Date": "order_date",
        "Ship Date": "ship_date",
        "Ship Mode": "ship_mode",
        "Customer ID": "customer_id",
        "Customer Name": "customer_name",
        "Segment": "segment",
        "Country": "country",
        "City": "city",
        "State": "state",
        "Postal Code": "postal_code",
        "Region": "region",
        "Product ID": "product_id",
        "Category": "category",
        "Sub-Category": "sub_category",
        "Product Name": "product_name",
        "Sales": "sales",
        "Quantity": "quantity",
        "Discount": "discount",
        "Profit": "profit"
    }

    df.rename(columns=column_mapping, inplace=True)

    # Converti date
    df['order_date'] = pd.to_datetime(df['order_date'], format='%m/%d/%Y').dt.date
    df['ship_date'] = pd.to_datetime(df['ship_date'], format='%m/%d/%Y').dt.date

    # Gestisci valori nulli
    df['postal_code'] = df['postal_code'].fillna('')

    print(f"Righe da importare: {len(df)}")

    # Truncate tabella esistente (fresh import)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE public.orders RESTART IDENTITY CASCADE;")
        conn.commit()
    print("✓ Tabella orders troncata")

    # Insert batch
    insert_sql = """
    INSERT INTO public.orders (
        order_id, order_date, ship_date, ship_mode,
        customer_id, customer_name, segment,
        country, city, state, postal_code, region,
        product_id, category, sub_category, product_name,
        sales, quantity, discount, profit
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    """

    data_tuples = [
        (
            row['order_id'], row['order_date'], row['ship_date'], row['ship_mode'],
            row['customer_id'], row['customer_name'], row['segment'],
            row['country'], row['city'], row['state'], row['postal_code'], row['region'],
            row['product_id'], row['category'], row['sub_category'], row['product_name'],
            float(row['sales']), int(row['quantity']), float(row['discount']), float(row['profit'])
        )
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_sql, data_tuples, page_size=1000)
        conn.commit()

    print(f"✓ {len(df)} righe importate con successo")

def verify_import(conn):
    """Verifica import con query test"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.orders;")
        count = cur.fetchone()[0]
        print(f"✓ Verifica: {count} righe in public.orders")

        cur.execute("SELECT category, COUNT(*) FROM public.orders GROUP BY category ORDER BY category;")
        categories = cur.fetchall()
        print("\nDistribuzione categorie:")
        for cat, cnt in categories:
            print(f"  - {cat}: {cnt} righe")

if __name__ == "__main__":
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL non trovato in .env")
        sys.exit(1)

    print("=== IMPORT DATASET KAGGLE SUPERSTORE SALES ===\n")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        print(f"✓ Connesso a database: {DATABASE_URL.split('@')[1]}\n")

        create_orders_table(conn)
        import_csv_data(conn, CSV_PATH)
        create_indexes(conn)
        verify_import(conn)

        conn.close()
        print("\n✓ IMPORT COMPLETATO CON SUCCESSO")

    except Exception as e:
        print(f"❌ ERRORE: {e}")
        sys.exit(1)
```

---

### Area 4: Struttura Cartelle Progetto

**Comando creazione:**

```bash
# Eseguire dalla root del progetto
mkdir -p backend/app/{models,services,api,utils}
mkdir -p backend/tests
mkdir -p backend/alembic/versions
mkdir -p frontend/src/{components/{ui,Chat,Charts,PowerBI,Database,Settings},store,api,types,utils,styles}
mkdir -p frontend/public
mkdir -p frontend/tests/components
mkdir -p database/data
mkdir -p mcp-config
mkdir -p docs
mkdir -p scripts

# Crea __init__.py per Python packages
touch backend/app/__init__.py
touch backend/app/models/__init__.py
touch backend/app/services/__init__.py
touch backend/app/api/__init__.py
touch backend/app/utils/__init__.py
touch backend/tests/__init__.py
```

**Struttura finale:**

```
C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   └── __init__.py
│   │   ├── services/
│   │   │   └── __init__.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   └── utils/
│   │       └── __init__.py
│   ├── tests/
│   │   └── __init__.py
│   └── alembic/
│       └── versions/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── Chat/
│   │   │   ├── Charts/
│   │   │   ├── PowerBI/
│   │   │   ├── Database/
│   │   │   └── Settings/
│   │   ├── store/
│   │   ├── api/
│   │   ├── types/
│   │   ├── utils/
│   │   └── styles/
│   ├── public/
│   └── tests/
│       └── components/
├── database/
│   ├── data/                  # CSV dataset Kaggle
│   └── init_schema.sql
├── mcp-config/
├── docs/
├── scripts/
│   └── import_kaggle_dataset.py
├── directives/                # File directive (questa fase)
├── BRIEFING.md
├── PRD.md
└── .env.example
```

---

### Area 5: File .env.example

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\.env.example`

```bash
# ============================================================
# DATACHAT BI PLATFORM - ENVIRONMENT CONFIGURATION
# ============================================================
# IMPORTANTE: Copiare come .env e sostituire placeholder con valori reali
# NON committare .env in Git (già in .gitignore)
# ============================================================

# --- DATABASE CONFIGURATION ---
DATABASE_URL=postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# --- LLM PROVIDER CONFIGURATION ---
# Multi-provider: scegliere "claude" OPPURE "azure" (NON fallback automatico)
# L'utente configura quale provider utilizzare
DEFAULT_LLM_PROVIDER=claude

# OpenRouter (per Claude Sonnet 4.5)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=anthropic/claude-sonnet-4.5

# Azure OpenAI (alternativo, configurabile dall'utente)
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# LLM Parameters (condivisi tra provider)
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4096
LLM_TIMEOUT_SECONDS=30

# --- MCP CONFIGURATION ---
# PostgreSQL MCP Server
MCP_POSTGRES_READ_ONLY=true
MCP_POSTGRES_CONNECTION_STRING=postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db

# Power BI MCP Server (Fase 6)
MCP_POWERBI_WORKSPACE_PATH=C:/Users/TF536AC/PowerBI/Reports
MCP_POWERBI_BACKUP_ENABLED=true

# --- VANNA 2.0 CONFIGURATION (Fase 2) ---
VANNA_MODEL=datachat_superstore
VANNA_TRAINING_AUTO_SAVE=true
VANNA_RAG_TOP_K=5

# --- CHROMADB CONFIGURATION (Fase 2) ---
CHROMADB_PERSIST_DIRECTORY=./data/chromadb
CHROMADB_COLLECTION_NAME=vanna_training

# --- API CONFIGURATION ---
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
API_WORKERS=1
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# --- LOGGING ---
LOG_LEVEL=INFO
LOG_FORMAT=json

# --- FRONTEND URL (per CORS) ---
FRONTEND_URL=http://localhost:3000

# --- SECURITY ---
SECRET_KEY=change-this-secret-key-in-production-use-random-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# --- FEATURE FLAGS (opzionale) ---
FEATURE_DARK_MODE=true
FEATURE_EXPORT_CHARTS=true
FEATURE_QUERY_HISTORY=true

# --- PERFORMANCE TUNING ---
SQL_QUERY_TIMEOUT_SECONDS=30
CHART_GENERATION_TIMEOUT_SECONDS=15
DAX_GENERATION_TIMEOUT_SECONDS=20
```

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\.gitignore`

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
dist/
*.egg-info/
.pytest_cache/
.coverage

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# Environment
.env
.env.local
.env.production

# Database
*.db
*.sqlite
*.sqlite3

# ChromaDB
data/chromadb/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
logs/
*.log

# Backup
*.bak
*.backup

# Power BI (backup locali)
*.pbix.bak
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `database/init_schema.sql` | Creare | Script SQL creazione schema `poc_metadata` e tabelle metadata |
| `scripts/import_kaggle_dataset.py` | Creare | Script Python import CSV Kaggle → PostgreSQL `public.orders` |
| `database/data/Sample-Superstore.csv` | Scaricare | Dataset Kaggle Superstore Sales (~10k righe) |
| `.env.example` | Creare | Template variabili d'ambiente con placeholder |
| `.gitignore` | Creare | Esclude `.env`, `__pycache__`, `node_modules`, ecc. |
| `backend/app/__init__.py` | Creare | File vuoto (Python package marker) |
| `backend/app/models/__init__.py` | Creare | File vuoto (Python package marker) |
| `backend/app/services/__init__.py` | Creare | File vuoto (Python package marker) |
| `backend/app/api/__init__.py` | Creare | File vuoto (Python package marker) |
| `backend/app/utils/__init__.py` | Creare | File vuoto (Python package marker) |
| `backend/tests/__init__.py` | Creare | File vuoto (Python package marker) |

## Dipendenze da Installare

### Prerequisiti Sistema Operativo

**Software da installare manualmente:**

1. **PostgreSQL 16.x**
   - Download: https://www.postgresql.org/download/windows/
   - Installer: PostgreSQL 16.x Windows x86-64
   - Durante installazione: annotare password `postgres`, port `5432`

2. **Python 3.11.9**
   - Download: https://www.python.org/downloads/release/python-3119/
   - Installer: Windows installer (64-bit)
   - **IMPORTANTE:** Selezionare "Add Python to PATH"

3. **Node.js 20.x LTS**
   - Download: https://nodejs.org/en/download/
   - Installer: Windows Installer (.msi) 64-bit
   - Include npm automaticamente

4. **Git 2.x**
   - Download: https://git-scm.com/download/win
   - Installer: 64-bit Git for Windows Setup

### Backend (Python)

```bash
# Installare dopo creazione venv in Fase 2
# Dipendenze base per questa fase:
pip install psycopg2-binary==2.9.9
pip install pandas==2.2.0
pip install python-dotenv==1.0.1
```

### Frontend (Node.js)

```bash
# Non necessario in questa fase (Fase 7)
```

## Variabili d'Ambiente

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `DATABASE_URL` | Connection string PostgreSQL completo | `postgresql://datachat_user:DataChat2026!Secure@localhost:5432/datachat_db` |
| `DATABASE_POOL_SIZE` | Dimensione pool connessioni SQLAlchemy | `10` |
| `DATABASE_MAX_OVERFLOW` | Max connessioni extra oltre pool | `20` |

**NOTA:** Le altre variabili in `.env.example` saranno utilizzate dalle fasi successive.

## Criteri di Completamento

- [ ] PostgreSQL 16 installato e servizio attivo (`pg_ctl status`)
- [ ] Database `datachat_db` creato con owner `datachat_user`
- [ ] Extension UUID attivata (`uuid-ossp`)
- [ ] Schema `poc_metadata` esiste in database
- [ ] Tabelle `saved_charts`, `query_history`, `vanna_training_data` create con indici
- [ ] File `database/init_schema.sql` esiste ed è eseguibile senza errori
- [ ] Dataset Kaggle `Sample-Superstore.csv` scaricato in `database/data/`
- [ ] Tabella `public.orders` contiene esattamente ~9994 righe importate
- [ ] Indici creati su colonne: `order_date`, `category`, `sub_category`, `region`, `state`, `segment`, `customer_id`
- [ ] Script `scripts/import_kaggle_dataset.py` esegue senza errori
- [ ] File `.env.example` esiste con tutte le variabili documentate
- [ ] File `.gitignore` esiste ed esclude `.env`
- [ ] Struttura cartelle `backend/`, `frontend/`, `database/`, `scripts/`, `docs/`, `mcp-config/` creata
- [ ] File `__init__.py` presenti in tutti i package Python (`backend/app/`, `backend/app/models/`, etc.)

## Test di Verifica

### Test 1: Connessione Database

```bash
# Verificare connessione PostgreSQL come datachat_user
psql -U datachat_user -d datachat_db -h localhost -p 5432

# Output atteso: prompt psql
datachat_db=>
```

### Test 2: Verifica Schema e Tabelle

```sql
-- Dentro psql
\dn  -- Lista schemi (deve mostrare public, poc_metadata)

\dt poc_metadata.*  -- Lista tabelle metadata

-- Output atteso:
--  Schema       | Name                 | Type  | Owner
-- --------------+----------------------+-------+---------------
--  poc_metadata | query_history        | table | datachat_user
--  poc_metadata | saved_charts         | table | datachat_user
--  poc_metadata | vanna_training_data  | table | datachat_user

\d public.orders  -- Descrizione tabella orders

-- Output atteso: lista completa colonne con tipi
```

### Test 3: Verifica Import Dataset

```sql
-- Conteggio righe
SELECT COUNT(*) FROM public.orders;
-- Output atteso: ~9994

-- Verifica distribuzione categorie
SELECT category, COUNT(*) as count
FROM public.orders
GROUP BY category
ORDER BY count DESC;

-- Output atteso:
--  category          | count
-- -------------------+-------
--  Office Supplies   | ~6000
--  Furniture         | ~2121
--  Technology        | ~1847

-- Verifica range date
SELECT MIN(order_date) as min_date, MAX(order_date) as max_date
FROM public.orders;

-- Output atteso: date tra 2014 e 2017 circa
```

### Test 4: Esecuzione Script Import

```bash
# Dalla root del progetto
cd C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator

# Creare file .env copiando .env.example
copy .env.example .env

# Modificare .env con password reale PostgreSQL

# Eseguire script import
python scripts/import_kaggle_dataset.py

# Output atteso:
# === IMPORT DATASET KAGGLE SUPERSTORE SALES ===
#
# ✓ Connesso a database: localhost:5432/datachat_db
# ✓ Tabella public.orders creata (se non esisteva)
# Lettura CSV: database/data/Sample-Superstore.csv
# Righe da importare: 9994
# ✓ Tabella orders troncata
# ✓ 9994 righe importate con successo
# ✓ Indici creati
# ✓ Verifica: 9994 righe in public.orders
#
# Distribuzione categorie:
#   - Furniture: 2121 righe
#   - Office Supplies: 6026 righe
#   - Technology: 1847 righe
#
# ✓ IMPORT COMPLETATO CON SUCCESSO
```

### Test 5: Verifica Indici

```sql
-- Verifica indici creati
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'orders'
ORDER BY indexname;

-- Output atteso: almeno 7 indici (pkey + 6 custom)
```

### Test 6: Test Query Performance

```sql
-- Query con filtro su colonna indicizzata (deve essere rapida <100ms)
EXPLAIN ANALYZE
SELECT region, SUM(sales) as total_sales
FROM public.orders
WHERE order_date >= '2016-01-01' AND order_date < '2017-01-01'
GROUP BY region
ORDER BY total_sales DESC;

-- Verificare nel piano di esecuzione che usi idx_orders_order_date
-- Execution Time: < 100 ms
```

## Note per l'Agente di Sviluppo

### Convenzioni Naming

- **Schema database:** `snake_case` (es. `poc_metadata`)
- **Tabelle:** `snake_case` plurale (es. `saved_charts`)
- **Colonne:** `snake_case` (es. `created_at`, `sql_template`)
- **Indici:** `idx_<tabella>_<colonna>` (es. `idx_orders_order_date`)
- **File Python:** `snake_case.py` (es. `import_kaggle_dataset.py`)
- **Cartelle:** `lowercase` o `PascalCase` per componenti React (es. `backend/`, `Chat/`)

### Pattern di Codice

1. **Script Python standalone:** Usare `if __name__ == "__main__":` per esecuzione diretta
2. **Gestione errori:** Try/except con messaggi user-friendly (es. `❌ ERRORE: <descrizione>`)
3. **Logging:** Print con simboli Unicode (✓ successo, ❌ errore, → processo)
4. **SQL scripts:** Commenti descrittivi, sezioni separate con banner `-- ===...===`

### Errori Comuni da Evitare

1. **Password PostgreSQL in chiaro:** Usare sempre `.env`, mai hardcoded
2. **Dimenticare indici:** Performance critiche per query su >10k righe
3. **Encoding CSV errato:** Superstore dataset è UTF-8, specificare in `pd.read_csv()`
4. **Date format mismatch:** Dataset usa `MM/DD/YYYY`, convertire con `pd.to_datetime(format='%m/%d/%Y')`
5. **Permessi schema:** Sempre grant espliciti a `datachat_user` per schema `poc_metadata`
6. **UUID extension:** Necessaria per `uuid_generate_v4()`, creare prima delle tabelle

### Troubleshooting

**Errore: "psycopg2 not found"**
```bash
pip install psycopg2-binary
```

**Errore: "relation does not exist"**
- Verificare schema corretto con `\dt poc_metadata.*`
- Eseguire `init_schema.sql` come postgres superuser

**Errore: "CSV file not found"**
- Verificare path relativo: `database/data/Sample-Superstore.csv`
- Eseguire script dalla root del progetto

**Import lento (>1 minuto)**
- Normale per ~10k righe con batch insert
- Usare `execute_batch` con `page_size=1000` (già implementato)

**Errore: "permission denied for schema poc_metadata"**
```sql
-- Eseguire come postgres
GRANT ALL ON SCHEMA poc_metadata TO datachat_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA poc_metadata GRANT ALL ON TABLES TO datachat_user;
```

## Riferimenti

- **BRIEFING.md**: Sezione "Dati e Integrazioni" (database, dataset), "Stack Tecnologico"
- **PRD.md**: Sezione 4.3 "Schema Database" (definizione tabelle metadata), Sezione 8 "Dipendenze e Prerequisiti"
- **Fase precedente**: N/A (prima fase)
- **Kaggle Dataset**: https://www.kaggle.com/datasets/vivek468/superstore-dataset-final
- **PostgreSQL 16 Docs**: https://www.postgresql.org/docs/16/
- **psycopg2 Docs**: https://www.psycopg.org/docs/
- **Pandas Docs**: https://pandas.pydata.org/docs/
