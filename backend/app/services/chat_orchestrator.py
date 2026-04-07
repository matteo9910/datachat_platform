"""
Chat Orchestrator - Gestione conversazione multi-turno con context
Orchestrazione workflow: NL -> Vanna SQL -> Execute -> NL response generation
"""

import logging
import uuid
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.vanna_service import get_vanna_service
from app.services.llm_provider import get_llm_provider_manager
from app.services.chart_service import create_chart_service
from app.services.metadata_service import metadata_service
from app.dependencies import SessionLocal
from app.config import settings
from app.database import get_system_session_factory
from app.models.system import Instruction, InstructionType

logger = logging.getLogger(__name__)


# In-memory session storage (POC, production usa Redis)
_sessions: Dict[str, List[Dict[str, Any]]] = {}


class ChatOrchestrator:
    """Orchestrazione chat conversazionale con text-to-SQL"""

    def __init__(self, llm_provider: Optional[str] = None):
        """
        Args:
            llm_provider: "claude" | "azure" | None (usa default)
        """
        self.llm_provider = llm_provider or settings.default_llm_provider
        self.vanna = get_vanna_service(llm_provider=self.llm_provider)
        self.chart_service = create_chart_service(llm_provider=self.llm_provider)
        logger.info(f"ChatOrchestrator initialized with provider={self.llm_provider}")

    def _fetch_instructions(self, query: str) -> List[str]:
        """
        Fetch matching instructions from the system DB.

        - Global instructions are always included.
        - Topic instructions are included only when the user's query
          contains the topic keyword (case-insensitive substring match).

        Returns a list of instruction text strings.
        """
        try:
            SystemSession = get_system_session_factory()
            db = SystemSession()
            try:
                all_instructions = db.query(Instruction).all()
                matched: List[str] = []
                query_lower = query.lower()
                for inst in all_instructions:
                    inst_type = inst.type.value if hasattr(inst.type, "value") else str(inst.type)
                    if inst_type == "global":
                        matched.append(inst.text)
                    elif inst_type == "topic" and inst.topic:
                        if inst.topic.lower() in query_lower:
                            matched.append(f"[Topic: {inst.topic}] {inst.text}")
                return matched
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to fetch instructions (non-blocking): {e}")
            return []

    def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        include_chart: bool = True
    ) -> Dict[str, Any]:
        """
        Processa query NL utente con context conversazionale

        Args:
            query: Domanda NL
            session_id: ID sessione (se None, crea nuovo)
            include_chart: Flag generazione chart (Fase 05)

        Returns:
            {
                "session_id": str,
                "nl_response": str,       # Risposta testuale LLM
                "sql": str,
                "results": list[dict],
                "chart": dict | None,     # Fase 05
                "execution_time_ms": float,
                "success": bool,
                "error": str | None,
                "llm_provider": str,
                "llm_stats": dict
            }
        """
        start_time = time.time()

        # Session management
        if not session_id:
            session_id = str(uuid.uuid4())
        
        if session_id not in _sessions:
            _sessions[session_id] = []

        try:
            # 1. Recupera context conversazionale (rolling window 5 turni)
            context = self._get_conversation_context(session_id, window_size=5)

            # 2. Detect se servono multiple query
            from app.services.chart_service import LLMChartSelector
            multi_viz = LLMChartSelector.detect_multi_visualization(query)
            requires_multi_query = multi_viz.get("requires_multiple_queries", False)
            
            logger.info(f"Multi-query detection: requires_multi={requires_multi_query}, viz={multi_viz}")

            # 2b. Fetch active instructions for prompt injection
            instructions = self._fetch_instructions(query)
            if instructions:
                logger.info(f"Injecting {len(instructions)} instructions into SQL generation prompt")

            # 3. Se servono multiple query, genera ed esegui ciascuna
            if requires_multi_query and multi_viz.get("num_visualizations", 1) > 1:
                return self._process_multi_query(
                    query=query,
                    session_id=session_id,
                    multi_viz=multi_viz,
                    include_chart=include_chart,
                    start_time=start_time,
                    instructions=instructions
                )

            # 4. Single query flow (standard)
            sql_result = self.vanna.generate_sql(query, instructions=instructions)

            if not sql_result["success"]:
                return self._error_response(
                    session_id=session_id,
                    query=query,
                    error=sql_result.get("error", "SQL generation failed"),
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            sql = sql_result["sql"]
            llm_stats = {
                "provider": sql_result.get("llm_provider"),
                "latency_ms": sql_result.get("llm_latency_ms"),
                "tokens": sql_result.get("llm_tokens")
            }

            # 5. Esegui SQL
            exec_result = self.vanna.execute_sql(sql)

            if not exec_result["success"]:
                return self._error_response(
                    session_id=session_id,
                    query=query,
                    error=exec_result.get("error", "SQL execution failed"),
                    execution_time_ms=(time.time() - start_time) * 1000,
                    sql=sql,
                    llm_stats=llm_stats
                )

            rows = self._round_float_values(exec_result["rows"])

            # 6. Genera chart (SE include_chart=True e ci sono risultati)
            chart_data = None
            if include_chart and rows:
                try:
                    chart_data = self.chart_service.generate_chart(
                        results=rows,
                        sql=sql,
                        query=query
                    )
                    logger.info(f"Chart generated: type={chart_data['chart_type']}")
                except Exception as e:
                    logger.warning(f"Chart generation failed: {e}")
                    # Continue senza chart (non-blocking error)

            # 5. Genera risposta NL finale
            nl_response = self._generate_nl_response(
                query=query,
                sql=sql,
                results=rows
            )

            # 6. Salva in session context
            self._add_to_context(
                session_id=session_id,
                query=query,
                sql=sql,
                result_count=len(rows),
                nl_response=nl_response
            )

            execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Query processed: session={session_id[:8]}..., "
                f"{len(rows)} rows, {execution_time_ms:.0f}ms, provider={self.llm_provider}"
            )

            # 7. Log query to history (non-blocking)
            self._log_query_history(
                session_id=session_id,
                query=query,
                sql=sql,
                success=True,
                execution_time_ms=int(execution_time_ms),
                result_rows=len(rows)
            )

            # 8. Determina se mostrare il grafico (CR5: solo quando appropriato)
            # Se il chart_service ha deciso "none", rispetta la decisione
            if chart_data and chart_data.get("chart_type") == "none":
                should_show_chart = False
                chart_data = None
            else:
                should_show_chart = self._should_show_chart(query, rows, sql)
            
            # 9. Genera suggested follow-ups (CR3)
            suggested_followups = self._generate_suggested_followups(query, sql, rows)
            
            # 10. Build thinking steps DETTAGLIATI (CR4 migliorato)
            thinking_steps = self._build_detailed_thinking_steps(
                query=query,
                sql=sql,
                sql_result=sql_result,
                exec_result=exec_result,
                rows=rows,
                chart_data=chart_data if should_show_chart else None
            )

            # 11. Compute Trust Score (multi-factor confidence)
            trust_score = None
            trust_grade = None
            trust_factors = None
            try:
                from app.services.trust_score_service import TrustScoreService
                trust_service = TrustScoreService()

                # Get schema DDL and column list for syntactic validation
                schema_ddl = ""
                schema_columns = []
                try:
                    schema_ddl = self.vanna.get_schema_from_mcp()
                    import re
                    schema_columns = re.findall(
                        r'^\s+"?(\w+)"?\s+\w+',
                        schema_ddl, re.MULTILINE
                    )
                except Exception:
                    pass

                trust_result = trust_service.compute_trust_score(
                    sql=sql,
                    question=query,
                    rows=rows,
                    vanna_service=self.vanna,
                    schema_ddl=schema_ddl,
                    schema_columns=schema_columns,
                )
                trust_score = trust_result.score
                trust_grade = trust_result.grade
                trust_factors = trust_result.factors
                logger.info(f"Trust score: {trust_score}/100 ({trust_grade})")
            except Exception as e:
                logger.warning(f"Trust score computation failed (non-blocking): {e}")

            return {
                "session_id": session_id,
                "nl_response": nl_response,
                "sql": sql,
                "results": rows,
                "chart": chart_data if should_show_chart else None,
                "execution_time_ms": execution_time_ms,
                "success": True,
                "error": None,
                "llm_provider": self.llm_provider,
                "llm_stats": llm_stats,
                "thinking_steps": thinking_steps,
                "suggested_followups": suggested_followups,
                "should_show_chart": should_show_chart,
                "trust_score": trust_score,
                "trust_grade": trust_grade,
                "trust_factors": trust_factors,
            }

        except Exception as e:
            logger.error(f"Chat orchestrator error: {e}")
            return self._error_response(
                session_id=session_id,
                query=query,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    def _get_conversation_context(
        self,
        session_id: str,
        window_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recupera ultimi N turni conversazione

        Returns:
            [{"query": str, "sql": str, "result_count": int}, ...]
        """
        if session_id not in _sessions:
            return []
        return _sessions[session_id][-window_size:]

    def _process_multi_query(
        self,
        query: str,
        session_id: str,
        multi_viz: Dict[str, Any],
        include_chart: bool,
        start_time: float,
        instructions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Processa richieste che richiedono MULTIPLE query SQL
        Genera ed esegue query separate per ogni visualizzazione richiesta
        """
        visualizations = multi_viz.get("visualizations", [])
        charts = []
        all_results = []
        all_sqls = []
        llm_stats = {}
        
        for i, viz in enumerate(visualizations):
            viz_desc = viz.get("description", f"Visualizzazione {i+1}")
            sql_hint = viz.get("sql_hint", "")
            chart_type_hint = viz.get("chart_type_hint", "bar")
            
            # Genera sub-query specifica per questa visualizzazione - SOLO UNA QUERY
            sub_query = f"GENERA SOLO UNA SINGOLA QUERY SQL per: {viz_desc}. {sql_hint}. Anno di riferimento dalla domanda originale: {query}"
            
            logger.info(f"Generating SQL for viz {i+1}: {viz_desc}")
            
            sql_result = self.vanna.generate_sql(sub_query, instructions=instructions)
            
            if not sql_result["success"]:
                logger.warning(f"SQL generation failed for viz {i+1}: {sql_result.get('error')}")
                continue
            
            sql = sql_result["sql"]
            
            # Pulisci SQL: prendi solo la prima query se ce ne sono multiple
            if ";" in sql:
                sql_parts = [s.strip() for s in sql.split(";") if s.strip() and s.strip().upper().startswith("SELECT")]
                if sql_parts:
                    sql = sql_parts[0] + ";"
            
            all_sqls.append(sql)
            logger.info(f"SQL for viz {i+1}: {sql[:100]}...")
            
            if i == 0:
                llm_stats = {
                    "provider": sql_result.get("llm_provider"),
                    "latency_ms": sql_result.get("llm_latency_ms"),
                    "tokens": sql_result.get("llm_tokens")
                }
            
            # Esegui la query
            exec_result = self.vanna.execute_sql(sql)
            
            if not exec_result["success"]:
                logger.warning(f"SQL execution failed for viz {i+1}: {exec_result.get('error')}")
                continue
            
            rows = self._round_float_values(exec_result["rows"])
            all_results.extend(rows[:10])  # Primi 10 per ogni query per la risposta NL
            
            # Genera chart per questa visualizzazione
            if include_chart and rows:
                try:
                    from app.services.chart_service import ChartAnalyzer, PlotlyConfigGenerator, LLMChartSelector
                    
                    columns_info = ChartAnalyzer.analyze_results(rows)
                    
                    # Usa hint per chart type o fai detect automatico
                    if chart_type_hint in ['kpi', 'indicator']:
                        chart_type = 'kpi'
                        chart_title = viz_desc
                    else:
                        llm_result = LLMChartSelector.select_chart_type_and_title(
                            viz_desc, columns_info, rows
                        )
                        chart_type = llm_result["chart_type"]
                        chart_title = llm_result["chart_title"]
                    
                    plotly_gen = PlotlyConfigGenerator()
                    plotly_config = plotly_gen.generate_config(
                        results=rows,
                        chart_type=chart_type,
                        columns_info=columns_info,
                        title=chart_title
                    )
                    
                    charts.append({
                        "chart_type": chart_type,
                        "chart_title": chart_title,
                        "plotly_config": plotly_config,
                        "data_focus": viz.get("data_focus", "breakdown"),
                        "sql": sql
                    })
                    
                    logger.info(f"Chart {i+1} generated: type={chart_type}, title={chart_title}")
                    
                except Exception as e:
                    logger.warning(f"Chart generation failed for viz {i+1}: {e}")
        
        # Genera risposta NL combinata
        combined_sql = "\n\n-- Query separate --\n".join(all_sqls)
        nl_response = self._generate_nl_response(
            query=query,
            sql=combined_sql,
            results=all_results
        )
        
        # Salva in context
        self._add_to_context(
            session_id=session_id,
            query=query,
            sql=combined_sql,
            result_count=len(all_results),
            nl_response=nl_response
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Log query
        self._log_query_history(
            session_id=session_id,
            query=query,
            sql=combined_sql,
            success=True,
            execution_time_ms=int(execution_time_ms),
            result_rows=len(all_results)
        )
        
        # Costruisci risposta con charts multipli
        chart_data = None
        if charts:
            chart_data = {
                "chart_type": "multi",
                "chart_title": "Analisi Multipla",
                "plotly_config": charts[0]["plotly_config"] if charts else None,
                "charts": charts,
                "parameters": {},
                "sql_template": combined_sql
            }
        
        return {
            "session_id": session_id,
            "nl_response": nl_response,
            "sql": combined_sql,
            "results": all_results,
            "chart": chart_data,
            "execution_time_ms": execution_time_ms,
            "success": True,
            "error": None,
            "llm_provider": self.llm_provider,
            "llm_stats": llm_stats
        }

    def _add_to_context(
        self,
        session_id: str,
        query: str,
        sql: str,
        result_count: int,
        nl_response: str
    ):
        """Aggiungi turno a session context"""
        if session_id not in _sessions:
            _sessions[session_id] = []

        _sessions[session_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "query": query,
            "sql": sql,
            "result_count": result_count,
            "nl_response": nl_response
        })

        # Limit session storage (max 50 turni, POC)
        if len(_sessions[session_id]) > 50:
            _sessions[session_id] = _sessions[session_id][-50:]

    def _generate_nl_response(
        self,
        query: str,
        sql: str,
        results: List[Dict[str, Any]]
    ) -> str:
        """
        Genera risposta NL finale per utente
        Usa LLM per sintetizzare risultati in risposta user-friendly
        """
        if not results:
            return "La query non ha restituito risultati."

        # Costruisci prompt per LLM
        results_preview = results[:5]  # Prime 5 righe
        results_text = "\n".join([str(row) for row in results_preview])

        # Prepara dati per il LLM (mostra tutti i risultati fino a 20 righe)
        if len(results) <= 20:
            results_text = "\n".join([str(row) for row in results])
        elif len(results) <= 50:
            results_top = results[:15]
            results_bottom = results[-5:]
            results_text = "Prime 15 righe:\n" + "\n".join([str(row) for row in results_top])
            results_text += f"\n\n... ({len(results) - 20} righe omesse) ...\n\nUltime 5 righe:\n" + "\n".join([str(row) for row in results_bottom])
        else:
            results_top = results[:10]
            results_bottom = results[-5:]
            results_text = "Prime 10 righe:\n" + "\n".join([str(row) for row in results_top])
            results_text += f"\n\n... ({len(results) - 15} righe omesse) ...\n\nUltime 5 righe:\n" + "\n".join([str(row) for row in results_bottom])
        
        # Estrai nomi tabelle dalla query SQL per il contesto
        tables_used = self._extract_tables_from_sql(sql)
        tables_str = ", ".join([f"**{t}**" for t in tables_used]) if tables_used else "tabelle del database"
        
        prompt = f"""Sei un analista BI esperto. Devi rispondere alla domanda dell'utente basandoti sui dati.

DOMANDA UTENTE: "{query}"

SQL ESEGUITO:
{sql}

TABELLE UTILIZZATE: {', '.join(tables_used) if tables_used else 'N/A'}

DATI OTTENUTI ({len(results)} righe totali):
{results_text}

=== ISTRUZIONI ===

PRIMA DI RISPONDERE, analizza la domanda dell'utente e decidi:

**TIPO A - DOMANDA DIRETTA**: Se l'utente chiede un valore specifico, un totale, un conteggio, o una informazione puntuale
→ Rispondi in modo BREVE e DIRETTO (2-3 frasi)
→ Inizia con "Per rispondere alla tua domanda, ho utilizzato i dati dalla tabella..." poi dai la risposta

**TIPO B - DOMANDA ANALITICA**: Se l'utente chiede di analizzare, confrontare, vedere distribuzioni, ranking, trend, o capire pattern nei dati
→ Rispondi in modo STRUTTURATO e DETTAGLIATO:
  1. Contesto (1-2 frasi): spiega QUALI dati hai utilizzato, da QUALE tabella, e COME li hai elaborati (somma, conteggio, media, join, filtri temporali, ecc.)
  2. Risultati principali: lista i risultati chiave con valori numerici (top performers, trend, ecc.)
  3. Risultati secondari: se rilevante, mostra anche i bottom performers o altri dati significativi
  4. Insight finale (2-3 frasi): conclusione analitica con pattern, gap, concentrazione, anomalie

=== FORMATO OUTPUT ===

Per TIPO A:
- Inizia SEMPRE con il contesto dei dati usati
- Poi la risposta diretta con il dato in **grassetto**

Per TIPO B:
- Inizia SEMPRE con: "Per rispondere alla tua domanda, ho utilizzato i dati dalla tabella [nome] per [operazione fatta]..."
- Usa **grassetto** per nomi e numeri importanti
- Usa bullet point (- ) per le liste
- Struttura: contesto dati → risultati principali → risultati secondari → insight
- Evidenzia gap tra top e bottom performer
- Nota pattern significativi (concentrazione, dispersione, outlier)
- Includi valori numerici precisi

ESEMPIO TIPO B (ranking semplice):
Per rispondere alla tua domanda, ho utilizzato i dati degli ordini nella tabella **Ordini** per sommare le quantita vendute nel periodo 2015-2018, e l'anagrafica nella tabella **Prodotti** per ottenere il nome dei prodotti.

Ecco i 10 prodotti piu venduti tra il 2015 e il 2018 (per quantita totale venduta):

1. **Perfect Fitness Perfect Rip Deck** — Totale: 75.690 unita
2. **Nike Men's Dri-FIT Victory Golf Polo** — Totale: 62.058 unita
3. **O'Brien Men's Neoprene Life Vest** — Totale: 57.803 unita
4. **Nike Men's Free 5.0+ Running Shoe** — Totale: 35.660 unita
5. **Under Armour Girls' Toddler Spine Surge Running** — Totale: 31.753 unita

In sintesi, il **Perfect Fitness Perfect Rip Deck** domina nettamente con un volume di vendite superiore del 22% rispetto al secondo classificato.

ESEMPIO TIPO B (breakdown con sotto-categorie):
Per rispondere alla tua domanda, ho utilizzato i dati dalla tabella **fact_orders** per sommare le vendite nel periodo 2015-2018, filtrandole per i segmenti Consumer, Corporate e Home Office, e la tabella **dim_products** per ottenere i nomi dei prodotti.

Ecco il confronto delle vendite dei top 10 prodotti tra i segmenti:

1. **Perfect Fitness Perfect Rip Deck** — Totale: 75.690
- Consumer: 28.144
- Corporate: 21.981
- Home Office: 13.573

2. **Nike Men's Dri-FIT Victory Golf Polo** — Totale: 62.058
- Consumer: 32.478
- Corporate: 19.851
- Home Office: 11.177

3. **O'Brien Men's Neoprene Life Vest** — Totale: 57.803
- Consumer: 29.821
- Corporate: 18.029
- Home Office: 9.999

In sintesi, il segmento **Consumer** rappresenta costantemente la quota maggiore di vendite per tutti i prodotti, seguito da **Corporate** e **Home Office**.

REGOLE DI FORMATO:
- Scrivi in italiano
- NON usare emoji
- NON usare intestazioni markdown (#, ##)
- Tono professionale ma accessibile
- SEMPRE inizia spiegando quali dati hai usato e come
- Per elenchi di entita (prodotti, clienti, regioni): usa lista NUMERATA (1. 2. 3.) con nome in **grassetto** e valore totale sulla stessa riga dopo un trattino lungo (—)
- Per sotto-dettagli di ogni entita (es. breakdown per segmento): usa sotto-bullet con trattino "- " indentati SOTTO l'entita numerata, uno per riga
- Lascia SEMPRE una riga vuota tra un'entita numerata e la successiva
- NON mettere tutto su una sola riga separato da pipe o barre verticali
- I numeri con decimali devono avere MASSIMO 2 cifre decimali (es: 1.234,56 non 1.234,5678901)
- Per numeri grandi, usa il separatore delle migliaia con il punto (es: 1.234.567,89)

Risposta:"""

        try:
            llm_manager = get_llm_provider_manager()
            llm_result = llm_manager.complete_text(
                prompt=prompt.strip(),
                provider=self.llm_provider,
                temperature=0.5,
                max_tokens=1200
            )

            nl_response = llm_result["content"].strip()
            return nl_response

        except Exception as e:
            logger.warning(f"NL response generation failed: {e}")
            # Fallback risposta semplice
            return f"Ho trovato {len(results)} risultati per la tua domanda."

    def _log_query_history(
        self,
        session_id: str,
        query: str,
        sql: Optional[str],
        success: bool,
        execution_time_ms: int,
        result_rows: int = 0,
        error_message: Optional[str] = None
    ):
        """Log query to database (non-blocking)"""
        try:
            db = SessionLocal()
            metadata_service.log_query(
                db=db,
                session_id=session_id,
                nl_query=query,
                sql_generated=sql,
                llm_provider=self.llm_provider,
                success=success,
                error_message=error_message,
                execution_time_ms=execution_time_ms,
                result_rows=result_rows
            )
            db.close()
        except Exception as e:
            logger.warning(f"Query history logging failed: {e}")

    def _error_response(
        self,
        session_id: str,
        query: str,
        error: str,
        execution_time_ms: float,
        sql: str = "",
        llm_stats: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Risposta errore standardizzata"""
        # Log failed query
        self._log_query_history(
            session_id=session_id,
            query=query,
            sql=sql if sql else None,
            success=False,
            execution_time_ms=int(execution_time_ms),
            error_message=error
        )
        
        return {
            "session_id": session_id,
            "nl_response": f"Mi dispiace, si e verificato un errore: {error}",
            "sql": sql,
            "results": [],
            "chart": None,
            "execution_time_ms": execution_time_ms,
            "success": False,
            "error": error,
            "llm_provider": self.llm_provider,
            "llm_stats": llm_stats
        }

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Recupera full history sessione"""
        return _sessions.get(session_id, [])

    def clear_session(self, session_id: str) -> bool:
        """Elimina sessione"""
        if session_id in _sessions:
            del _sessions[session_id]
            return True
        return False

    def _should_show_chart(self, query: str, rows: List[Dict], sql: str) -> bool:
        """
        CR5: Determina se mostrare una visualizzazione (grafico O tabella) basandosi sulla query.
        Ritorna True se serve una visualizzazione (il tipo sara' determinato dal chart_service).
        """
        query_lower = query.lower()
        
        # Keywords che indicano bisogno di grafico (bar, line, pie, etc.)
        chart_keywords = [
            'andamento', 'trend', 'nel tempo', 'over time', 'evoluzione',
            'per categoria', 'per regione', 'per mese', 'per anno', 'per giorno',
            'confronto', 'distribuzione', 'ripartizione', 'breakdown',
            'top 10', 'top 5', 'classifica', 'ranking',
            'mostrami', 'visualizza', 'grafico'
        ]
        
        # Keywords che indicano bisogno di TABELLA (non grafico ma visualizzazione tabellare)
        table_keywords = [
            'elenco', 'lista', 'elenca', 'quali sono', 'dammi',
            'mostra tutti', 'tutti i', 'tutte le', 'list', 'show all'
        ]
        
        # Keywords che indicano NO visualizzazione (singolo valore)
        no_visual_keywords = [
            'totale', 'somma', 'quanto costa', 'quanti sono in totale',
            'qual e il', 'quale il', 'what is the', 'how much is',
            'media di', 'average of', 'massimo', 'minimo'
        ]
        
        # Se risultato e singola riga con singolo valore numerico, no visual
        if len(rows) == 1 and len(rows[0]) == 1:
            return False
        
        # Se e' una domanda di elenco/lista, mostra TABELLA
        for kw in table_keywords:
            if kw in query_lower:
                return True  # Ritorna True - il chart_service determinera' che serve una tabella
        
        # Se risultato e singola riga con pochi valori, no visual
        if len(rows) == 1 and len(rows[0]) <= 3:
            return False
        
        # Check keywords positive (grafico SI)
        for kw in chart_keywords:
            if kw in query_lower:
                return True
        
        # Check keywords negative (no visual se singola riga)
        for kw in no_visual_keywords:
            if kw in query_lower and len(rows) <= 1:
                return False
        
        # Default: mostra visual se ci sono piu righe
        return len(rows) > 1

    def _generate_suggested_followups(self, query: str, sql: str, rows: List[Dict]) -> List[str]:
        """
        CR3: Genera suggested follow-ups basati sulla query corrente.
        """
        query_lower = query.lower()
        suggestions = []
        
        # Analizza il tipo di query e suggerisci follow-ups appropriati
        if 'vendite' in query_lower or 'sales' in query_lower:
            if 'tempo' in query_lower or 'mese' in query_lower or 'anno' in query_lower:
                suggestions.extend([
                    "Confronta le vendite per categoria",
                    "Mostra le vendite aggregate per trimestre",
                    "Quali sono i top 5 prodotti per vendite?"
                ])
            elif 'categoria' in query_lower:
                suggestions.extend([
                    "Mostra l'andamento delle vendite nel tempo",
                    "Quali categorie hanno il margine piu alto?",
                    "Confronta le vendite per segmento cliente"
                ])
            else:
                suggestions.extend([
                    "Mostra l'andamento delle vendite nel tempo",
                    "Vendite per categoria di prodotto",
                    "Top 10 prodotti per fatturato"
                ])
        
        elif 'prodotti' in query_lower or 'product' in query_lower:
            suggestions.extend([
                "Quali prodotti hanno lo stock piu basso?",
                "Vendite per categoria di prodotto",
                "Confronta i prezzi medi per categoria"
            ])
        
        elif 'inventario' in query_lower or 'stock' in query_lower:
            suggestions.extend([
                "Prodotti sotto il punto di riordino",
                "Distribuzione dello stock per magazzino",
                "Valore totale dell'inventario"
            ])
        
        else:
            # Suggerimenti generici basati sullo schema
            suggestions.extend([
                "Mostra l'andamento delle vendite nel tempo",
                "Quali sono le top 5 categorie per fatturato?",
                "Analizza la distribuzione degli ordini per citta"
            ])
        
        return suggestions[:3]  # Max 3 suggerimenti

    def _build_detailed_thinking_steps(
        self,
        query: str,
        sql: str,
        sql_result: Dict[str, Any],
        exec_result: Dict[str, Any],
        rows: List[Dict[str, Any]],
        chart_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        CR4 MIGLIORATO: Usa il reasoning REALE dal modello LLM quando disponibile.
        Fallback a analisi a posteriori se il modello non fornisce reasoning.
        """
        thinking_steps = []
        
        # Prova a usare il reasoning dal modello LLM
        llm_reasoning = sql_result.get("reasoning")
        
        if llm_reasoning:
            # ======= USA REASONING REALE DAL MODELLO =======
            return self._build_steps_from_llm_reasoning(
                llm_reasoning=llm_reasoning,
                sql=sql,
                sql_result=sql_result,
                exec_result=exec_result,
                rows=rows,
                chart_data=chart_data
            )
        
        # ======= FALLBACK: Analisi a posteriori =======
        tables_in_query = self._extract_tables_from_sql(sql)
        columns_in_query = self._extract_columns_from_sql(sql)
        
        schema_details = [
            {"title": "Database connesso", "content": "PostgreSQL via MCP Server"},
            {"title": "Tabelle identificate", "content": tables_in_query if tables_in_query else ["Nessuna tabella rilevata"]},
        ]
        
        if columns_in_query:
            schema_details.append({
                "title": "Colonne rilevanti",
                "content": columns_in_query[:10]
            })
        
        thinking_steps.append({
            "step": "schema_analysis",
            "description": f"Analizzato schema DB, identificate {len(tables_in_query)} tabelle rilevanti",
            "status": "completed",
            "duration_ms": int(sql_result.get("llm_latency_ms", 0) * 0.2),
            "details": schema_details
        })
        
        query_intent = self._analyze_query_intent(query)
        
        intent_details = [
            {"title": "Domanda utente", "content": query},
            {"title": "Tipo di analisi", "content": query_intent.get("analysis_type", "Aggregazione dati")},
            {"title": "Metriche richieste", "content": query_intent.get("metrics", ["Non specificate"])},
        ]
        
        if query_intent.get("dimensions"):
            intent_details.append({
                "title": "Dimensioni di raggruppamento",
                "content": query_intent["dimensions"]
            })
        
        if query_intent.get("filters"):
            intent_details.append({
                "title": "Filtri applicati",
                "content": query_intent["filters"]
            })
        
        thinking_steps.append({
            "step": "query_understanding",
            "description": f"Interpretata richiesta: {query_intent.get('analysis_type', 'analisi dati')}",
            "status": "completed",
            "duration_ms": int(sql_result.get("llm_latency_ms", 0) * 0.1),
            "details": intent_details
        })
        
        sql_analysis = self._analyze_sql_structure(sql)
        
        sql_details = [
            {"title": "Query generata", "content": sql},
            {"title": "Tipo operazione", "content": sql_analysis.get("operation_type", "SELECT")},
        ]
        
        if sql_analysis.get("aggregations"):
            sql_details.append({
                "title": "Funzioni di aggregazione",
                "content": sql_analysis["aggregations"]
            })
        
        if sql_analysis.get("group_by"):
            sql_details.append({
                "title": "Raggruppamento (GROUP BY)",
                "content": sql_analysis["group_by"]
            })
        
        if sql_analysis.get("order_by"):
            sql_details.append({
                "title": "Ordinamento",
                "content": sql_analysis["order_by"]
            })
        
        if sql_analysis.get("joins"):
            sql_details.append({
                "title": "Join tra tabelle",
                "content": sql_analysis["joins"]
            })
        
        if sql_analysis.get("where_conditions"):
            sql_details.append({
                "title": "Condizioni WHERE",
                "content": sql_analysis["where_conditions"]
            })
        
        thinking_steps.append({
            "step": "sql_generation",
            "description": f"Costruita query SQL con {len(sql_analysis.get('aggregations', []))} aggregazioni",
            "status": "completed",
            "duration_ms": int(sql_result.get("llm_latency_ms", 0) * 0.7),
            "details": sql_details
        })
        
        # ======= STEP 4: Esecuzione Query =======
        exec_details = [
            {"title": "Righe restituite", "content": str(len(rows))},
            {"title": "Tempo esecuzione", "content": f"{exec_result.get('execution_time_ms', 0):.0f} ms"},
            {"title": "Eseguita via", "content": exec_result.get("executed_via", "MCP Server")},
        ]
        
        # Preview dei risultati
        if rows:
            columns = list(rows[0].keys())
            exec_details.append({
                "title": "Colonne risultato",
                "content": columns
            })
            
            # Mostra prime 3 righe come preview
            if len(rows) <= 3:
                exec_details.append({
                    "title": "Dati estratti",
                    "content": [str(row) for row in rows]
                })
        
        thinking_steps.append({
            "step": "sql_execution",
            "description": f"Query eseguita con successo: {len(rows)} righe in {exec_result.get('execution_time_ms', 0):.0f}ms",
            "status": "completed",
            "duration_ms": int(exec_result.get("execution_time_ms", 0)),
            "details": exec_details
        })
        
        # ======= STEP 5: Generazione Risposta =======
        response_details = [
            {"title": "Formato risposta", "content": "Linguaggio naturale italiano"},
            {"title": "Dati sintetizzati", "content": f"{len(rows)} record analizzati"},
        ]
        
        thinking_steps.append({
            "step": "response_generation",
            "description": "Generata risposta in linguaggio naturale",
            "status": "completed",
            "duration_ms": 150,
            "details": response_details
        })
        
        # ======= STEP 6: Generazione Grafico (se presente) =======
        if chart_data:
            chart_details = [
                {"title": "Tipo grafico", "content": chart_data.get("chart_type", "bar")},
                {"title": "Titolo", "content": chart_data.get("chart_title", "Visualizzazione")},
            ]
            
            if chart_data.get("charts"):
                chart_details.append({
                    "title": "Visualizzazioni multiple",
                    "content": f"{len(chart_data['charts'])} grafici generati"
                })
            
            thinking_steps.append({
                "step": "chart_generation",
                "description": f"Generato grafico {chart_data.get('chart_type', 'bar')}",
                "status": "completed",
                "duration_ms": 200,
                "details": chart_details
            })
        
        return thinking_steps

    def _build_steps_from_llm_reasoning(
        self,
        llm_reasoning: Dict[str, Any],
        sql: str,
        sql_result: Dict[str, Any],
        exec_result: Dict[str, Any],
        rows: List[Dict[str, Any]],
        chart_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Costruisce thinking steps dal REASONING REALE del modello LLM.
        Questo e il vero chain-of-thought del modello!
        """
        thinking_steps = []
        latency_ms = sql_result.get("llm_latency_ms", 0)
        
        # ======= STEP 1: Comprensione della Domanda (dal modello) =======
        question_understanding = llm_reasoning.get("question_understanding", {})
        
        understanding_details = [
            {"title": "Domanda originale", "content": question_understanding.get("original_question", "N/A")},
            {"title": "Tipo di analisi richiesta", "content": question_understanding.get("analysis_type", "N/A")},
            {"title": "Obiettivo", "content": question_understanding.get("what_user_wants", "N/A")},
        ]
        
        thinking_steps.append({
            "step": "query_understanding",
            "description": f"Compreso: {question_understanding.get('analysis_type', 'analisi dati')} - {question_understanding.get('what_user_wants', '')[:60]}",
            "status": "completed",
            "duration_ms": int(latency_ms * 0.15),
            "details": understanding_details
        })
        
        # ======= STEP 2: Selezione Tabella (dal modello) =======
        table_selection = llm_reasoning.get("table_selection", {})
        
        table_details = [
            {"title": "Tabella principale selezionata", "content": table_selection.get("selected_table", "N/A")},
            {"title": "Motivazione", "content": table_selection.get("why_this_table", "N/A")},
        ]
        
        join_tables = table_selection.get("join_tables", [])
        if join_tables:
            table_details.append({
                "title": "Tabelle per JOIN",
                "content": join_tables
            })
        
        thinking_steps.append({
            "step": "table_selection",
            "description": f"Selezionata tabella: {table_selection.get('selected_table', 'N/A')}",
            "status": "completed",
            "duration_ms": int(latency_ms * 0.15),
            "details": table_details
        })
        
        # ======= STEP 3: Selezione Colonne (dal modello) =======
        column_selection = llm_reasoning.get("column_selection", {})
        
        column_details = [
            {"title": "Colonne per metriche (calcoli)", "content": column_selection.get("metric_columns", ["N/A"])},
            {"title": "Colonne per dimensioni (raggruppamento)", "content": column_selection.get("dimension_columns", ["N/A"])},
        ]
        
        filter_cols = column_selection.get("filter_columns", [])
        if filter_cols:
            column_details.append({
                "title": "Colonne per filtri",
                "content": filter_cols
            })
        
        why_columns = column_selection.get("why_these_columns", "")
        if why_columns:
            column_details.append({
                "title": "Motivazione scelta colonne",
                "content": why_columns
            })
        
        metric_cols = column_selection.get("metric_columns", [])
        thinking_steps.append({
            "step": "column_selection",
            "description": f"Identificate {len(metric_cols)} colonne metriche, {len(column_selection.get('dimension_columns', []))} dimensioni",
            "status": "completed",
            "duration_ms": int(latency_ms * 0.15),
            "details": column_details
        })
        
        # ======= STEP 4: Logica Query (dal modello) =======
        query_logic = llm_reasoning.get("query_logic", {})
        
        logic_details = [
            {"title": "Funzione di aggregazione", "content": query_logic.get("aggregation_function", "nessuna")},
            {"title": "Raggruppamento necessario", "content": "Si" if query_logic.get("grouping_needed") else "No"},
        ]
        
        grouping_cols = query_logic.get("grouping_columns", [])
        if grouping_cols:
            logic_details.append({
                "title": "Colonne GROUP BY",
                "content": grouping_cols
            })
        
        ordering = query_logic.get("ordering", "none")
        if ordering != "none":
            logic_details.append({
                "title": "Ordinamento",
                "content": f"{ordering} - {query_logic.get('ordering_reason', '')}"
            })
        
        if query_logic.get("limit_needed"):
            logic_details.append({
                "title": "LIMIT",
                "content": str(query_logic.get("limit_value", "N/A"))
            })
        
        filters = query_logic.get("filters", [])
        if filters:
            logic_details.append({
                "title": "Filtri WHERE",
                "content": filters
            })
        
        thinking_steps.append({
            "step": "query_logic",
            "description": f"Logica: {query_logic.get('aggregation_function', 'SELECT')} con ORDER BY {ordering}",
            "status": "completed",
            "duration_ms": int(latency_ms * 0.15),
            "details": logic_details
        })
        
        # ======= STEP 5: Costruzione Query SQL =======
        sql_details = [
            {"title": "Query SQL generata", "content": sql},
        ]
        
        thinking_steps.append({
            "step": "sql_generation",
            "description": "Query SQL costruita dal ragionamento",
            "status": "completed",
            "duration_ms": int(latency_ms * 0.4),
            "details": sql_details
        })
        
        # ======= STEP 6: Esecuzione Query =======
        exec_details = [
            {"title": "Righe restituite", "content": str(len(rows))},
            {"title": "Tempo esecuzione", "content": f"{exec_result.get('execution_time_ms', 0):.0f} ms"},
            {"title": "Eseguita via", "content": exec_result.get("executed_via", "MCP Server")},
        ]
        
        if rows:
            exec_details.append({
                "title": "Colonne risultato",
                "content": list(rows[0].keys())
            })
        
        thinking_steps.append({
            "step": "sql_execution",
            "description": f"Query eseguita: {len(rows)} righe in {exec_result.get('execution_time_ms', 0):.0f}ms",
            "status": "completed",
            "duration_ms": int(exec_result.get("execution_time_ms", 0)),
            "details": exec_details
        })
        
        # ======= STEP 7: Generazione Risposta =======
        thinking_steps.append({
            "step": "response_generation",
            "description": "Generata risposta in linguaggio naturale",
            "status": "completed",
            "duration_ms": 150,
            "details": [
                {"title": "Formato", "content": "Linguaggio naturale italiano"},
                {"title": "Dati sintetizzati", "content": f"{len(rows)} record"}
            ]
        })
        
        # ======= STEP 8: Generazione Grafico (se presente) =======
        if chart_data:
            thinking_steps.append({
                "step": "chart_generation",
                "description": f"Generato grafico {chart_data.get('chart_type', 'bar')}",
                "status": "completed",
                "duration_ms": 200,
                "details": [
                    {"title": "Tipo grafico", "content": chart_data.get("chart_type", "bar")},
                    {"title": "Titolo", "content": chart_data.get("chart_title", "Visualizzazione")}
                ]
            })
        
        return thinking_steps

    @staticmethod
    def _round_float_values(rows: List[Dict[str, Any]], decimals: int = 2) -> List[Dict[str, Any]]:
        """Arrotonda tutti i valori numerici con decimali a N decimali per leggibilita'"""
        from decimal import Decimal
        rounded = []
        for row in rows:
            new_row = {}
            for k, v in row.items():
                if isinstance(v, float):
                    new_row[k] = round(v, decimals)
                elif isinstance(v, Decimal):
                    new_row[k] = round(float(v), decimals)
                elif isinstance(v, (int,)):
                    new_row[k] = v
                else:
                    # Prova a convertire stringhe numeriche
                    try:
                        fv = float(v)
                        if fv != int(fv) or '.' in str(v):
                            new_row[k] = round(fv, decimals)
                        else:
                            new_row[k] = v
                    except (ValueError, TypeError):
                        new_row[k] = v
            rounded.append(new_row)
        return rounded

    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Estrae nomi tabelle dalla query SQL"""
        import re
        tables = []
        
        # Pattern per FROM e JOIN
        patterns = [
            r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_\.]*)',
            r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_\.]*)',
        ]
        
        sql_upper = sql.upper()
        sql_original = sql
        
        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                # Rimuovi schema prefix se presente (public.table -> table)
                table_name = match.split('.')[-1]
                if table_name.lower() not in ['select', 'where', 'and', 'or', 'on']:
                    tables.append(table_name)
        
        return list(set(tables))

    def _extract_columns_from_sql(self, sql: str) -> List[str]:
        """Estrae nomi colonne dalla query SQL"""
        import re
        columns = []
        
        # Estrai colonne dal SELECT
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            # Split per virgola e pulisci
            parts = select_clause.split(',')
            for part in parts:
                part = part.strip()
                # Rimuovi alias (AS ...) e funzioni
                if ' AS ' in part.upper():
                    part = part.split(' AS ')[0].strip()
                    part = part.split(' as ')[0].strip()
                # Estrai nome colonna da funzioni come SUM(column)
                func_match = re.search(r'\w+\s*\(\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\)', part)
                if func_match:
                    columns.append(func_match.group(1).split('.')[-1])
                elif part != '*':
                    # Rimuovi table prefix
                    col_name = part.split('.')[-1].strip()
                    if col_name and col_name.upper() not in ['DISTINCT']:
                        columns.append(col_name)
        
        return list(set(columns))

    def _analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """Analizza l'intento della domanda utente"""
        query_lower = query.lower()
        
        result = {
            "analysis_type": "Interrogazione dati",
            "metrics": [],
            "dimensions": [],
            "filters": []
        }
        
        # Determina tipo di analisi
        if any(kw in query_lower for kw in ['trend', 'andamento', 'nel tempo', 'evoluzione']):
            result["analysis_type"] = "Analisi temporale (trend)"
        elif any(kw in query_lower for kw in ['top', 'migliori', 'classifica', 'ranking']):
            result["analysis_type"] = "Classifica (ranking)"
        elif any(kw in query_lower for kw in ['confronto', 'confronta', 'compare', 'vs']):
            result["analysis_type"] = "Analisi comparativa"
        elif any(kw in query_lower for kw in ['distribuzione', 'ripartizione', 'breakdown']):
            result["analysis_type"] = "Analisi distribuzione"
        elif any(kw in query_lower for kw in ['totale', 'somma', 'quanto', 'quanti']):
            result["analysis_type"] = "Aggregazione totale"
        elif any(kw in query_lower for kw in ['media', 'average', 'avg']):
            result["analysis_type"] = "Calcolo media"
        
        # Identifica metriche
        metric_keywords = {
            'vendite': 'Vendite/Fatturato',
            'sales': 'Sales',
            'revenue': 'Revenue',
            'fatturato': 'Fatturato',
            'ordini': 'Numero ordini',
            'orders': 'Orders count',
            'quantita': 'Quantita',
            'quantity': 'Quantity',
            'profitto': 'Profitto',
            'profit': 'Profit',
            'margine': 'Margine'
        }
        
        for kw, metric in metric_keywords.items():
            if kw in query_lower:
                result["metrics"].append(metric)
        
        if not result["metrics"]:
            result["metrics"] = ["Da determinare dal contesto"]
        
        # Identifica dimensioni
        dimension_keywords = {
            'categoria': 'Categoria',
            'category': 'Category',
            'regione': 'Regione',
            'region': 'Region',
            'mese': 'Mese',
            'month': 'Month',
            'anno': 'Anno',
            'year': 'Year',
            'prodotto': 'Prodotto',
            'product': 'Product',
            'cliente': 'Cliente',
            'customer': 'Customer',
            'citta': 'Citta',
            'city': 'City'
        }
        
        for kw, dim in dimension_keywords.items():
            if kw in query_lower:
                result["dimensions"].append(dim)
        
        # Identifica filtri temporali
        import re
        year_match = re.search(r'\b(20\d{2})\b', query)
        if year_match:
            result["filters"].append(f"Anno = {year_match.group(1)}")
        
        return result

    def _analyze_sql_structure(self, sql: str) -> Dict[str, Any]:
        """Analizza la struttura della query SQL generata"""
        import re
        
        result = {
            "operation_type": "SELECT",
            "aggregations": [],
            "group_by": [],
            "order_by": [],
            "joins": [],
            "where_conditions": []
        }
        
        sql_upper = sql.upper()
        
        # Tipo operazione
        if sql_upper.strip().startswith('SELECT'):
            result["operation_type"] = "SELECT (lettura dati)"
        
        # Aggregazioni
        agg_patterns = {
            r'\bSUM\s*\(': 'SUM (somma)',
            r'\bCOUNT\s*\(': 'COUNT (conteggio)',
            r'\bAVG\s*\(': 'AVG (media)',
            r'\bMAX\s*\(': 'MAX (massimo)',
            r'\bMIN\s*\(': 'MIN (minimo)'
        }
        
        for pattern, agg_name in agg_patterns.items():
            if re.search(pattern, sql_upper):
                result["aggregations"].append(agg_name)
        
        # GROUP BY
        group_match = re.search(r'GROUP\s+BY\s+(.*?)(?:ORDER|HAVING|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if group_match:
            group_clause = group_match.group(1).strip()
            # Pulisci e splitta
            groups = [g.strip().split('.')[-1] for g in group_clause.split(',')]
            result["group_by"] = [g for g in groups if g and not g.upper().startswith('ORDER')]
        
        # ORDER BY
        order_match = re.search(r'ORDER\s+BY\s+(.*?)(?:LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if order_match:
            order_clause = order_match.group(1).strip()
            if 'DESC' in order_clause.upper():
                result["order_by"].append("Decrescente")
            elif 'ASC' in order_clause.upper():
                result["order_by"].append("Crescente")
            else:
                result["order_by"].append("Default (crescente)")
        
        # JOIN
        join_matches = re.findall(r'(LEFT|RIGHT|INNER|OUTER|CROSS)?\s*JOIN\s+(\w+)', sql, re.IGNORECASE)
        for join_type, table in join_matches:
            join_desc = f"{join_type.upper() if join_type else 'INNER'} JOIN {table}"
            result["joins"].append(join_desc)
        
        # WHERE conditions (semplificato)
        where_match = re.search(r'WHERE\s+(.*?)(?:GROUP|ORDER|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_clause = where_match.group(1).strip()
            # Estrai condizioni principali
            conditions = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
            for cond in conditions[:3]:  # Max 3 condizioni
                cond = cond.strip()
                if cond and len(cond) < 100:
                    result["where_conditions"].append(cond)
        
        return result


def create_chat_orchestrator(llm_provider: Optional[str] = None) -> ChatOrchestrator:
    """
    Factory per ChatOrchestrator

    Args:
        llm_provider: "claude" | "azure" | None (usa default)
    """
    return ChatOrchestrator(llm_provider=llm_provider)


def get_active_sessions() -> List[str]:
    """Lista session IDs attivi"""
    return list(_sessions.keys())