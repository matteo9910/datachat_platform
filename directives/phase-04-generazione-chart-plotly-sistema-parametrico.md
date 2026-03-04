# Fase 04: Generazione Chart Plotly e Sistema Parametrico

## Panoramica
- **Obiettivo**: Implementare auto-generazione chart Plotly con detection automatica tipo chart e sistema di estrazione parametri modificabili
- **Dipendenza**: Fase 03 (Chat orchestrator funzionante con SQL execution)
- **Complessità stimata**: Alta
- **Componenti coinvolti**: Backend, AI

## Contesto
La Fase 03 ha completato il workflow text-to-SQL con risposta NL. Ora aggiungiamo visualizzazione grafica dei risultati: chart Plotly interattivi generati automaticamente.

Il sistema deve:
1. **Analizzare risultati SQL** (struttura colonne, tipi dati, cardinalità) per determinare chart type appropriato
2. **Generare config Plotly** (JSON) con LLM guidance per layout ottimale
3. **Estrarre parametri modificabili** dal SQL template (es. `DATE_TRUNC('month', ...)` → parametro `time_granularity` con opzioni `day/week/month/quarter/year`)
4. **Templating SQL** con placeholder `{param_name}` per futura modifica parametri (Fase 5)

Questo è il **gap di mercato** identificato nel BRIEFING: nessuna soluzione competitor permette modifica parametri chart post-generazione senza rifare query NL.

Plotly.js è scelto per:
- 40+ chart types built-in
- Config JSON-serializable (facile storage PostgreSQL JSONB)
- Interattività nativa (hover, zoom, pan, download PNG)
- Perfect sync Plotly Python (backend) ↔ Plotly.js (frontend)

## Obiettivi Specifici
1. Creare `chart_service.py` con logica auto-detection chart type
2. Implementare `ChartAnalyzer` che analizza risultati SQL e suggerisce chart type (bar/line/pie/scatter/histogram)
3. Implementare `PlotlyConfigGenerator` che genera config Plotly completa da risultati + chart type
4. Creare `ParameterExtractor` che identifica pattern SQL parametrizzabili (date granularity, filters, limits)
5. Implementare SQL templating engine: converte SQL concreto in template con `{param_name}` placeholder
6. Integrare chart generation in `chat_orchestrator.py`
7. Estendere endpoint `/api/chat/query` response con campo `chart` (Plotly config JSON)
8. Testare generazione chart su 10 query diverse (tutti chart types coperti)
9. Validare config Plotly generata (render frontend mock in Fase 7)

## Specifiche Tecniche Dettagliate

### Area 1: Chart Service - Auto-Detection e Generation

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\chart_service.py`

```python
"""
Chart Service - Auto-detection chart type e generazione config Plotly
"""

import logging
import json
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass

from app.services.llm_provider import llm_provider_manager
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    """Info colonna risultato SQL"""
    name: str
    type: str  # 'numeric', 'text', 'date', 'boolean'
    cardinality: int  # Numero valori unici
    sample_values: List[Any]


ChartType = Literal["bar", "line", "pie", "scatter", "histogram", "table"]


class ChartAnalyzer:
    """Analizza risultati SQL e determina chart type appropriato"""

    @staticmethod
    def analyze_results(results: List[Dict[str, Any]]) -> List[ColumnInfo]:
        """
        Analizza struttura risultati SQL

        Returns:
            Lista ColumnInfo con metadata ogni colonna
        """
        if not results:
            return []

        columns_info = []

        # Analizza ogni colonna
        for col_name in results[0].keys():
            values = [row[col_name] for row in results if row[col_name] is not None]

            # Determina type
            col_type = ChartAnalyzer._infer_column_type(values)

            # Calcola cardinalità (valori unici)
            unique_values = set(values)
            cardinality = len(unique_values)

            # Sample values (max 10)
            sample_values = list(unique_values)[:10]

            columns_info.append(ColumnInfo(
                name=col_name,
                type=col_type,
                cardinality=cardinality,
                sample_values=sample_values
            ))

        return columns_info

    @staticmethod
    def _infer_column_type(values: List[Any]) -> str:
        """Infer tipo colonna da sample values"""
        if not values:
            return "text"

        sample = values[0]

        # Numeric
        if isinstance(sample, (int, float)):
            return "numeric"

        # Date (heuristic: str con pattern date-like)
        if isinstance(sample, str):
            # Check ISO date pattern (YYYY-MM-DD o YYYY-MM-DD HH:MM:SS)
            if len(sample) >= 10 and sample[4] == '-' and sample[7] == '-':
                return "date"

        # Boolean
        if isinstance(sample, bool):
            return "boolean"

        # Default text
        return "text"

    @staticmethod
    def suggest_chart_type(columns_info: List[ColumnInfo]) -> ChartType:
        """
        Suggerisci chart type basato su struttura dati

        Regole euristiche:
        - 1 colonna text + 1 numeric → bar chart
        - 1 colonna date + 1+ numeric → line chart
        - 1 colonna text (low cardinality <10) + 1 numeric → pie chart
        - 2+ colonne numeric → scatter plot
        - 1 colonna numeric solo → histogram
        - Default → table
        """
        if len(columns_info) < 2:
            # Solo 1 colonna → histogram se numeric, altrimenti table
            if len(columns_info) == 1 and columns_info[0].type == "numeric":
                return "histogram"
            return "table"

        # Classifica colonne
        text_cols = [c for c in columns_info if c.type == "text"]
        numeric_cols = [c for c in columns_info if c.type == "numeric"]
        date_cols = [c for c in columns_info if c.type == "date"]

        # Date + numeric → line chart (time series)
        if date_cols and numeric_cols:
            return "line"

        # Text (low cardinality) + numeric → pie chart
        if text_cols and numeric_cols:
            text_col = text_cols[0]
            if text_col.cardinality <= 10:
                return "pie"
            else:
                return "bar"

        # 2+ numeric → scatter
        if len(numeric_cols) >= 2:
            return "scatter"

        # Fallback bar chart
        if text_cols and numeric_cols:
            return "bar"

        # Default table
        return "table"


class PlotlyConfigGenerator:
    """Genera config Plotly completa da risultati + chart type"""

    def __init__(self, llm_provider: str = "claude"):
        self.llm_provider = llm_provider

    def generate_config(
        self,
        results: List[Dict[str, Any]],
        chart_type: ChartType,
        columns_info: List[ColumnInfo],
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera config Plotly completa

        Returns:
            {
                "data": [...],    # Plotly data traces
                "layout": {...}   # Plotly layout
            }
        """
        if chart_type == "bar":
            return self._generate_bar_chart(results, columns_info, title)
        elif chart_type == "line":
            return self._generate_line_chart(results, columns_info, title)
        elif chart_type == "pie":
            return self._generate_pie_chart(results, columns_info, title)
        elif chart_type == "scatter":
            return self._generate_scatter_chart(results, columns_info, title)
        elif chart_type == "histogram":
            return self._generate_histogram(results, columns_info, title)
        else:  # table
            return self._generate_table(results, columns_info, title)

    def _generate_bar_chart(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Bar chart: 1 text col (x) + 1+ numeric cols (y)"""
        # Identifica x (text) e y (numeric)
        text_col = next((c for c in columns_info if c.type == "text"), None)
        numeric_cols = [c for c in columns_info if c.type == "numeric"]

        if not text_col or not numeric_cols:
            # Fallback: usa prime 2 colonne
            text_col = columns_info[0]
            numeric_cols = columns_info[1:2]

        x_values = [row[text_col.name] for row in results]

        # Crea trace per ogni colonna numeric
        data = []
        for num_col in numeric_cols:
            y_values = [row[num_col.name] for row in results]

            data.append({
                "type": "bar",
                "x": x_values,
                "y": y_values,
                "name": num_col.name,
                "marker": {"color": self._get_color(len(data))}
            })

        layout = {
            "title": title or "Bar Chart",
            "xaxis": {"title": text_col.name},
            "yaxis": {"title": numeric_cols[0].name if len(numeric_cols) == 1 else "Value"},
            "barmode": "group" if len(numeric_cols) > 1 else "relative"
        }

        return {"data": data, "layout": layout}

    def _generate_line_chart(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Line chart: 1 date col (x) + 1+ numeric cols (y)"""
        date_col = next((c for c in columns_info if c.type == "date"), None)
        numeric_cols = [c for c in columns_info if c.type == "numeric"]

        if not date_col or not numeric_cols:
            # Fallback: prime 2 colonne
            date_col = columns_info[0]
            numeric_cols = columns_info[1:2]

        x_values = [row[date_col.name] for row in results]

        data = []
        for num_col in numeric_cols:
            y_values = [row[num_col.name] for row in results]

            data.append({
                "type": "scatter",
                "mode": "lines+markers",
                "x": x_values,
                "y": y_values,
                "name": num_col.name,
                "line": {"color": self._get_color(len(data))}
            })

        layout = {
            "title": title or "Line Chart",
            "xaxis": {"title": date_col.name, "type": "date"},
            "yaxis": {"title": numeric_cols[0].name if len(numeric_cols) == 1 else "Value"}
        }

        return {"data": data, "layout": layout}

    def _generate_pie_chart(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Pie chart: 1 text col (labels) + 1 numeric col (values)"""
        text_col = next((c for c in columns_info if c.type == "text"), None)
        numeric_col = next((c for c in columns_info if c.type == "numeric"), None)

        if not text_col or not numeric_col:
            text_col = columns_info[0]
            numeric_col = columns_info[1]

        labels = [row[text_col.name] for row in results]
        values = [row[numeric_col.name] for row in results]

        data = [{
            "type": "pie",
            "labels": labels,
            "values": values,
            "hoverinfo": "label+percent+value",
            "textinfo": "label+percent"
        }]

        layout = {
            "title": title or "Pie Chart"
        }

        return {"data": data, "layout": layout}

    def _generate_scatter_chart(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Scatter: 2 numeric cols (x, y)"""
        numeric_cols = [c for c in columns_info if c.type == "numeric"]

        if len(numeric_cols) < 2:
            # Fallback bar chart
            return self._generate_bar_chart(results, columns_info, title)

        x_col = numeric_cols[0]
        y_col = numeric_cols[1]

        x_values = [row[x_col.name] for row in results]
        y_values = [row[y_col.name] for row in results]

        data = [{
            "type": "scatter",
            "mode": "markers",
            "x": x_values,
            "y": y_values,
            "marker": {"size": 10, "color": self._get_color(0)}
        }]

        layout = {
            "title": title or "Scatter Plot",
            "xaxis": {"title": x_col.name},
            "yaxis": {"title": y_col.name}
        }

        return {"data": data, "layout": layout}

    def _generate_histogram(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Histogram: 1 numeric col"""
        numeric_col = next((c for c in columns_info if c.type == "numeric"), columns_info[0])

        x_values = [row[numeric_col.name] for row in results]

        data = [{
            "type": "histogram",
            "x": x_values,
            "marker": {"color": self._get_color(0)}
        }]

        layout = {
            "title": title or "Histogram",
            "xaxis": {"title": numeric_col.name},
            "yaxis": {"title": "Count"}
        }

        return {"data": data, "layout": layout}

    def _generate_table(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: Optional[str]
    ) -> Dict[str, Any]:
        """Table fallback"""
        headers = [c.name for c in columns_info]
        cells = [[row[col] for row in results] for col in headers]

        data = [{
            "type": "table",
            "header": {"values": headers},
            "cells": {"values": cells}
        }]

        layout = {"title": title or "Data Table"}

        return {"data": data, "layout": layout}

    @staticmethod
    def _get_color(index: int) -> str:
        """Palette colori Plotly standard"""
        colors = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
        ]
        return colors[index % len(colors)]


# ============================================================
# PARAMETER EXTRACTION & SQL TEMPLATING
# ============================================================

@dataclass
class Parameter:
    """Parametro SQL modificabile"""
    name: str
    type: Literal["enum", "number", "date", "text"]
    current_value: Any
    options: Optional[List[Any]] = None  # Per type="enum"
    min_value: Optional[Any] = None      # Per type="number"/"date"
    max_value: Optional[Any] = None
    label: str = ""  # Label UI-friendly


class ParameterExtractor:
    """Estrae parametri modificabili da SQL query"""

    @staticmethod
    def extract_parameters(sql: str) -> Dict[str, Parameter]:
        """
        Identifica pattern SQL parametrizzabili

        Pattern supportati:
        - DATE_TRUNC('month', ...) → time_granularity enum
        - LIMIT 10 → limit number
        - WHERE year = 2023 → year number
        - WHERE region = 'West' → region enum (se lista limitata)

        Returns:
            {param_name: Parameter}
        """
        import re

        parameters = {}

        # Pattern 1: DATE_TRUNC time granularity
        date_trunc_match = re.search(
            r"DATE_TRUNC\('(\w+)',\s*(\w+)\)",
            sql,
            re.IGNORECASE
        )
        if date_trunc_match:
            granularity = date_trunc_match.group(1).lower()
            column_name = date_trunc_match.group(2)

            parameters["time_granularity"] = Parameter(
                name="time_granularity",
                type="enum",
                current_value=granularity,
                options=["day", "week", "month", "quarter", "year"],
                label="Granularità Temporale"
            )

        # Pattern 2: LIMIT clause
        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        if limit_match:
            limit_value = int(limit_match.group(1))

            parameters["limit"] = Parameter(
                name="limit",
                type="number",
                current_value=limit_value,
                min_value=1,
                max_value=1000,
                label="Numero Massimo Risultati"
            )

        # Pattern 3: Year filter (WHERE EXTRACT(YEAR FROM ...) = YYYY)
        year_match = re.search(
            r"EXTRACT\(YEAR\s+FROM\s+\w+\)\s*=\s*(\d{4})",
            sql,
            re.IGNORECASE
        )
        if year_match:
            year_value = int(year_match.group(1))

            parameters["year"] = Parameter(
                name="year",
                type="number",
                current_value=year_value,
                min_value=2014,
                max_value=2026,
                label="Anno"
            )

        # TODO: Pattern 4, 5, 6... (espandibile)

        return parameters

    @staticmethod
    def create_sql_template(sql: str, parameters: Dict[str, Parameter]) -> str:
        """
        Converte SQL concreto in template con placeholder

        Es: "DATE_TRUNC('month', order_date)"
            → "DATE_TRUNC('{time_granularity}', order_date)"
        """
        import re

        template = sql

        for param_name, param in parameters.items():
            if param.type == "enum" and param_name == "time_granularity":
                # Replace 'month' con '{time_granularity}'
                template = re.sub(
                    r"DATE_TRUNC\('(\w+)',",
                    r"DATE_TRUNC('{time_granularity}',",
                    template,
                    flags=re.IGNORECASE
                )

            elif param.type == "number" and param_name == "limit":
                # Replace LIMIT 10 con LIMIT {limit}
                template = re.sub(
                    r"LIMIT\s+\d+",
                    "LIMIT {limit}",
                    template,
                    flags=re.IGNORECASE
                )

            elif param.type == "number" and param_name == "year":
                # Replace year value con {year}
                template = re.sub(
                    r"EXTRACT\(YEAR\s+FROM\s+\w+\)\s*=\s*\d{4}",
                    f"EXTRACT(YEAR FROM order_date) = {{year}}",
                    template,
                    flags=re.IGNORECASE
                )

        return template


class ChartService:
    """Service unificato chart generation + parameter extraction"""

    def __init__(self, llm_provider: str = "claude"):
        self.llm_provider = llm_provider
        self.plotly_generator = PlotlyConfigGenerator(llm_provider=llm_provider)

    def generate_chart(
        self,
        results: List[Dict[str, Any]],
        sql: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Workflow completo: analisi → chart generation → parameter extraction

        Returns:
            {
                "chart_type": str,
                "plotly_config": {data, layout},
                "parameters": {param_name: Parameter},
                "sql_template": str
            }
        """
        if not results:
            return {
                "chart_type": "table",
                "plotly_config": {"data": [], "layout": {"title": "Nessun risultato"}},
                "parameters": {},
                "sql_template": sql
            }

        # 1. Analizza risultati
        columns_info = ChartAnalyzer.analyze_results(results)

        # 2. Suggerisci chart type
        chart_type = ChartAnalyzer.suggest_chart_type(columns_info)

        logger.info(f"Chart type detected: {chart_type}")

        # 3. Genera config Plotly
        title = query[:50] + "..." if len(query) > 50 else query
        plotly_config = self.plotly_generator.generate_config(
            results=results,
            chart_type=chart_type,
            columns_info=columns_info,
            title=title
        )

        # 4. Estrai parametri
        parameters = ParameterExtractor.extract_parameters(sql)

        # 5. Crea SQL template
        sql_template = ParameterExtractor.create_sql_template(sql, parameters)

        return {
            "chart_type": chart_type,
            "plotly_config": plotly_config,
            "parameters": {k: v.__dict__ for k, v in parameters.items()},  # Serialize dataclass
            "sql_template": sql_template
        }


# Singleton
def create_chart_service(llm_provider: str = "claude") -> ChartService:
    """Factory ChartService"""
    return ChartService(llm_provider=llm_provider)
```

---

### Area 2: Integrazione in Chat Orchestrator

**File da modificare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\chat_orchestrator.py`

Aggiungere import e integrare chart generation:

```python
# Aggiungere import
from app.services.chart_service import create_chart_service

class ChatOrchestrator:
    """Orchestrazione chat conversazionale con text-to-SQL + chart generation"""

    def __init__(self, llm_provider: str = "claude"):
        self.llm_provider = llm_provider
        self.vanna = VannaService(llm_provider=llm_provider)
        self.chart_service = create_chart_service(llm_provider=llm_provider)  # NEW
        logger.info(f"ChatOrchestrator initialized with provider={llm_provider}")

    def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        include_chart: bool = True
    ) -> Dict[str, Any]:
        """
        Processa query NL utente con context conversazionale + chart generation

        Returns aggiornato con campo "chart"
        """
        import time
        start_time = time.time()

        # ... (codice esistente invariato fino a exec_result) ...

        rows = exec_result["rows"]

        # 4. Genera chart (SE include_chart=True)
        chart_data = None
        if include_chart and rows:
            try:
                chart_result = self.chart_service.generate_chart(
                    results=rows,
                    sql=sql,
                    query=query
                )
                chart_data = chart_result  # Include chart_type + plotly_config + parameters
                logger.info(f"Chart generated: type={chart_result['chart_type']}")

            except Exception as e:
                logger.warning(f"Chart generation failed: {e}")
                # Continue senza chart (non-blocking error)

        # 5. Genera risposta NL finale
        nl_response = self._generate_nl_response(
            query=query,
            sql=sql,
            results=rows
        )

        # ... (resto codice invariato) ...

        return {
            "session_id": session_id,
            "nl_response": nl_response,
            "sql": sql,
            "results": rows,
            "chart": chart_data,  # UPDATED: chart data completo
            "execution_time_ms": execution_time_ms,
            "success": True,
            "error": None
        }
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `backend/app/services/chart_service.py` | Creare | Chart analyzer, Plotly generator, parameter extractor |
| `backend/app/services/chat_orchestrator.py` | Modificare | Integrare chart_service.generate_chart() in workflow |
| `backend/app/api/chat.py` | Modificare | Aggiornare `ChatQueryResponse` schema con campo `chart` completo |

## Dipendenze da Installare

### Backend (Python)

Nessuna nuova dipendenza (Plotly Python non necessario backend, generiamo JSON manualmente).

## Variabili d'Ambiente

Nessuna nuova variabile necessaria.

## Criteri di Completamento

- [ ] File `chart_service.py` creato con `ChartAnalyzer`, `PlotlyConfigGenerator`, `ParameterExtractor`
- [ ] `ChartAnalyzer.suggest_chart_type()` suggerisce correttamente tipo chart per 10 query test diverse
- [ ] `PlotlyConfigGenerator` genera config valido per tutti i chart types (bar, line, pie, scatter, histogram, table)
- [ ] `ParameterExtractor` identifica parametri `time_granularity`, `limit`, `year` da SQL
- [ ] SQL templating sostituisce valori concreti con placeholder `{param_name}`
- [ ] `chat_orchestrator.py` integra chart generation senza errori
- [ ] Endpoint `/api/chat/query` response include campo `chart` con `{chart_type, plotly_config, parameters, sql_template}`
- [ ] Test su 10 query diverse: ogni risposta include chart appropriato
- [ ] Config Plotly generata è valida JSON (parseable senza errori)
- [ ] Chart config include titolo, assi labels, legenda (se multi-serie)

## Test di Verifica

### Test 1: Chart Type Detection

```python
# Test interattivo Python
from app.services.chart_service import ChartAnalyzer

# Mock results
results_bar = [
    {"region": "West", "sales": 100000},
    {"region": "East", "sales": 80000},
    {"region": "South", "sales": 90000}
]

columns_info = ChartAnalyzer.analyze_results(results_bar)
chart_type = ChartAnalyzer.suggest_chart_type(columns_info)

print(f"Columns: {[(c.name, c.type) for c in columns_info]}")
print(f"Suggested chart type: {chart_type}")  # Expected: "bar"

# Test time series
results_line = [
    {"month": "2023-01-01", "sales": 50000},
    {"month": "2023-02-01", "sales": 60000},
    {"month": "2023-03-01", "sales": 55000}
]

columns_info_line = ChartAnalyzer.analyze_results(results_line)
chart_type_line = ChartAnalyzer.suggest_chart_type(columns_info_line)
print(f"Time series chart type: {chart_type_line}")  # Expected: "line"
```

### Test 2: Plotly Config Generation

```python
from app.services.chart_service import PlotlyConfigGenerator

generator = PlotlyConfigGenerator()

# Bar chart
config_bar = generator.generate_config(
    results=results_bar,
    chart_type="bar",
    columns_info=columns_info,
    title="Vendite per Regione"
)

print(json.dumps(config_bar, indent=2))

# Verificare struttura:
# - data[0].type == "bar"
# - data[0].x == ["West", "East", "South"]
# - data[0].y == [100000, 80000, 90000]
# - layout.title == "Vendite per Regione"
```

### Test 3: Parameter Extraction

```python
from app.services.chart_service import ParameterExtractor

sql = """
SELECT DATE_TRUNC('month', order_date) as month,
       SUM(sales) as total_sales
FROM public.orders
WHERE EXTRACT(YEAR FROM order_date) = 2023
GROUP BY month
ORDER BY month
LIMIT 10
"""

parameters = ParameterExtractor.extract_parameters(sql)

print("Extracted parameters:")
for name, param in parameters.items():
    print(f"  - {name}: {param.type} = {param.current_value}")

# Expected:
#   - time_granularity: enum = month (options: day, week, month, quarter, year)
#   - year: number = 2023 (min: 2014, max: 2026)
#   - limit: number = 10 (min: 1, max: 1000)

# Test SQL templating
sql_template = ParameterExtractor.create_sql_template(sql, parameters)
print("\nSQL Template:")
print(sql_template)

# Expected: placeholder {time_granularity}, {year}, {limit}
```

### Test 4: End-to-End Chart Generation

```bash
# Query con chart generation
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Vendite mensili per categoria negli ultimi 12 mesi",
    "llm_provider": "claude",
    "include_chart": true
  }' | jq '.chart'

# Output atteso:
# {
#   "chart_type": "line",
#   "plotly_config": {
#     "data": [
#       {
#         "type": "scatter",
#         "mode": "lines+markers",
#         "x": ["2023-01-01", "2023-02-01", ...],
#         "y": [50000, 60000, ...],
#         "name": "sales"
#       }
#     ],
#     "layout": {
#       "title": "Vendite mensili per categoria...",
#       "xaxis": {"title": "month", "type": "date"},
#       "yaxis": {"title": "total_sales"}
#     }
#   },
#   "parameters": {
#     "time_granularity": {
#       "name": "time_granularity",
#       "type": "enum",
#       "current_value": "month",
#       "options": ["day", "week", "month", "quarter", "year"],
#       "label": "Granularità Temporale"
#     }
#   },
#   "sql_template": "SELECT DATE_TRUNC('{time_granularity}', ...)..."
# }
```

### Test 5: Chart Types Coverage

```bash
# Test tutte le tipologie chart con query diverse

# Bar chart (text + numeric)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Vendite totali per regione"}' | jq '.chart.chart_type'
# Expected: "bar"

# Line chart (date + numeric)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Vendite mensili ultimi 6 mesi"}' | jq '.chart.chart_type'
# Expected: "line"

# Pie chart (text low cardinality + numeric)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Percentuale vendite per segmento cliente"}' | jq '.chart.chart_type'
# Expected: "pie"

# Scatter (2 numeric)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Scatter plot vendite vs profitto"}' | jq '.chart.chart_type'
# Expected: "scatter"

# Histogram (1 numeric)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Distribuzione profitti"}' | jq '.chart.chart_type'
# Expected: "histogram" or "table"
```

### Test 6: Plotly Config Validation

```python
# Validare config Plotly è JSON valido e render-able

import json
import requests

response = requests.post(
    "http://localhost:8000/api/chat/query",
    json={"query": "Vendite per regione"}
)

chart = response.json()["chart"]

# 1. Validare JSON parseable
plotly_config = chart["plotly_config"]
assert "data" in plotly_config
assert "layout" in plotly_config

# 2. Validare data traces
assert len(plotly_config["data"]) > 0
trace = plotly_config["data"][0]
assert "type" in trace  # bar/line/pie/scatter/histogram/table
assert "x" in trace or "values" in trace  # Data presente

# 3. Validare layout
layout = plotly_config["layout"]
assert "title" in layout

print("✓ Plotly config valid")

# 4. (Opzionale) Render con Plotly Python per verificare
# import plotly.graph_objects as go
# fig = go.Figure(data=plotly_config["data"], layout=plotly_config["layout"])
# fig.show()  # Apre browser con chart
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **Dataclass per strutture:** Usare `@dataclass` per `ColumnInfo`, `Parameter` (type safety + clean serialization)
2. **Heuristics chart type:** Regole deterministiche basate su tipi colonne e cardinalità (no LLM per performance)
3. **Plotly config manuale:** Generare JSON Plotly direttamente (no Plotly Python library backend), perfetto sync con Plotly.js frontend
4. **Regex SQL parsing:** `re.search()` case-insensitive per identificare pattern parametrizzabili
5. **Non-blocking errors:** Chart generation failure non blocca risposta (log warning, continua senza chart)

### Convenzioni Naming

- **Chart types:** Lowercase `"bar"`, `"line"`, `"pie"`, `"scatter"`, `"histogram"`, `"table"`
- **Parameter names:** Snake_case `"time_granularity"`, `"limit"`, `"year"`
- **SQL placeholders:** Curly braces `{param_name}` (Python `.format()` compatible)
- **Plotly colors:** Hex format `"#1f77b4"` (Plotly standard palette)

### Errori Comuni da Evitare

1. **Column type inference fallito:** Sample solo primo valore può essere non rappresentativo, controllare almeno 10 valori
2. **Cardinality computation troppo lenta:** Su >10k rows, limitare unique set a sample (es. prime 1000 righe)
3. **Regex SQL parsing fragile:** Testare con SQL variations (uppercase/lowercase, spacing extra)
4. **Plotly config invalid:** Sempre validare JSON serializable prima di return (no NaN, Infinity)
5. **Parameter extraction duplicati:** Stesso parametro estratto multiple volte, usare dict per dedup

### Troubleshooting

**Chart type sempre "table"**
- Verificare `_infer_column_type()` identifica correttamente tipi
- Debug logging `columns_info` per vedere types detected
- Controllare heuristics `suggest_chart_type()` match pattern dati

**Plotly config JSON non serializable**
```python
# Errore: numpy types not JSON serializable
# Soluzione: convert a Python native types
import numpy as np
y_values = [float(v) if isinstance(v, (np.integer, np.floating)) else v for v in y_values]
```

**Parameter extraction fallisce**
- SQL generato da Vanna può variare format
- Estendere regex pattern per coprire variations
- Logging SQL raw per debug

**Chart vuoto/assi sbagliati**
- Verificare mapping colonne x/y corretto
- Controllare `results` non vuoto
- Validare values non tutti `None`

## Riferimenti

- **BRIEFING.md**: Sezione "Chart Visualization" (Plotly.js, 40+ chart types)
- **PRD.md**: Sezione 3.4 "Flusso 1: Chat con i Dati" (chart generation), Sezione "Funzionalità Core" (chart parametrici)
- **Fase precedente**: `phase-03-multi-provider-llm-orchestrazione-chat.md` (chat orchestrator baseline)
- **Plotly.js Docs**: https://plotly.com/javascript/
- **Plotly Python Docs**: https://plotly.com/python/ (reference JSON schema)
