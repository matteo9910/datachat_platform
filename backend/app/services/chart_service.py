"""
Chart Service - Auto-detection chart type e generazione config Plotly
Utilizza LLM (Azure OpenAI) per selezione intelligente del tipo di grafico
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, asdict
from decimal import Decimal

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
        """Analizza struttura risultati SQL"""
        if not results:
            return []

        columns_info = []
        sample_size = min(len(results), 1000)  # Limita per performance
        sample_rows = results[:sample_size]

        for col_name in results[0].keys():
            values = [row[col_name] for row in sample_rows if row[col_name] is not None]
            col_type = ChartAnalyzer._infer_column_type(values)
            unique_values = set(str(v) for v in values)
            cardinality = len(unique_values)
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

        numeric_count = 0
        date_count = 0

        for v in values[:20]:  # Check primi 20 valori
            if isinstance(v, (int, float, Decimal)):
                numeric_count += 1
            elif isinstance(v, str):
                # Check se stringa numerica (es. "827455.94")
                try:
                    float(v.replace(',', ''))
                    numeric_count += 1
                    continue
                except (ValueError, AttributeError):
                    pass
                # Check ISO date pattern
                if len(v) >= 10 and v[4:5] == '-' and v[7:8] == '-':
                    try:
                        int(v[:4])  # Year
                        int(v[5:7])  # Month
                        int(v[8:10])  # Day
                        date_count += 1
                    except:
                        pass
            elif isinstance(v, bool):
                return "boolean"

        total = len(values[:20])
        if numeric_count / total > 0.8:
            return "numeric"
        if date_count / total > 0.8:
            return "date"
        return "text"

    @staticmethod
    def suggest_chart_type_heuristic(columns_info: List[ColumnInfo]) -> ChartType:
        """
        Suggerisci chart type basato su regole euristiche (fallback)
        """
        if len(columns_info) < 2:
            if len(columns_info) == 1 and columns_info[0].type == "numeric":
                return "histogram"
            return "table"

        text_cols = [c for c in columns_info if c.type == "text"]
        numeric_cols = [c for c in columns_info if c.type == "numeric"]
        date_cols = [c for c in columns_info if c.type == "date"]

        if date_cols and numeric_cols:
            return "line"

        if text_cols and numeric_cols:
            text_col = text_cols[0]
            if text_col.cardinality <= 6:
                return "pie"
            else:
                return "bar"

        if len(numeric_cols) >= 2:
            return "scatter"

        if text_cols and numeric_cols:
            return "bar"

        return "table"


class LLMChartSelector:
    """Usa LLM (Azure OpenAI) per selezione intelligente del tipo di grafico e titolo"""

    MULTI_CHART_DETECTION_PROMPT = """Sei un esperto di data visualization e business intelligence.

Analizza la domanda dell'utente e determina se richiede UNA o PIU' visualizzazioni separate con DATASET DIVERSI.

DOMANDA UTENTE: {query}

SCHEMA DATABASE DISPONIBILE:
- orders: order_id, order_date, region, sales, quantity, profit, customer_id, product_id
- customers: customer_id, customer_name, segment
- products: product_id, product_name, category, sub_category

REGOLE CRITICHE PER IDENTIFICARE MULTI-DATASET:
1. Se la domanda chiede dati raggruppati per DIMENSIONI DIVERSE (es. "per regione" E "per categoria/subcategory") -> SERVONO 2 QUERY SQL SEPARATE
2. Se chiede "top N di X" E anche "qualcosa per Y" dove X e Y sono dimensioni diverse -> 2 query
3. Se chiede un breakdown E un totale/KPI -> possono usare stessa query, splitta solo i risultati
4. Se chiede solo una dimensione di analisi -> 1 query

ESEMPI MULTI-DATASET (servono query SQL diverse):
- "Vendite per regione e top 5 subcategory" -> 2 query: GROUP BY region vs GROUP BY sub_category LIMIT 5
- "Vendite per categoria e per anno" -> 2 query: GROUP BY category vs GROUP BY year
- "Top 10 prodotti e vendite per segmento cliente" -> 2 query

ESEMPI SINGLE-DATASET (una query basta):
- "Vendite per regione e totale 2017" -> 1 query con GROUP BY region, poi splitta per KPI
- "Trend mensile vendite" -> 1 query
- "Top 5 categorie per vendite" -> 1 query

Rispondi SOLO con un JSON valido:
{{
  "requires_multiple_queries": <true|false>,
  "num_visualizations": <1 o 2>,
  "visualizations": [
    {{
      "description": "<descrizione chiara>",
      "chart_type_hint": "<bar|line|pie|kpi|table>",
      "data_focus": "<breakdown|aggregate|trend|topN>",
      "sql_hint": "<breve descrizione della query necessaria, es: GROUP BY region>"
    }}
  ]
}}"""

    CHART_SELECTION_PROMPT = """Sei un esperto di data visualization. Analizza il contesto e scegli il grafico PIU' APPROPRIATO.

DOMANDA UTENTE: {query}

COLONNE RISULTATO:
{columns_description}

NUMERO TOTALE RIGHE: {num_rows}

SAMPLE DATI (prime 5 righe):
{sample_data}

=== TIPI DI VISUALIZZAZIONE ===

"bar" - Grafico a barre. Per confrontare UNA dimensione categorica con UNA metrica numerica.
"line" - Grafico a linee. Per serie temporali, trend nel tempo.
"pie" - Grafico a torta. Per mostrare le proporzioni di UN totale suddiviso in 3-7 categorie.
"pie_with_filter" - Grafico a torta DINAMICO con filtro dropdown. Per mostrare la distribuzione di una metrica su POCHE categorie (3-6), con la possibilita' di cambiare il SOGGETTO tramite un filtro dropdown. L'utente puo' selezionare un soggetto diverso dal dropdown e il pie chart si aggiorna mostrando la distribuzione per quel soggetto.
"scatter" - Scatter plot. Per correlazioni tra 2 variabili numeriche continue.
"histogram" - Istogramma. Per distribuzione di una singola variabile numerica.
"table" - Tabella. Per elenchi, liste, dati grezzi.
"none" - Nessun grafico. Il testo e' sufficiente, il grafico non aggiungerebbe valore.

=== REGOLA PRIORITARIA ===
Se l'utente chiede ESPLICITAMENTE un tipo specifico di visualizzazione, rispetta SEMPRE la richiesta.

=== FEW-SHOT EXAMPLES ===

ESEMPIO 1 - BAR CHART:
Domanda: "Quali sono i top 10 prodotti piu venduti?"
Colonne: product_name (text), total_quantity (numeric)
Righe: 10
-> chart_type: "bar", reason: "Ranking di 10 prodotti con una sola metrica, bar chart ideale"

ESEMPIO 2 - PIE CHART:
Domanda: "Come si distribuiscono le vendite per segmento?"
Colonne: segment (text), total_sales (numeric)
Righe: 3 (Consumer, Corporate, Home Office)
-> chart_type: "pie", reason: "3 categorie con proporzioni di un totale, pie chart perfetto"

ESEMPIO 3 - PIE_WITH_FILTER (CRUCIALE):
Domanda: "Come si confrontano le vendite dei top 10 prodotti tra i segmenti Consumer, Corporate e Home Office?"
Colonne: product_name (text), segment (text), sales (numeric)  OPPURE  product_name (text), sales_consumer (numeric), sales_corporate (numeric), sales_home_office (numeric)
Righe: 30 (10 prodotti x 3 segmenti)  OPPURE  10 (10 prodotti con colonne per segmento)
-> chart_type: "pie_with_filter"
-> filter_column: "product_name" (la colonna con MOLTI valori diversi, i soggetti)
-> filter_values: i nomi dei prodotti
-> reason: "La domanda chiede la distribuzione delle vendite per 3 segmenti (poche categorie) su 10 prodotti (molti soggetti). Il pie chart mostra lo spaccato per segmento di un prodotto alla volta, con un dropdown per cambiare prodotto."

COME RICONOSCERE UN CASO PIE_WITH_FILTER:
- C'e' una dimensione con POCHI valori (3-6): i segmenti, le regioni, le categorie -> queste sono le FETTE del pie
- C'e' una dimensione con MOLTI valori (5-20+): i prodotti, i clienti, le citta -> questo e' il FILTRO dropdown
- C'e' una metrica numerica: vendite, quantita, profitto -> i VALORI delle fette
- ATTENZIONE: anche se i dati sono in formato PIVOTATO (una colonna per segmento: sales_consumer, sales_corporate, sales_home_office), il grafico corretto e' comunque pie_with_filter. In questo caso filter_column e' la colonna testuale (product_name) e le categorie del pie sono i nomi delle colonne numeriche.

ESEMPIO 4 - LINE CHART:
Domanda: "Come sono cambiate le vendite mensili nel 2017?"
Colonne: month (text/date), total_sales (numeric)
Righe: 12
-> chart_type: "line", reason: "Serie temporale mensile, line chart per mostrare il trend"

ESEMPIO 5 - TABLE:
Domanda: "Elenca tutti i clienti con ordini superiori a 1000 euro"
Colonne: customer_name (text), email (text), total_orders (numeric)
Righe: 45
-> chart_type: "table", reason: "Elenco con molte righe, tabella ideale per consultare i dati"

ESEMPIO 6 - PIE_WITH_FILTER (altro esempio):
Domanda: "Distribuzione del profitto per regione dei top 5 clienti"
Colonne: customer_name (text), region (text), profit (numeric)
Righe: 20 (5 clienti x 4 regioni)
-> chart_type: "pie_with_filter"
-> filter_column: "customer_name"
-> filter_values: i nomi dei clienti
-> reason: "4 regioni (poche categorie per le fette del pie) su 5 clienti (soggetti selezionabili dal dropdown)"

=== REGOLE DI LEGGIBILITA' ===
- Piu' di 15 elementi sull'asse X -> "table" o "limit_data": true (max 10-15 elementi)
- Un bar chart con 10 prodotti x 3 segmenti x valori = ILLEGGIBILE -> usa "pie_with_filter"
- Un bar chart stacked/grouped con molte serie e molte categorie -> ILLEGGIBILE -> valuta "pie_with_filter" o "table"

=== FORMATO TITOLO ===
Conciso (max 60 caratteri), professionale, maiuscole per parole principali, NO emoji.

Rispondi SOLO con un JSON valido:
{{
  "chart_type": "<tipo>",
  "chart_title": "<titolo professionale>",
  "reason": "<motivazione della scelta basata sull'analisi dei dati>",
  "limit_data": <true|false>,
  "limit_to": <numero, es: 10>,
  "limit_reason": "<se limit_data=true, spiega perche>",
  "filter_column": "<nome colonna per il dropdown, SOLO per pie_with_filter>",
  "filter_values": ["<valore1>", "<valore2>", "..."]
}}"""

    @staticmethod
    def select_chart_type_and_title(
        query: str,
        columns_info: List[ColumnInfo],
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Usa Azure OpenAI (gpt-4.1) per selezionare chart type e generare titolo professionale
        
        Returns:
            {"chart_type": str, "chart_title": str, "limit_data": bool, "limit_to": int}
        """
        try:
            from app.services.llm_provider import get_llm_provider_manager
            
            llm_manager = get_llm_provider_manager()
            
            # Prepara descrizione colonne
            columns_desc = "\n".join([
                f"- {c.name}: tipo={c.type}, cardinalita={c.cardinality}, esempi={c.sample_values[:5]}"
                for c in columns_info
            ])
            
            # Prepara sample dati (prime 5 righe)
            sample_rows = results[:5] if results else []
            sample_data = json.dumps(sample_rows, indent=2, default=str)
            
            # Costruisci prompt con numero righe
            prompt = LLMChartSelector.CHART_SELECTION_PROMPT.format(
                query=query,
                columns_description=columns_desc,
                num_rows=len(results),
                sample_data=sample_data
            )
            
            # Chiama Azure OpenAI (gpt-4.1) con system message per rinforzare il ragionamento
            response = llm_manager.complete(
                messages=[
                    {"role": "system", "content": "Sei un esperto di data visualization. Analizza ATTENTAMENTE la struttura dei dati (colonne, tipi, cardinalita) e la domanda dell'utente. Se i dati contengono UNA colonna testuale con molti valori (soggetti) e MULTIPLE colonne numeriche che rappresentano categorie (es. sales_consumer, sales_corporate, sales_home_office), questo e' un pattern PIVOTATO che richiede pie_with_filter: il pie chart mostra la distribuzione tra le colonne numeriche e il dropdown filtra per la colonna testuale."},
                    {"role": "user", "content": prompt}
                ],
                provider="azure",
                temperature=0.1,
                max_tokens=600
            )
            
            content = response["content"].strip()
            logger.info(f"LLM chart selection response: {content}")
            
            # Parse JSON response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            chart_type = result.get("chart_type", "bar")
            chart_title = result.get("chart_title", "Analisi Dati")
            reason = result.get("reason", "")
            limit_data = result.get("limit_data", False)
            limit_to = result.get("limit_to", 10)
            
            # Valida chart type
            valid_types = ["bar", "line", "pie", "pie_with_filter", "scatter", "histogram", "table", "none"]
            if chart_type not in valid_types:
                logger.warning(f"LLM returned invalid chart type: {chart_type}, defaulting to bar")
                chart_type = "bar"
            
            filter_column = result.get("filter_column")
            filter_values = result.get("filter_values", [])
            
            logger.info(f"LLM selected: type={chart_type}, title={chart_title}, limit={limit_data}/{limit_to}, filter_col={filter_column} - Reason: {reason}")
            return {
                "chart_type": chart_type, 
                "chart_title": chart_title,
                "limit_data": limit_data,
                "limit_to": limit_to,
                "filter_column": filter_column,
                "filter_values": filter_values
            }
            
        except Exception as e:
            logger.error(f"LLM chart selection failed: {e}, falling back to heuristics")
            fallback_type = ChartAnalyzer.suggest_chart_type_heuristic(columns_info)
            return {"chart_type": fallback_type, "chart_title": "Analisi Dati", "limit_data": False, "limit_to": 10}

    @staticmethod
    def detect_multi_visualization(query: str) -> Dict[str, Any]:
        """
        Rileva se la domanda richiede multiple visualizzazioni
        
        Returns:
            {"num_visualizations": int, "visualizations": [...]}
        """
        try:
            from app.services.llm_provider import get_llm_provider_manager
            
            llm_manager = get_llm_provider_manager()
            
            prompt = LLMChartSelector.MULTI_CHART_DETECTION_PROMPT.format(query=query)
            
            response = llm_manager.complete(
                messages=[{"role": "user", "content": prompt}],
                provider="azure",
                temperature=0.1,
                max_tokens=400
            )
            
            content = response["content"].strip()
            logger.info(f"Multi-viz detection response: {content}")
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            return result
            
        except Exception as e:
            logger.warning(f"Multi-viz detection failed: {e}, defaulting to single viz")
            return {
                "num_visualizations": 1,
                "visualizations": [{"description": "Visualizzazione standard", "chart_type_hint": "bar", "data_focus": "breakdown"}]
            }


class PlotlyConfigGenerator:
    """Genera config Plotly completa da risultati + chart type"""

    COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

    def generate_config(
        self,
        results: List[Dict[str, Any]],
        chart_type: ChartType,
        columns_info: List[ColumnInfo],
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Genera config Plotly completa"""
        generators = {
            "bar": self._generate_bar_chart,
            "line": self._generate_line_chart,
            "pie": self._generate_pie_chart,
            "scatter": self._generate_scatter_chart,
            "histogram": self._generate_histogram,
            "table": self._generate_table,
            "kpi": self._generate_kpi_card,
            "indicator": self._generate_kpi_card
        }
        
        generator = generators.get(chart_type, self._generate_table)
        return generator(results, columns_info, title)

    def _generate_kpi_card(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """KPI Card: mostra un valore singolo con formattazione"""
        if not results:
            return {"data": [], "layout": {"title": {"text": title or "KPI"}}}
        
        # Trova la colonna numerica principale
        numeric_col = next((c for c in columns_info if c.type == "numeric"), columns_info[0])
        value = self._to_native(results[0][numeric_col.name])
        
        # Formatta il valore
        if isinstance(value, (int, float)):
            if value >= 1000000:
                formatted = f"{value/1000000:.2f}M"
            elif value >= 1000:
                formatted = f"{value/1000:.1f}K"
            else:
                formatted = f"{value:,.2f}"
        else:
            formatted = str(value)
        
        data = [{
            "type": "indicator",
            "mode": "number",
            "value": value,
            "number": {
                "font": {"size": 72, "color": "#1f77b4"},
                "valueformat": ",.0f" if isinstance(value, (int, float)) and value >= 1000 else ""
            },
            "title": {
                "text": title or numeric_col.name,
                "font": {"size": 18, "color": "#666"}
            }
        }]
        
        layout = {
            "margin": {"t": 80, "b": 20, "l": 20, "r": 20},
            "paper_bgcolor": "white",
            "plot_bgcolor": "white"
        }
        
        return {"data": data, "layout": layout}

    def _to_native(self, value: Any) -> Any:
        """Convert to JSON-serializable native Python type"""
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, 'isoformat'):  # datetime
            return value.isoformat()
        return value

    def _is_temporal_column_static(self, col: ColumnInfo) -> bool:
        """Identifica colonne temporali dal nome (year, month, quarter, etc.)"""
        temporal_patterns = ['year', 'anno', 'month', 'mese', 'quarter', 'trimestre', 
                           'week', 'settimana', 'date', 'data', 'period', 'periodo']
        col_lower = col.name.lower()
        return any(pattern in col_lower for pattern in temporal_patterns)

    def _is_id_column(self, col_name: str) -> bool:
        """Identifica colonne ID che non dovrebbero essere mostrate negli assi"""
        id_patterns = ['_id', '_key', 'id_', 'key_', 'product_id', 'customer_id', 
                      'order_id', 'row_id', 'pk', 'fk', '_pk', '_fk']
        col_lower = col_name.lower()
        # Controlla se e' esattamente "id" o contiene pattern ID
        if col_lower == 'id':
            return True
        return any(pattern in col_lower for pattern in id_patterns)

    def _find_best_label_column(self, columns_info: List[ColumnInfo]) -> Optional[ColumnInfo]:
        """Trova la migliore colonna per le etichette (escludendo ID)"""
        # Priorita: colonne text che NON sono ID
        for col in columns_info:
            if col.type == "text" and not self._is_id_column(col.name):
                return col
        # Fallback: colonne temporali
        for col in columns_info:
            if self._is_temporal_column_static(col):
                return col
        # Ultimo fallback: prima colonna non-ID
        for col in columns_info:
            if not self._is_id_column(col.name):
                return col
        return columns_info[0] if columns_info else None

    def _should_use_horizontal_bars(self, x_values: List[Any], num_items: int) -> bool:
        """Determina se usare barre orizzontali basandosi sulla lunghezza delle etichette"""
        if num_items <= 3:
            return False
        # Calcola lunghezza media etichette
        avg_label_length = sum(len(str(v)) for v in x_values) / len(x_values) if x_values else 0
        # Usa barre orizzontali se:
        # - Ci sono molti item (>5) con etichette lunghe (>15 caratteri)
        # - Oppure etichette molto lunghe (>25 caratteri)
        return (num_items > 5 and avg_label_length > 15) or avg_label_length > 25

    def _generate_bar_chart(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Bar chart intelligente: esclude ID, usa barre orizzontali per nomi lunghi"""
        # Trova la migliore colonna per le etichette (ESCLUDI ID)
        x_col = self._find_best_label_column(columns_info)
        
        if not x_col:
            x_col = columns_info[0]
        
        # Le colonne Y sono quelle numeriche ESCLUSA la colonna X e colonne ID
        numeric_cols = [c for c in columns_info 
                       if c.type == "numeric" and c.name != x_col.name and not self._is_id_column(c.name)]

        if not numeric_cols:
            numeric_cols = [c for c in columns_info if c.name != x_col.name][:1]

        x_values = [self._to_native(row[x_col.name]) for row in results]
        num_items = len(results)
        
        # Determina se usare barre orizzontali
        use_horizontal = self._should_use_horizontal_bars(x_values, num_items)

        data = []
        for i, num_col in enumerate(numeric_cols):
            y_values = [self._to_native(row[num_col.name]) for row in results]
            
            if use_horizontal:
                # Per barre orizzontali, INVERTI l'ordine: il valore più alto deve essere IN CIMA
                # (Plotly disegna dal basso verso l'alto, quindi invertiamo)
                x_values_reversed = list(reversed(x_values))
                y_values_reversed = list(reversed(y_values))
                
                data.append({
                    "type": "bar",
                    "x": y_values_reversed,
                    "y": x_values_reversed,
                    "orientation": "h",
                    "name": num_col.name,
                    "marker": {"color": self.COLORS[i % len(self.COLORS)]},
                    "text": [f"{v:,.0f}" if isinstance(v, (int, float)) else str(v) for v in y_values_reversed],
                    "textposition": "outside"
                })
            else:
                # Barre verticali standard
                data.append({
                    "type": "bar",
                    "x": x_values,
                    "y": y_values,
                    "name": num_col.name,
                    "marker": {"color": self.COLORS[i % len(self.COLORS)]}
                })

        if use_horizontal:
            # Layout per barre orizzontali
            layout = {
                "title": {"text": title or "Bar Chart"},
                "xaxis": {"title": {"text": numeric_cols[0].name if len(numeric_cols) == 1 else "Value"}},
                "yaxis": {
                    "title": {"text": ""},
                    "automargin": True,
                    "tickfont": {"size": 11}
                },
                "barmode": "group" if len(numeric_cols) > 1 else "relative",
                "margin": {"t": 50, "b": 50, "l": 200, "r": 80},  # Margine sinistro ampio per etichette
                "height": max(400, num_items * 35)  # Altezza dinamica
            }
        else:
            # Layout per barre verticali
            layout = {
                "title": {"text": title or "Bar Chart"},
                "xaxis": {
                    "title": {"text": x_col.name},
                    "tickangle": -45 if num_items > 5 else 0,
                    "tickfont": {"size": 10}
                },
                "yaxis": {"title": {"text": numeric_cols[0].name if len(numeric_cols) == 1 else "Value"}},
                "barmode": "group" if len(numeric_cols) > 1 else "relative",
                "margin": {"t": 50, "b": 120 if num_items > 5 else 80, "l": 60, "r": 20}
            }

        return {"data": data, "layout": layout}

    def _is_temporal_column(self, col: ColumnInfo) -> bool:
        """Identifica colonne temporali dal nome (year, month, quarter, etc.)"""
        temporal_patterns = ['year', 'anno', 'month', 'mese', 'quarter', 'trimestre', 
                           'week', 'settimana', 'date', 'data', 'period', 'periodo']
        col_lower = col.name.lower()
        return any(pattern in col_lower for pattern in temporal_patterns)

    def _generate_line_chart(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Line chart: 1 date/temporal col (x) + 1+ numeric cols (y)"""
        # Prima cerca colonne date, poi colonne con nomi temporali
        x_col = next((c for c in columns_info if c.type == "date"), None)
        
        if not x_col:
            # Cerca colonne con nomi temporali (year, month, etc.)
            x_col = next((c for c in columns_info if self._is_temporal_column(c)), None)
        
        if not x_col:
            # Fallback: usa prima colonna
            x_col = columns_info[0]
        
        # Le colonne Y sono quelle numeriche ESCLUSA la colonna X
        numeric_cols = [c for c in columns_info if c.type == "numeric" and c.name != x_col.name]
        
        if not numeric_cols:
            # Se non ci sono altre colonne numeriche, cerca qualsiasi colonna diversa da x_col
            numeric_cols = [c for c in columns_info if c.name != x_col.name][:1]

        x_values = [self._to_native(row[x_col.name]) for row in results]

        data = []
        for i, num_col in enumerate(numeric_cols):
            y_values = [self._to_native(row[num_col.name]) for row in results]
            data.append({
                "type": "scatter",
                "mode": "lines+markers",
                "x": x_values,
                "y": y_values,
                "name": num_col.name,
                "line": {"color": self.COLORS[i % len(self.COLORS)], "width": 2},
                "marker": {"size": 8}
            })

        layout = {
            "title": {"text": title or "Line Chart"},
            "xaxis": {"title": {"text": x_col.name}},
            "yaxis": {"title": {"text": numeric_cols[0].name if len(numeric_cols) == 1 else "Value"}},
            "margin": {"t": 50, "b": 80, "l": 60, "r": 20}
        }

        return {"data": data, "layout": layout}

    def _generate_pie_chart(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Pie chart: 1 text col (labels) + 1 numeric col (values)"""
        text_col = next((c for c in columns_info if c.type == "text"), columns_info[0])
        numeric_col = next((c for c in columns_info if c.type == "numeric"), None)

        if not numeric_col:
            numeric_col = columns_info[1] if len(columns_info) > 1 else columns_info[0]

        labels = [self._to_native(row[text_col.name]) for row in results]
        values = [self._to_native(row[numeric_col.name]) for row in results]

        data = [{
            "type": "pie",
            "labels": labels,
            "values": values,
            "hoverinfo": "label+percent+value",
            "textinfo": "label+percent",
            "marker": {"colors": self.COLORS[:len(labels)]}
        }]

        layout = {
            "title": {"text": title or "Pie Chart"},
            "margin": {"t": 50, "b": 20, "l": 20, "r": 20}
        }

        return {"data": data, "layout": layout}

    def _generate_scatter_chart(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Scatter: 2 numeric cols (x, y)"""
        numeric_cols = [c for c in columns_info if c.type == "numeric"]

        if len(numeric_cols) < 2:
            return self._generate_bar_chart(results, columns_info, title)

        x_col, y_col = numeric_cols[0], numeric_cols[1]
        x_values = [self._to_native(row[x_col.name]) for row in results]
        y_values = [self._to_native(row[y_col.name]) for row in results]

        data = [{
            "type": "scatter",
            "mode": "markers",
            "x": x_values,
            "y": y_values,
            "marker": {"size": 10, "color": self.COLORS[0]}
        }]

        layout = {
            "title": {"text": title or "Scatter Plot"},
            "xaxis": {"title": {"text": x_col.name}},
            "yaxis": {"title": {"text": y_col.name}},
            "margin": {"t": 50, "b": 80, "l": 60, "r": 20}
        }

        return {"data": data, "layout": layout}

    def _generate_histogram(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Histogram: 1 numeric col"""
        numeric_col = next((c for c in columns_info if c.type == "numeric"), columns_info[0])
        x_values = [self._to_native(row[numeric_col.name]) for row in results]

        data = [{
            "type": "histogram",
            "x": x_values,
            "marker": {"color": self.COLORS[0]}
        }]

        layout = {
            "title": {"text": title or "Histogram"},
            "xaxis": {"title": {"text": numeric_col.name}},
            "yaxis": {"title": {"text": "Count"}},
            "margin": {"t": 50, "b": 80, "l": 60, "r": 20}
        }

        return {"data": data, "layout": layout}

    def _generate_table(
        self, results: List[Dict[str, Any]], columns_info: List[ColumnInfo], title: Optional[str]
    ) -> Dict[str, Any]:
        """Tabella stilizzata - restituisce dati per rendering frontend"""
        headers = [c.name for c in columns_info]
        
        # Formato per tabella stilizzata nel frontend
        rows_data = []
        for row in results:
            row_values = {}
            for col in columns_info:
                row_values[col.name] = self._to_native(row.get(col.name))
            rows_data.append(row_values)
        
        # Restituisce sia formato Plotly (per compatibilita) che formato custom per frontend
        cells = [[self._to_native(row[col]) for row in results] for col in headers]
        
        data = [{
            "type": "table",
            "header": {
                "values": [f"<b>{h.replace('_', ' ').title()}</b>" for h in headers],
                "fill": {"color": "#f97316"},  # Orange header
                "font": {"color": "white", "size": 12},
                "align": "left",
                "height": 40
            },
            "cells": {
                "values": cells,
                "fill": {"color": [["#fff7ed", "white"] * (len(results) // 2 + 1)]},
                "font": {"size": 11},
                "align": "left",
                "height": 35
            }
        }]

        layout = {
            "title": {"text": title or "Tabella Dati", "font": {"size": 16}},
            "margin": {"t": 50, "b": 20, "l": 20, "r": 20},
            "height": min(600, 100 + len(results) * 40)  # Altezza dinamica
        }
        
        return {
            "data": data, 
            "layout": layout,
            # Dati extra per rendering custom nel frontend
            "table_data": {
                "headers": headers,
                "rows": rows_data,
                "row_count": len(results)
            }
        }


@dataclass
class Parameter:
    """Parametro SQL modificabile"""
    name: str
    type: Literal["enum", "number", "date", "text"]
    current_value: Any
    options: Optional[List[Any]] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    label: str = ""


class ParameterExtractor:
    """Estrae parametri modificabili da SQL query"""

    @staticmethod
    def extract_parameters(sql: str) -> Dict[str, Parameter]:
        """
        Identifica pattern SQL parametrizzabili
        
        Pattern supportati:
        - DATE_TRUNC('month', ...) -> time_granularity enum
        - LIMIT N -> limit number
        - WHERE EXTRACT(YEAR FROM ...) = YYYY -> year number
        """
        parameters = {}

        # Pattern 1: DATE_TRUNC time granularity
        date_trunc_match = re.search(
            r"DATE_TRUNC\s*\(\s*'(\w+)'\s*,",
            sql,
            re.IGNORECASE
        )
        if date_trunc_match:
            granularity = date_trunc_match.group(1).lower()
            parameters["time_granularity"] = Parameter(
                name="time_granularity",
                type="enum",
                current_value=granularity,
                options=["day", "week", "month", "quarter", "year"],
                label="Granularita Temporale"
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

        # Pattern 3: Year filter
        year_match = re.search(
            r"EXTRACT\s*\(\s*YEAR\s+FROM\s+\w+\s*\)\s*=\s*(\d{4})",
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

        # Pattern 4: Top N / First N
        top_match = re.search(r"TOP\s+(\d+)|FETCH\s+FIRST\s+(\d+)", sql, re.IGNORECASE)
        if top_match:
            top_value = int(top_match.group(1) or top_match.group(2))
            parameters["top_n"] = Parameter(
                name="top_n",
                type="number",
                current_value=top_value,
                min_value=1,
                max_value=100,
                label="Top N"
            )

        return parameters

    @staticmethod
    def create_sql_template(sql: str, parameters: Dict[str, Parameter]) -> str:
        """Converte SQL concreto in template con placeholder"""
        template = sql

        for param_name, param in parameters.items():
            if param.type == "enum" and param_name == "time_granularity":
                template = re.sub(
                    r"DATE_TRUNC\s*\(\s*'(\w+)'\s*,",
                    r"DATE_TRUNC('{time_granularity}',",
                    template,
                    flags=re.IGNORECASE
                )
            elif param.type == "number" and param_name == "limit":
                template = re.sub(
                    r"LIMIT\s+\d+",
                    "LIMIT {limit}",
                    template,
                    flags=re.IGNORECASE
                )
            elif param.type == "number" and param_name == "year":
                template = re.sub(
                    r"(EXTRACT\s*\(\s*YEAR\s+FROM\s+\w+\s*\)\s*=\s*)\d{4}",
                    r"\g<1>{year}",
                    template,
                    flags=re.IGNORECASE
                )
            elif param.type == "number" and param_name == "top_n":
                template = re.sub(
                    r"TOP\s+\d+",
                    "TOP {top_n}",
                    template,
                    flags=re.IGNORECASE
                )

        return template


class ChartService:
    """Service unificato chart generation + parameter extraction"""

    def __init__(self, llm_provider: str = "azure", use_llm_for_chart_selection: bool = True):
        self.llm_provider = llm_provider
        self.use_llm_for_chart_selection = use_llm_for_chart_selection
        self.plotly_generator = PlotlyConfigGenerator()

    def generate_chart(
        self,
        results: List[Dict[str, Any]],
        sql: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Workflow completo: analisi -> chart generation -> parameter extraction
        Supporta generazione di MULTIPLE visualizzazioni se la query lo richiede
        """
        if not results:
            return {
                "chart_type": "table",
                "chart_title": "Nessun Risultato",
                "plotly_config": {"data": [], "layout": {"title": {"text": "Nessun risultato"}}},
                "parameters": {},
                "sql_template": sql,
                "charts": None
            }

        # 1. Analizza risultati
        columns_info = ChartAnalyzer.analyze_results(results)
        logger.info(f"Columns analyzed: {[(c.name, c.type, c.cardinality) for c in columns_info]}")

        # 2. Single visualization - sempre un solo grafico, il piu' appropriato
        chart_results = results  # Default: tutti i risultati
        
        if self.use_llm_for_chart_selection:
            llm_result = LLMChartSelector.select_chart_type_and_title(query, columns_info, results)
            chart_type = llm_result["chart_type"]
            chart_title = llm_result["chart_title"]
            limit_data = llm_result.get("limit_data", False)
            limit_to = llm_result.get("limit_to", 10)
            
            # Se LLM dice "none", non mostrare nessun grafico
            if chart_type == "none":
                logger.info("LLM decided no chart needed for this query")
                return {
                    "chart_type": "none",
                    "chart_title": "",
                    "plotly_config": None,
                    "parameters": {},
                    "sql_template": sql,
                    "charts": None
                }
            
            # Se LLM suggerisce pie_with_filter, genera pie chart con filtro
            if chart_type == "pie_with_filter":
                filter_column = llm_result.get("filter_column")
                filter_values = llm_result.get("filter_values", [])
                return self._generate_pie_with_filter(
                    results=results,
                    columns_info=columns_info,
                    title=chart_title,
                    filter_column=filter_column,
                    filter_values=filter_values,
                    sql=sql
                )
            
            # Se LLM suggerisce di limitare i dati per leggibilita'
            if limit_data and len(results) > limit_to:
                chart_results = results[:limit_to]
                if "top" not in chart_title.lower():
                    chart_title = f"Top {limit_to} - {chart_title}"
                logger.info(f"LLM suggested limiting data: {len(results)} -> {limit_to} rows")
            
            logger.info(f"LLM selected: type={chart_type}, title={chart_title}")
        else:
            chart_type = ChartAnalyzer.suggest_chart_type_heuristic(columns_info)
            chart_title = "Analisi Dati"
            logger.info(f"Chart type detected by heuristics: {chart_type}")

        # Genera config con i risultati (eventualmente limitati)
        plotly_config = self.plotly_generator.generate_config(
            results=chart_results,
            chart_type=chart_type,
            columns_info=columns_info,
            title=chart_title
        )

        parameters = ParameterExtractor.extract_parameters(sql)
        sql_template = ParameterExtractor.create_sql_template(sql, parameters)

        return {
            "chart_type": chart_type,
            "chart_title": chart_title,
            "plotly_config": plotly_config,
            "parameters": {k: asdict(v) for k, v in parameters.items()},
            "sql_template": sql_template,
            "charts": None
        }

    def _generate_pie_with_filter(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: str,
        filter_column: Optional[str],
        filter_values: List[str],
        sql: str
    ) -> Dict[str, Any]:
        """
        Genera un pie chart con filtro dropdown.
        Supporta DUE formati dati:
        
        FORMATO LUNGO (long): product_name, segment, sales
          -> ogni riga e' un (soggetto, categoria, valore)
        
        FORMATO PIVOTATO (wide): product_name, sales_consumer, sales_corporate, sales_home_office
          -> ogni riga e' un soggetto, le categorie sono nelle colonne numeriche
        """
        if not filter_column or not results:
            return self._pie_with_filter_fallback(results, columns_info, title, sql)
        
        # Determina il formato dei dati
        text_cols = [c for c in columns_info if c.type == "text"]
        numeric_cols = [c for c in columns_info if c.type == "numeric"]
        
        # FORMATO PIVOTATO: 1 colonna testo (filter) + N colonne numeriche (categorie)
        # Es: product_name, sales_consumer, sales_corporate, sales_home_office
        is_pivoted = (
            len(text_cols) <= 2 and 
            len(numeric_cols) >= 2 and 
            filter_column in [c.name for c in text_cols]
        )
        
        # FORMATO LUNGO: filter_column + category_column + value_column
        category_col = None
        value_col = None
        if not is_pivoted:
            for col in columns_info:
                if col.name == filter_column:
                    continue
                if col.type == "text" and not category_col:
                    category_col = col
                elif col.type == "numeric" and not value_col:
                    value_col = col
            
            if not category_col or not value_col:
                is_pivoted = True  # Fallback a formato pivotato
        
        # Raccogli valori del filtro
        if not filter_values:
            filter_values = list(dict.fromkeys(
                str(row[filter_column]) for row in results if row.get(filter_column)
            ))
        
        if not filter_values:
            return self._pie_with_filter_fallback(results, columns_info, title, sql)
        
        # Costruisci dati per ogni valore del filtro
        data_by_filter = {}
        
        if is_pivoted:
            # FORMATO PIVOTATO: le categorie sono i nomi delle colonne numeriche
            # Escludi colonne che NON sono metriche: ID, totali, codici
            exclude_patterns = ['total', 'totale', '_id', 'id_', 'code', 'key', 'count']
            category_names = []
            for nc in numeric_cols:
                name_lower = nc.name.lower()
                # Escludi se il nome matcha un pattern di esclusione
                if any(pat in name_lower for pat in exclude_patterns):
                    continue
                # Escludi se la cardinalita e' uguale al numero di righe (probabilmente un ID univoco)
                if nc.cardinality == len(results) and nc.cardinality > 3:
                    continue
                category_names.append(nc.name)
            
            # Se non rimane nulla, prova piu' permissivo (escludi solo ID e total)
            if not category_names:
                for nc in numeric_cols:
                    name_lower = nc.name.lower()
                    if not (name_lower.endswith('_id') or name_lower.startswith('id_') or name_lower == 'id'):
                        if 'total' not in name_lower and 'totale' not in name_lower:
                            category_names.append(nc.name)
            
            # Ultimo fallback: usa tutte le numeriche tranne quelle con "id"
            if not category_names:
                category_names = [nc.name for nc in numeric_cols if 'id' not in nc.name.lower()]
            
            if not category_names:
                category_names = [nc.name for nc in numeric_cols]
            
            for row in results:
                fv = str(row.get(filter_column, ""))
                if fv:
                    cats = {}
                    for cn in category_names:
                        # Rendi il nome leggibile:
                        # consumer_sales -> Consumer, sales_consumer -> Consumer
                        # home_office_sales -> Home Office
                        dn = cn.lower()
                        for prefix in ['sales_', 'vendite_', 'revenue_', 'profit_', 'quantity_']:
                            dn = dn.replace(prefix, '')
                        for suffix in ['_sales', '_vendite', '_revenue', '_profit', '_quantity']:
                            if dn.endswith(suffix):
                                dn = dn[:-len(suffix)]
                        display_name = dn.replace('_', ' ').strip().title()
                        if not display_name:
                            display_name = cn.replace('_', ' ').title()
                        cats[display_name] = round(float(row.get(cn, 0) or 0), 2)
                    data_by_filter[fv] = cats
            
            logger.info(f"Pivoted format detected: categories from columns {category_names}")
        else:
            # FORMATO LUNGO: raggruppa per filter_column -> {categoria: valore}
            for row in results:
                fv = str(row.get(filter_column, ""))
                if fv not in data_by_filter:
                    data_by_filter[fv] = {}
                cat = str(row.get(category_col.name, ""))
                val = float(row.get(value_col.name, 0) or 0)
                data_by_filter[fv][cat] = data_by_filter[fv].get(cat, 0) + val
            
            logger.info(f"Long format detected: category_col={category_col.name}, value_col={value_col.name}")
        
        # Genera tracce Plotly: una per ogni valore del filtro
        traces = []
        buttons = []
        
        for i, fv in enumerate(filter_values):
            cats = data_by_filter.get(fv, {})
            if not cats:
                continue
            labels = list(cats.keys())
            values = list(cats.values())
            
            traces.append({
                "type": "pie",
                "labels": labels,
                "values": values,
                "hoverinfo": "label+percent+value",
                "textinfo": "label+percent",
                "textposition": "auto",
                "marker": {"colors": self.plotly_generator.COLORS[:len(labels)]},
                "visible": i == 0,
                "name": fv,
                "hole": 0.35
            })
            
            visibility = [False] * len(filter_values)
            visibility[i] = True
            buttons.append({
                "label": fv[:45],
                "method": "update",
                "args": [
                    {"visible": visibility},
                    {"title": {"text": f"{title}<br><span style='font-size:12px;color:#64748b'>{fv}</span>"}}
                ]
            })
        
        if not traces:
            return self._pie_with_filter_fallback(results, columns_info, title, sql)
        
        first_filter = filter_values[0]
        filter_label = filter_column.replace('_', ' ').title()
        
        layout = {
            "title": {
                "text": title,
                "x": 0.0,
                "xanchor": "left",
                "y": 0.98,
                "yanchor": "top",
                "font": {"size": 14, "color": "#1e293b"}
            },
            "margin": {"t": 120, "b": 50, "l": 30, "r": 30},
            "showlegend": True,
            "legend": {"orientation": "h", "y": -0.05, "x": 0.5, "xanchor": "center", "font": {"size": 12}},
            "updatemenus": [{
                "buttons": buttons,
                "direction": "down",
                "showactive": True,
                "active": 0,
                "x": 1.0,
                "xanchor": "right",
                "y": 1.01,
                "yanchor": "top",
                "bgcolor": "#f1f5f9",
                "bordercolor": "#cbd5e1",
                "borderwidth": 1,
                "font": {"size": 11, "color": "#334155"},
                "pad": {"r": 0, "t": 0}
            }],
            "annotations": [{
                "text": f"<b>{filter_label}:</b>",
                "x": 1.0,
                "xref": "paper",
                "xanchor": "right",
                "y": 1.07,
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 11, "color": "#64748b"}
            }]
        }
        
        plotly_config = {"data": traces, "layout": layout}
        
        parameters = ParameterExtractor.extract_parameters(sql)
        sql_template = ParameterExtractor.create_sql_template(sql, parameters)
        
        logger.info(f"Generated pie_with_filter: {len(traces)} filter values, format={'pivoted' if is_pivoted else 'long'}")
        
        return {
            "chart_type": "pie_with_filter",
            "chart_title": title,
            "plotly_config": plotly_config,
            "parameters": {k: asdict(v) for k, v in parameters.items()},
            "sql_template": sql_template,
            "charts": None
        }

    def _pie_with_filter_fallback(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        title: str,
        sql: str
    ) -> Dict[str, Any]:
        """Fallback a bar chart se pie_with_filter non e' possibile"""
        logger.warning("pie_with_filter fallback to bar chart")
        plotly_config = self.plotly_generator.generate_config(
            results=results, chart_type="bar", columns_info=columns_info, title=title
        )
        return {
            "chart_type": "bar", "chart_title": title, "plotly_config": plotly_config,
            "parameters": {}, "sql_template": sql, "charts": None
        }

    def _generate_multi_charts(
        self,
        results: List[Dict[str, Any]],
        columns_info: List[ColumnInfo],
        query: str,
        multi_viz: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Genera multiple visualizzazioni basate sull'analisi multi-viz"""
        charts = []
        
        for i, viz in enumerate(multi_viz.get("visualizations", [])):
            chart_type_hint = viz.get("chart_type_hint", "bar")
            data_focus = viz.get("data_focus", "breakdown")
            description = viz.get("description", f"Visualizzazione {i+1}")
            
            # Se e' un KPI/aggregate, genera KPI card
            if data_focus == "aggregate" or chart_type_hint == "kpi":
                # Calcola aggregato dai risultati
                numeric_cols = [c for c in columns_info if c.type == "numeric"]
                if numeric_cols:
                    # Somma tutti i valori della prima colonna numerica
                    total = sum(float(row[numeric_cols[0].name] or 0) for row in results)
                    kpi_result = [{numeric_cols[0].name: total}]
                    kpi_columns = [ColumnInfo(name=numeric_cols[0].name, type="numeric", cardinality=1, sample_values=[total])]
                    
                    plotly_config = self.plotly_generator.generate_config(
                        results=kpi_result,
                        chart_type="kpi",
                        columns_info=kpi_columns,
                        title=description
                    )
                    
                    charts.append({
                        "chart_type": "kpi",
                        "chart_title": description,
                        "plotly_config": plotly_config,
                        "data_focus": data_focus
                    })
            else:
                # Breakdown/trend - usa chart standard
                llm_result = LLMChartSelector.select_chart_type_and_title(
                    f"{query} - {description}", 
                    columns_info, 
                    results
                )
                
                plotly_config = self.plotly_generator.generate_config(
                    results=results,
                    chart_type=llm_result["chart_type"],
                    columns_info=columns_info,
                    title=llm_result["chart_title"]
                )
                
                charts.append({
                    "chart_type": llm_result["chart_type"],
                    "chart_title": llm_result["chart_title"],
                    "plotly_config": plotly_config,
                    "data_focus": data_focus
                })
        
        return charts


def create_chart_service(llm_provider: str = "azure", use_llm_for_chart_selection: bool = True) -> ChartService:
    """Factory ChartService - usa Azure OpenAI per selezione intelligente chart type"""
    return ChartService(llm_provider=llm_provider, use_llm_for_chart_selection=use_llm_for_chart_selection)