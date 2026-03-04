"""
Database Analyzer Service - Genera report strutturato del database usando LLM
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
from app.services.llm_provider import get_llm_provider_manager
from app.services.mcp_manager import mcp_postgres_client

logger = logging.getLogger(__name__)

class DatabaseAnalyzer:
    def __init__(self, llm_provider: str = "azure"):
        self.llm_provider = llm_provider
        self.llm_manager = get_llm_provider_manager()
    
    def analyze_database(self, schema: str = "public") -> Dict[str, Any]:
        try:
            logger.info(f"Starting database analysis for schema: {schema}")
            tables_info = self._get_tables_structure(schema)
            tables_stats = self._get_tables_statistics(tables_info)
            llm_analysis = self._generate_llm_analysis(tables_info, tables_stats)
            return {
                "success": True,
                "generated_at": datetime.now().isoformat(),
                "schema": schema,
                "summary": llm_analysis.get("summary", ""),
                "domain": llm_analysis.get("domain", ""),
                "tables_count": len(tables_info),
                "tables_analysis": llm_analysis.get("tables_analysis", []),
                "data_insights": llm_analysis.get("data_insights", {}),
                "relationships_description": llm_analysis.get("relationships_description", "")
            }
        except Exception as e:
            logger.error(f"Database analysis failed: {e}", exc_info=True)
            return {"success": False, "error": str(e), "generated_at": datetime.now().isoformat()}
    
    def _get_tables_structure(self, schema: str) -> List[Dict[str, Any]]:
        tables = []
        result = mcp_postgres_client.execute_query(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE' ORDER BY table_name")
        for row in result:
            table_name = row.get("table_name")
            columns = mcp_postgres_client.execute_query(f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = '{schema}' AND table_name = '{table_name}' ORDER BY ordinal_position")
            tables.append({"table_name": table_name, "columns": columns})
        return tables
    
    def _get_tables_statistics(self, tables_info: List[Dict]) -> Dict[str, Any]:
        stats = {}
        for table in tables_info:
            table_name = table["table_name"]
            try:
                count_result = mcp_postgres_client.execute_query(f"SELECT COUNT(*) as cnt FROM {table_name}")
                row_count = count_result[0].get("cnt", 0) if count_result else 0
                column_stats = {}
                for col in table["columns"]:
                    col_name = col.get("column_name")
                    data_type = col.get("data_type", "").lower()
                    if "date" in data_type or "timestamp" in data_type:
                        try:
                            date_stats = mcp_postgres_client.execute_query(f"SELECT MIN({col_name}) as min_date, MAX({col_name}) as max_date FROM {table_name} WHERE {col_name} IS NOT NULL")
                            if date_stats:
                                column_stats[col_name] = {"type": "date_range", "min": str(date_stats[0].get("min_date")), "max": str(date_stats[0].get("max_date"))}
                        except: pass
                    elif data_type in ["character varying", "text", "varchar"]:
                        try:
                            distinct_result = mcp_postgres_client.execute_query(f"SELECT COUNT(DISTINCT {col_name}) as distinct_count FROM {table_name}")
                            distinct_count = distinct_result[0].get("distinct_count", 0) if distinct_result else 0
                            if distinct_count <= 20:
                                values_result = mcp_postgres_client.execute_query(f"SELECT DISTINCT {col_name} as val FROM {table_name} WHERE {col_name} IS NOT NULL ORDER BY {col_name} LIMIT 20")
                                column_stats[col_name] = {"type": "categorical", "distinct_count": distinct_count, "values": [r.get("val") for r in values_result]}
                        except: pass
                stats[table_name] = {"row_count": row_count, "column_stats": column_stats}
            except Exception as e:
                stats[table_name] = {"row_count": 0, "error": str(e)}
        return stats
    
    def _generate_llm_analysis(self, tables_info: List[Dict], tables_stats: Dict[str, Any]) -> Dict[str, Any]:
        context = self._prepare_llm_context(tables_info, tables_stats)
        prompt = f"""Sei un esperto analista di database e Business Intelligence. Genera un report DETTAGLIATO che aiuti un utente NON TECNICO a comprendere il database.

=== STRUTTURA DATABASE ===
{context}

=== COMPITO ===
Genera un JSON con descrizioni DETTAGLIATE e APPROFONDITE. NON essere generico - usa i dati reali che vedi.

Formato JSON richiesto:
{{
  "domain": "<dominio specifico es: Retail - Vendita al Dettaglio>",
  "summary": "<PARAGRAFO DETTAGLIATO di 5-8 frasi: cosa rappresenta il database, quali processi di business traccia, che tipo di analisi permette di fare, quali sono i punti di forza dei dati disponibili, come possono essere usati per prendere decisioni di business>",
  "tables_analysis": [
    {{
      "table_name": "<nome tabella>",
      "business_description": "<DESCRIZIONE DETTAGLIATA di 3-4 frasi: cosa contiene la tabella, quali informazioni di business rappresenta, perche e importante per analisi>",
      "table_type": "<fact|dimension>",
      "key_columns": ["<colonne importanti per analisi>"],
      "relationships": "<come si collega alle altre tabelle>",
      "suggested_analyses": ["<3-4 analisi SPECIFICHE che si possono fare>"]
    }}
  ],
  "data_insights": {{
    "time_range": "<periodo esatto es: dal 1 Gennaio 2015 al 31 Dicembre 2018>",
    "data_volume": "<volume dati es: oltre 180.000 transazioni registrate in 3 tabelle>",
    "key_metrics": ["<lista metriche quantitative con breve descrizione>"],
    "key_dimensions": ["<lista dimensioni di analisi con breve descrizione>"],
    "suggested_questions": ["<8-10 domande di esempio SPECIFICHE e CONCRETE basate sui dati reali>"]
  }},
  "relationships_description": "<PARAGRAFO che descrive come le tabelle sono collegate tra loro, il modello dati e il flusso logico delle informazioni>"
}}

IMPORTANTE: Scrivi TUTTO in ITALIANO. Sii SPECIFICO usando nomi reali di tabelle, colonne e valori che vedi."""
        
        try:
            response = self.llm_manager.complete(messages=[{"role": "user", "content": prompt}], provider=self.llm_provider, temperature=0.3, max_tokens=3000)
            content = response["content"].strip()
            if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content: content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {"domain": "Non determinato", "summary": "Analisi non disponibile.", "tables_analysis": [], "data_insights": {}}
    
    def _prepare_llm_context(self, tables_info: List[Dict], tables_stats: Dict[str, Any]) -> str:
        lines = []
        for table in tables_info:
            table_name = table["table_name"]
            stats = tables_stats.get(table_name, {})
            lines.append(f"\n### Tabella: {table_name} ({stats.get('row_count', 0):,} righe)")
            for col in table["columns"]:
                col_name, data_type = col.get("column_name"), col.get("data_type")
                lines.append(f"  - {col_name}: {data_type}")
                col_stats = stats.get("column_stats", {}).get(col_name)
                if col_stats:
                    if col_stats.get("type") == "date_range": 
                        lines.append(f"    [Range date: {col_stats.get('min')} - {col_stats.get('max')}]")
                    elif col_stats.get("type") == "categorical": 
                        lines.append(f"    [Valori: {', '.join(str(v) for v in col_stats.get('values', [])[:10])}]")
        return "\n".join(lines)

_analyzer_instance: Optional[DatabaseAnalyzer] = None
_cached_report: Optional[Dict[str, Any]] = None

def get_database_analyzer(llm_provider: str = "azure") -> DatabaseAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None: _analyzer_instance = DatabaseAnalyzer(llm_provider)
    return _analyzer_instance

def get_cached_report() -> Optional[Dict[str, Any]]:
    return _cached_report

def set_cached_report(report: Dict[str, Any]):
    global _cached_report
    _cached_report = report
