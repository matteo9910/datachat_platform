"""
Data Quality Audit Service - 6 dimensions of scoring for DB health assessment.

Dimensions:
  A. Completeness (25%) - NULL analysis
  B. Consistency  (25%) - Data format coherence, outliers, referential integrity
  C. Naming       (15%) - Column/table naming conventions
  D. Normalization(15%) - Schema structure, low-cardinality candidates
  E. Performance  (10%) - Index coverage, PK/FK analysis
  F. Documentation(10%) - pg_description comments
"""

import logging
import re
import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.mcp_manager import mcp_postgres_client
from app.services.llm_provider import get_llm_provider_manager

logger = logging.getLogger(__name__)


@dataclass
class AuditIssue:
    severity: str  # "high", "medium", "low"
    table: str
    column: Optional[str]
    message: str


@dataclass
class DimensionResult:
    name: str
    score: float  # 0-100
    weight: float
    issues: List[AuditIssue] = field(default_factory=list)


@dataclass
class AuditResult:
    overall_score: int
    dimensions: Dict[str, Any]
    recommendations: List[str]
    summary: str
    table_count: int
    generated_at: str


class DataQualityService:
    """Runs a multi-dimension audit on the connected client database."""

    SCHEMA = "public"

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run_full_audit(self, llm_provider: Optional[str] = None) -> AuditResult:
        """Execute all 6 audit dimensions and produce a scored report."""
        logger.info("Starting full data quality audit")

        tables_info = self._get_tables_info()
        if not tables_info:
            return AuditResult(
                overall_score=0,
                dimensions={},
                recommendations=["Nessuna tabella trovata nel database."],
                summary="Audit impossibile: database vuoto.",
                table_count=0,
                generated_at=datetime.now().isoformat(),
            )

        dim_completeness = self._score_completeness(tables_info)
        dim_consistency = self._score_consistency(tables_info)
        dim_naming = self._score_naming(tables_info)
        dim_normalization = self._score_normalization(tables_info)
        dim_performance = self._score_performance(tables_info)
        dim_documentation = self._score_documentation(tables_info)

        dimensions = [
            dim_completeness,
            dim_consistency,
            dim_naming,
            dim_normalization,
            dim_performance,
            dim_documentation,
        ]

        overall = sum(d.score * d.weight for d in dimensions)
        overall_score = max(0, min(100, round(overall)))

        recommendations = self._build_recommendations(dimensions)

        summary = self._generate_summary(
            overall_score, dimensions, tables_info, recommendations, llm_provider
        )

        dims_dict = {}
        for d in dimensions:
            dims_dict[d.name] = {
                "score": round(d.score, 1),
                "weight": d.weight,
                "issues_count": len(d.issues),
                "issues": [asdict(i) for i in d.issues[:20]],  # cap for storage
            }

        return AuditResult(
            overall_score=overall_score,
            dimensions=dims_dict,
            recommendations=recommendations,
            summary=summary,
            table_count=len(tables_info),
            generated_at=datetime.now().isoformat(),
        )

    # ------------------------------------------------------------------
    # Helpers: table introspection
    # ------------------------------------------------------------------

    def _get_tables_info(self) -> List[Dict[str, Any]]:
        """Return list of tables with columns, row counts, constraints."""
        rows = mcp_postgres_client.execute_query(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{self.SCHEMA}' AND table_type = 'BASE TABLE' "
            f"ORDER BY table_name"
        )
        tables: List[Dict[str, Any]] = []
        for r in rows:
            tname = r["table_name"]
            cols = mcp_postgres_client.execute_query(
                f"SELECT column_name, data_type, is_nullable, column_default "
                f"FROM information_schema.columns "
                f"WHERE table_schema = '{self.SCHEMA}' AND table_name = '{tname}' "
                f"ORDER BY ordinal_position"
            )
            try:
                cnt = mcp_postgres_client.execute_query(
                    f'SELECT COUNT(*) AS cnt FROM "{tname}"'
                )
                row_count = int(cnt[0]["cnt"]) if cnt else 0
            except Exception:
                row_count = 0
            tables.append({
                "table_name": tname,
                "columns": cols,
                "row_count": row_count,
            })
        return tables

    def _get_pk_columns(self) -> Dict[str, List[str]]:
        """Return {table_name: [pk_columns]}."""
        rows = mcp_postgres_client.execute_query(
            f"""
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = '{self.SCHEMA}'
            """
        )
        pks: Dict[str, List[str]] = {}
        for r in rows:
            pks.setdefault(r["table_name"], []).append(r["column_name"])
        return pks

    def _get_fk_info(self) -> List[Dict[str, str]]:
        """Return FK relationships."""
        rows = mcp_postgres_client.execute_query(
            f"""
            SELECT
              tc.table_name AS from_table,
              kcu.column_name AS from_column,
              ccu.table_name AS to_table,
              ccu.column_name AS to_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
              AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = '{self.SCHEMA}'
            """
        )
        return rows

    def _get_indexes(self) -> List[Dict[str, str]]:
        """Return all indexes in the schema."""
        rows = mcp_postgres_client.execute_query(
            f"""
            SELECT tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = '{self.SCHEMA}'
            """
        )
        return rows

    # ------------------------------------------------------------------
    # Dimension A: Completeness (25%)
    # ------------------------------------------------------------------

    def _score_completeness(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []
        null_pcts: List[float] = []

        for t in tables_info:
            tname = t["table_name"]
            row_count = t["row_count"]

            if row_count == 0:
                issues.append(AuditIssue("high", tname, None, f"Tabella '{tname}' vuota (0 righe)"))
                continue

            for col in t["columns"]:
                cname = col["column_name"]
                try:
                    res = mcp_postgres_client.execute_query(
                        f'SELECT COUNT(*) - COUNT("{cname}") AS nulls FROM "{tname}"'
                    )
                    nulls = int(res[0]["nulls"]) if res else 0
                except Exception:
                    continue
                pct = (nulls / row_count) * 100 if row_count > 0 else 0
                null_pcts.append(pct)
                if pct > 50:
                    issues.append(AuditIssue(
                        "high", tname, cname,
                        f"Colonna '{cname}' ha {pct:.0f}% di NULL"
                    ))
                elif pct > 20:
                    issues.append(AuditIssue(
                        "medium", tname, cname,
                        f"Colonna '{cname}' ha {pct:.0f}% di NULL"
                    ))

        if not null_pcts:
            score = 50.0
        else:
            avg_null = sum(null_pcts) / len(null_pcts)
            score = max(0, 100 - avg_null * 1.5)

        return DimensionResult("completeness", score, 0.25, issues)

    # ------------------------------------------------------------------
    # Dimension B: Consistency (25%)
    # ------------------------------------------------------------------

    def _score_consistency(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []
        penalties: List[float] = []

        fks = self._get_fk_info()

        # B1: Referential integrity check
        for fk in fks:
            try:
                orphan_q = (
                    f'SELECT COUNT(*) AS cnt FROM "{fk["from_table"]}" c '
                    f'LEFT JOIN "{fk["to_table"]}" p ON c."{fk["from_column"]}" = p."{fk["to_column"]}" '
                    f'WHERE p."{fk["to_column"]}" IS NULL AND c."{fk["from_column"]}" IS NOT NULL'
                )
                res = mcp_postgres_client.execute_query(orphan_q)
                orphans = int(res[0]["cnt"]) if res else 0
                if orphans > 0:
                    issues.append(AuditIssue(
                        "high", fk["from_table"], fk["from_column"],
                        f"{orphans} record orfani: {fk['from_table']}.{fk['from_column']} → {fk['to_table']}.{fk['to_column']}"
                    ))
                    penalties.append(30)
            except Exception:
                pass

        # B2: Mixed date formats in text columns
        for t in tables_info:
            tname = t["table_name"]
            if t["row_count"] == 0:
                continue
            for col in t["columns"]:
                dtype = col.get("data_type", "").lower()
                if dtype not in ("character varying", "text", "varchar"):
                    continue
                cname = col["column_name"]
                # Sample a few values and check if they look like dates
                try:
                    sample = mcp_postgres_client.execute_query(
                        f'SELECT DISTINCT "{cname}" AS val FROM "{tname}" '
                        f'WHERE "{cname}" IS NOT NULL LIMIT 20'
                    )
                    vals = [str(r["val"]) for r in sample if r.get("val")]
                    date_patterns = sum(
                        1 for v in vals if re.match(r"^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$", v)
                    )
                    if date_patterns > 3 and date_patterns < len(vals):
                        issues.append(AuditIssue(
                            "medium", tname, cname,
                            f"Colonna testo '{cname}' contiene valori misti (date e non-date)"
                        ))
                        penalties.append(15)
                except Exception:
                    pass

        if not penalties:
            score = 95.0
        else:
            score = max(0, 100 - sum(penalties) / max(len(penalties), 1))

        return DimensionResult("consistency", score, 0.25, issues)

    # ------------------------------------------------------------------
    # Dimension C: Naming Conventions (15%)
    # ------------------------------------------------------------------

    _SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
    _CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")

    def _score_naming(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []
        total_names = 0
        snake_count = 0
        camel_count = 0
        other_count = 0

        for t in tables_info:
            tname = t["table_name"]
            total_names += 1
            if self._SNAKE_RE.match(tname):
                snake_count += 1
            elif self._CAMEL_RE.match(tname):
                camel_count += 1
            else:
                other_count += 1
                issues.append(AuditIssue(
                    "low", tname, None,
                    f"Nome tabella '{tname}' non segue snake_case"
                ))

            for col in t["columns"]:
                cname = col["column_name"]
                total_names += 1
                if self._SNAKE_RE.match(cname):
                    snake_count += 1
                elif self._CAMEL_RE.match(cname):
                    camel_count += 1
                else:
                    other_count += 1

        if total_names == 0:
            score = 50.0
        else:
            # Majority convention bonus
            dominant = max(snake_count, camel_count)
            consistency_ratio = dominant / total_names
            # Penalize "other" (mixed / uppercase / spaces)
            other_ratio = other_count / total_names
            score = consistency_ratio * 100 - other_ratio * 50

        # Detect mixed languages (basic heuristic: Italian vs English)
        italian_hints = 0
        english_hints = 0
        it_words = {"codice", "numero", "data", "importo", "quantita", "descrizione", "nome", "cognome", "indirizzo", "fattura", "ordine"}
        en_words = {"name", "date", "amount", "quantity", "description", "address", "order", "invoice", "price", "status", "type", "code"}
        for t in tables_info:
            for col in t["columns"]:
                lower = col["column_name"].lower().replace("_", " ")
                for w in it_words:
                    if w in lower:
                        italian_hints += 1
                for w in en_words:
                    if w in lower:
                        english_hints += 1
        if italian_hints > 2 and english_hints > 2:
            issues.append(AuditIssue(
                "medium", "*", None,
                f"Mix di naming italiano ({italian_hints} hints) e inglese ({english_hints} hints)"
            ))
            score = max(0, score - 15)

        score = max(0, min(100, score))
        return DimensionResult("naming", score, 0.15, issues)

    # ------------------------------------------------------------------
    # Dimension D: Normalization (15%)
    # ------------------------------------------------------------------

    def _score_normalization(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []
        penalties: List[float] = []

        for t in tables_info:
            tname = t["table_name"]
            if t["row_count"] < 10:
                continue
            for col in t["columns"]:
                cname = col["column_name"]
                dtype = col.get("data_type", "").lower()
                if dtype not in ("character varying", "text", "varchar"):
                    continue
                try:
                    res = mcp_postgres_client.execute_query(
                        f'SELECT COUNT(DISTINCT "{cname}") AS dist, COUNT(*) AS tot '
                        f'FROM "{tname}" WHERE "{cname}" IS NOT NULL'
                    )
                    if not res:
                        continue
                    dist = int(res[0]["dist"])
                    tot = int(res[0]["tot"])
                    if tot == 0:
                        continue
                    ratio = dist / tot
                    # Low cardinality repeated text → candidate for dimension table
                    if dist <= 15 and tot > 50 and ratio < 0.05:
                        issues.append(AuditIssue(
                            "medium", tname, cname,
                            f"Colonna '{cname}' ha solo {dist} valori distinti su {tot} righe — candidata per tabella dimensione"
                        ))
                        penalties.append(10)
                except Exception:
                    pass

            # Check for potential composite columns (address-like)
            col_names = [c["column_name"].lower() for c in t["columns"]]
            address_fields = {"indirizzo", "address", "via", "citta", "city", "cap", "zip", "provincia", "regione"}
            has_address = sum(1 for c in col_names if any(a in c for a in address_fields))
            if has_address == 1:
                issues.append(AuditIssue(
                    "low", tname, None,
                    f"Possibile campo indirizzo composito (un solo campo address-like trovato)"
                ))
                penalties.append(5)

        if not penalties:
            score = 95.0
        else:
            score = max(0, 100 - sum(penalties) / max(len(penalties), 1) * 2)

        return DimensionResult("normalization", score, 0.15, issues)

    # ------------------------------------------------------------------
    # Dimension E: Performance (10%)
    # ------------------------------------------------------------------

    def _score_performance(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []
        pks = self._get_pk_columns()
        fks = self._get_fk_info()
        indexes = self._get_indexes()

        indexed_cols: Dict[str, set] = {}
        for idx in indexes:
            tbl = idx.get("tablename", "")
            defn = idx.get("indexdef", "")
            # Extract column names from CREATE INDEX ... (col1, col2)
            match = re.search(r"\((.+?)\)", defn)
            if match:
                cols = [c.strip().strip('"') for c in match.group(1).split(",")]
                indexed_cols.setdefault(tbl, set()).update(cols)

        # E1: Tables without PK
        tables_without_pk = 0
        for t in tables_info:
            tname = t["table_name"]
            if tname not in pks:
                tables_without_pk += 1
                issues.append(AuditIssue(
                    "high", tname, None,
                    f"Tabella '{tname}' senza PRIMARY KEY"
                ))

        # E2: FK columns without index
        fk_no_idx = 0
        for fk in fks:
            tbl = fk["from_table"]
            col = fk["from_column"]
            if col not in indexed_cols.get(tbl, set()):
                fk_no_idx += 1
                issues.append(AuditIssue(
                    "medium", tbl, col,
                    f"FK '{col}' su '{tbl}' senza indice — potenziale lentezza JOIN"
                ))

        # E3: Large tables without indexes beyond PK
        for t in tables_info:
            tname = t["table_name"]
            if t["row_count"] > 10000:
                idx_count = sum(1 for idx in indexes if idx.get("tablename") == tname)
                if idx_count <= 1:
                    issues.append(AuditIssue(
                        "medium", tname, None,
                        f"Tabella '{tname}' ({t['row_count']} righe) con solo {idx_count} indice/i"
                    ))

        total_tables = len(tables_info)
        if total_tables == 0:
            score = 50.0
        else:
            pk_coverage = (total_tables - tables_without_pk) / total_tables * 100
            fk_penalty = min(30, fk_no_idx * 10)
            score = max(0, pk_coverage - fk_penalty)

        return DimensionResult("performance", score, 0.10, issues)

    # ------------------------------------------------------------------
    # Dimension F: Documentation (10%)
    # ------------------------------------------------------------------

    def _score_documentation(self, tables_info: List[Dict]) -> DimensionResult:
        issues: List[AuditIssue] = []

        # Count objects with pg_description comments
        try:
            res = mcp_postgres_client.execute_query(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM pg_catalog.pg_description d
                   JOIN pg_catalog.pg_class c ON d.objoid = c.oid
                   JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                   WHERE n.nspname = '{self.SCHEMA}' AND d.objsubid = 0) AS table_comments,
                  (SELECT COUNT(*) FROM pg_catalog.pg_description d
                   JOIN pg_catalog.pg_class c ON d.objoid = c.oid
                   JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                   WHERE n.nspname = '{self.SCHEMA}' AND d.objsubid > 0) AS column_comments
                """
            )
            table_comments = int(res[0]["table_comments"]) if res else 0
            column_comments = int(res[0]["column_comments"]) if res else 0
        except Exception:
            table_comments = 0
            column_comments = 0

        total_tables = len(tables_info)
        total_columns = sum(len(t["columns"]) for t in tables_info)
        total_objects = total_tables + total_columns
        documented = table_comments + column_comments

        if total_objects == 0:
            score = 50.0
        else:
            score = (documented / total_objects) * 100

        if total_tables > 0 and table_comments == 0:
            issues.append(AuditIssue(
                "medium", "*", None,
                f"Nessuna tabella ha un commento (COMMENT ON TABLE)"
            ))
        if total_columns > 0 and column_comments == 0:
            issues.append(AuditIssue(
                "low", "*", None,
                f"Nessuna colonna ha un commento (COMMENT ON COLUMN)"
            ))
        elif total_columns > 0 and column_comments < total_columns * 0.3:
            issues.append(AuditIssue(
                "low", "*", None,
                f"Solo {column_comments}/{total_columns} colonne documentate"
            ))

        return DimensionResult("documentation", score, 0.10, issues)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(self, dimensions: List[DimensionResult]) -> List[str]:
        recs: List[str] = []
        for d in sorted(dimensions, key=lambda x: x.score):
            if d.score >= 80:
                continue
            high_issues = [i for i in d.issues if i.severity == "high"]
            if d.name == "completeness":
                if high_issues:
                    recs.append(
                        f"Completezza ({d.score:.0f}/100): Ci sono colonne con >50% NULL. "
                        f"Valuta se i dati mancanti sono un problema di ETL o se le colonne sono obsolete."
                    )
                else:
                    recs.append(
                        f"Completezza ({d.score:.0f}/100): Alcune colonne hanno percentuali significative di NULL."
                    )
            elif d.name == "consistency":
                recs.append(
                    f"Coerenza ({d.score:.0f}/100): "
                    + (f"Trovati {len(high_issues)} problemi di integrita referenziale. " if high_issues else "")
                    + "Verifica la consistenza dei formati dati."
                )
            elif d.name == "naming":
                recs.append(
                    f"Convenzioni di naming ({d.score:.0f}/100): "
                    f"Standardizza i nomi delle colonne su un'unica convenzione (preferibilmente snake_case)."
                )
            elif d.name == "normalization":
                recs.append(
                    f"Normalizzazione ({d.score:.0f}/100): "
                    f"Ci sono colonne a bassa cardinalita che potrebbero essere estratte in tabelle dimensione."
                )
            elif d.name == "performance":
                recs.append(
                    f"Performance ({d.score:.0f}/100): "
                    + ("Alcune tabelle non hanno PRIMARY KEY. " if any(i.message and "PRIMARY KEY" in i.message for i in d.issues) else "")
                    + "Aggiungi indici sulle colonne FK usate nei JOIN."
                )
            elif d.name == "documentation":
                recs.append(
                    f"Documentazione ({d.score:.0f}/100): "
                    f"Aggiungi commenti (COMMENT ON) a tabelle e colonne per migliorare la comprensibilita."
                )
        return recs[:8]

    # ------------------------------------------------------------------
    # LLM Summary
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        overall_score: int,
        dimensions: List[DimensionResult],
        tables_info: List[Dict],
        recommendations: List[str],
        llm_provider: Optional[str] = None,
    ) -> str:
        """Generate a human-readable executive summary via LLM."""
        try:
            llm_manager = get_llm_provider_manager()
            provider = llm_provider or "azure"

            dims_text = "\n".join(
                f"- {d.name}: {d.score:.0f}/100 (peso {d.weight*100:.0f}%) — {len(d.issues)} issue"
                for d in dimensions
            )
            recs_text = "\n".join(f"- {r}" for r in recommendations)
            tables_text = ", ".join(
                f"{t['table_name']} ({t['row_count']} righe)"
                for t in tables_info[:20]
            )

            prompt = (
                f"Sei un esperto di data quality. Genera un executive summary in italiano (3-5 frasi) "
                f"per questo audit del database.\n\n"
                f"Score complessivo: {overall_score}/100\n"
                f"Tabelle analizzate: {len(tables_info)} ({tables_text})\n\n"
                f"Dimensioni:\n{dims_text}\n\n"
                f"Raccomandazioni:\n{recs_text}\n\n"
                f"Scrivi un riassunto chiaro e conciso per un manager non tecnico. "
                f"Includi il punteggio e le aree principali di miglioramento."
            )

            response = llm_manager.complete(prompt, provider=provider)
            return response.strip()
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")
            grade = "buona" if overall_score >= 70 else "discreta" if overall_score >= 40 else "bassa"
            return (
                f"Audit completato con score {overall_score}/100 (qualita {grade}). "
                f"Analizzate {len(tables_info)} tabelle. "
                f"Aree di miglioramento principali: "
                + ", ".join(d.name for d in sorted(dimensions, key=lambda x: x.score)[:3])
                + "."
            )
