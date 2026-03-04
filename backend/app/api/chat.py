"""
Chat API endpoints - Production-ready
Endpoint /api/chat/query e /api/chat/history
Endpoint /api/chat/query/stream per streaming con reasoning steps
"""

import logging
import json
import asyncio
import time
from datetime import datetime, date
from decimal import Decimal
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any


def json_serializer(obj):
    """Custom JSON serializer per tipi non standard"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def safe_json_dumps(obj):
    """JSON dumps con serializer custom per datetime, Decimal, etc."""
    return json.dumps(obj, default=json_serializer)

from app.services.chat_orchestrator import create_chat_orchestrator, get_active_sessions
from app.services.llm_provider import get_llm_provider_manager
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ChatQueryRequest(BaseModel):
    """Request chat query"""
    query: str = Field(..., min_length=1, max_length=1000, description="Domanda NL")
    session_id: Optional[str] = Field(None, description="ID sessione (opzionale, crea nuovo se None)")
    llm_provider: Optional[Literal["claude", "azure", "gpt52"]] = Field(
        None,
        description="Provider LLM (claude/azure/gpt52). Se None usa default."
    )
    include_chart: bool = Field(True, description="Genera chart (Fase 05)")


class LLMStats(BaseModel):
    """Statistiche LLM"""
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens: Optional[int] = None


class ThinkingStepDetail(BaseModel):
    """Dettaglio espandibile di uno step"""
    title: str
    content: Any  # Puo essere stringa, lista, dict

class ThinkingStep(BaseModel):
    """Step di ragionamento del modello"""
    step: str
    description: str
    status: str = "pending"  # pending, running, completed, error
    duration_ms: Optional[float] = None
    details: Optional[List[ThinkingStepDetail]] = None  # Contenuto espandibile

class ChatQueryResponse(BaseModel):
    """Response chat query"""
    success: bool
    session_id: str
    nl_response: str
    sql: str
    results: List[Dict[str, Any]]
    result_count: int
    chart: Optional[Dict[str, Any]] = None
    execution_time_ms: float
    llm_provider: str
    llm_stats: Optional[LLMStats] = None
    error: Optional[str] = None
    thinking_steps: Optional[List[ThinkingStep]] = None
    suggested_followups: Optional[List[str]] = None
    should_show_chart: bool = True


class ChatHistoryItem(BaseModel):
    """Singolo item history"""
    timestamp: str
    query: str
    sql: str
    result_count: int
    nl_response: str


class ChatHistoryResponse(BaseModel):
    """Response chat history"""
    session_id: str
    history: List[ChatHistoryItem]
    turn_count: int


class ProvidersResponse(BaseModel):
    """Response lista providers"""
    available_providers: List[str]
    default_provider: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(request: ChatQueryRequest):
    """
    Endpoint principale chat: invia query NL, ricevi SQL + risultati + risposta NL

    **Workflow:**
    1. Validazione input
    2. Orchestrazione: NL -> SQL -> execute -> NL response
    3. Session context management (rolling window 5 turni)
    4. Chart generation (Fase 05)

    **Multi-provider:** Specifica `llm_provider` per scegliere Claude o Azure
    """
    try:
        # Determina provider
        provider = request.llm_provider or settings.default_llm_provider
        
        # Verifica provider disponibile
        llm_manager = get_llm_provider_manager()
        available = llm_manager.list_available_providers()
        if provider not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider}' non disponibile. Disponibili: {available}"
            )

        # Crea orchestrator con provider richiesto
        orchestrator = create_chat_orchestrator(llm_provider=provider)

        # Processa query
        result = orchestrator.process_query(
            query=request.query,
            session_id=request.session_id,
            include_chart=request.include_chart
        )

        # Costruisci response
        llm_stats = None
        if result.get("llm_stats"):
            llm_stats = LLMStats(**result["llm_stats"])

        # Build thinking steps for response
        thinking_steps = None
        if result.get("thinking_steps"):
            thinking_steps = [ThinkingStep(**step) for step in result["thinking_steps"]]

        return ChatQueryResponse(
            success=result["success"],
            session_id=result["session_id"],
            nl_response=result["nl_response"],
            sql=result["sql"],
            results=result["results"],
            result_count=len(result["results"]),
            chart=result.get("chart"),
            execution_time_ms=result["execution_time_ms"],
            llm_provider=result["llm_provider"],
            llm_stats=llm_stats,
            error=result.get("error"),
            thinking_steps=thinking_steps,
            suggested_followups=result.get("suggested_followups"),
            should_show_chart=result.get("should_show_chart", True)
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno server")


@router.post("/query/stream")
async def chat_query_stream(request: ChatQueryRequest):
    """
    Endpoint streaming con REASONING REALE dal modello LLM.
    Usa Chain-of-Thought strutturato per mostrare il vero ragionamento.
    """
    async def generate_stream():
        start_time = time.time()
        
        try:
            provider = request.llm_provider or settings.default_llm_provider
            llm_manager = get_llm_provider_manager()
            available = llm_manager.list_available_providers()
            
            if provider not in available:
                yield f"data: {safe_json_dumps({'type': 'error', 'error': f'Provider {provider} non disponibile'})}\n\n"
                return
            
            orchestrator = create_chat_orchestrator(llm_provider=provider)
            
            # ===== STEP 1: Analisi Schema =====
            step1_start = time.time()
            schema_running = {"type": "thinking_step", "step": {"step": "schema_analysis", "description": "Analisi schema database...", "status": "running", "details": None}}
            yield f"data: {safe_json_dumps(schema_running)}\n\n"
            await asyncio.sleep(0.1)  # Delay ridotto per velocita
            
            from app.services.mcp_manager import mcp_postgres_client
            try:
                tables_list = mcp_postgres_client.list_tables(schema="public")
            except:
                tables_list = []
            
            step1_duration = (time.time() - step1_start) * 1000
            schema_done = {
                "type": "thinking_step",
                "step": {
                    "step": "schema_analysis",
                    "description": f"Identificate {len(tables_list)} tabelle nel database",
                    "status": "completed",
                    "duration_ms": step1_duration,
                    "details": [
                        {"title": "Database", "content": "PostgreSQL via MCP Server"},
                        {"title": "Tabelle disponibili", "content": tables_list if tables_list else ["Nessuna"]}
                    ]
                }
            }
            yield f"data: {safe_json_dumps(schema_done)}\n\n"
            await asyncio.sleep(0.2)  # Delay tra step
            
            # ===== STEP 2: Comprensione Domanda (running mentre LLM lavora) =====
            understanding_running = {"type": "thinking_step", "step": {"step": "query_understanding", "description": "Il modello sta analizzando la domanda...", "status": "running", "details": None}}
            yield f"data: {safe_json_dumps(understanding_running)}\n\n"
            
            # Genera SQL CON REASONING dal modello (questa chiamata richiede tempo)
            step2_start = time.time()
            sql_result = orchestrator.vanna.generate_sql(request.query)
            
            if not sql_result["success"]:
                error_data = {"type": "error", "error": sql_result.get("error", "SQL generation failed")}
                yield f"data: {safe_json_dumps(error_data)}\n\n"
                return
            
            sql = sql_result["sql"]
            reasoning = sql_result.get("reasoning")
            step2_duration = (time.time() - step2_start) * 1000
            
            # Ora mostriamo gli step di reasoning UNO ALLA VOLTA con delay
            if reasoning:
                # STEP 2: Comprensione domanda (completato)
                qu = reasoning.get("question_understanding", {})
                qu_desc = (qu.get("what_user_wants", "Analisi richiesta") or "Analisi richiesta")[:80]
                qu_done = {
                    "type": "thinking_step",
                    "step": {
                        "step": "query_understanding",
                        "description": qu_desc,
                        "status": "completed",
                        "duration_ms": step2_duration * 0.2,
                        "details": [
                            {"title": "Domanda", "content": qu.get("original_question", request.query)},
                            {"title": "Tipo analisi", "content": qu.get("analysis_type", "N/A")},
                            {"title": "Obiettivo", "content": qu.get("what_user_wants", "N/A")}
                        ]
                    }
                }
                yield f"data: {safe_json_dumps(qu_done)}\n\n"
                await asyncio.sleep(0.15)  # Delay visibile tra step
                
                # STEP 3: Selezione tabella
                ts = reasoning.get("table_selection", {})
                selected_table = ts.get("selected_table", "N/A")
                table_details = [
                    {"title": "Tabella principale", "content": selected_table},
                    {"title": "Motivazione", "content": ts.get("why_this_table", "N/A")}
                ]
                if ts.get("join_tables"):
                    table_details.append({"title": "Tabelle JOIN", "content": ts["join_tables"]})
                
                ts_running = {"type": "thinking_step", "step": {"step": "table_selection", "description": "Identificazione tabella...", "status": "running", "details": None}}
                yield f"data: {safe_json_dumps(ts_running)}\n\n"
                await asyncio.sleep(0.15)
                
                ts_done = {
                    "type": "thinking_step",
                    "step": {
                        "step": "table_selection",
                        "description": f"Selezionata tabella: {selected_table}",
                        "status": "completed",
                        "duration_ms": step2_duration * 0.15,
                        "details": table_details
                    }
                }
                yield f"data: {safe_json_dumps(ts_done)}\n\n"
                await asyncio.sleep(0.15)
                
                # STEP 4: Selezione colonne
                cs = reasoning.get("column_selection", {})
                col_details = [
                    {"title": "Colonne metriche (per calcoli)", "content": cs.get("metric_columns", ["N/A"])},
                    {"title": "Colonne dimensioni (per raggruppamento)", "content": cs.get("dimension_columns", ["N/A"])}
                ]
                if cs.get("filter_columns"):
                    col_details.append({"title": "Colonne filtro", "content": cs["filter_columns"]})
                if cs.get("why_these_columns"):
                    col_details.append({"title": "Motivazione", "content": cs["why_these_columns"]})
                
                num_metrics = len(cs.get("metric_columns", []))
                num_dims = len(cs.get("dimension_columns", []))
                
                cs_running = {"type": "thinking_step", "step": {"step": "column_selection", "description": "Identificazione colonne...", "status": "running", "details": None}}
                yield f"data: {safe_json_dumps(cs_running)}\n\n"
                await asyncio.sleep(0.15)
                
                cs_done = {
                    "type": "thinking_step",
                    "step": {
                        "step": "column_selection",
                        "description": f"{num_metrics} metriche, {num_dims} dimensioni identificate",
                        "status": "completed",
                        "duration_ms": step2_duration * 0.15,
                        "details": col_details
                    }
                }
                yield f"data: {safe_json_dumps(cs_done)}\n\n"
                await asyncio.sleep(0.15)
                
                # STEP 5: Logica query
                ql = reasoning.get("query_logic", {})
                logic_details = [
                    {"title": "Aggregazione", "content": ql.get("aggregation_function", "nessuna")},
                    {"title": "Raggruppamento", "content": "Si" if ql.get("grouping_needed") else "No"}
                ]
                if ql.get("grouping_columns"):
                    logic_details.append({"title": "GROUP BY", "content": ql["grouping_columns"]})
                ordering = ql.get("ordering", "none")
                if ordering and ordering != "none":
                    ordering_reason = ql.get("ordering_reason", "")
                    logic_details.append({"title": "Ordinamento", "content": f"{ordering} - {ordering_reason}"})
                if ql.get("limit_needed"):
                    logic_details.append({"title": "LIMIT", "content": str(ql.get("limit_value", "N/A"))})
                if ql.get("filters"):
                    logic_details.append({"title": "Filtri WHERE", "content": ql["filters"]})
                
                agg = ql.get("aggregation_function", "SELECT")
                
                ql_running = {"type": "thinking_step", "step": {"step": "query_logic", "description": "Definizione logica query...", "status": "running", "details": None}}
                yield f"data: {safe_json_dumps(ql_running)}\n\n"
                await asyncio.sleep(0.15)
                
                ql_done = {
                    "type": "thinking_step",
                    "step": {
                        "step": "query_logic",
                        "description": f"Logica: {agg} con ORDER BY {ordering}",
                        "status": "completed",
                        "duration_ms": step2_duration * 0.2,
                        "details": logic_details
                    }
                }
                yield f"data: {safe_json_dumps(ql_done)}\n\n"
                await asyncio.sleep(0.15)
            
            # STEP 6 (ULTIMO): Costruzione Query SQL finale
            sql_running = {"type": "thinking_step", "step": {"step": "sql_generation", "description": "Costruzione query SQL...", "status": "running", "details": None}}
            yield f"data: {safe_json_dumps(sql_running)}\n\n"
            await asyncio.sleep(0.15)
            
            sql_done = {
                "type": "thinking_step",
                "step": {
                    "step": "sql_generation",
                    "description": "Query SQL costruita",
                    "status": "completed",
                    "duration_ms": step2_duration * 0.3,
                    "details": [{"title": "Query generata", "content": sql}]
                }
            }
            yield f"data: {safe_json_dumps(sql_done)}\n\n"
            await asyncio.sleep(0.15)
            
            # ===== STEP 7: Esecuzione Query =====
            step3_start = time.time()
            exec_running = {"type": "thinking_step", "step": {"step": "sql_execution", "description": "Esecuzione query sul database...", "status": "running", "details": None}}
            yield f"data: {safe_json_dumps(exec_running)}\n\n"
            
            exec_result = orchestrator.vanna.execute_sql(sql)
            
            if not exec_result["success"]:
                error_msg = exec_result.get("error", "SQL execution failed")
                yield f"data: {safe_json_dumps({'type': 'error', 'error': error_msg})}\n\n"
                return
            
            rows = exec_result["rows"]
            step3_duration = (time.time() - step3_start) * 1000
            
            exec_details = [
                {"title": "Righe restituite", "content": str(len(rows))},
                {"title": "Tempo esecuzione", "content": f"{step3_duration:.0f} ms"},
                {"title": "Eseguita via", "content": exec_result.get("executed_via", "MCP Server")}
            ]
            if rows:
                exec_details.append({"title": "Colonne risultato", "content": list(rows[0].keys())})
            
            exec_done = {
                "type": "thinking_step",
                "step": {
                    "step": "sql_execution",
                    "description": f"Estratte {len(rows)} righe in {step3_duration:.0f}ms",
                    "status": "completed",
                    "duration_ms": step3_duration,
                    "details": exec_details
                }
            }
            yield f"data: {safe_json_dumps(exec_done)}\n\n"
            
            # ===== STEP 4: Generazione Risposta =====
            step4_start = time.time()
            resp_running = {"type": "thinking_step", "step": {"step": "response_generation", "description": "Generazione risposta...", "status": "running", "details": None}}
            yield f"data: {safe_json_dumps(resp_running)}\n\n"
            
            nl_response = orchestrator._generate_nl_response(query=request.query, sql=sql, results=rows)
            step4_duration = (time.time() - step4_start) * 1000
            
            resp_done = {
                "type": "thinking_step",
                "step": {
                    "step": "response_generation",
                    "description": "Risposta generata",
                    "status": "completed",
                    "duration_ms": step4_duration,
                    "details": [{"title": "Formato", "content": "Linguaggio naturale"}, {"title": "Record analizzati", "content": str(len(rows))}]
                }
            }
            yield f"data: {safe_json_dumps(resp_done)}\n\n"
            
            # ===== STEP 5: Generazione Grafico =====
            chart_data = None
            should_show_chart = orchestrator._should_show_chart(request.query, rows, sql)
            
            if request.include_chart and rows and should_show_chart:
                step5_start = time.time()
                chart_running = {"type": "thinking_step", "step": {"step": "chart_generation", "description": "Generazione grafico...", "status": "running", "details": None}}
                yield f"data: {safe_json_dumps(chart_running)}\n\n"
                
                try:
                    chart_data = orchestrator.chart_service.generate_chart(results=rows, sql=sql, query=request.query)
                    step5_duration = (time.time() - step5_start) * 1000
                    chart_type = chart_data.get("chart_type", "bar")
                    chart_title = chart_data.get("chart_title", "Visualizzazione")
                    chart_done = {
                        "type": "thinking_step",
                        "step": {
                            "step": "chart_generation",
                            "description": f"Grafico {chart_type} generato",
                            "status": "completed",
                            "duration_ms": step5_duration,
                            "details": [{"title": "Tipo", "content": chart_type}, {"title": "Titolo", "content": chart_title}]
                        }
                    }
                    yield f"data: {safe_json_dumps(chart_done)}\n\n"
                except Exception as e:
                    logger.warning(f"Chart generation failed: {e}")
            
            suggested_followups = orchestrator._generate_suggested_followups(request.query, sql, rows)
            
            orchestrator._add_to_context(
                session_id=request.session_id or "stream-session",
                query=request.query,
                sql=sql,
                result_count=len(rows),
                nl_response=nl_response
            )
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Estrai thought_process dal reasoning (bullet point testuali)
            thought_process = None
            if reasoning and reasoning.get("thought_process"):
                thought_process = reasoning.get("thought_process")
            
            # Final result
            final_result = {
                "type": "result",
                "data": {
                    "success": True,
                    "session_id": request.session_id or "stream-session",
                    "nl_response": nl_response,
                    "sql": sql,
                    "results": rows,
                    "result_count": len(rows),
                    "chart": chart_data if should_show_chart else None,
                    "execution_time_ms": execution_time_ms,
                    "llm_provider": provider,
                    "suggested_followups": suggested_followups,
                    "should_show_chart": should_show_chart,
                    "thought_process": thought_process
                }
            }
            yield f"data: {safe_json_dumps(final_result)}\n\n"
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {safe_json_dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: str):
    """
    Recupera storico conversazione sessione

    **Use case:** Frontend visualizza conversazioni passate
    """
    try:
        orchestrator = create_chat_orchestrator()
        history = orchestrator.get_session_history(session_id)

        history_items = [ChatHistoryItem(**item) for item in history]

        return ChatHistoryResponse(
            session_id=session_id,
            history=history_items,
            turn_count=len(history_items)
        )

    except Exception as e:
        logger.error(f"Chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Elimina sessione chat"""
    try:
        orchestrator = create_chat_orchestrator()
        deleted = orchestrator.clear_session(session_id)
        
        if deleted:
            return {"message": f"Sessione {session_id} eliminata", "success": True}
        else:
            return {"message": f"Sessione {session_id} non trovata", "success": False}

    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """Lista sessioni attive"""
    sessions = get_active_sessions()
    return {
        "sessions": sessions,
        "count": len(sessions)
    }


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers():
    """Lista provider LLM disponibili"""
    try:
        llm_manager = get_llm_provider_manager()
        available = llm_manager.list_available_providers()
        
        return ProvidersResponse(
            available_providers=available,
            default_provider=settings.default_llm_provider
        )

    except Exception as e:
        logger.error(f"List providers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
