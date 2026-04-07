"""
File Import Service — parse CSV/Excel, infer schema, suggest column names,
create table and import data into the connected client database.
"""

import io
import logging
import re
import uuid as uuid_module
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.services.mcp_manager import mcp_postgres_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColumnSchema:
    original_name: str
    suggested_name: str
    pg_type: str
    nullable: bool
    sample_values: List[Any] = field(default_factory=list)


@dataclass
class ParsedFile:
    filename: str
    file_type: str  # "csv" or "xlsx"
    columns: List[str]
    dtypes: Dict[str, str]
    preview_rows: List[Dict[str, Any]]
    total_rows: int
    df: pd.DataFrame  # kept in memory for later import


@dataclass
class ImportResult:
    success: bool
    table_name: str
    rows_imported: int
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Temporary in-memory storage for pending imports (keyed by import_id)
# ---------------------------------------------------------------------------

_pending_imports: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Italian date patterns for auto-detection
# ---------------------------------------------------------------------------

_IT_DATE_PATTERNS = [
    (r"^\d{2}/\d{2}/\d{4}$", "%d/%m/%Y"),
    (r"^\d{2}-\d{2}-\d{4}$", "%d-%m-%Y"),
    (r"^\d{2}\.\d{2}\.\d{4}$", "%d.%m.%Y"),
    (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),
    (r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$", "%d/%m/%Y %H:%M"),
    (r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$", "%d/%m/%Y %H:%M:%S"),
]


class FileImportService:
    """Handles file parsing, schema inference, and data import to client DB."""

    # ------------------------------------------------------------------
    # 1. Parse uploaded file
    # ------------------------------------------------------------------

    def parse_file(self, file_bytes: bytes, filename: str) -> ParsedFile:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext == "csv":
            df = self._read_csv(file_bytes)
            file_type = "csv"
        elif ext in ("xlsx", "xls"):
            df = self._read_excel(file_bytes, ext)
            file_type = "xlsx"
        else:
            raise ValueError(f"Unsupported file type: .{ext}. Use .csv or .xlsx")

        # Drop fully-empty rows/columns
        df.dropna(how="all", inplace=True)
        df.dropna(axis=1, how="all", inplace=True)

        preview = df.head(20).fillna("").to_dict(orient="records")
        # Convert non-serialisable values to string in preview
        for row in preview:
            for k, v in row.items():
                if isinstance(v, (datetime, pd.Timestamp)):
                    row[k] = v.isoformat()
                elif pd.isna(v):
                    row[k] = None

        return ParsedFile(
            filename=filename,
            file_type=file_type,
            columns=list(df.columns),
            dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
            preview_rows=preview,
            total_rows=len(df),
            df=df,
        )

    # ------------------------------------------------------------------
    # 2. Infer PostgreSQL schema from DataFrame
    # ------------------------------------------------------------------

    def infer_schema(self, df: pd.DataFrame) -> List[ColumnSchema]:
        schemas: List[ColumnSchema] = []
        for col in df.columns:
            series = df[col]
            nullable = bool(series.isna().any())
            pg_type = self._map_dtype(series)
            suggested = self._sanitize_column_name(col)
            samples = (
                series.dropna().head(5).tolist()
            )
            # Convert samples to serialisable types
            clean_samples = []
            for s in samples:
                if isinstance(s, (datetime, pd.Timestamp)):
                    clean_samples.append(str(s))
                else:
                    clean_samples.append(s)

            schemas.append(ColumnSchema(
                original_name=str(col),
                suggested_name=suggested,
                pg_type=pg_type,
                nullable=nullable,
                sample_values=clean_samples[:5],
            ))
        return schemas

    # ------------------------------------------------------------------
    # 3. Suggest better column names via LLM
    # ------------------------------------------------------------------

    async def suggest_column_names(
        self, columns: List[ColumnSchema], llm_provider: Optional[str] = None
    ) -> List[ColumnSchema]:
        """Use LLM to clean up column names (Italian-aware snake_case)."""
        try:
            from app.services.llm_provider import get_llm_provider_manager
            from app.config import settings

            provider = llm_provider or settings.default_llm_provider
            llm = get_llm_provider_manager()

            col_list = "\n".join(
                f"- \"{c.original_name}\" (type: {c.pg_type}, samples: {c.sample_values[:3]})"
                for c in columns
            )
            prompt = f"""Sei un esperto di database. Devi rinominare le seguenti colonne in snake_case valido per PostgreSQL.

Regole:
- Mantieni la lingua italiana se il nome originale e in italiano
- Converti spazi, trattini e caratteri speciali in underscore
- Rimuovi accenti e caratteri non-ASCII
- Usa nomi descrittivi (es. "N. Fattura" -> "numero_fattura", "Cod. Art." -> "codice_articolo")
- Massimo 63 caratteri per nome colonna
- Se il nome e gia valido snake_case, mantienilo

Colonne:
{col_list}

Rispondi SOLO con un JSON array di stringhe, un nome per colonna, nello stesso ordine.
Esempio: ["numero_fattura", "codice_articolo", "data_ordine"]"""

            messages = [
                {"role": "system", "content": "Rispondi solo con JSON valido, nessun testo aggiuntivo."},
                {"role": "user", "content": prompt},
            ]
            result = llm.complete(messages, provider=provider, temperature=0.1)
            content = result["content"].strip()

            # Strip markdown fences if present
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                content = "\n".join(lines).strip()

            import json
            suggested_names = json.loads(content)

            if isinstance(suggested_names, list) and len(suggested_names) == len(columns):
                for col, name in zip(columns, suggested_names):
                    col.suggested_name = str(name).strip()
        except Exception as e:
            logger.warning(f"LLM column name suggestion failed (non-blocking): {e}")

        return columns

    # ------------------------------------------------------------------
    # 4. Create table and import data
    # ------------------------------------------------------------------

    def create_table_and_import(
        self,
        table_name: str,
        columns: List[ColumnSchema],
        df: pd.DataFrame,
    ) -> ImportResult:
        if not mcp_postgres_client._connected:
            return ImportResult(
                success=False, table_name=table_name, rows_imported=0,
                errors=["Client database not connected"],
            )

        errors: List[str] = []
        table_name_safe = self._sanitize_table_name(table_name)

        # Build CREATE TABLE DDL
        col_defs = []
        for cs in columns:
            null_clause = "" if cs.nullable else " NOT NULL"
            col_defs.append(f'    "{cs.suggested_name}" {cs.pg_type}{null_clause}')
        ddl = f'CREATE TABLE IF NOT EXISTS "{table_name_safe}" (\n{",\n".join(col_defs)}\n);'

        logger.info(f"Creating table: {table_name_safe} with {len(columns)} columns")
        try:
            mcp_postgres_client.execute_query(ddl)
        except Exception as e:
            return ImportResult(
                success=False, table_name=table_name_safe, rows_imported=0,
                errors=[f"CREATE TABLE failed: {e}"],
            )

        # Batch INSERT
        col_names = [f'"{cs.suggested_name}"' for cs in columns]
        col_names_str = ", ".join(col_names)

        # Rename DataFrame columns to match suggested names
        rename_map = {cs.original_name: cs.suggested_name for cs in columns}
        df_import = df.rename(columns=rename_map)

        rows_imported = 0
        batch_size = 100

        for batch_start in range(0, len(df_import), batch_size):
            batch = df_import.iloc[batch_start:batch_start + batch_size]
            value_rows = []
            for _, row in batch.iterrows():
                vals = []
                for cs in columns:
                    v = row.get(cs.suggested_name)
                    vals.append(self._pg_literal(v, cs.pg_type))
                value_rows.append(f"({', '.join(vals)})")

            if not value_rows:
                continue

            insert_sql = (
                f'INSERT INTO "{table_name_safe}" ({col_names_str}) VALUES\n'
                + ",\n".join(value_rows)
                + ";"
            )
            try:
                mcp_postgres_client.execute_query(insert_sql)
                rows_imported += len(value_rows)
            except Exception as e:
                errors.append(f"INSERT batch at row {batch_start} failed: {e}")
                logger.error(f"Import batch error: {e}")

        return ImportResult(
            success=len(errors) == 0,
            table_name=table_name_safe,
            rows_imported=rows_imported,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Pending import management (in-memory with TTL)
    # ------------------------------------------------------------------

    def store_pending(self, import_id: str, parsed: ParsedFile, schema: List[ColumnSchema]):
        _pending_imports[import_id] = {
            "parsed": parsed,
            "schema": schema,
            "created_at": datetime.utcnow(),
        }
        # Evict old entries (>30 min)
        self._evict_stale()

    def get_pending(self, import_id: str) -> Optional[Dict[str, Any]]:
        return _pending_imports.get(import_id)

    def remove_pending(self, import_id: str):
        _pending_imports.pop(import_id, None)

    def _evict_stale(self):
        now = datetime.utcnow()
        stale = [
            k for k, v in _pending_imports.items()
            if (now - v["created_at"]).total_seconds() > 1800
        ]
        for k in stale:
            _pending_imports.pop(k, None)

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _read_csv(self, file_bytes: bytes) -> pd.DataFrame:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Cannot decode CSV — tried utf-8, latin-1, cp1252")

    def _read_excel(self, file_bytes: bytes, ext: str) -> pd.DataFrame:
        engine = "openpyxl" if ext == "xlsx" else None
        return pd.read_excel(io.BytesIO(file_bytes), engine=engine)

    def _map_dtype(self, series: pd.Series) -> str:
        dtype = series.dtype
        if pd.api.types.is_integer_dtype(dtype):
            if series.max() > 2_147_483_647 or series.min() < -2_147_483_648:
                return "BIGINT"
            return "INTEGER"
        if pd.api.types.is_float_dtype(dtype):
            return "NUMERIC(18,4)"
        if pd.api.types.is_bool_dtype(dtype):
            return "BOOLEAN"
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return "TIMESTAMP"
        # Check if string column contains dates
        if pd.api.types.is_object_dtype(dtype):
            date_fmt = self._detect_date_format(series)
            if date_fmt:
                return "DATE"
            # Estimate VARCHAR size
            max_len = series.dropna().astype(str).str.len().max()
            if pd.isna(max_len) or max_len == 0:
                return "TEXT"
            max_len = int(max_len)
            if max_len <= 50:
                return "VARCHAR(100)"
            if max_len <= 200:
                return "VARCHAR(500)"
            return "TEXT"
        return "TEXT"

    def _detect_date_format(self, series: pd.Series) -> Optional[str]:
        sample = series.dropna().head(20).astype(str)
        if len(sample) == 0:
            return None
        for pattern, fmt in _IT_DATE_PATTERNS:
            matches = sample.str.match(pattern).sum()
            if matches >= len(sample) * 0.8:
                return fmt
        return None

    def _sanitize_column_name(self, name: str) -> str:
        s = str(name).strip().lower()
        # Replace common Italian abbreviations
        s = re.sub(r"[àáâã]", "a", s)
        s = re.sub(r"[èéêë]", "e", s)
        s = re.sub(r"[ìíîï]", "i", s)
        s = re.sub(r"[òóôõ]", "o", s)
        s = re.sub(r"[ùúûü]", "u", s)
        # Replace non-alphanumeric with underscore
        s = re.sub(r"[^a-z0-9_]", "_", s)
        # Collapse multiple underscores
        s = re.sub(r"_+", "_", s).strip("_")
        # Ensure starts with letter
        if s and not s[0].isalpha():
            s = "col_" + s
        return s[:63] if s else "unnamed_col"

    def _sanitize_table_name(self, name: str) -> str:
        s = str(name).strip().lower()
        s = re.sub(r"[^a-z0-9_]", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        if s and not s[0].isalpha():
            s = "tbl_" + s
        return s[:63] if s else "imported_table"

    def _pg_literal(self, value: Any, pg_type: str) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "NULL"
        if pd.isna(value):
            return "NULL"
        if pg_type in ("INTEGER", "BIGINT"):
            try:
                return str(int(value))
            except (ValueError, TypeError):
                return "NULL"
        if pg_type.startswith("NUMERIC"):
            try:
                return str(float(value))
            except (ValueError, TypeError):
                return "NULL"
        if pg_type == "BOOLEAN":
            return "TRUE" if value else "FALSE"
        if pg_type in ("DATE", "TIMESTAMP"):
            s = str(value).replace("'", "''")
            return f"'{s}'"
        # String types — escape single quotes
        s = str(value).replace("'", "''")
        return f"'{s}'"
