# PRD - DataChat BI Platform

## 1. Informazioni Generali
- **Nome Progetto**: DataChat BI Platform (Natural Language Business Intelligence POC)
- **Versione PRD**: 2.1
- **Data**: 4 Marzo 2026
- **Versione POC Attuale**: 0.5.0
- **Team**: EY AI Engineering
- **Repository**: `ai_engineer_poc_orchestrator/`

## 2. Vision e Obiettivi

### Vision
Piattaforma di Generative BI installabile on-premise presso il cliente che permette a utenti non tecnici di interagire in linguaggio naturale con la propria infrastruttura dati, ottenendo insight, grafici, query SQL e dashboard interattive, con la possibilita' di addestrare progressivamente il sistema tramite knowledge base aziendale.

### Obiettivo Principale
Creare un prodotto di Generative BI che:
1. Interroghi database aziendali in linguaggio naturale (text-to-SQL) e tramite comando vocale
2. Generi automaticamente visualizzazioni interattive e insight allineati al branding del cliente
3. Si auto-migliori tramite knowledge base di coppie domanda-SQL e istruzioni aziendali
4. Permetta la creazione di viste materializzate SQL e operazioni di scrittura autorizzate sul DB del cliente
5. Offra dashboard generabili in linguaggio naturale con filtri globali interattivi
6. Gestisca account utente con livelli di autorizzazione differenziati (Admin, Analyst, User)

### Metriche di Successo
| Metrica | Target | Stato Attuale |
|---------|--------|---------------|
| Latenza NL -> SQL -> Chart | < 10 secondi | ~5-8s (raggiunto) |
| Accuratezza SQL generato | > 90% | In validazione benchmark |
| Cambio parametro chart | < 5 secondi | ~2-3s (raggiunto) |
| Tempo di setup iniziale | < 5 minuti | ~3 min via Setup Wizard |

## 3. Stato Attuale del POC (v0.5.0)

### 3.1 Architettura Implementata

**Pattern**: Hybrid Architecture - Vanna RAG + MCP Server + Multi-Provider LLM

```
Frontend (React 18 + TypeScript + Vite)
    |
    | REST API (HTTP)
    |
Backend (FastAPI + Uvicorn)
    |
    |--- Chat Orchestrator (session management, streaming)
    |--- Vanna RAG Engine (ChromaDB + Azure Embeddings)
    |--- Multi-Provider LLM Manager (Claude / GPT-4.1 / GPT-5.2)
    |--- MCP PostgreSQL Client (query + schema inspection)
    |--- Chart Service (auto-detection tipo + Plotly config)
    |--- Metadata Service (SQLAlchemy + PostgreSQL JSONB)
    |
Database Layer
    |--- Supabase PostgreSQL (dati cliente)
    |--- ChromaDB locale (RAG embeddings)
```

### 3.2 Funzionalita' Implementate

| Funzionalita' | Stato | Note |
|----------------|-------|------|
| Setup Wizard (4 step) | Completato | Selezione sorgente, credenziali, tabelle, provider AI |
| Connessione PostgreSQL / Supabase | Completato | Con pooler e connection string |
| Visualizzazione schema database | Completato | Tabelle, colonne, tipi dati, preview dati |
| Chat conversazionale text-to-SQL | Completato | Con streaming e reasoning steps |
| Risposta NL + SQL + tabella risultati | Completato | Formattazione Markdown, code highlight |
| Auto-generazione chart Plotly | Completato | Bar, line, pie, scatter, area, histogram |
| Salvataggio chart in Gallery | Completato | CRUD completo con metadata JSONB |
| Charts Gallery | Completato | Griglia con preview, filtri, eliminazione |
| Dashboard Builder | Parziale | Layout drag e drop, pannello controllo da completare |
| Multi-Provider LLM | Completato | Claude (OpenRouter), GPT-4.1 (Azure), GPT-5.2 (Azure) |
| Conversational context | Completato | Rolling window 5 turni per sessione |
| Overview tabelle nella chat | Completato | Mostra struttura tabelle nella risposta |
| Streaming risposte | Completato | Server-Sent Events con reasoning steps |

### 3.3 Stack Tecnologico Attuale

| Componente | Tecnologia | Versione |
|------------|-----------|----------|
| **Backend** | Python + FastAPI + Uvicorn | 3.11 / 0.115.x |
| **Frontend** | React + TypeScript + Vite | 18.x / 5.x / 7.3.x |
| **UI Components** | Tailwind CSS + shadcn/ui | 3.x |
| **Charts** | Plotly.js (frontend) | 2.x |
| **State Management** | Zustand | 4.x |
| **Text-to-SQL** | Vanna 2.0 + ChromaDB | Latest |
| **Embeddings** | Azure OpenAI text-embedding-3-large | - |
| **LLM - Claude** | Anthropic Claude Sonnet 4.6 via OpenRouter | - |
| **LLM - GPT-4.1** | Azure OpenAI GPT-4.1 | - |
| **LLM - GPT-5.2** | Azure OpenAI GPT-5.2 | - |
| **Database** | Supabase PostgreSQL (pooler 6543) | 16.x |
| **ORM** | SQLAlchemy 2.0 | 2.x |

### 3.4 Struttura Progetto

```
ai_engineer_poc_orchestrator/
|-- backend/                        # Backend Python FastAPI
|   |-- app/
|   |   |-- api/                    # Endpoints REST
|   |   |-- services/               # Business logic
|   |   |-- config.py, main.py, dependencies.py
|   |-- venv/
|-- frontend/                       # Frontend React + TypeScript
|   |-- src/
|   |   |-- components/             # UI components per sezione
|   |   |-- api/                    # Client HTTP
|   |   |-- store/                  # Zustand state
|   |   |-- pages/                  # SetupWizard, OAuthCallback
|-- database/                       # SQL scripts
|-- mcp-config/                     # Configurazione MCP servers
|-- directives/                     # Guide sviluppo + STARTUP-GUIDE
|-- .env, .env.example              # Configurazione ambiente
```

### 3.5 Sezioni UI

1. **Chat con i Dati** - Interfaccia conversazionale principale
2. **Charts Gallery** - Galleria grafici salvati
3. **Dashboard** - Builder dashboard (parziale)
4. **Schema DB** - Visualizzazione struttura database
5. **Impostazioni** - Configurazione connessione e provider

### 3.6 Flusso Utente Attuale

1. Avvio app -> Setup Wizard (selezione DB, credenziali, tabelle, provider AI)
2. Chat con i Dati -> domanda NL -> SQL generato -> risultati tabella + chart Plotly
3. Salvataggio chart nella Gallery
4. Visualizzazione Gallery con tutti i grafici salvati
5. Dashboard Builder per comporre layout con grafici salvati

## 4. Roadmap Feature Future

### 4.1 FASE ATTUALE - Stabilizzazione e Benchmark (Priorita': CRITICA)

Obiettivo: validare accuratezza e affidabilita' del text-to-SQL tramite benchmark comparativo con WrenAI.

- Stress test con 40 domande di complessita' crescente
- Fix di tutti i bug e le imprecisioni trovate
- Ottimizzazione prompt e RAG training
- Validazione su tutti e 3 i provider LLM

### 4.2 Knowledge Base - Coppie Domanda-SQL (Priorita': ALTA)

**Riferimento competitor**: WrenAI "Question-SQL Pairs" (Knowledge > Question-SQL pairs)

Sezione dell'applicazione dedicata alla gestione di coppie domanda-SQL che alimentano il training del sistema. Il concetto e' identico a quello di WrenAI: salvare coppie di domande e relative query SQL validate, che il sistema utilizzera' come esempi per migliorare progressivamente l'accuratezza delle query generate.

**Funzionamento**:
- Ad ogni risposta nella chat, l'utente puo' cliccare un pulsante per salvare la coppia (domanda, SQL generato) nella Knowledge Base
- La query SQL e' **modificabile dall'utente** prima del salvataggio: l'utente puo' correggere o ottimizzare la query per allinearla alle best practice aziendali
- La pagina Knowledge Base mostra l'elenco di tutte le coppie salvate, con possibilita' di modifica e cancellazione
- Queste coppie vengono usate dal sistema RAG (Vanna + ChromaDB) come esempi di training per le query future
- Il sistema impara progressivamente come l'organizzazione scrive SQL, generando query sempre piu' allineate alle aspettative del cliente

**Valore**: il sistema funziona anche senza questa feature, ma la Knowledge Base permette un addestramento incrementale che migliora significativamente l'accuratezza nel tempo.

### 4.3 Istruzioni di Sistema (Priorita': ALTA)

**Riferimento competitor**: WrenAI "Instructions" (Knowledge > Instructions)

Sezione complementare alla Knowledge Base dove l'utente puo' inserire e salvare istruzioni testuali che guidano il sistema nella generazione delle query SQL.

**Tipi di istruzioni**:
- **Istruzioni Globali**: si applicano a tutte le query (es. "Usa sempre LEFT JOIN invece di INNER JOIN", "Arrotonda i valori monetari a 2 decimali", "Filtra sempre gli ordini con status diverso da cancelled")
- **Istruzioni per Argomento**: si applicano solo a domande che corrispondono a determinati pattern (es. "Quando si parla di fatturato, usa sempre SUM(sales) e non COUNT", "Per le analisi temporali, usa DATE_TRUNC")

**Funzionamento**:
- L'utente accede alla sezione Istruzioni dalla pagina Knowledge
- Puo' aggiungere, modificare ed eliminare istruzioni
- Le istruzioni vengono incluse nel prompt del sistema come contesto aggiuntivo
- Il sistema le utilizza per generare SQL che rispetti le regole di business e le convenzioni aziendali

**Valore**: migliora l'accuracy delle query, riduce le correzioni manuali, e permette di codificare le regole di business in modo che il sistema le rispetti automaticamente.

### 4.4 Viste Materializzate SQL (Priorita': MEDIA)

**Riferimento competitor**: WrenAI "Save as View" (dalla chat)

Dalla sezione Chat con i Dati, l'utente puo' salvare una query SQL come vista direttamente sul database del cliente.

**Funzionamento**:
- Nella chat, dopo una risposta con SQL, l'utente clicca "Salva come Vista"
- Si apre un modale dove l'utente assegna un nome alla vista, visualizza e modifica lo SQL, e clicca "Salva"
- Il sistema crea la vista SQL direttamente sul database del cliente tramite il server MCP
- La vista appare nello schema del database e puo' essere usata nelle query successive
- La vista viene anche registrata nella metadata interna dell'applicazione per tracking

**Valore**: permette di materializzare query ricorrenti come viste SQL riutilizzabili, migliorando le performance e creando un layer semantico progressivo sul database del cliente.

### 4.5 Gestione Account e Autorizzazioni (Priorita': ALTA)

Sistema di autenticazione e autorizzazione per l'installazione on-premise presso il cliente.

**Funzionamento**:
- Ogni installazione ha un set di account con username e password
- L'accesso all'applicazione richiede login
- Gestione sessioni utente (login, logout, scadenza sessione)
- Pagina di amministrazione per creare, modificare, disabilitare account

**Livelli di autorizzazione**:
- **Admin**: accesso completo, gestione account, operazioni di scrittura sul DB, configurazione sistema
- **Analyst**: accesso a chat, knowledge base, viste, dashboard, operazioni di scrittura limitate sul DB (es. UPDATE su campi specifici, ma no DELETE, TRUNCATE, DROP)
- **User** (base): solo lettura, chat con i dati, visualizzazione dashboard e grafici, no operazioni di scrittura sul DB

**Valore**: requisito fondamentale per il deploy on-premise. Ogni cliente avra' utenti con permessi diversi in base al ruolo aziendale.

### 4.6 Brand Guidelines del Cliente (Priorita': MEDIA)

Sezione dell'applicazione per configurare l'identita' visiva del cliente, applicata a tutti i grafici e le dashboard generate dal sistema.

**Funzionamento**:
- Sezione dedicata nelle Impostazioni dove l'utente configura:
  - Palette colori primari e secondari (es. colori aziendali)
  - Font family preferito
  - Logo aziendale (opzionale, per header dashboard)
  - Stile grafici di default (es. bordi arrotondati, ombreggiature, trasparenze)
- Il sistema applica automaticamente queste impostazioni a:
  - Tutti i chart generati nella chat con i dati
  - Tutti i grafici nella Charts Gallery
  - Le dashboard esportate
- Le brand guidelines vengono salvate nel database e caricate all'avvio

**Valore**: i grafici generati sono immediatamente presentabili in contesti aziendali senza bisogno di riformattazione manuale. Il cliente vede i propri colori e il proprio branding in ogni output.

### 4.7 Operazioni di Scrittura sul DB in Linguaggio Naturale (Priorita': MEDIA)

Sezione dedicata dell'applicazione che permette di effettuare modifiche ai dati del database del cliente tramite linguaggio naturale, con livelli di sicurezza e autorizzazione.

**Funzionamento**:
- Sezione separata dalla chat di lettura (per evitare operazioni accidentali)
- L'utente descrive la modifica in linguaggio naturale (es. "Cambia il prezzo del prodotto webcamera a 600 euro")
- Il sistema genera la query SQL di modifica (UPDATE, INSERT)
- La query viene mostrata all'utente per conferma PRIMA dell'esecuzione
- Solo dopo conferma esplicita, la query viene eseguita sul DB tramite MCP
- Log completo di tutte le operazioni effettuate (audit trail)

**Operazioni consentite** (configurabili per ruolo):
- UPDATE su campi specifici (es. prezzo, categoria, nome prodotto)
- INSERT di nuovi record
- Creazione di viste SQL

**Operazioni SEMPRE bloccate** (hardcoded, nessun ruolo puo' eseguirle):
- DELETE, TRUNCATE, DROP TABLE, DROP SCHEMA, ALTER TABLE DROP COLUMN
- Qualsiasi operazione DDL distruttiva

**Sicurezza**:
- Whitelist di tabelle e colonne modificabili (configurabile dall'admin)
- Doppia conferma per operazioni bulk (UPDATE senza WHERE specifico)
- Audit log con utente, timestamp, query eseguita, righe modificate
- Possibilita' di rollback (log delle modifiche precedenti)

**Valore**: l'utente non deve mai entrare direttamente nel database per modifiche operative. Tutto avviene tramite linguaggio naturale con sicurezza integrata.

### 4.8 Interazione Vocale - Speech-to-Text (Priorita': MEDIA)

Possibilita' di interagire con il sistema tramite comandi vocali, sia nella chat con i dati sia nella sezione di modifica dati.

**Modello**: OpenAI Whisper (disponibile su Azure AI Foundry)
- Supporta **99 lingue incluso l'italiano** con buona accuratezza
- Addestrato su 680.000 ore di audio multilingue
- Disponibile come deployment su Azure OpenAI (coerente con lo stack attuale)
- Word Error Rate ~7.4% (Whisper Large V3)

**Funzionamento**:
- Pulsante microfono nell'area di input della chat e della sezione modifiche
- Click per iniziare la registrazione, click per fermarla (oppure voice activity detection)
- L'audio viene inviato al backend -> chiamata API Azure Whisper -> testo trascritto
- Il testo trascritto viene inserito nell'input come se fosse stato digitato
- L'utente puo' modificare il testo prima di inviarlo

**Implementazione tecnica**:
- Frontend: Web Audio API / MediaRecorder per cattura audio dal microfono
- Backend: endpoint `/api/speech/transcribe` che chiama Azure Whisper API
- Formato audio: WAV o WebM (supportati da Whisper)
- Latenza stimata: 1-3 secondi per trascrizione di frasi brevi

**Valore**: rende l'applicazione ancora piu' accessibile, soprattutto per utenti che preferiscono parlare piuttosto che digitare. Differenziante rispetto ai competitor che offrono solo input testuale.

### 4.9 Dashboard Avanzata con Generazione in Linguaggio Naturale (Priorita': MEDIA)

Evoluzione della dashboard attuale. L'obiettivo NON e' sostituire Power BI, ma offrire un sistema semplice e NL-driven per creare dashboard operative.

**Stato attuale**: layout drag e drop con grafici dalla Gallery, pannello di controllo laterale (parzialmente funzionante).

**Evoluzioni previste**:

**A. Generazione Dashboard in linguaggio naturale**:
- L'utente puo' descrivere la dashboard desiderata in linguaggio naturale (es. "Crea una dashboard che mostri i risultati operativi delle vendite, con lo spacchettamento per le top 5 citta' e il fatturato totale")
- Il sistema analizza la richiesta, identifica quali grafici servono, li genera (o li seleziona dalla Gallery se gia' esistenti), e li dispone nella dashboard
- Se un grafico richiesto non esiste nella Gallery, il sistema lo genera automaticamente eseguendo le query necessarie

**B. Selezione manuale dalla Charts Gallery**:
- Modalita' manuale: l'utente seleziona i grafici dalla Gallery e li posiziona nella dashboard
- Pannello di configurazione per personalizzazione (colori, font, dimensioni, titoli)

**C. Filtri globali**:
- Filtri (es. orizzonte temporale, segmento cliente, citta') che si applicano a tutti i grafici contemporaneamente
- Ogni grafico ha una query SQL associata; i filtri globali modificano dinamicamente le clausole WHERE, rieseguono le query e aggiornano i grafici
- Esempio: dashboard con grafici del 2017, l'utente seleziona "Q1 2017", tutte le query si aggiornano

**D. Export**: possibilita' di esportare la dashboard come PDF o immagine

### 4.10 Integrazione Power BI via MCP (Priorita': BASSA - Future)

Spostata a priorita' bassa. Il Microsoft Power BI Modeling MCP Server e' ancora in preview e instabile. Potra' essere ripresa quando sara' stabile.

## 5. Analisi Competitiva e Feature Distintive

### 5.1 Panorama Competitivo 2026

| Soluzione | Tipo | Punti di Forza | Debolezze | Nostro Vantaggio |
|-----------|------|---------------|-----------|------------------|
| **WrenAI** | Open-source | GenBI completo, semantic layer MDL, 12+ DB, knowledge base | Setup complesso, infra dedicata | Setup guidato, multi-provider LLM, dashboard |
| **ThoughtSpot** | Enterprise SaaS | Search-driven analytics, SpotterAI agent | Molto costoso, lock-in cloud | Costo accessibile, on-premise |
| **Julius AI** | SaaS | No-code, natural language, rapido | Solo cloud, no on-premise | On-premise, dati restano al cliente |
| **Power BI Copilot** | Microsoft | Integrazione nativa ecosistema MS | Solo Power BI, no cross-database | Cross-database, vendor-independent |
| **Tableau AI** | Salesforce | Agentic analytics, visualizzazioni | Costoso, enterprise-only | Piu' accessibile, conversational |
| **Upsolve AI** | SaaS (YC W24) | Customer-facing analytics | Solo cloud, focus embedding | On-premise, uso interno |
| **Powerdrill Bloom** | SaaS | No-code, smart insights | Solo cloud, limitato | Knowledge base, viste SQL |

### 5.2 Elementi Differenzianti

1. **Installazione on-premise**: dati non escono dal perimetro aziendale (requisito enterprise, banche, PA)
2. **Multi-Provider LLM configurabile**: Claude, GPT-4.1, GPT-5.2, possibilita' modelli self-hosted
3. **Knowledge Base con apprendimento incrementale**: coppie domanda-SQL + istruzioni personalizzate
4. **Viste materializzate su DB cliente**: costruzione progressiva di un semantic layer
5. **Dashboard NL-driven con filtri globali**: generazione dashboard in linguaggio naturale + filtri cross-query
6. **Architettura MCP-first**: estensibilita' a nuovi database senza modificare il core
7. **Interazione vocale**: speech-to-text tramite Whisper per input in linguaggio naturale (italiano e multilingue)
8. **Operazioni di scrittura NL con sicurezza**: modifica dati DB in linguaggio naturale con autorizzazioni per ruolo
9. **Brand guidelines integrate**: grafici e dashboard automaticamente allineati all'identita' visiva del cliente
10. **Gestione account e ruoli**: sistema di autenticazione con livelli di autorizzazione (Admin, Analyst, User)

### 5.3 Feature Proposte per Sviluppi Futuri

| Feature | Ispirazione | Valore | Complessita' |
|---------|-------------|--------|-------------|
| **Feedback loop thumbs up/down** | WrenAI, ThoughtSpot | L'utente valuta le risposte, il sistema impara | Bassa |
| **Suggerimenti domande contestuali** | WrenAI, Julius AI | Domande follow-up dopo ogni risposta | Bassa |
| **Scheduled reports via email** | ThoughtSpot, Power BI | Dashboard esportata periodicamente | Media |
| **Multi-database support** | WrenAI (12+ DB) | MySQL, SQL Server, BigQuery via MCP | Media |
| **Row-level security** | Vanna 2.0, ThoughtSpot | Filtri automatici per ruolo utente | Media |
| **Semantic layer dichiarativo** | WrenAI MDL, dbt | Metriche e relazioni centralizzate | Alta |
| **Anomaly detection** | ThoughtSpot Spotter | Segnalazione anomalie automatica | Alta |
| **Embedded analytics API** | Upsolve AI, WrenAI | Embeddare grafici in app terze | Alta |
| **NL to Python** | Julius AI | Analisi statistiche avanzate | Alta |
| **Multi-tenant SSO** | Enterprise | Autenticazione centralizzata | Alta |

## 6. Architettura Tecnica

### 6.1 Database del POC

**Supabase PostgreSQL** - Schema `public`:

| Tabella | Righe | Descrizione |
|---------|-------|-------------|
| `dim_products` | 118 | Anagrafica prodotti (id, nome, categoria, prezzo, immagine) |
| `fact_orders` | 180.519 | Ordini (order_id, product_id, date, sales, qty, delivery, shipping, city, segment) |
| `inventory_snapshot` | 118 | Inventario (product_id, warehouse, stock, reorder_point) |

### 6.2 API Endpoints

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/chat/query` | Chat text-to-SQL |
| POST | `/api/chat/query/stream` | Chat streaming |
| GET | `/api/chat/history/{session_id}` | Storico sessione |
| GET | `/api/chat/providers` | Provider LLM |
| POST | `/api/charts/save` | Salva chart |
| GET | `/api/charts` | Lista chart |
| GET/PUT/DELETE | `/api/charts/{id}` | CRUD chart |
| POST | `/api/charts/{id}/regenerate` | Rigenera chart |
| GET | `/api/database/status` | Stato connessione |
| POST | `/api/database/connect-string` | Connessione DB |
| GET | `/api/database/tables` | Lista tabelle |
| GET | `/api/database/schema/{table}` | Schema tabella |
| GET | `/api/database/preview/{table}` | Preview dati |

## 7. Configurazione e Deploy

### 7.1 Prerequisiti
- Python 3.11+ con virtual environment
- Node.js 18+ con npm
- File `.env` configurato (vedi `.env.example`)
- Accesso a Supabase o PostgreSQL

### 7.2 Avvio Rapido
Seguire `directives/STARTUP-GUIDE.md` per avvio backend (porta 8000) e frontend (porta 5173).

### 7.3 Provider LLM
| Provider | Modello | Configurazione |
|----------|---------|---------------|
| Claude | anthropic/claude-sonnet-4-6 | OpenRouter (`OPENROUTER_API_KEY`) |
| GPT-4.1 | gpt-4.1 | Azure OpenAI (`AZURE_OPENAI_*`) |
| GPT-5.2 | gpt-5.2 | Azure OpenAI (`AZURE_GPT52_*`) |

## 8. Rischi e Mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| Accuratezza SQL < 90% | Alto | Knowledge base, istruzioni, seed training |
| Rate limit LLM | Medio | Multi-provider fallback, retry, caching |
| Performance > 10s | Medio | Viste materializzate, indici, LIMIT |
| Filtri globali dashboard | Medio | Approccio incrementale |
| Dati sensibili | Alto | On-premise, read-only MCP, audit log |

## 9. Glossario

| Termine | Definizione |
|---------|-------------|
| **Text-to-SQL** | Conversione di domande NL in query SQL |
| **RAG** | Retrieval-Augmented Generation - arricchimento prompt con esempi da knowledge base |
| **MCP** | Model Context Protocol - standard comunicazione AI-database |
| **Knowledge Base** | Coppie domanda-SQL e istruzioni per guidare la generazione SQL |
| **GenBI** | Generative Business Intelligence |

---

*Documento aggiornato al 4 Marzo 2026 - Versione 2.1*
*Allineato allo stato attuale del POC v0.5.0*