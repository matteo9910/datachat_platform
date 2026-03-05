# DataChat BI Platform

**Version 0.5.0** · Generative BI Platform by EY AI Engineering

DataChat BI Platform is a Generative Business Intelligence application that enables non-technical users to query any PostgreSQL database using natural language, generate interactive charts, manage knowledge bases, and create dashboards — all without writing a single line of SQL.

---

## Architecture

**Pattern:** Hybrid — Vanna RAG + MCP Server + Multi-Provider LLM

```
Frontend (React 19 + TypeScript + Vite)
    |
    | REST API (HTTP + SSE Streaming)
    |
Backend (FastAPI + Uvicorn)
    |
    |--- Chat Orchestrator (session management, streaming)
    |--- Vanna RAG Engine (ChromaDB + Azure Embeddings)
    |--- Multi-Provider LLM Manager (Claude / GPT-4.1 / GPT-5.2)
    |--- MCP PostgreSQL Client (query + schema inspection)
    |--- Chart Service (auto-detection + Plotly config)
    +--- Metadata Service (SQLAlchemy + PostgreSQL JSONB)

Database Layer
    |--- System DB: PostgreSQL (Neon/Supabase) -- app state, auth, audit logs
    |--- Client DB: Any PostgreSQL database (database-agnostic)
    +--- Vector Store: ChromaDB (local, embedded) -- RAG training embeddings
```

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.11 · FastAPI · Uvicorn · SQLAlchemy 2.0 · Alembic |
| **Frontend** | React 19 · TypeScript · Vite 7 · Tailwind CSS · Zustand |
| **Charts** | Plotly.js with brand theming |
| **Text-to-SQL** | Vanna 2.0 + ChromaDB |
| **LLM Providers** | Claude Sonnet 4 (OpenRouter) · Azure GPT-4.1 · Azure GPT-5.2 |
| **Auth** | JWT (python-jose) · bcrypt · Role-based access control |

---

## Features

- **Natural Language to SQL** — Ask questions in plain language; get SQL, results, and charts instantly via multi-provider LLM
- **JWT Authentication** — Role-based access control with three roles: Admin, Analyst, User
- **Knowledge Base Management** — Save and curate question-SQL pairs that train the RAG system via ChromaDB
- **System Instructions** — Define global and per-topic rules that guide SQL generation
- **SQL Views** — Create views directly on the client database from the chat interface
- **Brand Guidelines** — Configure colors, fonts, and styling applied to all generated charts
- **Write Operations** — Execute INSERT/UPDATE via natural language with whitelist enforcement and full audit logging
- **Voice Input** — Azure Whisper speech-to-text for hands-free querying (99 languages)
- **NL-Driven Dashboards** — Describe a dashboard in natural language; get auto-generated charts with global filters and PDF/image export
- **Streaming Responses** — Server-Sent Events with reasoning steps for real-time feedback

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL 16+** — For the system database (Neon, Supabase, or self-hosted)
- **LLM API Key** — At least one of:
  - OpenRouter API key (for Claude)
  - Azure OpenAI API key (for GPT-4.1 / GPT-5.2)
- **Azure Whisper API key** *(optional)* — Required only for voice input

---

## Quick Start

### Backend

```bash
cd backend
python -m venv venv

# Activate virtual environment
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

# Copy and configure environment variables
cp ../.env.example ../.env
# Edit .env with your database URL and API keys

# Run database migrations (creates system tables)
alembic upgrade head

# Start the backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Health check: `GET /health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Environment Variables

Copy `.env.example` to `.env` and configure the following groups of variables:

| Category | Key Variables | Description |
|----------|---------------|-------------|
| **System Database** | `SYSTEM_DATABASE_URL`, `SEED_ADMIN_PASSWORD` | PostgreSQL connection for app metadata (auth, audit, config) |
| **Client Database** | `DATABASE_URL`, `MCP_POSTGRES_CONNECTION_STRING` | PostgreSQL connection for the data source being queried |
| **OpenRouter (Claude)** | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | API key and model for Claude LLM provider |
| **Azure OpenAI (GPT)** | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI endpoint, key, and deployment for GPT-4.1 |
| **Azure Whisper** | `AZURE_WHISPER_ENDPOINT`, `AZURE_WHISPER_API_KEY` | Speech-to-text API for voice input |
| **Vanna RAG** | `VANNA_MODEL`, `CHROMADB_PERSIST_DIRECTORY` | Vanna model name and ChromaDB storage path |
| **Server** | `BACKEND_HOST`, `BACKEND_PORT`, `SECRET_KEY` | FastAPI server configuration and JWT signing key |
| **Frontend** | `VITE_API_BASE_URL` | Backend API URL for the React client |
| **Feature Flags** | `FEATURE_MULTI_LLM`, `FEATURE_VANNA_TRAINING`, etc. | Toggle features on/off |

> **⚠️ Security:** Never commit `.env` files with real credentials. The `.env.example` file contains only placeholder values.

---

## Testing

### Backend Tests

```bash
cd backend
pip install pytest pytest-asyncio pytest-cov
pytest tests/ -v
```

### Frontend Checks

```bash
cd frontend
npx tsc --noEmit      # TypeScript type checking
npm run build          # Production build verification
```

---

## Deployment

| Component | Platform | Config File |
|-----------|----------|-------------|
| **Backend** | Railway | `backend/Dockerfile` + `backend/railway.toml` |
| **Frontend** | Vercel | `frontend/vercel.json` |
| **CI/CD** | GitHub Actions | `.github/workflows/ci.yml` |

The CI pipeline runs backend tests (pytest) and frontend checks (TypeScript + build) on every push to `main`.

---

## Project Structure

```
ai_engineer_poc_orchestrator/
|-- backend/
|   |-- app/
|   |   |-- api/              # REST API endpoints
|   |   |-- models/           # SQLAlchemy ORM models
|   |   |-- services/         # Business logic layer
|   |   |-- utils/            # Helper utilities
|   |   |-- config.py         # Settings & environment loading
|   |   |-- database.py       # DB engine & session management
|   |   |-- dependencies.py   # FastAPI dependency injection
|   |   +-- main.py           # Application entrypoint & CORS
|   |-- alembic/              # Database migration scripts
|   |-- tests/                # pytest test suite
|   |-- Dockerfile            # Multi-stage Docker build
|   |-- railway.toml          # Railway deployment config
|   +-- requirements.txt      # Python dependencies
|-- frontend/
|   |-- src/
|   |   |-- api/              # HTTP client (Axios)
|   |   |-- components/       # UI components
|   |   |   |-- Auth/         # Login, registration
|   |   |   |-- Chat/         # Conversational interface
|   |   |   |-- Charts/       # Chart gallery & rendering
|   |   |   |-- Dashboard/    # Dashboard builder
|   |   |   |-- Database/     # Schema explorer
|   |   |   |-- Knowledge/    # KB pairs & system instructions
|   |   |   |-- Settings/     # Brand config & preferences
|   |   |   +-- WriteOperations/  # NL write interface
|   |   |-- contexts/         # React context providers
|   |   |-- store/            # Zustand state management
|   |   |-- pages/            # Route-level page components
|   |   +-- types/            # TypeScript type definitions
|   |-- vercel.json           # Vercel deployment config
|   +-- package.json          # Node.js dependencies
|-- database/                 # SQL scripts & seed data
|-- mcp-config/               # MCP server configurations
|-- .github/workflows/        # CI/CD pipeline
|-- .env.example              # Environment variable template
+-- PRD.md                    # Product Requirements Document
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat/query` | Chat text-to-SQL query |
| `POST` | `/api/chat/query/stream` | Streaming chat with SSE |
| `GET` | `/api/chat/history/{session_id}` | Conversation history |
| `GET` | `/api/chat/providers` | Available LLM providers |
| `POST` | `/api/charts/save` | Save chart to gallery |
| `GET` | `/api/charts` | List saved charts |
| `GET/PUT/DELETE` | `/api/charts/{id}` | CRUD operations on charts |
| `GET` | `/api/database/status` | Database connection status |
| `POST` | `/api/database/connect-string` | Connect to a database |
| `GET` | `/api/database/tables` | List database tables |
| `GET` | `/api/database/schema/{table}` | Table schema details |
| `GET` | `/api/database/preview/{table}` | Preview table data |

---

## License

Proprietary — EY AI Engineering. All rights reserved.
