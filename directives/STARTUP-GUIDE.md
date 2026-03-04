# DataChat BI Platform - Guida Avvio Applicazione

## Prerequisiti

- **Python 3.10+** con virtual environment in `backend/venv/`
- **Node.js 18+** con dipendenze installate in `frontend/node_modules/`
- **File `.env`** configurato nella root del progetto (vedi `.env.example`)
- **Supabase** (o PostgreSQL locale) accessibile con le credenziali nel `.env`

## Avvio Rapido

### 1. Terminare eventuali processi precedenti

```powershell
# Trova e termina processi sulla porta 8000 (backend)
netstat -ano | findstr :8000 | findstr LISTENING
# Per ogni PID trovato:
taskkill /PID <PID> /F /T

# Trova e termina processi sulla porta 5173 (frontend)
netstat -ano | findstr :5173 | findstr LISTENING
# Per ogni PID trovato:
taskkill /PID <PID> /F /T
```

### 2. Avviare il Backend (FastAPI + Uvicorn)

```powershell
# IMPORTANTE: il working directory deve essere backend/
# perche' config.py cerca ../.env (relativo a backend/)
Set-Location "C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend"

# Avvio in background (detached)
Start-Process -FilePath "venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--reload" `
  -WorkingDirectory "C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend" `
  -NoNewWindow

# Oppure in foreground (per vedere i log):
& "venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Verifica:** `http://localhost:8000/health` deve rispondere `{"status":"healthy"}`

### 3. Avviare il Frontend (Vite + React)

```powershell
Set-Location "C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\frontend"

# Avvio in background (detached)
Start-Process -FilePath "npm" -ArgumentList "run","dev" `
  -WorkingDirectory "C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\frontend" `
  -NoNewWindow

# Oppure in foreground (per vedere i log):
npm run dev
```

**Verifica:** `http://localhost:5173` deve mostrare il Setup Wizard

### 4. Aprire l'applicazione

Aprire nel browser: **http://localhost:5173**

L'app mostrera' il **Setup Wizard** (4 step):
1. Seleziona sorgente dati (PostgreSQL / Supabase)
2. Inserisci credenziali di connessione
3. Seleziona tabelle da utilizzare
4. Seleziona provider AI (Claude / GPT-4.1 / GPT-5.2)

## Note Importanti

### Il Setup Wizard appare sempre al riavvio del backend

Il backend NON mantiene lo stato della connessione DB tra un riavvio e l'altro.
Quando il backend si avvia, resetta automaticamente lo stato della connessione.
Il frontend controlla lo stato del backend e, se non connesso, pulisce il localStorage
e mostra il Setup Wizard da zero.

**Questo e' il comportamento voluto**: ogni riavvio del backend richiede una nuova
configurazione della connessione DB tramite il wizard.

### Percorso .env

Il file `backend/app/config.py` cerca il `.env` in `../.env` (relativo al working directory).
Per questo motivo il backend **deve** essere avviato con working directory = `backend/`.
Se usi `--app-dir backend` dalla root, il `.env` non viene trovato e i provider LLM non si inizializzano.

### Porte utilizzate

| Servizio | Porta | URL |
|----------|-------|-----|
| Backend API | 8000 | http://localhost:8000 |
| Frontend | 5173 | http://localhost:5173 |
| Supabase Pooler | 6543 | (connessione DB) |

### Endpoint utili per debug

| Endpoint | Descrizione |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/database/status` | Stato connessione DB |
| `GET /api/internal/architecture` | Info architettura |
| `GET /api/internal/vanna-status` | Stato Vanna RAG |
| `POST /api/database/disconnect` | Disconnetti DB manualmente |

## Troubleshooting

### "LLM Provider initialization failed"
Il `.env` non e' stato trovato. Verifica che il working directory sia `backend/`.

### Porta gia' in uso (Errno 10048)
Un processo precedente non e' stato terminato. Usa `netstat -ano | findstr :8000`
per trovare il PID e `taskkill /PID <PID> /F /T` per terminarlo.

### Il wizard non appare (entro direttamente nell'app)
Il backend ha ancora una connessione attiva da un precedente avvio.
Termina **tutti** i processi Python (`tasklist | findstr python`) e riavvia.
Usa `/T` nel taskkill per terminare anche i processi figli.