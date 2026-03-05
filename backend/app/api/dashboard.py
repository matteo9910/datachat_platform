"""
Dashboard API router - NL-driven generation, CRUD, dynamic filters, apply-filters.

Dashboards are stored in the system DB (DashboardMetadata model).
Chart data is fetched from the client DB via MCP.
"""

import json
import logging
import re
import uuid as uuid_module
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import DashboardMetadata, User
from app.services.auth_middleware import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DashboardGenerateRequest(BaseModel):
    """NL description -> dashboard config."""
    description: str = Field(..., min_length=1, max_length=2000)
    llm_provider: str = Field("azure", description="LLM provider to use")


class ChartSpec(BaseModel):
    """Spec for a single chart inside a dashboard."""
    title: str
    sql: str
    chart_type: str
    plotly_config: Optional[Dict[str, Any]] = None
    data: Optional[List[Dict[str, Any]]] = None


class DashboardGenerateResponse(BaseModel):
    charts: List[ChartSpec]
    layout: Dict[str, Any]
    suggested_name: str


class DashboardSaveRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    layout: Optional[Dict[str, Any]] = None
    charts: Optional[List[Dict[str, Any]]] = None
    filters: Optional[Dict[str, Any]] = None


class DashboardResponse(BaseModel):
    id: str
    name: str
    layout: Optional[Dict[str, Any]] = None
    charts: Optional[List[Dict[str, Any]]] = None
    filters: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DashboardListItem(BaseModel):
    id: str
    name: str
    charts_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ApplyFiltersRequest(BaseModel):
    dashboard_id: str
    filter_values: Dict[str, Any]


class ApplyFiltersResponse(BaseModel):
    charts: List[Dict[str, Any]]


class FilterOption(BaseModel):
    column: str
    filter_type: str  # 'date', 'categorical', 'numeric'
    values: Optional[List[Any]] = None
    min_val: Optional[Any] = None
    max_val: Optional[Any] = None
    label: str = ""


class AvailableFiltersResponse(BaseModel):
    filters: List[FilterOption]


# ---------------------------------------------------------------------------
# POST /api/dashboard/generate
# ---------------------------------------------------------------------------

@router.post("/api/dashboard/generate", response_model=DashboardGenerateResponse)
async def generate_dashboard(
    request: DashboardGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    NL description -> LLM identifies charts needed, generates SQL for each,
    determines chart types, creates layout config.
    """
    try:
        from app.services.llm_provider import get_llm_provider_manager
        from app.services.mcp_manager import mcp_postgres_client
        from app.services.chart_service import (
            ChartAnalyzer,
            PlotlyConfigGenerator,
        )

        llm = get_llm_provider_manager()

        # Step 1: Get DB schema for context
        schema_ddl = ""
        try:
            if not mcp_postgres_client._connected:
                mcp_postgres_client.start()
            tables = mcp_postgres_client.list_tables()
            schema_parts = []
            for t in tables[:20]:
                try:
                    desc = mcp_postgres_client.describe_table(t)
                    schema_parts.append(f"Table {t}: {desc}")
                except Exception:
                    schema_parts.append(f"Table {t}")
            schema_ddl = "\n".join(schema_parts)
        except Exception as e:
            logger.warning(f"Could not fetch schema for dashboard gen: {e}")

        # Step 2: Ask LLM to plan charts
        plan_prompt = (
            "You are a BI dashboard expert. The user wants a dashboard described as:\n"
            f'"{request.description}"\n\n'
            f"DATABASE SCHEMA:\n{schema_ddl}\n\n"
            "Generate a JSON array of chart specifications. Each chart should have:\n"
            '- "title": concise chart title\n'
            '- "sql": a valid PostgreSQL SELECT query\n'
            '- "chart_type": one of "bar", "line", "pie", "scatter", "table", "indicator"\n\n'
            "Generate 2-6 charts that together form a comprehensive dashboard.\n"
            "Return ONLY a valid JSON array, no markdown."
        )

        resp = llm.complete(
            messages=[
                {"role": "system", "content": "You are a BI dashboard expert. Return only valid JSON."},
                {"role": "user", "content": plan_prompt},
            ],
            provider=request.llm_provider,
            temperature=0.2,
            max_tokens=2000,
        )

        content = resp["content"].strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        chart_specs_raw = json.loads(content)
        if not isinstance(chart_specs_raw, list):
            chart_specs_raw = [chart_specs_raw]

        # Step 3: Execute each SQL and generate plotly config
        generator = PlotlyConfigGenerator()
        charts: List[ChartSpec] = []

        for spec in chart_specs_raw[:6]:
            title = spec.get("title", "Chart")
            sql = spec.get("sql", "")
            chart_type = spec.get("chart_type", "bar")
            if not sql:
                continue
            try:
                if not mcp_postgres_client._connected:
                    mcp_postgres_client.start()
                results = mcp_postgres_client.execute_query(sql)
                if results:
                    columns_info = ChartAnalyzer.analyze_results(results)
                    plotly_config = generator.generate_config(
                        results=results,
                        chart_type=chart_type,
                        columns_info=columns_info,
                        title=title,
                    )
                else:
                    plotly_config = {
                        "data": [],
                        "layout": {"title": {"text": f"{title} - No data"}},
                    }
                    results = []

                charts.append(ChartSpec(
                    title=title,
                    sql=sql,
                    chart_type=chart_type,
                    plotly_config=plotly_config,
                    data=results[:100],
                ))
            except Exception as e:
                logger.warning(f"Chart SQL execution failed for '{title}': {e}")
                charts.append(ChartSpec(
                    title=title,
                    sql=sql,
                    chart_type=chart_type,
                    plotly_config={
                        "data": [],
                        "layout": {"title": {"text": f"{title} - Error"}},
                    },
                    data=[],
                ))

        # Step 4: Build grid layout
        layout = _build_grid_layout(len(charts))

        suggested_name = request.description[:60].strip()
        if len(request.description) > 60:
            suggested_name += "..."

        return DashboardGenerateResponse(
            charts=charts,
            layout=layout,
            suggested_name=suggested_name,
        )

    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON for dashboard: {e}")
        raise HTTPException(status_code=500, detail="LLM returned invalid chart plan")
    except Exception as e:
        logger.error(f"Dashboard generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("/api/dashboards", response_model=DashboardResponse, status_code=201)
async def save_dashboard(
    request: DashboardSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """Save a new dashboard."""
    dash = DashboardMetadata(
        id=uuid_module.uuid4(),
        name=request.name.strip(),
        layout=request.layout,
        charts=request.charts,
        filters=request.filters,
        created_by=current_user.id,
    )
    db.add(dash)
    db.commit()
    db.refresh(dash)
    return _dash_to_response(dash)


@router.get("/api/dashboards", response_model=List[DashboardListItem])
async def list_dashboards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """List all saved dashboards for the current user."""
    rows = (
        db.query(DashboardMetadata)
        .filter(DashboardMetadata.created_by == current_user.id)
        .order_by(DashboardMetadata.created_at.desc())
        .all()
    )
    return [
        DashboardListItem(
            id=str(d.id),
            name=d.name,
            charts_count=len(d.charts) if d.charts else 0,
            created_at=d.created_at.isoformat() if d.created_at else None,
            updated_at=d.updated_at.isoformat() if d.updated_at else None,
        )
        for d in rows
    ]


@router.get("/api/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """Get a dashboard by ID."""
    dash = _get_dashboard_or_404(db, dashboard_id, current_user)
    return _dash_to_response(dash)


@router.put("/api/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: str,
    request: DashboardSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """Update an existing dashboard."""
    dash = _get_dashboard_or_404(db, dashboard_id, current_user)
    dash.name = request.name.strip()
    dash.layout = request.layout
    dash.charts = request.charts
    dash.filters = request.filters
    db.commit()
    db.refresh(dash)
    return _dash_to_response(dash)


@router.delete("/api/dashboards/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """Delete a dashboard."""
    dash = _get_dashboard_or_404(db, dashboard_id, current_user)
    db.delete(dash)
    db.commit()
    return {"status": "deleted", "id": dashboard_id}


# ---------------------------------------------------------------------------
# POST /api/dashboard/apply-filters
# ---------------------------------------------------------------------------

@router.post("/api/dashboard/apply-filters", response_model=ApplyFiltersResponse)
async def apply_filters(
    request: ApplyFiltersRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """
    Accept dashboard_id + filter values, modify SQL queries with WHERE clauses,
    re-execute, return updated chart data.
    """
    try:
        dash = _get_dashboard_or_404(db, request.dashboard_id, current_user)

        from app.services.mcp_manager import mcp_postgres_client
        from app.services.chart_service import ChartAnalyzer, PlotlyConfigGenerator

        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()

        generator = PlotlyConfigGenerator()
        updated_charts: List[Dict[str, Any]] = []

        charts_list = dash.charts or []
        for chart_item in charts_list:
            sql = chart_item.get("sql", "")
            title = chart_item.get("title", "Chart")
            chart_type = chart_item.get("chart_type", "bar")

            if not sql:
                updated_charts.append(chart_item)
                continue

            filtered_sql = _inject_where_clauses(sql, request.filter_values)

            try:
                results = mcp_postgres_client.execute_query(filtered_sql)
                if results:
                    columns_info = ChartAnalyzer.analyze_results(results)
                    plotly_config = generator.generate_config(
                        results=results,
                        chart_type=chart_type,
                        columns_info=columns_info,
                        title=title,
                    )
                else:
                    plotly_config = {
                        "data": [],
                        "layout": {
                            "title": {"text": f"{title} - No data"},
                            "annotations": [{
                                "text": "No data for selected filters",
                                "xref": "paper", "yref": "paper",
                                "x": 0.5, "y": 0.5,
                                "showarrow": False,
                                "font": {"size": 16, "color": "#94a3b8"},
                            }],
                        },
                    }
                    results = []

                updated_charts.append({
                    **chart_item,
                    "plotly_config": plotly_config,
                    "data": results[:100],
                    "filtered_sql": filtered_sql,
                })
            except Exception as e:
                logger.warning(f"Filter apply failed for '{title}': {e}")
                updated_charts.append({
                    **chart_item,
                    "plotly_config": {
                        "data": [],
                        "layout": {"title": {"text": f"{title} - Filter error"}},
                    },
                    "data": [],
                    "error": str(e),
                })

        return ApplyFiltersResponse(charts=updated_charts)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apply filters error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/dashboard/{id}/available-filters
# ---------------------------------------------------------------------------

@router.get(
    "/api/dashboard/{dashboard_id}/available-filters",
    response_model=AvailableFiltersResponse,
)
async def get_available_filters(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """
    Analyze chart SQL columns. Return dynamic filters:
    date -> time picker, categorical -> dropdown, numeric -> range.
    """
    try:
        dash = _get_dashboard_or_404(db, dashboard_id, current_user)

        from app.services.mcp_manager import mcp_postgres_client
        from app.services.chart_service import ChartAnalyzer

        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()

        seen_columns: Dict[str, FilterOption] = {}
        charts_list = dash.charts or []

        for chart_item in charts_list:
            sql = chart_item.get("sql", "")
            if not sql:
                continue

            try:
                probe_sql = _limit_query(sql, 500)
                results = mcp_postgres_client.execute_query(probe_sql)
                if not results:
                    continue

                columns_info = ChartAnalyzer.analyze_results(results)

                for col in columns_info:
                    if col.name in seen_columns:
                        continue

                    label = col.name.replace("_", " ").title()

                    if col.type == "date":
                        min_val = None
                        max_val = None
                        for row in results:
                            v = row.get(col.name)
                            if v is not None:
                                vs = str(v)
                                if min_val is None or vs < min_val:
                                    min_val = vs
                                if max_val is None or vs > max_val:
                                    max_val = vs
                        seen_columns[col.name] = FilterOption(
                            column=col.name,
                            filter_type="date",
                            label=label,
                            min_val=min_val,
                            max_val=max_val,
                        )
                    elif col.type == "numeric":
                        vals = [
                            float(row[col.name])
                            for row in results
                            if row.get(col.name) is not None
                        ]
                        seen_columns[col.name] = FilterOption(
                            column=col.name,
                            filter_type="numeric",
                            label=label,
                            min_val=min(vals) if vals else None,
                            max_val=max(vals) if vals else None,
                        )
                    elif col.type == "text" and col.cardinality <= 50:
                        seen_columns[col.name] = FilterOption(
                            column=col.name,
                            filter_type="categorical",
                            label=label,
                            values=sorted(col.sample_values),
                        )

            except Exception as e:
                logger.warning(f"Filter probe failed for SQL: {e}")

        return AvailableFiltersResponse(filters=list(seen_columns.values()))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Available filters error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dashboard_or_404(
    db: Session, dashboard_id: str, current_user: User
) -> DashboardMetadata:
    """Fetch dashboard owned by current user or raise 404."""
    try:
        uid = uuid_module.UUID(dashboard_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    dash = (
        db.query(DashboardMetadata)
        .filter(
            DashboardMetadata.id == uid,
            DashboardMetadata.created_by == current_user.id,
        )
        .first()
    )
    if dash is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dash


def _dash_to_response(dash: DashboardMetadata) -> DashboardResponse:
    return DashboardResponse(
        id=str(dash.id),
        name=dash.name,
        layout=dash.layout,
        charts=dash.charts,
        filters=dash.filters,
        created_by=str(dash.created_by) if dash.created_by else None,
        created_at=dash.created_at.isoformat() if dash.created_at else None,
        updated_at=dash.updated_at.isoformat() if dash.updated_at else None,
    )


def _build_grid_layout(chart_count: int) -> Dict[str, Any]:
    """Build a grid layout dict for N charts (2 cols)."""
    positions = []
    col_width = 400
    row_height = 350
    gap = 20
    for i in range(chart_count):
        col = i % 2
        row = i // 2
        positions.append({
            "index": i,
            "x": gap + col * (col_width + gap),
            "y": gap + row * (row_height + gap),
            "width": col_width,
            "height": row_height - gap,
        })
    return {
        "columns": 2,
        "positions": positions,
        "total_width": 2 * col_width + 3 * gap,
        "total_height": ((chart_count + 1) // 2) * row_height + gap,
    }


def _inject_where_clauses(sql: str, filters: Dict[str, Any]) -> str:
    """
    Inject WHERE clauses into an existing SQL query based on filter values.
    """
    if not filters:
        return sql

    conditions: List[str] = []
    for col, val in filters.items():
        safe_col = re.sub(r"[^a-zA-Z0-9_]", "", col)
        if not safe_col:
            continue

        if isinstance(val, dict):
            if "min" in val and val["min"] is not None:
                conditions.append(f"{safe_col} >= {_quote_val(val['min'])}")
            if "max" in val and val["max"] is not None:
                conditions.append(f"{safe_col} <= {_quote_val(val['max'])}")
        elif isinstance(val, list):
            if val:
                quoted = ", ".join(_quote_val(v) for v in val)
                conditions.append(f"{safe_col} IN ({quoted})")
        elif isinstance(val, str) and val:
            conditions.append(f"{safe_col} = {_quote_val(val)}")
        elif isinstance(val, (int, float)):
            conditions.append(f"{safe_col} = {val}")

    if not conditions:
        return sql

    extra = " AND ".join(conditions)

    where_pattern = re.compile(r"(\bWHERE\b)", re.IGNORECASE)
    group_order_pattern = re.compile(
        r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|UNION)\b", re.IGNORECASE
    )

    if where_pattern.search(sql):
        sql = where_pattern.sub(r"\1 (" + extra + ") AND", sql, count=1)
    else:
        match = group_order_pattern.search(sql)
        if match:
            pos = match.start()
            sql = sql[:pos] + f"WHERE {extra} " + sql[pos:]
        else:
            sql = sql.rstrip().rstrip(";") + f" WHERE {extra}"

    return sql


def _quote_val(v: Any) -> str:
    """Quote a value for safe SQL injection (basic sanitisation)."""
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _limit_query(sql: str, limit: int = 500) -> str:
    """Add LIMIT to query if not already present."""
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql
    return sql.rstrip().rstrip(";") + f" LIMIT {limit}"