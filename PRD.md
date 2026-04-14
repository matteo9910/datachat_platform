# PRD - DataChat BI Platform

## 1. Informazioni Generali
- **Nome Progetto**: DataChat BI Platform (Natural Language Business Intelligence)
- **Versione PRD**: 3.0
- **Data**: 7 Aprile 2026
- **Versione POC Attuale**: 0.6.0
- **Team**: EY AI Engineering
- **Repository**: `datachat_bi/`

## 2. Vision e Obiettivi

### Vision
Piattaforma di Generative BI installabile on-premise che trasforma il modo in cui le PMI italiane accedono e analizzano i propri dati aziendali. DataChat BI elimina la dipendenza da estrazioni manuali, fogli Excel e competenze tecniche, permettendo a qualsiasi stakeholder — dal responsabile operations al CEO — di interrogare i dati aziendali in linguaggio naturale e ottenere risposte in pochi secondi.

### Proposta di Valore Fondamentale

**Per PMI con database esistente (Scenario A):**
Connessione diretta al DB aziendale e interrogazione immediata via chat in linguaggio naturale. Audit automatico della qualita dei dati, knowledge base incrementale, grafici e report generati istantaneamente.

**Per PMI con solo ERP/gestionale (Scenario B e C):**
Connessione diretta al gestionale o importazione automatizzata da cartelle predefinite. Creazione automatica di un data warehouse su PostgreSQL con storicizzazione dei dati. Sync schedulato che mantiene i dati sempre aggiornati. Il cliente ottiene un DWH strutturato come asset aziendale, interrogabile in linguaggio naturale.

### Il Problema che Risolviamo

Nelle PMI italiane (50M-500M EUR fatturato), l'iter tipico per ottenere un dato e:
1. Accedere al gestionale (SAP, Zucchetti, ecc.)
2. Configurare i parametri dell'estrazione
3. Esportare in CSV/Excel
4. Riformattare il file (colonne, formati date, ecc.)
5. Creare formule, pivot, colonne calcolate
6. Ottenere finalmente il dato

Questo processo richiede da 30 minuti a diverse ore per ogni singola analisi. Con DataChat BI, lo stesso dato si ottiene in 5 secondi con una domanda in linguaggio naturale.

Inoltre, i dati su Excel presentano limiti strutturali: capacita massima ~1M righe, nessuna storicizzazione, nessuna possibilita di analisi cross-anno efficiente. DataChat BI costruisce un data warehouse che supera tutti questi limiti.

### Obiettivi Principali
1. Interrogare dati aziendali in linguaggio naturale (text-to-SQL) e tramite comando vocale
2. Connettere database esistenti (PostgreSQL, Supabase, SQL Server) o gestionali ERP (SAP B1, altri)
3. Creare automaticamente un data warehouse strutturato dai dati del gestionale
4. Sincronizzare i dati dal gestionale con job schedulati configurabili
5. Generare visualizzazioni interattive, grafici e report istantaneamente
6. Permettere l'auto-miglioramento tramite knowledge base incrementale (coppie domanda-SQL + istruzioni)
7. Abilitare analisi storiche (fino a 3 anni di storico rolling) per supporto a budget, forecast, decisioni strategiche
8. Gestire account utente con livelli di autorizzazione e table-level security per business unit

### Metriche di Successo
| Metrica | Target | Stato Attuale |
|---------|--------|---------------|
| Latenza NL -> SQL -> Risultato | < 10 secondi | ~5-8s (raggiunto) |
| Accuratezza SQL generato | > 90% | In validazione |
| Tempo setup connessione DB | < 5 minuti | ~3 min (raggiunto) |
| Tempo setup connessione ERP | < 1 ora (assistito) | Da sviluppare |
| Tempo creazione automatica DWH | < 10 minuti | Da sviluppare |
| Sync incrementale nightly | < 30 minuti | Da sviluppare |

## 3. I Tre Scenari di Utilizzo

### 3.1 Scenario A — Connessione Diretta a Database Esistente

**Cliente tipo**: PMI che ha gia un database, DWH o data mart (PostgreSQL, SQL Server, Supabase, ecc.)

**Flusso**:
1. Setup Wizard: selezione tipo DB, inserimento credenziali, test connessione
2. Selezione tabelle da rendere interrogabili
3. Il sistema analizza lo schema e si connette
4. L'utente interroga i dati via chat in linguaggio naturale
5. Opzionale: DB Audit per valutare la qualita dei dati

**Stato implementazione**: Funzionante per PostgreSQL e Supabase. SQL Server da aggiungere.

### 3.2 Scenario B — Connessione Diretta al Gestionale ERP

**Cliente tipo**: PMI con ERP (SAP Business One, altri) che vuole automazione totale. Non ha un DWH.

**Flusso**:
1. **Connessione al gestionale**: inserimento credenziali API (es. SAP Service Layer: host, user, password, company DB)
2. **Esplorazione entita**: il sistema si collega e mostra le entita disponibili (Ordini, Fatture, Clienti, Prodotti, ecc.) con mapping trasparente transazione SAP → entita API
3. **Selezione entita e configurazione parametri**: per ogni entita selezionata:
   - Campo data di riferimento (es. `DocDate` per ordini) — per sync incrementale
   - Filtri fissi (es. "solo ordini attivi", "solo area vendita 01") — builder visuale campo/operatore/valore
   - Campi da estrarre (selezione colonne)
   - Preview: "Trovate N righe con questi filtri"
4. **Creazione automatica DWH**: il sistema genera automaticamente su PostgreSQL:
   - Tabelle con nomi puliti (snake_case italiano)
   - Indici sulle colonne chiave
   - Relazioni FK dove inferibili
   - Chiavi primarie per UPSERT
5. **Sync iniziale**: prima importazione massiva (storico configurato, es. da 01/01/2023)
6. **Configurazione schedule**: frequenza sync (ogni ora, 6 ore, notte, settimana) + sync manuale "Aggiorna ora"
7. **Utilizzo**: stessa esperienza dello Scenario A — chat NL, grafici, KB, audit

**Configurazione parametri estrazione** (punto critico):
- Le transazioni SAP classiche (VA05, ME21N, ecc.) non corrispondono 1:1 agli endpoint API. Il connettore SAP include un mapping predefinito: "Ordini di Vendita" → endpoint `Orders`, "Fatture" → `Invoices`, ecc.
- Per ogni entita, la UI mostra i campi disponibili (recuperati da API) e un builder di filtri semplice
- Questa configurazione viene fatta dal team EY in fase di setup progetto, non dal cliente autonomamente
- I parametri configurati vengono usati per ogni sync schedulato successivo

**Sync incrementale**:
- Ogni sync usa il campo data + timestamp ultima sync per estrarre solo dati nuovi/modificati
- UPSERT nel DWH (INSERT ON CONFLICT UPDATE) usando la chiave primaria dell'entita
- Log di ogni esecuzione (righe sincronizzate, errori, durata)

**Stato implementazione**: Da sviluppare. Per la demo: connettore SAP Business One via Service Layer REST API.

### 3.3 Scenario C — Importazione da Cartelle Predefinite

**Cliente tipo**: PMI con ERP che non vuole (o non puo) fornire accesso diretto al gestionale. L'utente continua a fare estrazioni manuali ma le organizza in cartelle predefinite.

**Flusso**:
1. **Definizione cartelle**: in fase di setup, si definiscono le cartelle monitorate. Ogni cartella corrisponde a una transazione/entita (es. `/dati/ordini/`, `/dati/fatture/`, `/dati/produzione/`)
2. **Mapping cartella → tabella**: per ogni cartella si configura:
   - Nome tabella DWH di destinazione
   - Mapping colonne (dal CSV/Excel alla tabella)
   - Formato date, encoding, separatore CSV
   - Chiave primaria per deduplicazione
3. **Creazione automatica DWH**: come Scenario B, il sistema crea la struttura PostgreSQL basandosi sulla struttura dei file trovati nelle cartelle
4. **Monitoraggio periodico**: il sistema scansiona periodicamente le cartelle:
   - Rileva file nuovi o modificati
   - Importa i dati nel DWH con UPSERT (no duplicati)
   - Logga l'operazione
5. **Utilizzo**: stessa esperienza degli altri scenari

**Guida al cliente**: forniamo istruzioni su come organizzare le estrazioni manuali (naming convention file, struttura cartelle, frequenza suggerita).

**Stato implementazione**: Parziale. L'import CSV/Excel manuale esiste (upload singolo file). Da sviluppare: monitoraggio cartelle, import automatico, deduplicazione.

### 3.4 Tabella Comparativa Scenari

| Aspetto | Scenario A | Scenario B | Scenario C |
|---------|------------|------------|------------|
| Connessione | Diretta al DB | Via API gestionale | A cartelle locali/rete |
| Creazione DWH | Non serve | Automatica | Automatica |
| Aggiornamento dati | Live (query diretta) | Sync schedulato automatico | Scansione periodica cartelle |
| Estrazione manuale | No | No | Si (l'utente esporta dal gestionale) |
| Setup | Semplice (~5 min) | Complesso (~1 ora, assistito) | Medio (~30 min, assistito) |
| Manutenzione | Nessuna | Monitoraggio sync | Dipende dalla disciplina utente |
| DWH come asset | No (DB gia esiste) | Si — creato da noi | Si — creato da noi |

## 4. Architettura del Sistema

### 4.1 Architettura Generale

```
                    +---------------------+
                    |    Frontend React    |
                    |  (Chat, Gallery,     |
                    |   Sorgenti Dati,     |
                    |   Audit, Dashboard)  |
                    +----------+----------+
                               |
                          REST API (HTTP)
                               |
                    +----------+----------+
                    |   Backend FastAPI    |
                    +----------+----------+
                               |
          +--------------------+--------------------+
          |                    |                    |
+---------+--------+  +-------+--------+  +--------+---------+
| Chat & NL Engine |  | Sync Engine    |  | Data Quality     |
| - Orchestrator   |  | - ERP Connector|  | - DB Audit       |
| - Vanna RAG      |  | - Folder Watch |  | - Trust Score    |
| - Multi-LLM      |  | - Scheduler    |  | - Schema Analyzer|
| - Chart Service  |  | - DWH Builder  |  |                  |
+------------------+  +-------+--------+  +------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
+---------+------+  +---------+------+  +---------+------+
| DB Diretto     |  | API Gestionale |  | Cartelle       |
| (PostgreSQL,   |  | (SAP Service   |  | (CSV/Excel     |
|  SQL Server,   |  |  Layer, altri) |  |  monitorati)   |
|  Supabase)     |  |                |  |                |
+----------------+  +----------------+  +----------------+
          |                   |                   |
          +-------------------+-------------------+
                              |
                    +---------+---------+
                    |   PostgreSQL DWH   |
                    | (on-prem o cloud)  |
                    | Dati storicizzati  |
                    +-------------------+
```

### 4.2 Componenti Principali

**Chat & NL Engine** (esistente, da mantenere):
- Chat Orchestrator con session management e streaming
- Vanna RAG Engine (ChromaDB + Azure Embeddings) per text-to-SQL
- Multi-Provider LLM Manager (Claude / GPT-4.1 / GPT-5.2)
- Chart Service (auto-detection tipo + Plotly config)
- Trust Score Service (scoring affidabilita 0-100)

**Sync Engine** (da sviluppare):
- ERP Connector: modulo per connessione a gestionali via API (primo: SAP B1 Service Layer)
- Folder Watcher: monitoraggio cartelle per Scenario C
- Scheduler: job periodici per sync incrementale (APScheduler o simile)
- DWH Builder: creazione automatica schema PostgreSQL dalle entita selezionate
- Import Engine: UPSERT incrementale con deduplicazione

**Data Quality** (parzialmente esistente):
- DB Audit: scoring qualita dati su 6 dimensioni (esistente)
- Trust Score: scoring affidabilita per-query (esistente)
- Schema Analyzer: analisi struttura DB per ottimizzazioni

### 4.3 Stack Tecnologico

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
| **Database client** | PostgreSQL / Supabase / SQL Server (da aggiungere) | 16.x |
| **Database DWH** | PostgreSQL (on-prem o cloud) | 16.x |
| **Database sistema** | SQLite o PostgreSQL | - |
| **ORM** | SQLAlchemy 2.0 | 2.x |
| **Scheduler** | APScheduler | 3.x |
| **ERP Connector** | SAP Service Layer REST (OData) | - |

## 5. Funzionalita del Prodotto

### 5.1 Core Features (Implementate)

| Funzionalita | Stato | Descrizione |
|--------------|-------|-------------|
| **Chat con i Dati** | Completato | Interrogazione NL con streaming, reasoning steps, SQL + tabella + grafico |
| **Connessione DB** | Completato | PostgreSQL, Supabase. Da aggiungere: SQL Server |
| **Setup Wizard** | Completato | 4 step: sorgente, credenziali, tabelle, provider AI |
| **Schema DB** | Completato | Visualizzazione tabelle, colonne, tipi dati, preview, relazioni |
| **Multi-Provider LLM** | Completato | Claude, GPT-4.1, GPT-5.2 con switch runtime |
| **Auto-generazione grafici** | Completato | Bar, line, pie, scatter, area, histogram via Plotly |
| **Charts Gallery** | Completato | CRUD completo con metadata, filtri, preview |
| **Knowledge Base** | Completato | Coppie domanda-SQL per training incrementale RAG |
| **Instructions** | Completato | Istruzioni globali e per argomento per guidare generazione SQL |
| **Speech-to-Text** | Completato | Input vocale via Azure AI Speech + Whisper fallback |
| **Write Operations** | Completato | Modifica dati DB in NL con conferma, audit trail, whitelist |
| **Account & Auth** | Completato | Login, ruoli (Admin/Analyst/User), sessioni |
| **Trust Score** | Completato | Scoring affidabilita 0-100 con 4 fattori oggettivi |
| **DB Audit** | Completato | Audit qualita dati su 6 dimensioni con raccomandazioni |
| **Dashboard Builder** | Parziale | Layout drag-and-drop con grafici dalla Gallery |
| **Import CSV/Excel** | Parziale | Upload singolo file con auto-schema. Da evolvere |

### 5.2 Features da Sviluppare (Nuove)

#### A. Connettore ERP — SAP Business One (Priorita: CRITICA)

Connessione diretta a SAP Business One via Service Layer REST API per estrazione automatizzata dei dati.

**Componenti**:
- Modulo connettore SAP B1 (`sap_b1_connector.py`): autenticazione, discovery entita, estrazione dati
- Mapping transazioni SAP → entita API (dizionario predefinito, estensibile)
- Builder filtri per configurazione parametri estrazione per entita
- Gestione sessione SAP (login, session timeout, reconnect)

**Entita SAP B1 supportate in fase iniziale**:
- Orders (Ordini di Vendita)
- Invoices (Fatture di Vendita)
- BusinessPartners (Anagrafica Clienti/Fornitori)
- Items (Anagrafica Prodotti)
- PurchaseOrders (Ordini di Acquisto)
- DeliveryNotes (Documenti di Trasporto)
- CreditNotes (Note di Credito)
- ChartOfAccounts (Piano dei Conti)

Per la demo: utilizzare ambiente SAP B1 demo/sandbox o mock realistico.

#### B. DWH Builder — Creazione Automatica Data Warehouse (Priorita: CRITICA)

Creazione automatica della struttura PostgreSQL a partire dalle entita selezionate (Scenario B) o dai file nelle cartelle (Scenario C).

**Livello di intelligenza**: Medio
- Nomi tabelle e colonne in snake_case italiano pulito
- Indici automatici su chiavi primarie, campi data, FK
- Relazioni FK inferite dove possibile (es. Orders.CardCode → BusinessPartners.CardCode)
- Tipi dati PostgreSQL appropriati (mapping da tipi SAP/CSV)
- Chiave primaria per ogni tabella (per UPSERT incrementale)

**Non incluso in questa fase**: ristrutturazione in star schema, viste aggregate pre-calcolate (evoluzione futura).

#### C. Sync Engine — Scheduler e Sincronizzazione (Priorita: CRITICA)

Motore di sincronizzazione per mantenere il DWH aggiornato.

**Funzionalita**:
- Scheduler configurabile (ogni ora, 6 ore, notte, settimana)
- Sync manuale "Aggiorna ora" da UI
- Sync incrementale basato su campo data (solo dati nuovi/modificati dall'ultima sync)
- UPSERT con chiave primaria (INSERT ON CONFLICT UPDATE)
- Retry automatico in caso di errore
- Log dettagliato per ogni esecuzione (timestamp, righe sincronizzate, errori, durata)

**Per Scenario B**: il sync si collega al gestionale via API, estrae con i parametri configurati, fa UPSERT nel DWH.

**Per Scenario C**: il sync scansiona le cartelle, rileva file nuovi/modificati, importa con deduplicazione.

#### D. Folder Watcher — Monitoraggio Cartelle (Priorita: ALTA)

Per Scenario C: monitoraggio periodico di cartelle predefinite contenenti export CSV/Excel dal gestionale.

**Funzionalita**:
- Configurazione cartelle monitorate (percorso, mapping a tabella DWH, formato file)
- Scansione periodica (stessa frequenza del sync scheduler)
- Rilevamento file nuovi/modificati (basato su nome file + data modifica + hash)
- Import automatico dei file rilevati con UPSERT
- Gestione errori (file corrotto, formato inatteso, colonne mancanti)
- Log delle operazioni

#### E. Connettore SQL Server (Priorita: ALTA)

Aggiunta supporto SQL Server come database sorgente per Scenario A.

**Implementazione**: MCP client per SQL Server (pattern identico a PostgreSQL).

#### F. Table-Level Security (Priorita: ALTA)

Controllo di accesso a livello di tabella/business unit.

**Funzionalita**:
- L'admin configura quali tabelle sono visibili per ogni ruolo/utente
- In fase di setup: associazione business unit → tabelle DWH
- Il sistema filtra automaticamente lo schema visibile in base all'utente loggato
- La chat NL genera SQL solo sulle tabelle autorizzate per l'utente

**Esempio**: L'utente HR vede solo `dipendenti`, `presenze`, `cedolini`. L'utente Operations vede `ordini`, `produzione`, `inventario`.

#### G. Retention Policy — Pulizia Dati Storici (Priorita: MEDIA)

Job automatico per eliminare dati piu vecchi di N anni (default: 3 anni rolling).

**Funzionalita**:
- Configurabile per tabella (alcune tabelle es. anagrafica clienti: per sempre)
- Job periodico (settimanale o mensile)
- Log delle righe eliminate
- Warning prima della prima esecuzione

### 5.3 Features Esistenti da Mantenere

| Feature | Note |
|---------|------|
| Chat con i Dati | Core del prodotto, invariato |
| Trust Score | Differenziante, invariato |
| Knowledge Base | Essenziale per accuratezza incrementale, invariato |
| Instructions | Regole di business, invariato |
| Charts Gallery | Invariato |
| Speech-to-Text | Effetto wow in demo, invariato |
| DB Audit & Quality | Promosso a voce propria in sidebar, molto utile per Scenario A |
| Write Operations | Differenziante, invariato |
| Account & Auth | Base per table-level security |
| Dashboard Builder | Mantenuto com'e per ora, non prioritario |
| Viste Materializzate | Ancora piu utile con DWH, manteniamo |

### 5.4 Features Deprioritizzate

| Feature | Motivazione |
|---------|-------------|
| Brand Guidelines | Nice-to-have, non essenziale per vendere. Futura. |
| Dashboard NL-driven | La dashboard builder manuale e sufficiente per ora |
| Alerting/Anomaly Detection | Troppo complessa per questa fase. Futura. |
| Power BI via MCP | MCP Power BI ancora instabile. Futura. |

## 6. Interfaccia Utente

### 6.1 Sidebar (nuova organizzazione)

```
- Chat con i Dati          (tutti gli utenti)
- Charts Gallery            (tutti gli utenti)
- Dashboard                 (tutti gli utenti)
- Sorgenti Dati            (admin, analyst) — ex "Importa Dati"
- Schema DB                 (tutti gli utenti)
- Audit Dati               (admin, analyst) — ex sottosezione di Schema DB
- Knowledge Base            (admin, analyst) — include Instructions come tab
- Write Operations          (admin, analyst)
- Impostazioni             (admin)
- Admin Panel              (admin) — include table-level security
```

### 6.2 Sezione "Sorgenti Dati" (nuova)

Sostituisce la vecchia "Importa Dati". Contiene:

**Tab 1 — Connessioni Attive**:
- Lista delle sorgenti dati configurate (DB diretto, ERP, cartelle)
- Per ogni sorgente: stato (verde/rosso), ultima sync, prossima sync, righe totali
- Bottone "Aggiorna ora" per sync manuale
- Alert se un sync e fallito

**Tab 2 — Configura Nuova Sorgente**:
- Scelta tipo: "Database Esistente" / "Gestionale ERP" / "Cartelle File"
- Per DB: wizard connessione (esistente)
- Per ERP: wizard connessione API + selezione entita + config parametri + schedule
- Per Cartelle: definizione percorsi + mapping cartella→tabella + schedule scansione

**Tab 3 — Storico Sync**:
- Log di tutte le sincronizzazioni eseguite
- Per ogni sync: timestamp, sorgente, righe sincronizzate, durata, eventuali errori

**Tab 4 — Import Manuale**:
- Upload singolo file CSV/Excel (funzionalita esistente, mantenuta come fallback)

### 6.3 Flusso Demo

**Parte 1 — "Hai gia un database"** (~3 min):
1. Connessione a PostgreSQL con dati demo
2. Chat: "Quali sono le top 5 citta per fatturato?" → risposta in 5 secondi con grafico
3. Trust Score visibile, salvataggio in KB
4. DB Audit: score qualita dati con raccomandazioni

**Parte 2 — "Hai solo un gestionale"** (~5 min):
5. Connessione a SAP B1 (demo/mock): credenziali → il sistema mostra entita disponibili
6. Selezione entita (Ordini, Fatture, Clienti) con configurazione parametri/filtri
7. Creazione automatica DWH: le tabelle PostgreSQL si creano automaticamente
8. Sync iniziale: i dati fluiscono dal gestionale al DWH
9. Chat sugli stessi dati: stessa esperienza dello Scenario A

**Parte 3 — "Il sistema lavora per te"** (~2 min):
10. Dashboard sync: "ultima sync 6 ore fa, prossima stanotte alle 02:00"
11. "E domani mattina avrete i dati aggiornati senza fare nulla"
12. Menzione: "Se preferite non dare accesso al gestionale, potete organizzare i file in cartelle e il sistema li importa automaticamente"

## 7. Modello Dati Sistema

### 7.1 Tabelle System DB (esistenti)

| Tabella | Descrizione |
|---------|-------------|
| `users` | Account utente con ruoli |
| `sessions` | Sessioni di login |
| `saved_charts` | Grafici salvati nella Gallery |
| `import_history` | Storico import manuali |
| `audit_reports` | Report audit qualita dati |

### 7.2 Tabelle System DB (da aggiungere)

| Tabella | Descrizione |
|---------|-------------|
| `data_sources` | Sorgenti dati configurate (tipo, credenziali criptate, stato) |
| `sync_jobs` | Definizione job di sync (sorgente, entita, parametri, frequenza, schedule) |
| `sync_runs` | Storico esecuzioni sync (timestamp, righe, errori, durata) |
| `erp_entity_configs` | Configurazione per entita ERP (mapping campi, filtri, chiave primaria) |
| `folder_watches` | Cartelle monitorate per Scenario C (percorso, mapping, formato) |
| `table_permissions` | Table-level security (utente/ruolo → tabelle autorizzate) |

### 7.3 Migrazioni Alembic necessarie

| Migrazione | Tabelle | Dipendenza |
|-----------|---------|------------|
| `0005_add_data_sources.py` | `data_sources`, `sync_jobs`, `sync_runs` | `0004` |
| `0006_add_erp_configs.py` | `erp_entity_configs`, `folder_watches` | `0005` |
| `0007_add_table_permissions.py` | `table_permissions` | `0006` |

## 8. API Endpoints

### 8.1 Esistenti

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| POST | `/api/chat/query` | Chat text-to-SQL |
| POST | `/api/chat/query/stream` | Chat streaming |
| GET | `/api/chat/history/{session_id}` | Storico sessione |
| POST | `/api/database/connect-string` | Connessione DB |
| GET | `/api/database/tables` | Lista tabelle |
| GET | `/api/database/schema/{table}` | Schema tabella |
| POST | `/api/charts/save` | Salva chart |
| GET | `/api/charts` | Lista chart |
| POST | `/api/imports/upload` | Upload file CSV/Excel |
| POST | `/api/imports/confirm` | Conferma import |
| GET | `/api/imports/history` | Storico import |
| POST | `/api/database/audit/run` | Esegui audit qualita |
| POST | `/api/speech/transcribe` | Speech-to-text |
| POST | `/api/write/execute` | Write operation |
| POST | `/api/auth/login` | Login |
| GET | `/api/admin/users` | Lista utenti |

### 8.2 Da Aggiungere

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| **Sorgenti Dati** | | |
| GET | `/api/sources` | Lista sorgenti configurate con stato |
| POST | `/api/sources` | Crea nuova sorgente (DB, ERP, cartella) |
| PUT | `/api/sources/{id}` | Modifica sorgente |
| DELETE | `/api/sources/{id}` | Rimuovi sorgente |
| POST | `/api/sources/{id}/test` | Test connessione |
| **ERP** | | |
| POST | `/api/erp/connect` | Connessione a gestionale |
| GET | `/api/erp/entities` | Lista entita disponibili dal gestionale connesso |
| GET | `/api/erp/entities/{entity}/fields` | Campi disponibili per un'entita (per filtri) |
| POST | `/api/erp/entities/{entity}/preview` | Preview dati con filtri (per test configurazione) |
| **Sync** | | |
| POST | `/api/sync/jobs` | Crea job di sync |
| GET | `/api/sync/jobs` | Lista job configurati |
| PUT | `/api/sync/jobs/{id}` | Modifica job |
| POST | `/api/sync/jobs/{id}/run` | Esegui sync manuale "Aggiorna ora" |
| GET | `/api/sync/runs` | Storico esecuzioni |
| **DWH** | | |
| POST | `/api/dwh/build` | Crea/aggiorna struttura DWH dalle entita configurate |
| GET | `/api/dwh/status` | Stato DWH (tabelle, righe, ultimo aggiornamento) |
| **Folder Watch** | | |
| POST | `/api/folders/watch` | Aggiungi cartella monitorata |
| GET | `/api/folders/watches` | Lista cartelle monitorate |
| POST | `/api/folders/watches/{id}/scan` | Forza scansione cartella |
| **Table Security** | | |
| GET | `/api/admin/table-permissions` | Lista permessi tabella |
| PUT | `/api/admin/table-permissions` | Aggiorna permessi |

## 9. Connettore SAP Business One — Dettaglio Tecnico

### 9.1 SAP B1 Service Layer

SAP Business One espone un Service Layer REST (OData) per l'accesso programmatico.

**Autenticazione**:
```
POST https://{host}:50000/b1s/v1/Login
Body: {"CompanyDB": "SBODemo", "UserName": "manager", "Password": "***"}
Response: {"SessionId": "..."}
```

**Discovery entita**: `GET /b1s/v1/$metadata` → schema OData con tutte le entita disponibili

**Estrazione dati con filtri**:
```
GET /b1s/v1/Orders?$filter=DocDate ge '2024-01-01'&$select=DocNum,DocDate,CardCode,DocTotal&$top=100&$skip=0
```

**Paginazione**: `$top` + `$skip` per batch. Default batch size: 500 righe.

### 9.2 Mapping Transazioni SAP → Entita API

| Transazione SAP | Entita API | Endpoint |
|-----------------|-----------|----------|
| VA01/VA05 (Ordini vendita) | Orders | `/b1s/v1/Orders` |
| VF01 (Fatture vendita) | Invoices | `/b1s/v1/Invoices` |
| XD01 (Anagrafica clienti) | BusinessPartners | `/b1s/v1/BusinessPartners` |
| MM01 (Anagrafica materiali) | Items | `/b1s/v1/Items` |
| ME21N (Ordini acquisto) | PurchaseOrders | `/b1s/v1/PurchaseOrders` |
| VL01N (Consegne) | DeliveryNotes | `/b1s/v1/DeliveryNotes` |
| VF11 (Note credito) | CreditNotes | `/b1s/v1/CreditNotes` |

### 9.3 Demo SAP

Per la demo: simulare il Service Layer con un mock server che risponde allo stesso schema OData con dati realistici generati. In futuro: test su ambiente SAP B1 Trial su SAP BTP.

## 10. Retention e Storicizzazione

### 10.1 Policy di Retention

- **Default**: 3 anni rolling
- **Configurabile per tabella**: alcune tabelle (es. anagrafica clienti) possono avere retention illimitata
- **Job di pulizia**: settimanale, elimina righe con data > soglia configurata
- **Log**: ogni pulizia viene loggata (tabella, righe eliminate, data soglia)

### 10.2 Valore della Storicizzazione

Il DWH costruito da DataChat diventa un asset aziendale:
- Analisi storiche cross-anno per budget e forecast
- Superamento limiti Excel (~1M righe)
- Dati strutturati e normalizzati vs export grezzi
- Base per collegamento con strumenti BI esterni (Power BI, Tableau, Looker)

## 11. Sicurezza

### 11.1 Autenticazione e Autorizzazione

| Livello | Permessi |
|---------|----------|
| **Admin** | Tutto: gestione utenti, configurazione sorgenti, table-level security, write operations, audit |
| **Analyst** | Chat, KB, Instructions, viste, grafici, import manuale, write operations limitato |
| **User** | Solo lettura: chat, grafici, dashboard |

### 11.2 Table-Level Security

- Configurazione admin: associazione utente/ruolo → tabelle visibili
- Filtering automatico: il motore NL-to-SQL vede solo le tabelle autorizzate
- Scenario: HR vede solo tabelle HR, Operations vede solo tabelle Operations

### 11.3 Credenziali ERP

- Credenziali gestionale criptate nel system DB (AES-256 o simile)
- Mai visibili in chiaro nell'UI dopo il primo inserimento
- Accesso alle credenziali limitato al servizio sync (non esposto via API)

## 12. Analisi Competitiva

### 12.1 Posizionamento

DataChat BI si posiziona in uno spazio unico: **GenBI + ERP Integration + DWH auto-generato** per PMI italiane.

| Soluzione | GenBI | Connessione ERP | Creazione DWH | On-Premise | Target |
|-----------|-------|-----------------|--------------|------------|--------|
| **DataChat BI** | Si | Si (SAP B1+) | Si (automatico) | Si | PMI italiane |
| WrenAI | Si | No | No | Si (self-hosted) | Developer-friendly |
| ThoughtSpot | Si | Parziale (via ETL) | No | No (cloud) | Enterprise |
| Julius AI | Si | No | No | No (SaaS) | Consumer/SMB |
| Power BI Copilot | Si | Via connettori MS | No | No (cloud) | Enterprise MS |
| Fivetran/Airbyte | No | Si (100+ connettori) | No (solo ETL) | Parziale | Data engineering |

**Differenziante chiave**: nessun competitor offre GenBI + connessione ERP diretta + creazione automatica DWH in un unico prodotto. Fivetran/Airbyte fanno ETL ma non hanno chat NL. WrenAI/ThoughtSpot hanno chat NL ma non si collegano ai gestionali.

### 12.2 Elementi Differenzianti Aggiornati

1. **Connessione diretta ERP con creazione DWH automatica** — unico nel mercato
2. **Sync schedulato che storicizza i dati** — il DWH come asset aziendale
3. **Installazione on-premise** — dati non escono dal perimetro aziendale
4. **Multi-Provider LLM configurabile** — Claude, GPT-4.1, GPT-5.2
5. **Knowledge Base incrementale** — il sistema migliora con l'uso
6. **Trust Score** — scoring affidabilita oggettivo per ogni risposta
7. **DB Audit & Data Quality** — audit automatico unico nel mercato
8. **Speech-to-text** — interazione vocale in italiano
9. **Write Operations sicure** — modifica dati in NL con audit trail
10. **Table-level security** — accesso per business unit
11. **3 scenari flessibili** — si adatta a qualsiasi livello di maturita digitale del cliente

## 13. Rischi e Mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| Accesso API SAP non disponibile dal cliente | Alto | Scenario C (cartelle) come fallback; connessione diretta al DB sottostante |
| Complessita configurazione parametri estrazione | Alto | Setup assistito dal team EY; builder filtri intuitivo; preview dati in tempo reale |
| Performance sync con milioni di righe | Medio | Sync incrementale (solo delta); batch processing; indici ottimizzati |
| Accuratezza SQL su schema complesso (30-50 tabelle) | Alto | Knowledge base ricca; istruzioni specifiche per dominio; Trust Score per trasparenza |
| Variabilita tra installazioni ERP (ogni SAP e diverso) | Medio | Connettore configurabile; mapping personalizzabile per cliente |
| Retention dati e GDPR | Medio | Policy configurabile; log eliminazioni; consenso in fase contrattuale |

## 14. Glossario

| Termine | Definizione |
|---------|-------------|
| **Text-to-SQL** | Conversione di domande in linguaggio naturale in query SQL |
| **RAG** | Retrieval-Augmented Generation — arricchimento prompt con esempi da knowledge base |
| **DWH** | Data Warehouse — database strutturato per analisi storiche |
| **Sync incrementale** | Sincronizzazione che trasferisce solo dati nuovi/modificati dall'ultima esecuzione |
| **UPSERT** | INSERT + UPDATE: inserisce righe nuove, aggiorna quelle esistenti (basato su chiave primaria) |
| **Service Layer** | API REST di SAP Business One per accesso programmatico ai dati |
| **Table-Level Security** | Controllo di accesso che limita la visibilita delle tabelle per utente/ruolo |
| **Folder Watcher** | Servizio che monitora cartelle per rilevare nuovi file da importare |
| **GenBI** | Generative Business Intelligence |
| **MCP** | Model Context Protocol — standard comunicazione AI-database |

---

*Documento aggiornato al 7 Aprile 2026 - Versione 3.0*
*Riflette la nuova visione prodotto con 3 scenari (DB diretto, ERP, Cartelle) e creazione automatica DWH*
