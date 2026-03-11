"""
Metadata Service - CRUD saved charts e query history
"""

import logging
import time
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import desc

from app.models.system import SavedChart
from app.models.database import QueryHistory
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
        """Salva chart con metadata"""
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
        """Lista chart salvati (ordinati per data creazione DESC)"""
        query = db.query(SavedChart)

        if user_id:
            query = query.filter(SavedChart.user_id == user_id)

        charts = query.order_by(desc(SavedChart.created_at)).limit(limit).offset(offset).all()
        return charts

    @staticmethod
    def get_chart(db: Session, chart_id: UUID) -> Optional[SavedChart]:
        """Recupera singolo chart per ID"""
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
        6. Update DB
        """
        start_time = time.time()

        # 1. Recupera chart
        chart = db.query(SavedChart).filter(SavedChart.chart_id == chart_id).first()

        if not chart:
            raise ValueError(f"Chart {chart_id} not found")

        # 2. Merge parameters
        updated_params = dict(chart.parameters)  # Copy

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
            sql_concrete = sql_concrete.replace(placeholder, str(value))

        logger.info(f"SQL regenerated: {sql_concrete[:100]}...")

        # 4. Execute SQL
        try:
            if not mcp_postgres_client._connected:
                mcp_postgres_client.start()
            results = mcp_postgres_client.execute_query(sql_concrete)
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            raise ValueError(f"SQL execution failed: {e}")

        # 5. Regenerate Plotly config
        plotly_generator = PlotlyConfigGenerator()
        columns_info = ChartAnalyzer.analyze_results(results)

        # Mantieni chart_type originale dalla plotly_config salvata
        original_data = chart.plotly_config.get("data", [])
        original_chart_type = "bar"
        if original_data and len(original_data) > 0:
            original_chart_type = original_data[0].get("type", "bar")
            if original_chart_type == "scatter" and original_data[0].get("mode") == "lines+markers":
                original_chart_type = "line"

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
        
        # Flag JSONB columns as modified for SQLAlchemy to detect changes
        flag_modified(chart, "parameters")
        flag_modified(chart, "plotly_config")

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
        """Elimina chart"""
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
        """Log query in query_history table"""
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
        """Recupera query history"""
        query = db.query(QueryHistory)

        if session_id:
            query = query.filter(QueryHistory.session_id == session_id)

        history = query.order_by(desc(QueryHistory.created_at)).limit(limit).all()
        return history


# Singleton
metadata_service = MetadataService()