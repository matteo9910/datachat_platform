"""
Charts API endpoints - CRUD saved charts
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.services.metadata_service import metadata_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/charts", tags=["charts"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class SaveChartRequest(BaseModel):
    """Request save chart"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    sql_template: str = Field(..., min_length=1)
    parameters: Dict[str, Any]
    plotly_config: Dict[str, Any]


class SaveChartResponse(BaseModel):
    """Response save chart"""
    chart_id: str
    created_at: str


class ChartSummary(BaseModel):
    """Chart summary per lista"""
    chart_id: str
    title: str
    description: Optional[str]
    sql_template: str
    parameters: Dict[str, Any]
    plotly_config: Dict[str, Any]
    created_at: str
    updated_at: Optional[str]


class ListChartsResponse(BaseModel):
    """Response list charts"""
    charts: List[ChartSummary]
    total: int


class ChartDetail(BaseModel):
    """Chart completo"""
    chart_id: str
    title: str
    description: Optional[str]
    sql_template: str
    parameters: Dict[str, Any]
    plotly_config: Dict[str, Any]
    created_at: str
    updated_at: Optional[str]


class UpdateParametersRequest(BaseModel):
    """Request update parameters"""
    parameters: Dict[str, Any] = Field(..., description="Es: {'time_granularity': 'quarter'}")
    llm_provider: str = Field("claude", description="Provider per chart regeneration")


class ModifyChartNLRequest(BaseModel):
    """Request modifica chart con linguaggio naturale"""
    modification_request: str = Field(..., description="Es: 'mostrami il 2017', 'ultimi 6 mesi', 'solo Q1'")
    llm_provider: str = Field("claude", description="Provider LLM")


class ModifyVisualizationRequest(BaseModel):
    """Request modifica visualizzazione Plotly"""
    current_plotly_config: Dict[str, Any] = Field(..., description="Config Plotly attuale")
    modification_request: str = Field(..., description="Es: 'cambia in pie chart', 'aggiungi etichette'")
    sql_query: str = Field(..., description="Query SQL originale")
    original_results: List[Dict[str, Any]] = Field(..., description="Risultati originali")
    llm_provider: str = Field("azure", description="Provider LLM (raccomandato: azure per gpt-4.1)")


class UpdateParametersResponse(BaseModel):
    """Response update parameters"""
    chart_id: str
    plotly_config: Dict[str, Any]
    results: List[Dict[str, Any]]
    updated_at: str
    execution_time_ms: float


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/save", response_model=SaveChartResponse)
async def save_chart(request: SaveChartRequest, db: Session = Depends(get_system_db)):
    """Salva chart con metadata parametrica"""
    try:
        chart = metadata_service.save_chart(
            db=db,
            title=request.title,
            description=request.description,
            sql_template=request.sql_template,
            parameters=request.parameters,
            plotly_config=request.plotly_config
        )

        return SaveChartResponse(
            chart_id=str(chart.chart_id),
            created_at=chart.created_at.isoformat()
        )

    except Exception as e:
        logger.error(f"Save chart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ListChartsResponse)
async def list_charts(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_system_db)
):
    """Lista tutti i chart salvati (ordinati per data creazione DESC)"""
    try:
        charts = metadata_service.list_charts(db=db, limit=limit, offset=offset)

        chart_summaries = [
            ChartSummary(
                chart_id=str(c.chart_id),
                title=c.title,
                description=c.description,
                sql_template=c.sql_template,
                parameters=c.parameters or {},
                plotly_config=c.plotly_config or {},
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat() if c.updated_at else None
            )
            for c in charts
        ]

        return ListChartsResponse(
            charts=chart_summaries,
            total=len(chart_summaries)
        )

    except Exception as e:
        logger.error(f"List charts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chart_id}", response_model=ChartDetail)
async def get_chart(chart_id: UUID, db: Session = Depends(get_system_db)):
    """Recupera dettagli chart salvato per ID"""
    try:
        chart = metadata_service.get_chart(db=db, chart_id=chart_id)

        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")

        return ChartDetail(
            chart_id=str(chart.chart_id),
            title=chart.title,
            description=chart.description,
            sql_template=chart.sql_template,
            parameters=chart.parameters,
            plotly_config=chart.plotly_config,
            created_at=chart.created_at.isoformat(),
            updated_at=chart.updated_at.isoformat() if chart.updated_at else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chart error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{chart_id}/parameters", response_model=UpdateParametersResponse)
async def update_chart_parameters(
    chart_id: UUID,
    request: UpdateParametersRequest,
    db: Session = Depends(get_system_db)
):
    """
    Modifica parametri chart e rigenera
    
    **Performance target:** < 5s
    """
    try:
        result = metadata_service.update_chart_parameters(
            db=db,
            chart_id=chart_id,
            new_parameters=request.parameters,
            llm_provider=request.llm_provider
        )

        return UpdateParametersResponse(**result)

    except ValueError as e:
        logger.error(f"Update parameters error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Update parameters error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{chart_id}")
async def delete_chart(chart_id: UUID, db: Session = Depends(get_system_db)):
    """Elimina chart salvato"""
    try:
        deleted = metadata_service.delete_chart(db=db, chart_id=chart_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Chart not found")

        return {"status": "deleted", "chart_id": str(chart_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete chart error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modify-visualization")
async def modify_chart_visualization(request: ModifyVisualizationRequest):
    """
    Modifica la visualizzazione del grafico (tipo, etichette, colori, etc.)
    SENZA rieseguire la query SQL.
    
    Usa LLM per generare una nuova config Plotly basata sulle istruzioni dell'utente.
    """
    import time
    import json
    start_time = time.time()
    
    try:
        from app.services.llm_provider import get_llm_provider_manager
        
        llm_manager = get_llm_provider_manager()
        
        # Prepara sample dati per contesto
        sample_results = request.original_results[:5] if request.original_results else []
        
        # Rileva se è una tabella
        is_table = False
        if request.current_plotly_config:
            chart_data = request.current_plotly_config.get("data", [])
            if chart_data and chart_data[0].get("type") == "table":
                is_table = True
        
        if is_table:
            # Prepara tutti i dati per la tabella (non solo sample)
            all_results = request.original_results if request.original_results else []
            headers = list(all_results[0].keys()) if all_results else []
            
            # Prompt specifico per modifiche alle tabelle
            prompt = f"""Sei un esperto di data visualization. Devi modificare una TABELLA secondo le istruzioni dell'utente.

DATI ATTUALI DELLA TABELLA ({len(all_results)} righe):
```json
{json.dumps(all_results, indent=2, default=str)}
```

Headers attuali: {headers}

RICHIESTA UTENTE: "{request.modification_request}"

ISTRUZIONI:
1. Se l'utente chiede di dividere valori per 1000 (K€), 1000000 (M€), etc.:
   - CALCOLA i nuovi valori dividendo per il fattore richiesto
   - ARROTONDA a 2 decimali
   - AGGIORNA l'header della colonna (es: "FATTURATO_2017" -> "FATTURATO_2017 (K€)")
2. DEVI includere TUTTE le {len(all_results)} righe nei dati modificati

ESEMPIO DI OUTPUT per una tabella con valori divisi per 1000:
{{
  "data": [{{
    "type": "table",
    "header": {{
      "values": ["CATEGORY_NAME", "FATTURATO_2017 (K€)"],
      "fill": {{"color": "#1e293b"}},
      "font": {{"color": "white", "size": 12}},
      "align": "left"
    }},
    "cells": {{
      "values": [
        ["Fishing", "Cleats", "...tutte le categorie..."],
        [1900.31, 1199.02, "...tutti i valori divisi per 1000 e arrotondati..."]
      ],
      "fill": {{"color": ["white", "#f8fafc"]}},
      "align": "left"
    }}
  }}],
  "layout": {{"title": {{"text": "Categorie Prodotto per Fatturato 2017 (K€)"}}}}
}}

IMPORTANTE: 
- Rispondi SOLO con il JSON, senza markdown o spiegazioni
- Includi TUTTE le righe, non solo un esempio
- I valori numerici modificati devono essere NUMERI, non stringhe

JSON:"""
        else:
            # Prompt standard per grafici
            prompt = f"""Sei un esperto di Plotly.js. Devi modificare una configurazione Plotly esistente secondo le istruzioni dell'utente.

CONFIG PLOTLY ATTUALE:
```json
{json.dumps(request.current_plotly_config, indent=2, default=str)}
```

DATI DISPONIBILI (prime 5 righe):
```json
{json.dumps(sample_results, indent=2, default=str)}
```

TUTTI I DATI ({len(request.original_results)} righe):
Colonne disponibili: {list(request.original_results[0].keys()) if request.original_results else []}

RICHIESTA UTENTE: "{request.modification_request}"

ISTRUZIONI:
1. Modifica la config Plotly per soddisfare la richiesta dell'utente
2. MANTIENI gli stessi dati (x, y, values, labels) dalla config originale
3. Se l'utente chiede "etichette" o "labels sui valori":
   - Per bar chart: aggiungi "text" array con i valori y, e "textposition": "outside" o "auto"
   - Per pie chart: usa "textinfo": "label+percent+value"
4. Se l'utente chiede di cambiare tipo di grafico:
   - bar -> pie: converti x in labels e y in values
   - bar -> line: cambia "type" in "scatter" e aggiungi "mode": "lines+markers"
   - pie -> bar: converti labels in x e values in y
5. NON inventare nuovi dati, usa SOLO quelli presenti nella config originale
6. Mantieni layout.title se presente

IMPORTANTE: Rispondi SOLO con il JSON della nuova config Plotly, senza spiegazioni o markdown.

NUOVA CONFIG PLOTLY:"""

        logger.info(f"Table modification request: is_table={is_table}, num_results={len(request.original_results)}")
        
        response = llm_manager.complete(
            messages=[{"role": "user", "content": prompt}],
            provider=request.llm_provider,
            temperature=0.1,
            max_tokens=4000  # Aumentato per tabelle grandi
        )
        
        content = response["content"].strip()
        logger.info(f"LLM visualization modification response length: {len(content)}")
        logger.info(f"LLM response preview: {content[:300]}...")
        
        # Parse JSON response - rimuovi markdown se presente
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        try:
            new_config = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw content: {content[:500]}")
            raise HTTPException(status_code=500, detail="Errore nel parsing della risposta LLM")
        
        execution_time_ms = (time.time() - start_time) * 1000
        logger.info(f"Visualization modified in {execution_time_ms:.0f}ms")
        
        # Per le tabelle, estrai anche i dati modificati per aggiornare results
        modified_results = None
        if is_table and new_config.get("data") and new_config["data"][0].get("type") == "table":
            try:
                table_data = new_config["data"][0]
                headers = table_data.get("header", {}).get("values", [])
                cells = table_data.get("cells", {}).get("values", [])
                
                if headers and cells:
                    # Ricostruisci i results dalla tabella modificata
                    num_rows = len(cells[0]) if cells else 0
                    modified_results = []
                    for i in range(num_rows):
                        row = {}
                        for j, header in enumerate(headers):
                            row[header] = cells[j][i] if j < len(cells) else None
                        modified_results.append(row)
                    logger.info(f"Extracted {len(modified_results)} modified results from table")
            except Exception as ex:
                logger.warning(f"Could not extract modified results: {ex}")
        
        logger.info(f"Returning modified_results: {modified_results is not None}, count: {len(modified_results) if modified_results else 0}")
        if modified_results:
            logger.info(f"First modified result: {modified_results[0]}")
        
        return {
            "success": True,
            "plotly_config": new_config,
            "modified_results": modified_results,
            "execution_time_ms": execution_time_ms
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Modify visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{chart_id}/modify")
async def modify_chart_with_nl(
    chart_id: UUID,
    request: ModifyChartNLRequest,
    db: Session = Depends(get_system_db)
):
    """
    Modifica chart usando linguaggio naturale.
    
    L'utente puo' chiedere modifiche come:
    - "mostrami il 2017"
    - "ultimi 6 mesi"
    - "solo il Q1"
    - "per categoria invece che per regione"
    
    L'LLM interpreta la richiesta e genera una nuova SQL.
    """
    import time
    start_time = time.time()
    
    try:
        from app.services.llm_provider import get_llm_provider_manager
        from app.services.mcp_manager import mcp_postgres_client
        from app.services.chart_service import create_chart_service
        
        # 1. Recupera chart originale
        chart = metadata_service.get_chart(db=db, chart_id=chart_id)
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        
        # 2. Usa LLM per generare nuova SQL basata sulla modifica richiesta
        llm_manager = get_llm_provider_manager()
        
        prompt = f"""Sei un esperto SQL. Devi modificare una query SQL esistente basandoti sulla richiesta dell'utente.

QUERY SQL ORIGINALE:
{chart.sql_template}

RICHIESTA UTENTE: "{request.modification_request}"

REGOLE:
1. Modifica la query per soddisfare la richiesta dell'utente
2. Mantieni la struttura generale della query (SELECT, GROUP BY, ORDER BY)
3. Se l'utente chiede un anno specifico, aggiungi/modifica il filtro WHERE con EXTRACT(YEAR FROM order_date) = anno
4. Se chiede "ultimi X mesi", usa WHERE order_date >= CURRENT_DATE - INTERVAL 'X months'
5. Se chiede un trimestre (Q1, Q2, Q3, Q4), filtra con EXTRACT(QUARTER FROM order_date) = numero
6. Restituisci SOLO la query SQL modificata, senza spiegazioni

QUERY SQL MODIFICATA:"""
        
        response = llm_manager.complete(
            messages=[{"role": "user", "content": prompt}],
            provider=request.llm_provider,
            temperature=0.1,
            max_tokens=500
        )
        
        new_sql = response["content"].strip()
        # Rimuovi eventuali markdown code blocks
        if "```sql" in new_sql:
            new_sql = new_sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in new_sql:
            new_sql = new_sql.split("```")[1].split("```")[0].strip()
        
        logger.info(f"Modified SQL: {new_sql[:100]}...")
        
        # 3. Esegui la nuova query
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        results = mcp_postgres_client.execute_query(new_sql)
        
        if not results:
            return {
                "success": True,
                "chart_id": str(chart_id),
                "sql": new_sql,
                "results": [],
                "plotly_config": {"data": [], "layout": {"title": {"text": "Nessun risultato"}}},
                "message": "La query non ha restituito risultati",
                "execution_time_ms": (time.time() - start_time) * 1000
            }
        
        # 4. Genera nuovo grafico
        chart_service = create_chart_service(llm_provider=request.llm_provider)
        chart_data = chart_service.generate_chart(
            results=results,
            sql=new_sql,
            query=request.modification_request
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "chart_id": str(chart_id),
            "sql": new_sql,
            "results": results,
            "plotly_config": chart_data["plotly_config"],
            "chart_title": chart_data.get("chart_title", chart.title),
            "execution_time_ms": execution_time_ms
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Modify chart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))