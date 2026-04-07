"""
Trust Score Service — Multi-factor confidence scoring for NL-to-SQL responses.

Computes an objective trust score (0-100) for each generated SQL query based on:
- Query Complexity (30%): SQL AST analysis via sqlparse
- RAG Match (25%): ChromaDB similarity distance to best training example
- Result Validation (25%): Row count, NULL ratio, schema match
- Syntactic Confidence (20%): SQL parsing, table/column existence verification
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Parenthesis
from sqlparse.tokens import Keyword, DML

logger = logging.getLogger(__name__)


@dataclass
class TrustScoreResult:
    score: int                       # 0-100 composite
    grade: str                       # "high" | "medium" | "low"
    factors: Dict[str, Any]          # per-factor breakdown
    explanation: str                 # one-line human-readable summary


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------
WEIGHT_COMPLEXITY = 0.30
WEIGHT_RAG_MATCH = 0.25
WEIGHT_VALIDATION = 0.25
WEIGHT_SYNTACTIC = 0.20


class TrustScoreService:
    """Computes multi-factor trust score for generated SQL queries."""

    # ------------------------------------------------------------------
    # Factor A: Query Complexity (30%)
    # ------------------------------------------------------------------
    def compute_complexity_score(self, sql: str) -> Tuple[float, Dict[str, Any]]:
        """
        Simpler SQL = higher score.  Complex queries are harder for LLMs to
        get right, so confidence should be lower.

        Returns (score 0-100, details dict).
        """
        sql_upper = sql.upper()
        details: Dict[str, Any] = {}

        score = 100.0

        # JOINs
        join_count = len(re.findall(r'\bJOIN\b', sql_upper))
        details["joins"] = join_count
        score -= join_count * 10

        # Subqueries (count opening parens that follow SELECT)
        subquery_count = len(re.findall(r'\(\s*SELECT\b', sql_upper))
        details["subqueries"] = subquery_count
        score -= subquery_count * 15

        # Window functions
        window_count = len(re.findall(r'\bOVER\s*\(', sql_upper))
        details["window_functions"] = window_count
        score -= window_count * 10

        # HAVING
        has_having = 1 if re.search(r'\bHAVING\b', sql_upper) else 0
        details["having"] = has_having
        score -= has_having * 5

        # CASE statements
        case_count = len(re.findall(r'\bCASE\b', sql_upper))
        details["case_statements"] = case_count
        score -= case_count * 5

        # UNION
        union_count = len(re.findall(r'\bUNION\b', sql_upper))
        details["unions"] = union_count
        score -= union_count * 10

        # CTEs (WITH ... AS)
        cte_count = len(re.findall(r'\bWITH\b\s+\w+\s+AS\b', sql_upper))
        details["ctes"] = cte_count
        score -= cte_count * 8

        score = max(5.0, min(100.0, score))
        details["raw_score"] = round(score, 1)
        return round(score, 1), details

    # ------------------------------------------------------------------
    # Factor B: RAG Match (25%)
    # ------------------------------------------------------------------
    def compute_rag_match_score(
        self,
        question: str,
        vanna_service: Any,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Measures how close the user question is to existing training examples.
        Uses ChromaDB L2 distances — lower distance = better match = higher score.

        Returns (score 0-100, details dict).
        """
        details: Dict[str, Any] = {}

        try:
            examples_with_distances = vanna_service.get_similar_examples_with_distances(
                question, n_results=3
            )
        except Exception as e:
            logger.warning(f"RAG match scoring failed: {e}")
            return 0.0, {"error": str(e), "has_examples": False}

        if not examples_with_distances:
            return 0.0, {"has_examples": False, "reason": "no training examples"}

        best_distance = examples_with_distances[0].get("distance", 999)
        details["best_distance"] = round(best_distance, 4)
        details["best_match_question"] = examples_with_distances[0].get("question", "")[:80]
        details["num_matches"] = len(examples_with_distances)
        details["has_examples"] = True

        # Convert L2 distance to 0-100 score.
        # Typical ChromaDB L2 distances: 0 = identical, ~1-2 = related, >3 = unrelated.
        score = max(0.0, 100.0 - best_distance * 40)
        score = min(100.0, score)
        details["raw_score"] = round(score, 1)
        return round(score, 1), details

    # ------------------------------------------------------------------
    # Factor C: Result Validation (25%)
    # ------------------------------------------------------------------
    def compute_validation_score(
        self,
        rows: List[Dict[str, Any]],
        sql: str,
        schema_columns: Optional[List[str]] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Checks the reasonableness of query results.

        Returns (score 0-100, details dict).
        """
        details: Dict[str, Any] = {}
        sub_scores: List[float] = []

        # --- Row count reasonableness ---
        row_count = len(rows)
        details["row_count"] = row_count

        if row_count == 0:
            row_score = 20.0  # suspicious — query may have wrong filters
            details["row_assessment"] = "zero_rows"
        elif row_count <= 1000:
            row_score = 95.0
            details["row_assessment"] = "normal"
        elif row_count <= 5000:
            row_score = 75.0
            details["row_assessment"] = "large"
        else:
            row_score = 55.0  # may be missing WHERE clause
            details["row_assessment"] = "very_large"
        sub_scores.append(row_score)

        # --- NULL ratio ---
        if rows:
            total_cells = 0
            null_cells = 0
            for row in rows[:200]:  # sample first 200 rows for performance
                for v in row.values():
                    total_cells += 1
                    if v is None:
                        null_cells += 1
            null_ratio = null_cells / total_cells if total_cells > 0 else 0
            details["null_ratio"] = round(null_ratio, 3)

            if null_ratio > 0.5:
                null_score = 30.0
            elif null_ratio > 0.2:
                null_score = 70.0
            else:
                null_score = 95.0
            sub_scores.append(null_score)
        else:
            details["null_ratio"] = None

        # --- Column name plausibility ---
        if rows and schema_columns:
            result_cols = set(rows[0].keys())
            schema_set = set(schema_columns)
            matched = result_cols & schema_set
            match_ratio = len(matched) / len(result_cols) if result_cols else 0
            details["column_match_ratio"] = round(match_ratio, 2)

            col_score = match_ratio * 100
            sub_scores.append(col_score)

        score = sum(sub_scores) / len(sub_scores) if sub_scores else 50.0
        score = max(0.0, min(100.0, score))
        details["raw_score"] = round(score, 1)
        return round(score, 1), details

    # ------------------------------------------------------------------
    # Factor D: Syntactic Confidence (20%)
    # ------------------------------------------------------------------
    def compute_syntactic_score(
        self,
        sql: str,
        schema_ddl: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Validates SQL syntax and checks that referenced tables/columns exist.

        Returns (score 0-100, details dict).
        """
        details: Dict[str, Any] = {}
        sub_scores: List[float] = []

        # --- Parse success ---
        try:
            parsed = sqlparse.parse(sql)
            if parsed and len(parsed) > 0:
                stmt = parsed[0]
                # Check it's a SELECT (not empty or garbage)
                first_token_type = stmt.get_type()
                if first_token_type == "SELECT":
                    sub_scores.append(100.0)
                    details["parse_success"] = True
                    details["statement_type"] = "SELECT"
                elif first_token_type:
                    sub_scores.append(80.0)
                    details["parse_success"] = True
                    details["statement_type"] = first_token_type
                else:
                    sub_scores.append(40.0)
                    details["parse_success"] = False
            else:
                sub_scores.append(20.0)
                details["parse_success"] = False
        except Exception:
            sub_scores.append(10.0)
            details["parse_success"] = False

        # --- Extract table names from schema DDL ---
        schema_tables = set(
            t.lower()
            for t in re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\w+\.)?(\w+)', schema_ddl, re.IGNORECASE)
        )
        details["schema_table_count"] = len(schema_tables)

        # --- Extract table names referenced in SQL ---
        sql_tables = self._extract_table_names(sql)
        details["sql_tables"] = list(sql_tables)

        if sql_tables and schema_tables:
            matched = sql_tables & schema_tables
            match_ratio = len(matched) / len(sql_tables)
            details["table_match_ratio"] = round(match_ratio, 2)
            sub_scores.append(match_ratio * 100)
        elif not sql_tables:
            # Could not extract tables (unusual but not necessarily wrong)
            sub_scores.append(60.0)

        # --- Extract column names from schema DDL ---
        schema_columns = set(
            c.lower()
            for c in re.findall(r'^\s+"?(\w+)"?\s+(?:BIGINT|INTEGER|NUMERIC|VARCHAR|TEXT|BOOLEAN|DATE|TIMESTAMP|SERIAL|UUID|JSONB|REAL|DOUBLE|SMALLINT|CHAR)',
                                schema_ddl, re.IGNORECASE | re.MULTILINE)
        )

        # --- Extract column names referenced in SQL ---
        sql_columns = self._extract_column_names(sql, sql_tables)

        if sql_columns and schema_columns:
            matched_cols = sql_columns & schema_columns
            col_ratio = len(matched_cols) / len(sql_columns)
            details["column_match_ratio"] = round(col_ratio, 2)
            sub_scores.append(col_ratio * 100)

        score = sum(sub_scores) / len(sub_scores) if sub_scores else 50.0
        score = max(0.0, min(100.0, score))
        details["raw_score"] = round(score, 1)
        return round(score, 1), details

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------
    def compute_trust_score(
        self,
        sql: str,
        question: str,
        rows: List[Dict[str, Any]],
        vanna_service: Any,
        schema_ddl: str = "",
        schema_columns: Optional[List[str]] = None,
    ) -> TrustScoreResult:
        """
        Compute the overall trust score combining all four factors.
        """
        try:
            complexity_score, complexity_details = self.compute_complexity_score(sql)
        except Exception as e:
            logger.warning(f"Complexity scoring failed: {e}")
            complexity_score, complexity_details = 50.0, {"error": str(e)}

        try:
            rag_score, rag_details = self.compute_rag_match_score(question, vanna_service)
        except Exception as e:
            logger.warning(f"RAG scoring failed: {e}")
            rag_score, rag_details = 0.0, {"error": str(e)}

        try:
            validation_score, validation_details = self.compute_validation_score(
                rows, sql, schema_columns
            )
        except Exception as e:
            logger.warning(f"Validation scoring failed: {e}")
            validation_score, validation_details = 50.0, {"error": str(e)}

        try:
            syntactic_score, syntactic_details = self.compute_syntactic_score(sql, schema_ddl)
        except Exception as e:
            logger.warning(f"Syntactic scoring failed: {e}")
            syntactic_score, syntactic_details = 50.0, {"error": str(e)}

        # Weighted composite
        composite = (
            complexity_score * WEIGHT_COMPLEXITY
            + rag_score * WEIGHT_RAG_MATCH
            + validation_score * WEIGHT_VALIDATION
            + syntactic_score * WEIGHT_SYNTACTIC
        )
        composite = int(round(max(0, min(100, composite))))

        # Grade
        if composite >= 70:
            grade = "high"
        elif composite >= 40:
            grade = "medium"
        else:
            grade = "low"

        # Explanation
        weakest_name = min(
            [
                ("complessita query", complexity_score),
                ("match RAG", rag_score),
                ("validazione risultati", validation_score),
                ("sintassi SQL", syntactic_score),
            ],
            key=lambda x: x[1],
        )
        explanation = f"Affidabilita {grade} ({composite}/100). Fattore piu debole: {weakest_name[0]} ({int(weakest_name[1])}/100)."

        factors = {
            "complexity": {
                "score": complexity_score,
                "weight": WEIGHT_COMPLEXITY,
                "weighted": round(complexity_score * WEIGHT_COMPLEXITY, 1),
                "details": complexity_details,
            },
            "rag_match": {
                "score": rag_score,
                "weight": WEIGHT_RAG_MATCH,
                "weighted": round(rag_score * WEIGHT_RAG_MATCH, 1),
                "details": rag_details,
            },
            "validation": {
                "score": validation_score,
                "weight": WEIGHT_VALIDATION,
                "weighted": round(validation_score * WEIGHT_VALIDATION, 1),
                "details": validation_details,
            },
            "syntactic": {
                "score": syntactic_score,
                "weight": WEIGHT_SYNTACTIC,
                "weighted": round(syntactic_score * WEIGHT_SYNTACTIC, 1),
                "details": syntactic_details,
            },
        }

        return TrustScoreResult(
            score=composite,
            grade=grade,
            factors=factors,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_table_names(self, sql: str) -> set:
        """Extract table names referenced in SQL (FROM / JOIN clauses)."""
        tables = set()
        # FROM table / JOIN table patterns
        for match in re.finditer(
            r'(?:FROM|JOIN)\s+(?:ONLY\s+)?(?:(\w+)\.)?(\w+)',
            sql, re.IGNORECASE
        ):
            tables.add(match.group(2).lower())

        # Remove common SQL keywords that might be falsely captured
        sql_keywords = {
            "select", "where", "group", "order", "having", "limit",
            "offset", "union", "except", "intersect", "values", "set",
            "lateral", "unnest",
        }
        tables -= sql_keywords
        return tables

    def _extract_column_names(self, sql: str, table_names: set) -> set:
        """
        Extract column names from SQL.  Simplified heuristic: grabs
        identifiers from SELECT and WHERE clauses.
        """
        columns = set()

        # Remove string literals to avoid false matches
        cleaned = re.sub(r"'[^']*'", "''", sql)

        # table.column patterns
        for match in re.finditer(r'(\w+)\.(\w+)', cleaned):
            col = match.group(2).lower()
            if col not in {"*"}:
                columns.add(col)

        # Bare identifiers after SELECT (before FROM)
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM\b', cleaned, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            for ident in re.findall(r'\b(\w+)\b', select_clause):
                lower = ident.lower()
                if lower not in table_names and lower not in {
                    "select", "distinct", "as", "case", "when", "then",
                    "else", "end", "sum", "count", "avg", "max", "min",
                    "coalesce", "cast", "null", "true", "false",
                    "asc", "desc", "and", "or", "not", "in", "between",
                    "like", "ilike", "is", "over", "partition", "by",
                    "row_number", "rank", "dense_rank", "round",
                    "extract", "date_trunc", "to_char",
                }:
                    columns.add(lower)

        # Remove numbers and very short identifiers that are likely aliases
        columns = {c for c in columns if len(c) > 1 and not c.isdigit()}
        return columns
