# DataChat BI Platform - Guida Completa di Test

> Questo documento serve come checklist operativa per testare tutte le funzionalita
> dell'applicazione. Per ogni sezione, seguire i passi nell'ordine indicato e annotare
> eventuali problemi nella colonna "Esito".

---

## 0. PRE-REQUISITI

Prima di iniziare il test:

1. Verificare di avere accesso con **account Admin** (admin@datachat.local)
2. Verificare che il backend Railway sia up (check health endpoint)
3. Verificare che il DB Supabase sia connesso (icona verde nella sidebar o in Settings)
4. Verificare che le 3 tabelle siano visibili: `fact_orders`, `dim_products`, `inventory_snapshot`
5. Tenere aperta la console browser (F12 > Console) per catturare errori JS

| Check | Esito | Note |
|-------|-------|------|
| Login admin funzionante | | |
| Backend health OK | | |
| DB connesso | | |
| Tabelle visibili | | |

---

## 1. AUTENTICAZIONE e GESTIONE UTENTI

### 1.1 Login/Logout

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 1.1.1 | Login admin | Inserire admin@datachat.local + password, Login | | |
| 1.1.2 | Login con credenziali errate | Inserire email corretta + password sbagliata, verificare messaggio errore | | |
| 1.1.3 | Logout | Cliccare logout nella sidebar, verificare redirect a login | | |
| 1.1.4 | Sessione persistente | Dopo login, ricaricare la pagina (F5), verificare che si resti loggati | | |

### 1.2 Admin Panel - Gestione Utenti

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 1.2.1 | Creare utente Analyst | Admin Panel, Crea utente: analyst@test.com, password "test123", ruolo Analyst | | |
| 1.2.2 | Creare utente User | Admin Panel, Crea utente: user@test.com, password "test123", ruolo User | | |
| 1.2.3 | Modifica ruolo | Cambiare ruolo di analyst@test.com da Analyst a User, poi tornare ad Analyst | | |
| 1.2.4 | Disattivare utente | Disattivare user@test.com, verificare che non possa piu loggare | | |
| 1.2.5 | Riattivare utente | Riattivare user@test.com, verificare che possa loggare di nuovo | | |
| 1.2.6 | Email duplicata | Provare a creare un utente con email gia esistente, verificare errore | | |

### 1.3 RBAC - Permessi per Ruolo

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 1.3.1 | Visibilita menu Admin | Login come Admin, verificare: Chat, Charts Gallery, Dashboard, Knowledge, Instructions, Views, Write Ops, Admin Panel, Settings tutti visibili | | |
| 1.3.2 | Visibilita menu Analyst | Login come Analyst, verificare: Chat, Charts Gallery, Dashboard, Knowledge, Instructions, Views, Write Ops visibili. Admin Panel NON visibile | | |
| 1.3.3 | Visibilita menu User | Login come User, verificare: Chat, Charts Gallery, Dashboard visibili. Knowledge, Instructions, Write Ops, Admin Panel NON visibili | | |

---

## 2. CHAT CON I DATI

### 2.1 Query Semplici (singola tabella, nessun JOIN)

Testare ciascuna domanda e verificare: risposta testuale corretta, SQL generato sensato, dati coerenti.

| # | Domanda | Tipo atteso | Esito | Note |
|---|---------|-------------|-------|------|
| 2.1.1 | "Quanti ordini ci sono in totale?" | KPI numerico | | |
| 2.1.2 | "Qual e il valore totale delle vendite?" | KPI numerico | | |
| 2.1.3 | "Qual e il valore medio degli ordini?" | KPI numerico | | |
| 2.1.4 | "Quante righe ci sono nella tabella fact_orders?" | KPI numerico | | |
| 2.1.5 | "Mostrami i primi 10 ordini" | Tabella | | |
| 2.1.6 | "Quanti prodotti ci sono nel catalogo?" | KPI numerico | | |
| 2.1.7 | "Qual e il prezzo medio dei prodotti?" | KPI numerico | | |
| 2.1.8 | "Mostrami tutti i magazzini disponibili" | Tabella | | |

### 2.2 Query con Aggregazione e GROUP BY

| # | Domanda | Chart atteso | Esito | Note |
|---|---------|--------------|-------|------|
| 2.2.1 | "Vendite per categoria di prodotto" | Bar chart | | |
| 2.2.2 | "Numero di ordini per segmento cliente" | Bar/Pie chart | | |
| 2.2.3 | "Vendite per modalita di spedizione" | Bar/Pie chart | | |
| 2.2.4 | "Distribuzione degli ordini per stato consegna" | Pie chart | | |
| 2.2.5 | "Top 10 citta per fatturato" | Bar chart (orizzontale) | | |
| 2.2.6 | "Top 5 prodotti piu venduti per quantita" | Bar chart | | |
| 2.2.7 | "Stock totale per magazzino" | Bar chart | | |

### 2.3 Query Temporali (trend, serie storiche)

| # | Domanda | Chart atteso | Esito | Note |
|---|---------|--------------|-------|------|
| 2.3.1 | "Andamento delle vendite nel tempo per mese" | Line chart | | |
| 2.3.2 | "Vendite per anno" | Bar/Line chart | | |
| 2.3.3 | "Vendite per trimestre" | Bar/Line chart | | |
| 2.3.4 | "Andamento del numero di ordini mensile" | Line chart | | |
| 2.3.5 | "Vendite giornaliere nell'ultimo anno disponibile" | Line chart | | |

### 2.4 Query con JOIN (multi-tabella)

| # | Domanda | Chart atteso | Esito | Note |
|---|---------|--------------|-------|------|
| 2.4.1 | "Top 10 prodotti per fatturato con nome prodotto" | Bar chart | | |
| 2.4.2 | "Vendite e stock per categoria di prodotto" | Bar chart | | |
| 2.4.3 | "Prodotti sotto il punto di riordino con nome e categoria" | Tabella | | |
| 2.4.4 | "Quantita venduta per categoria e anno" | Bar/Line chart | | |
| 2.4.5 | "Confronto tra prezzo unitario e vendite totali per prodotto (top 15)" | Scatter chart | | |

### 2.5 Query Complesse (filtri, subquery, condizioni multiple)

| # | Domanda | Esito | Note |
|---|---------|-------|------|
| 2.5.1 | "Quali sono le categorie con vendite superiori a 100000 euro?" | | |
| 2.5.2 | "Mostrami i prodotti che hanno venduto piu della media" | | |
| 2.5.3 | "Vendite per categoria nel 2017 vs 2018" | | |
| 2.5.4 | "Qual e la citta con il valore medio ordine piu alto tra quelle con almeno 50 ordini?" | | |
| 2.5.5 | "Percentuale di ordini consegnati vs non consegnati per modalita di spedizione" | | |
| 2.5.6 | "Andamento mensile delle vendite per la categoria con il fatturato piu alto" | | |
| 2.5.7 | "Per ogni magazzino, mostra i 3 prodotti con stock piu basso" | | |

### 2.6 Query Multi-Visualization

| # | Domanda | Atteso | Esito | Note |
|---|---------|--------|-------|------|
| 2.6.1 | "Dammi una panoramica completa delle vendite: totale vendite, numero ordini, e breakdown per categoria" | KPI + Bar chart | | |
| 2.6.2 | "Mostrami fatturato totale, ordine medio e vendite per segmento cliente" | KPI + chart | | |

### 2.7 Contesto Conversazionale (Follow-up)

Queste domande vanno fatte **in sequenza nella stessa sessione**:

| # | Domanda | Verifica | Esito | Note |
|---|---------|----------|-------|------|
| 2.7.1 | "Vendite per categoria" | Risposta base | | |
| 2.7.2 | "E per anno?" | Deve capire "vendite per anno" dal contesto | | |
| 2.7.3 | "Mostrami solo il 2017" | Deve filtrare i dati per anno 2017 | | |
| 2.7.4 | "Confrontalo con il 2018" | Deve mostrare confronto 2017 vs 2018 | | |
| 2.7.5 | "Qual e la categoria migliore in quel periodo?" | Deve ricordare il contesto temporale | | |

### 2.8 Thinking Steps

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 2.8.1 | Visibilita steps | Fare una query qualsiasi, verificare che appaiano gli step di ragionamento (Schema Analysis, Query Understanding, ecc.) | | |
| 2.8.2 | Espandibilita | Cliccare su ogni step, verificare che si espanda mostrando i dettagli | | |
| 2.8.3 | Timing | Verificare che ogni step mostri la durata | | |

### 2.9 Suggested Follow-ups

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 2.9.1 | Presenza suggerimenti | Dopo una risposta, verificare che appaiano 3 domande suggerite sotto la risposta | | |
| 2.9.2 | Click su suggerimento | Cliccare un suggerimento, verificare che venga inviato come nuova domanda | | |

### 2.10 Cambio LLM Provider

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 2.10.1 | Selezionare Claude Sonnet | Cambiare provider, fare query "Vendite totali", verificare risposta | | |
| 2.10.2 | Selezionare GPT-4.1 | Cambiare provider, fare stessa query, verificare risposta | | |
| 2.10.3 | Selezionare GPT-5.2 | Cambiare provider, fare stessa query, verificare risposta | | |

### 2.11 Input Vocale

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 2.11.1 | Permesso microfono | Cliccare icona microfono, concedere permesso, verificare che inizi la registrazione | | |
| 2.11.2 | Trascrizione | Dire "Quanti ordini ci sono in totale", stop, verificare che il testo appaia nell'input | | |
| 2.11.3 | Invio dopo trascrizione | Dopo la trascrizione, premere invio, verificare che la query venga elaborata | | |
| 2.11.4 | Annullamento | Iniziare registrazione, cliccare di nuovo per annullare, verificare che non invii nulla | | |

---

## 3. CHARTS GALLERY

### 3.1 Salvataggio Chart dalla Chat

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 3.1.1 | Salvataggio base | In Chat, fare "Vendite per categoria", cliccare il pulsante Salva chart, inserire titolo e descrizione, Salva | | |
| 3.1.2 | Salvataggio con titolo custom | Salvare un altro chart con titolo personalizzato "Test Vendite Mensili" | | |
| 3.1.3 | Verifica in Gallery | Andare in Charts Gallery, verificare che i chart salvati appaiano | | |

### 3.2 Visualizzazione Gallery

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 3.2.1 | Grid view | Verificare che i chart appaiano in griglia con preview | | |
| 3.2.2 | Apertura dettaglio | Cliccare su un chart, verificare che si apra il dettaglio con chart interattivo | | |
| 3.2.3 | Ricerca/filtro | Se presente, usare la barra di ricerca per filtrare i chart | | |

### 3.3 Modifica Parametri Chart

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 3.3.1 | Modifica granularita temporale | Aprire un chart temporale (vendite per mese), se visibili i parametri, cambiare granularita da mese a trimestre, verificare aggiornamento | | |
| 3.3.2 | Modifica LIMIT | Su un chart con top-N, modificare il parametro LIMIT (es. da 10 a 5), verificare aggiornamento | | |
| 3.3.3 | Modifica filtro anno | Se presente filtro anno, cambiare l'anno, verificare che i dati si aggiornino | | |

### 3.4 Modifica Chart via Natural Language (dalla Chat)

Per questi test, generare prima un chart in chat, poi usare le richieste di modifica:

| # | Domanda iniziale | Modifica NL | Verifica | Esito | Note |
|---|------------------|-------------|----------|-------|------|
| 3.4.1 | "Vendite per categoria" | "Mostrami solo le top 3 categorie" | Il chart si aggiorna con solo 3 barre | | |
| 3.4.2 | "Vendite mensili" | "Mostrami solo il 2017" | Il chart filtra per anno 2017 | | |
| 3.4.3 | "Vendite per categoria" | "Cambia in pie chart" | Il tipo di grafico cambia da bar a pie | | |
| 3.4.4 | "Top 10 prodotti per vendite" | "Mostrami in migliaia di euro (K)" | I valori vengono divisi per 1000 | | |
| 3.4.5 | "Vendite mensili nel 2017" | "Aggiungi le etichette ai valori" | Le etichette appaiono sulle barre/punti | | |

### 3.5 Eliminazione Chart

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 3.5.1 | Eliminare un chart | In Gallery, cliccare elimina su un chart, confermare, verificare che scompaia dalla lista | | |

---

## 4. DASHBOARDS

### 4.1 Creazione Dashboard via NL

| # | Descrizione NL | Charts attesi | Esito | Note |
|---|----------------|---------------|-------|------|
| 4.1.1 | "Dashboard panoramica vendite con vendite totali, vendite per categoria, trend mensile e top 10 prodotti" | circa 4 charts (KPI + bar + line + bar) | | |
| 4.1.2 | "Dashboard inventario: stock per magazzino, prodotti sotto soglia riordino, stock per categoria" | circa 3 charts | | |
| 4.1.3 | "Dashboard logistica: ordini per stato consegna, ordini per modalita spedizione, trend ordini mensili" | circa 3 charts | | |

### 4.2 Visualizzazione Dashboard

| # | Test | Verifica | Esito | Note |
|---|------|----------|-------|------|
| 4.2.1 | Layout griglia | Verificare che i charts siano disposti in griglia 2 colonne | | |
| 4.2.2 | Interattivita charts | Hover sui charts, verificare tooltip, zoom, pan | | |
| 4.2.3 | Brand colors | Verificare che i colori del brand siano applicati ai charts | | |

### 4.3 Global Filters

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 4.3.1 | Filtri disponibili | Aprire una dashboard, verificare che appaiano filtri (date, categoria, ecc.) | | |
| 4.3.2 | Filtro data | Applicare un filtro data, verificare che TUTTI i charts si aggiornino | | |
| 4.3.3 | Filtro categorico | Applicare un filtro categorico (es. segmento), verificare aggiornamento cross-chart | | |
| 4.3.4 | Reset filtri | Rimuovere i filtri, verificare che i charts tornino allo stato originale | | |

### 4.4 Dashboard CRUD

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 4.4.1 | Salvataggio | Dopo generazione, salvare la dashboard con un nome | | |
| 4.4.2 | Lista dashboards | Verificare che appaia nella lista delle dashboard salvate | | |
| 4.4.3 | Caricamento | Selezionare una dashboard salvata, verificare che i charts si carichino | | |
| 4.4.4 | Modifica nome | Modificare il nome della dashboard, salvare, verificare | | |
| 4.4.5 | Eliminazione | Eliminare una dashboard, verificare che scompaia dalla lista | | |

---

## 5. KNOWLEDGE BASE

### 5.1 Question-SQL Pairs

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 5.1.1 | Salvataggio da Chat | In Chat fare "Vendite per categoria", cliccare "Salva in KB", verificare che la coppia domanda-SQL venga salvata | | |
| 5.1.2 | Visualizzazione KB | Andare in Knowledge Base, verificare che le coppie salvate appaiano in lista | | |
| 5.1.3 | Creazione manuale | Cliccare "Aggiungi coppia", inserire domanda: "Revenue per quarter" e SQL: SELECT DATE_TRUNC('quarter', order_date) as quarter, SUM(sales) FROM fact_orders GROUP BY 1 ORDER BY 1, Salva | | |
| 5.1.4 | Modifica coppia | Selezionare una coppia, modificare la query SQL, Salva, verificare aggiornamento | | |
| 5.1.5 | Eliminazione coppia | Eliminare una coppia, verificare che scompaia | | |
| 5.1.6 | Efficacia RAG | Dopo aver salvato coppie, tornare in Chat e fare una domanda simile, verificare che la SQL generata sia influenzata dagli esempi in KB | | |

### 5.2 System Instructions

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 5.2.1 | Creazione istruzione globale | Andare in Instructions, Crea nuova, Tipo: Globale, Testo: "Arrotonda sempre i valori monetari a 2 decimali", Salva | | |
| 5.2.2 | Creazione istruzione topic | Crea nuova, Tipo: Topic, Topic: "vendite", Testo: "Quando si parla di vendite, usa sempre SUM(sales) e mostra il risultato in euro", Salva | | |
| 5.2.3 | Verifica istruzione globale | In Chat, fare qualsiasi query con valori monetari, verificare che siano arrotondati a 2 decimali | | |
| 5.2.4 | Verifica istruzione topic | In Chat, fare "Vendite totali", verificare che la risposta menzioni l'euro | | |
| 5.2.5 | Modifica istruzione | Modificare il testo di un'istruzione, Salva | | |
| 5.2.6 | Eliminazione istruzione | Eliminare un'istruzione, verificare che scompaia | | |

---

## 6. SQL VIEWS

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 6.1 | Creazione View da Chat | In Chat fare "Top 10 prodotti per vendite", cliccare "Salva come View", nome: v_top_products, Salva | | |
| 6.2 | Verifica in Schema | Andare in Database Schema, verificare che v_top_products appaia tra le viste | | |
| 6.3 | Query sulla View | In Chat fare "Mostrami tutti i dati dalla vista v_top_products" | | |
| 6.4 | Lista Views | Andare nella sezione Views, verificare che la view appaia in lista | | |
| 6.5 | Eliminazione View | Eliminare la view, verificare che scompaia sia dalla lista che dallo schema browser | | |
| 6.6 | Nome non valido | Provare a creare una view con nome "SELECT" o con spazi, verificare errore di validazione | | |

---

## 7. WRITE OPERATIONS

ATTENZIONE: Queste operazioni modificano i dati nel database. Procedere con cautela.

### 7.1 Whitelist Configuration (fare PRIMA di testare le write ops)

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 7.1.1 | Visualizzare tabelle disponibili | Andare in Write Operations, Whitelist, verificare che le tabelle del DB appaiano | | |
| 7.1.2 | Aggiungere tabella a whitelist | Aggiungere inventory_snapshot alla whitelist con colonna current_stock_qty | | |
| 7.1.3 | Verifica whitelist | La tabella/colonna appare nella lista whitelist | | |

### 7.2 Generazione e Esecuzione Write

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 7.2.1 | Generazione UPDATE | Scrivere: "Aggiorna la quantita in stock del prodotto con id 1 a 500 nel magazzino principale", verificare SQL generato | | |
| 7.2.2 | Anteprima SQL | Verificare che il SQL venga mostrato per conferma PRIMA dell'esecuzione | | |
| 7.2.3 | Esecuzione confermata | Confermare l'esecuzione, verificare successo e righe modificate | | |
| 7.2.4 | Verifica dati | In Chat fare "Mostra lo stock del prodotto con id 1", verificare che il valore sia 500 | | |

### 7.3 Sicurezza Write Operations

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 7.3.1 | Blocco DELETE | Scrivere: "Elimina tutti gli ordini del 2015", verificare che venga BLOCCATO | | |
| 7.3.2 | Blocco DROP | Scrivere: "Elimina la tabella fact_orders", verificare che venga BLOCCATO | | |
| 7.3.3 | Blocco TRUNCATE | Scrivere: "Svuota la tabella inventory_snapshot", verificare che venga BLOCCATO | | |
| 7.3.4 | Blocco tabella non in whitelist | Provare a fare UPDATE su una tabella NON in whitelist, verificare blocco | | |
| 7.3.5 | Blocco bulk UPDATE | Scrivere: "Aggiorna tutti i prezzi dei prodotti aumentandoli del 10%", verificare che richieda conferma extra (UPDATE senza WHERE) | | |

### 7.4 Audit Log

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 7.4.1 | Visualizzazione log | Andare in Audit Log, verificare che le operazioni precedenti appaiano | | |
| 7.4.2 | Dettagli log | Verificare che ogni entry abbia: utente, azione, SQL, timestamp, righe affected | | |
| 7.4.3 | Paginazione | Se ci sono molte entries, verificare che la paginazione funzioni | | |

---

## 8. DATABASE SCHEMA BROWSER

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 8.1 | Lista tabelle | Verificare che fact_orders, dim_products, inventory_snapshot siano visibili | | |
| 8.2 | Dettaglio colonne | Cliccare su fact_orders, verificare: tutte le colonne con tipo, nullable, PK/FK | | |
| 8.3 | Foreign keys | Verificare che product_id in fact_orders mostri il riferimento a dim_products | | |
| 8.4 | Preview dati | Cliccare "Preview" su dim_products, verificare che mostra le prime righe | | |
| 8.5 | Row count | Verificare che il conteggio righe sia visibile per ogni tabella | | |

---

## 9. BRAND CONFIGURATION

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 9.1 | Modifica colore primario | Settings, Brand, cambiare colore primario (es. #1a237e), Salva | | |
| 9.2 | Modifica colore secondario | Cambiare colore secondario, Salva | | |
| 9.3 | Aggiungere accent colors | Inserire 3-4 colori accent separati da virgola, Salva | | |
| 9.4 | Cambiare font | Selezionare un font diverso (es. Montserrat), Salva | | |
| 9.5 | Verifica su chart | Tornare in Chat, fare una query con chart, verificare che colori e font del brand siano applicati | | |
| 9.6 | Verifica su dashboard | Aprire/generare una dashboard, verificare brand colors su tutti i charts | | |
| 9.7 | Preview | Verificare che le anteprime colore/font in Settings siano corrette | | |

---

## 10. SETTINGS

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 10.1 | Stato connessione DB | Verificare che lo stato mostri "Connesso" con info del DB | | |
| 10.2 | Cambio LLM provider | Cambiare provider LLM, verificare che la selezione persista dopo refresh | | |
| 10.3 | Connessione Supabase | Se non connesso via OAuth, provare la connessione manuale con connection string | | |

---

## 11. UI/UX GENERALE

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 11.1 | Sidebar collapse | Cliccare toggle sidebar, verificare che si comprima/espanda correttamente | | |
| 11.2 | Navigazione | Navigare tra tutte le sezioni, verificare che non ci siano errori di routing | | |
| 11.3 | Loading states | Durante le query, verificare che appaiano spinner/indicatori di caricamento | | |
| 11.4 | Errori di rete | Disattivare internet momentaneamente, fare una query, verificare messaggio errore user-friendly | | |
| 11.5 | Responsive | Ridimensionare la finestra, verificare che il layout si adatti (se previsto) | | |
| 11.6 | Refresh pagina | Su ogni sezione, fare F5, verificare che lo stato si mantenga | | |

---

## 12. SESSIONI CHAT

| # | Test | Passi | Esito | Note |
|---|------|-------|-------|------|
| 12.1 | Nuova sessione | Creare una nuova sessione chat | | |
| 12.2 | Switch sessione | Passare da una sessione all'altra, verificare che la history sia separata | | |
| 12.3 | Eliminazione sessione | Eliminare una sessione, verificare che scompaia | | |
| 12.4 | Titolo sessione | Verificare che il titolo della sessione si aggiorni dopo la prima domanda | | |

---

## TEMPLATE PER ANNOTARE I FIX

Usare questo template per ogni problema trovato:

**[SEZIONE] - [TEST #] - [TITOLO BREVE]**
- Severita: Critico / Alto / Medio / Basso
- Tipo: Bug / Miglioramento / Nuova Feature
- Descrizione: ...
- Passi per riprodurre: ...
- Comportamento atteso: ...
- Comportamento attuale: ...
- Screenshot: (se applicabile)
- Console errors: (se presenti)

---

## RIEPILOGO ESECUZIONE TEST

| Sezione | Tot. Test | Passati | Falliti | Da verificare |
|---------|-----------|---------|---------|---------------|
| 1. Autenticazione | 13 | | | |
| 2. Chat con i Dati | 35 | | | |
| 3. Charts Gallery | 9 | | | |
| 4. Dashboards | 12 | | | |
| 5. Knowledge Base | 11 | | | |
| 6. SQL Views | 6 | | | |
| 7. Write Operations | 12 | | | |
| 8. Schema Browser | 5 | | | |
| 9. Brand Config | 7 | | | |
| 10. Settings | 3 | | | |
| 11. UI/UX | 6 | | | |
| 12. Sessioni Chat | 4 | | | |
| **TOTALE** | **123** | | | |