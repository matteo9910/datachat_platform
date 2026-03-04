# Fase 05: Persistenza Chart con Metadata JSONB e Modifica Parametri

## Panoramica
- **Obiettivo**: Implementare CRUD chart salvati con metadata JSONB PostgreSQL e API modifica parametri real-time
- **Dipendenza**: Fase 04 (Chart generation con parameter extraction funzionante)
- **Complessità stimata**: Media
- **Componenti coinvolti**: Backend, Database

## Contesto
La Fase 04 ha implementato generazione chart con estrazione parametri modificabili. Ora rendiamo questi chart **persistenti** e **modificabili post-creazione**: l'utente salva un chart, poi può cambiare parametri (es. granularità temporale da "mensile" a "trimestrale") senza rifare la query NL.

Questo è il **gap di mercato chiave**: nessuna soluzione competitor permette modifica parametri chart salvati. Wren AI, Vanna, ThoughtSpot generano chart statici. Noi creiamo chart **parametrici dinamici**.

Storage in PostgreSQL schema `poc_metadata.saved_charts`:
- `sql_template`: SQL con placeholder `{param_name}`
- `parameters`: JSONB con schema parametri (type, current, options)
- `plotly_config`: JSONB con config Plotly completa
- `created_at`, `updated_at`: Timestamps
- `chart_id`: UUID primary key

Workflow modifica parametri:
1. Frontend cambia dropdown "Granularità: Mensile → Trimestrale"
2. PUT `/api/charts/{id}/parameters` con `{"time_granularity": "quarter"}`
3. Backend recupera `sql_template`, sostituisce `{time_granularity}` con `"quarter"`
4. Esegue SQL via MCP PostgreSQL
5. Rigenera config Plotly con nuovi dati
6. Response aggiornata < 5s (target performance)

## Obiettivi Specifici
1. Creare SQLAlchemy models per `saved_charts` e `query_history` (già definiti in schema Fase 1)
2. Creare `metadata_service.py` con CRUD operations saved charts
3. Implementare endpoint `/api/charts/save` (POST): salva chart con metadata
4. Implementare endpoint `/api/charts` (GET): lista tutti chart salvati
5. Implementare endpoint `/api/charts/{id}` (GET): recupera singolo chart
6. Implementare endpoint `/api/charts/{id}/parameters` (PUT): modifica parametri, rigenera chart
7. Implementare endpoint `/api/charts/{id}` (DELETE): elimina chart
8. Implementare query history logging in `query_history` table
9. Testare workflow completo: save → list → modify parameters → verify update
10. Validare performance modifica parametri < 5s

## Specifiche Tecniche Dettagliate

### Area 1: SQLAlchemy Models

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app/models/database.py`

```python
"""
SQLAlchemy models - Database tables
"""

from sqlalchemy import Column, String, Text, Boolean, Integer, TIMESTAMP, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class SavedChart(Base):
    """Tabella poc_metadata.saved_charts"""
    __tablename__ = "saved_charts"
    __table_args__ = {"schema": "poc_metadata"}

    chart_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=True)  # Future multi-user
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sql_template = Column(Text, nullable=False)  # SQL con placeholder {param_name}
    parameters = Column(JSONB, nullable=False, default={})  # Schema parametri
    plotly_config = Column(JSONB, nullable=False)  # Config Plotly
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())

    def to_dict(self):
        """Serialize to dict"""
        return {
            "chart_id": str(self.chart_id),
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "sql_template": self.sql_template,
            "parameters": self.parameters,
            "plotly_config": self.plotly_config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class QueryHistory(Base):
    """Tabella poc_metadata.query_history"""
    __tablename__ = "query_history"
    __table_args__ = {"schema": "poc_metadata"}

    query_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), nullable=False, index=True)
    nl_query = Column(Text, nullable=False)
    sql_generated = Column(Text, nullable=True)
    llm_provider = Column(String(20), nullable=True)  # 'claude' | 'azure'
    success = Column(Boolean, nullable=False, default=False, index=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    result_rows = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), index=True)

    def to_dict(self):
        """Serialize to dict"""
        return {
            "query_id": str(self.query_id),
            "session_id": self.session_id,
            "nl_query": self.nl_query,
            "sql_generated": self.sql_generated,
            "llm_provider": self.llm_provider,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "result_rows": self.result_rows,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
```

**Database connection setup:**

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\dependencies.py`

```python
"""
FastAPI dependencies - Database session, services, etc.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

# Database engine
engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=False  # Set True per debug SQL queries
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Dependency per ottenere DB session

    Usage in FastAPI:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

### Area 2: Metadata Service (CRUD Saved Charts)

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\metadata_service.py`

```python
"""
Metadata Service - CRUD saved charts e query history
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.database import SavedChart, QueryHistory
from app.services.mcp_manager import mcp_postgres_client
from app.services.chart_service import PlotlyConfigGenerator, ChartAnalyzer

logger = logging.getLogger(__name__)


class MetadataService:
    """Service gestione metadata (saved charts, query history)"""

    @staticmethod
    def save_chart(
        db: Session,
        title: str,
        sql_template: str,
        parameters: Dict[str, Any],
        plotly_config: Dict[str, Any],
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> SavedChart:
        """
        Salva chart con metadata

        Args:
            db: SQLAlchemy session
            title: Titolo chart
            sql_template: SQL con placeholder {param_name}
            parameters: Dict parametri (da ParameterExtractor)
            plotly_config: Config Plotly completa
            description: Descrizione opzionale
            user_id: ID utente (future multi-user)

        Returns:
            SavedChart instance
        """
        chart = SavedChart(
            title=title,
            description=description,
            sql_template=sql_template,
            parameters=parameters,
            plotly_config=plotly_config,
            user_id=user_id
        )

        db.add(chart)
        db.commit()
        db.refresh(chart)

        logger.info(f"Chart saved: id={chart.chart_id}, title='{title}'")
        return chart

    @staticmethod
    def list_charts(
        db: Session,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[str] = None
    ) -> List[SavedChart]:
        """
        Lista chart salvati (ordinati per data creazione DESC)

        Args:
            db: SQLAlchemy session
            limit: Max risultati
            offset: Offset paginazione
            user_id: Filtra per user (opzionale)

        Returns:
            Lista SavedChart
        """
        query = db.query(SavedChart)

        if user_id:
            query = query.filter(SavedChart.user_id == user_id)

        charts = query.order_by(desc(SavedChart.created_at)).limit(limit).offset(offset).all()

        return charts

    @staticmethod
    def get_chart(db: Session, chart_id: UUID) -> Optional[SavedChart]:
        """
        Recupera singolo chart per ID

        Returns:
            SavedChart o None se non trovato
        """
        chart = db.query(SavedChart).filter(SavedChart.chart_id == chart_id).first()
        return chart

    @staticmethod
    def update_chart_parameters(
        db: Session,
        chart_id: UUID,
        new_parameters: Dict[str, Any],
        llm_provider: str = "claude"
    ) -> Dict[str, Any]:
        """
        Modifica parametri chart e rigenera

        Workflow:
        1. Recupera chart da DB
        2. Merge new_parameters con parameters esistenti
        3. Sostituisci placeholder SQL template con nuovi valori
        4. Esegui SQL via MCP
        5. Rigenera config Plotly con nuovi dati
        6. Update DB (parameters, plotly_config, updated_at)

        Args:
            db: SQLAlchemy session
            chart_id: ID chart
            new_parameters: Dict {param_name: new_value}
            llm_provider: Provider per chart regeneration

        Returns:
            {
                "chart_id": str,
                "plotly_config": dict,
                "results": list[dict],
                "updated_at": str,
                "success": bool
            }
        """
        import time
        from datetime import datetime

        start_time = time.time()

        # 1. Recupera chart
        chart = db.query(SavedChart).filter(SavedChart.chart_id == chart_id).first()

        if not chart:
            raise ValueError(f"Chart {chart_id} not found")

        # 2. Merge parameters
        updated_params = chart.parameters.copy()

        for param_name, new_value in new_parameters.items():
            if param_name in updated_params:
                updated_params[param_name]["current_value"] = new_value
            else:
                logger.warning(f"Parameter '{param_name}' not found in chart schema")

        # 3. Generate SQL from template
        sql_template = chart.sql_template
        sql_concrete = sql_template

        for param_name, param_data in updated_params.items():
            placeholder = f"{{{param_name}}}"
            value = param_data["current_value"]

            # Replace placeholder
            sql_concrete = sql_concrete.replace(placeholder, str(value))

        logger.info(f"SQL regenerated: {sql_concrete[:100]}...")

        # 4. Execute SQL
        try:
            results = mcp_postgres_client.execute_query(sql_concrete)
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            raise ValueError(f"SQL execution failed: {e}")

        # 5. Regenerate Plotly config
        plotly_generator = PlotlyConfigGenerator(llm_provider=llm_provider)
        columns_info = ChartAnalyzer.analyze_results(results)

        # Mantieni chart_type originale (no re-detection)
        original_chart_type = chart.plotly_config.get("chart_type", "bar")

        new_plotly_config = plotly_generator.generate_config(
            results=results,
            chart_type=original_chart_type,
            columns_info=columns_info,
            title=chart.title
        )

        # 6. Update database
        chart.parameters = updated_params
        chart.plotly_config = new_plotly_config
        chart.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(chart)

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Chart parameters updated: id={chart_id}, "
            f"{len(results)} rows, {execution_time_ms:.0f}ms"
        )

        return {
            "chart_id": str(chart.chart_id),
            "plotly_config": new_plotly_config,
            "results": results,
            "updated_at": chart.updated_at.isoformat(),
            "execution_time_ms": execution_time_ms,
            "success": True
        }

    @staticmethod
    def delete_chart(db: Session, chart_id: UUID) -> bool:
        """
        Elimina chart

        Returns:
            True se eliminato, False se non trovato
        """
        chart = db.query(SavedChart).filter(SavedChart.chart_id == chart_id).first()

        if not chart:
            return False

        db.delete(chart)
        db.commit()

        logger.info(f"Chart deleted: id={chart_id}")
        return True

    # ============================================================
    # QUERY HISTORY
    # ============================================================

    @staticmethod
    def log_query(
        db: Session,
        session_id: str,
        nl_query: str,
        sql_generated: Optional[str],
        llm_provider: str,
        success: bool,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        result_rows: Optional[int] = None
    ) -> QueryHistory:
        """
        Log query in query_history table

        Usage: chiamare dopo ogni chat query (success o failure)
        """
        history_entry = QueryHistory(
            session_id=session_id,
            nl_query=nl_query,
            sql_generated=sql_generated,
            llm_provider=llm_provider,
            success=success,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            result_rows=result_rows
        )

        db.add(history_entry)
        db.commit()
        db.refresh(history_entry)

        return history_entry

    @staticmethod
    def get_query_history(
        db: Session,
        session_id: Optional[str] = None,
        limit: int = 100
    ) -> List[QueryHistory]:
        """
        Recupera query history

        Args:
            db: SQLAlchemy session
            session_id: Filtra per session (opzionale)
            limit: Max risultati

        Returns:
            Lista QueryHistory ordinata per created_at DESC
        """
        query = db.query(QueryHistory)

        if session_id:
            query = query.filter(QueryHistory.session_id == session_id)

        history = query.order_by(desc(QueryHistory.created_at)).limit(limit).all()

        return history


# Singleton (stateless, no init necessario)
metadata_service = MetadataService()
```

---

### Area 3: API Endpoints Charts

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\api\charts.py`

```python
"""
Charts API endpoints - CRUD saved charts
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.dependencies import get_db
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
async def save_chart(request: SaveChartRequest, db: Session = Depends(get_db)):
    """
    Salva chart con metadata parametrica

    **Use case:** Utente genera chart da chat, clicca "Salva" → chiamata a questo endpoint
    """
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
    db: Session = Depends(get_db)
):
    """
    Lista tutti i chart salvati (ordinati per data creazione DESC)

    **Paginazione:** usa limit + offset
    """
    try:
        charts = metadata_service.list_charts(db=db, limit=limit, offset=offset)

        chart_summaries = [
            ChartSummary(
                chart_id=str(c.chart_id),
                title=c.title,
                description=c.description,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat() if c.updated_at else None
            )
            for c in charts
        ]

        return ListChartsResponse(
            charts=chart_summaries,
            total=len(chart_summaries)  # TODO: count(*) query per paginazione vera
        )

    except Exception as e:
        logger.error(f"List charts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chart_id}", response_model=ChartDetail)
async def get_chart(chart_id: UUID, db: Session = Depends(get_db)):
    """
    Recupera dettagli chart salvato per ID

    **Use case:** Frontend carica chart esistente per visualizzazione/modifica
    """
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
    db: Session = Depends(get_db)
):
    """
    Modifica parametri chart e rigenera

    **Use case:** Utente cambia dropdown "Granularità: Mensile → Trimestrale" su chart salvato

    **Workflow:**
    1. Recupera chart da DB
    2. Merge nuovi parametri
    3. Sostituisci placeholder SQL template
    4. Esegui SQL
    5. Rigenera config Plotly
    6. Update DB

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
        # Chart not found o SQL error
        logger.error(f"Update parameters error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Update parameters error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{chart_id}")
async def delete_chart(chart_id: UUID, db: Session = Depends(get_db)):
    """
    Elimina chart salvato

    **Returns:** 204 No Content se successo, 404 se non trovato
    """
    try:
        deleted = metadata_service.delete_chart(db=db, chart_id=chart_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Chart not found")

        return {"status": "deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete chart error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Aggiornare `main.py`:**

```python
# In backend/app/main.py, aggiungere:

from app.api import charts

# Include router
app.include_router(charts.router)
```

---

### Area 4: Query History Logging Integration

**Modificare `chat_orchestrator.py` per loggare query:**

```python
# In chat_orchestrator.py, aggiungere import
from app.services.metadata_service import metadata_service
from app.dependencies import SessionLocal

class ChatOrchestrator:
    def process_query(...):
        # ... (codice esistente) ...

        # AGGIUNGERE logging query history (fine metodo, prima di return)
        try:
            db = SessionLocal()
            metadata_service.log_query(
                db=db,
                session_id=session_id,
                nl_query=query,
                sql_generated=sql if sql_result["success"] else None,
                llm_provider=self.llm_provider,
                success=exec_result["success"],
                error_message=exec_result.get("error"),
                execution_time_ms=int(execution_time_ms),
                result_rows=len(rows)
            )
            db.close()
        except Exception as e:
            logger.warning(f"Query history logging failed: {e}")
            # Non bloccare risposta se logging fallisce

        return {...}
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `backend/app/models/database.py` | Creare | SQLAlchemy models `SavedChart`, `QueryHistory` |
| `backend/app/dependencies.py` | Creare | Database session factory + `get_db()` dependency |
| `backend/app/services/metadata_service.py` | Creare | CRUD saved charts, query history logging |
| `backend/app/api/charts.py` | Creare | API endpoints `/api/charts/*` |
| `backend/app/main.py` | Modificare | Include router charts |
| `backend/app/services/chat_orchestrator.py` | Modificare | Aggiungere query history logging |

## Dipendenze da Installare

Nessuna nuova dipendenza (SQLAlchemy già installato in Fase 2).

## Variabili d'Ambiente

Nessuna nuova variabile necessaria.

## Criteri di Completamento

- [ ] SQLAlchemy models `SavedChart` e `QueryHistory` creati con mapping tabelle PostgreSQL
- [ ] Database session factory `get_db()` funziona come dependency FastAPI
- [ ] Endpoint `/api/charts/save` salva chart senza errori
- [ ] Endpoint `/api/charts` lista chart salvati ordinati per created_at DESC
- [ ] Endpoint `/api/charts/{id}` recupera chart per UUID
- [ ] Endpoint `/api/charts/{id}/parameters` modifica parametri e rigenera chart in <5s
- [ ] Endpoint `/api/charts/{id}` DELETE elimina chart
- [ ] Query history logging funziona (ogni chat query salvata in `query_history`)
- [ ] Test workflow completo: save → list → get → modify parameters → verify update
- [ ] JSONB fields (parameters, plotly_config) salvati e recuperati correttamente
- [ ] Timestamps `created_at`, `updated_at` popolati automaticamente

## Test di Verifica

### Test 1: Save Chart

```bash
# Salva chart (mockare dati reali da chat query precedente)
curl -X POST http://localhost:8000/api/charts/save \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Vendite Mensili per Categoria",
    "description": "Test chart parametrico",
    "sql_template": "SELECT DATE_TRUNC('\''{time_granularity}'\'', order_date) as period, category, SUM(sales) as sales FROM public.orders WHERE EXTRACT(YEAR FROM order_date) = {year} GROUP BY period, category ORDER BY period LIMIT {limit}",
    "parameters": {
      "time_granularity": {
        "name": "time_granularity",
        "type": "enum",
        "current_value": "month",
        "options": ["day", "week", "month", "quarter", "year"],
        "label": "Granularità Temporale"
      },
      "year": {
        "name": "year",
        "type": "number",
        "current_value": 2023,
        "min_value": 2014,
        "max_value": 2026,
        "label": "Anno"
      },
      "limit": {
        "name": "limit",
        "type": "number",
        "current_value": 10,
        "min_value": 1,
        "max_value": 1000,
        "label": "Limite Risultati"
      }
    },
    "plotly_config": {
      "data": [{"type": "line", "x": ["2023-01"], "y": [50000]}],
      "layout": {"title": "Vendite Mensili"}
    }
  }'

# Output atteso:
# {
#   "chart_id": "550e8400-e29b-41d4-a716-446655440000",
#   "created_at": "2026-02-17T10:30:00"
# }

# Salvare chart_id per test successivi
```

### Test 2: List Charts

```bash
curl http://localhost:8000/api/charts

# Output atteso:
# {
#   "charts": [
#     {
#       "chart_id": "550e8400-...",
#       "title": "Vendite Mensili per Categoria",
#       "description": "Test chart parametrico",
#       "created_at": "2026-02-17T10:30:00",
#       "updated_at": null
#     }
#   ],
#   "total": 1
# }
```

### Test 3: Get Chart Detail

```bash
CHART_ID="550e8400-e29b-41d4-a716-446655440000"  # Sostituire con ID reale

curl "http://localhost:8000/api/charts/$CHART_ID"

# Output atteso: dettagli completi chart (sql_template, parameters, plotly_config)
```

### Test 4: Update Parameters (CORE TEST)

```bash
# Modifica granularità da "month" a "quarter"
curl -X PUT "http://localhost:8000/api/charts/$CHART_ID/parameters" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "time_granularity": "quarter"
    },
    "llm_provider": "claude"
  }'

# Output atteso:
# {
#   "chart_id": "550e8400-...",
#   "plotly_config": {
#     "data": [...],  # Dati rigenerati con aggregazione trimestrale
#     "layout": {...}
#   },
#   "results": [...],  # Nuovi risultati SQL
#   "updated_at": "2026-02-17T10:35:00",
#   "execution_time_ms": 2345.67
# }

# Verificare execution_time_ms < 5000 (5s)
```

### Test 5: Verify Update Persistence

```bash
# Recupera chart aggiornato
curl "http://localhost:8000/api/charts/$CHART_ID" | jq '.parameters.time_granularity.current_value'

# Output atteso: "quarter" (non più "month")
```

### Test 6: Delete Chart

```bash
curl -X DELETE "http://localhost:8000/api/charts/$CHART_ID"

# Output atteso: {"status": "deleted"}

# Verifica eliminazione
curl "http://localhost:8000/api/charts/$CHART_ID"

# Output atteso: 404 Not Found
```

### Test 7: Query History Logging

```sql
-- Query PostgreSQL per verificare logging
SELECT
    nl_query,
    sql_generated,
    llm_provider,
    success,
    execution_time_ms,
    result_rows,
    created_at
FROM poc_metadata.query_history
ORDER BY created_at DESC
LIMIT 10;

-- Verificare che ogni chat query sia loggata
```

### Test 8: Performance Test Update Parameters

```python
# Test performance modifiche parametri multiple
import requests
import time

CHART_ID = "550e8400-..."  # Sostituire con ID reale

# Test 10 modifiche consecutive
times = []

for granularity in ["day", "week", "month", "quarter", "year"] * 2:
    start = time.time()

    response = requests.put(
        f"http://localhost:8000/api/charts/{CHART_ID}/parameters",
        json={"parameters": {"time_granularity": granularity}}
    )

    elapsed = time.time() - start
    times.append(elapsed)

    assert response.status_code == 200
    print(f"Update {granularity}: {elapsed:.2f}s")

# Calcola statistiche
import statistics
print(f"\nMean: {statistics.mean(times):.2f}s")
print(f"Median: {statistics.median(times):.2f}s")
print(f"Max: {max(times):.2f}s")

# Verificare: Max < 5s, Median < 3s
assert max(times) < 5.0, "Performance target non rispettato: max > 5s"
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **SQLAlchemy declarative:** Usare `Base = declarative_base()`, tutti models ereditano da `Base`
2. **UUID primary keys:** Tipo `UUID(as_uuid=True)` per native Python UUID objects
3. **JSONB columns:** PostgreSQL native, no serialization manuale necessaria
4. **Dependency Injection:** `db: Session = Depends(get_db)` in ogni endpoint che accede database
5. **Service layer stateless:** `metadata_service` singleton senza stato, DB session passata come parametro

### Convenzioni Naming

- **Table names:** Plural `saved_charts`, `query_history`
- **Schema:** Sempre specificare `__table_args__ = {"schema": "poc_metadata"}`
- **UUID string format:** Sempre serialize UUID con `str(uuid_obj)` in API responses
- **Timestamps:** ISO 8601 format `datetime.isoformat()`

### Errori Comuni da Evitare

1. **Foreign key constraints:** Non definite per POC (single-user), aggiungere in multi-user
2. **Session leaks:** Sempre `db.close()` in finally block o usare context manager
3. **JSONB serialization:** SQLAlchemy gestisce automaticamente, no `json.dumps()` necessario
4. **UUID type mismatch:** Endpoint riceve `str`, convertire con `UUID(str_value)` per query
5. **Placeholder replacement case-sensitive:** Usare exact match `{param_name}` con braces

### Troubleshooting

**Errore: "relation poc_metadata.saved_charts does not exist"**
```bash
# Verificare schema creato (Fase 1)
psql -U datachat_user -d datachat_db -c "\dt poc_metadata.*"

# Se mancante, eseguire init_schema.sql
psql -U postgres -d datachat_db -f database/init_schema.sql
```

**Errore: "column does not exist"**
- Verificare mapping SQLAlchemy column names match schema PostgreSQL
- Case-sensitivity: PostgreSQL lowercase, SQLAlchemy definisce `Column("created_at")`

**Update parameters lento (>5s)**
- Verificare indici PostgreSQL su `orders` table (creati Fase 1)
- Controllare query SQL generata: evitare full table scan
- Profilare con `EXPLAIN ANALYZE` SQL

**JSONB not serializable in response**
- Pydantic converte automaticamente dict → JSON
- Verificare no custom objects in JSONB (solo dict, list, primitives)

**Query history non loggata**
```python
# Debug: verificare SessionLocal() funziona
from app.dependencies import SessionLocal
db = SessionLocal()
print(db.execute("SELECT 1").fetchone())
db.close()
```

## Riferimenti

- **BRIEFING.md**: Sezione "Funzionalità Core" (salvataggio chart, modifica parametri)
- **PRD.md**: Sezione 4.2 "API Endpoints Chart Management", Sezione 3.4 "Flusso 2: Salvataggio Chart", "Flusso 3: Modifica Parametri"
- **Fase precedente**: `phase-04-generazione-chart-plotly-sistema-parametrico.md` (chart generation, parameter extraction)
- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/en/20/
- **FastAPI Dependency Injection**: https://fastapi.tiangolo.com/tutorial/dependencies/
- **PostgreSQL JSONB**: https://www.postgresql.org/docs/16/datatype-json.html
