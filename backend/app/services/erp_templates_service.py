"""
ERP Templates Service — pre-configured column mappings for Italian ERP systems.

Supports CSV exports from SAP Business One, Zucchetti, and Danea Easyfatt.
Each template maps expected ERP column names to clean PostgreSQL column names,
with fuzzy matching for minor variations.
"""

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColumnMapping:
    """Single column mapping from ERP export to PostgreSQL."""
    target: str          # Clean PostgreSQL column name
    pg_type: str         # PostgreSQL data type
    date_format: Optional[str] = None  # strptime format for date parsing
    nullable: bool = True


@dataclass
class ERPTemplate:
    """Complete mapping template for an ERP export type."""
    id: str
    erp_name: str
    export_type: str
    description: str
    expected_columns: Dict[str, ColumnMapping]
    instructions: str = ""  # Instructions for the user on how to export


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

ERP_TEMPLATES: Dict[str, ERPTemplate] = {
    # ==============================================================
    # SAP Business One
    # ==============================================================
    "sap_b1_orders": ERPTemplate(
        id="sap_b1_orders",
        erp_name="SAP Business One",
        export_type="Ordini di Vendita",
        description="Export ordini di vendita da SAP Business One",
        instructions="In SAP B1: Vendite > Ordini di vendita > Seleziona periodo > Tasto destro > Esporta in Excel",
        expected_columns={
            "DocNum":       ColumnMapping(target="numero_documento", pg_type="VARCHAR(50)", nullable=False),
            "DocDate":      ColumnMapping(target="data_documento", pg_type="DATE", date_format="%d.%m.%Y"),
            "DocDueDate":   ColumnMapping(target="data_scadenza", pg_type="DATE", date_format="%d.%m.%Y"),
            "CardCode":     ColumnMapping(target="codice_cliente", pg_type="VARCHAR(50)", nullable=False),
            "CardName":     ColumnMapping(target="nome_cliente", pg_type="VARCHAR(500)"),
            "DocTotal":     ColumnMapping(target="totale_documento", pg_type="NUMERIC(18,4)"),
            "DocCur":       ColumnMapping(target="valuta", pg_type="VARCHAR(10)"),
            "VatSum":       ColumnMapping(target="totale_iva", pg_type="NUMERIC(18,4)"),
            "DiscPrcnt":    ColumnMapping(target="sconto_percentuale", pg_type="NUMERIC(18,4)"),
            "DocStatus":    ColumnMapping(target="stato", pg_type="VARCHAR(50)"),
            "SlpName":      ColumnMapping(target="agente_vendita", pg_type="VARCHAR(200)"),
            "Comments":     ColumnMapping(target="note", pg_type="TEXT"),
        },
    ),
    "sap_b1_invoices": ERPTemplate(
        id="sap_b1_invoices",
        erp_name="SAP Business One",
        export_type="Fatture di Vendita",
        description="Export fatture attive da SAP Business One",
        instructions="In SAP B1: Vendite > Fatture Clienti > Seleziona periodo > Tasto destro > Esporta in Excel",
        expected_columns={
            "DocNum":       ColumnMapping(target="numero_fattura", pg_type="VARCHAR(50)", nullable=False),
            "DocDate":      ColumnMapping(target="data_fattura", pg_type="DATE", date_format="%d.%m.%Y"),
            "DocDueDate":   ColumnMapping(target="data_scadenza", pg_type="DATE", date_format="%d.%m.%Y"),
            "CardCode":     ColumnMapping(target="codice_cliente", pg_type="VARCHAR(50)", nullable=False),
            "CardName":     ColumnMapping(target="nome_cliente", pg_type="VARCHAR(500)"),
            "DocTotal":     ColumnMapping(target="totale_fattura", pg_type="NUMERIC(18,4)"),
            "VatSum":       ColumnMapping(target="totale_iva", pg_type="NUMERIC(18,4)"),
            "PaidToDate":   ColumnMapping(target="importo_pagato", pg_type="NUMERIC(18,4)"),
            "DocCur":       ColumnMapping(target="valuta", pg_type="VARCHAR(10)"),
            "DocStatus":    ColumnMapping(target="stato", pg_type="VARCHAR(50)"),
            "NumAtCard":    ColumnMapping(target="riferimento_cliente", pg_type="VARCHAR(100)"),
            "Comments":     ColumnMapping(target="note", pg_type="TEXT"),
        },
    ),
    "sap_b1_customers": ERPTemplate(
        id="sap_b1_customers",
        erp_name="SAP Business One",
        export_type="Anagrafica Clienti",
        description="Export anagrafica clienti da SAP Business One",
        instructions="In SAP B1: Business Partners > Anagrafica BP > Filtro: Clienti > Tasto destro > Esporta in Excel",
        expected_columns={
            "CardCode":     ColumnMapping(target="codice_cliente", pg_type="VARCHAR(50)", nullable=False),
            "CardName":     ColumnMapping(target="ragione_sociale", pg_type="VARCHAR(500)", nullable=False),
            "CardFName":    ColumnMapping(target="nome_contatto", pg_type="VARCHAR(200)"),
            "Address":      ColumnMapping(target="indirizzo", pg_type="VARCHAR(500)"),
            "City":         ColumnMapping(target="citta", pg_type="VARCHAR(100)"),
            "ZipCode":      ColumnMapping(target="cap", pg_type="VARCHAR(10)"),
            "Country":      ColumnMapping(target="nazione", pg_type="VARCHAR(50)"),
            "Phone1":       ColumnMapping(target="telefono", pg_type="VARCHAR(50)"),
            "E_Mail":       ColumnMapping(target="email", pg_type="VARCHAR(200)"),
            "VatIdUnCmp":   ColumnMapping(target="partita_iva", pg_type="VARCHAR(30)"),
            "FederalTaxID": ColumnMapping(target="codice_fiscale", pg_type="VARCHAR(30)"),
            "GroupCode":    ColumnMapping(target="gruppo_cliente", pg_type="VARCHAR(100)"),
        },
    ),
    "sap_b1_chart_of_accounts": ERPTemplate(
        id="sap_b1_chart_of_accounts",
        erp_name="SAP Business One",
        export_type="Piano dei Conti",
        description="Export piano dei conti da SAP Business One",
        instructions="In SAP B1: Finanza > Piano dei conti > Tasto destro > Esporta in Excel",
        expected_columns={
            "AcctCode":     ColumnMapping(target="codice_conto", pg_type="VARCHAR(50)", nullable=False),
            "AcctName":     ColumnMapping(target="descrizione_conto", pg_type="VARCHAR(500)", nullable=False),
            "FatherNum":    ColumnMapping(target="conto_padre", pg_type="VARCHAR(50)"),
            "GroupMask":    ColumnMapping(target="tipo_conto", pg_type="VARCHAR(50)"),
            "ActCurr":      ColumnMapping(target="valuta", pg_type="VARCHAR(10)"),
            "Balance":      ColumnMapping(target="saldo", pg_type="NUMERIC(18,4)"),
            "Finanse":      ColumnMapping(target="conto_finanziario", pg_type="VARCHAR(10)"),
        },
    ),

    # ==============================================================
    # Zucchetti
    # ==============================================================
    "zucchetti_employees": ERPTemplate(
        id="zucchetti_employees",
        erp_name="Zucchetti",
        export_type="Anagrafica Dipendenti",
        description="Export anagrafica dipendenti da Zucchetti HR",
        instructions="In Zucchetti: Anagrafiche > Dipendenti > Esporta CSV/Excel",
        expected_columns={
            "Matricola":        ColumnMapping(target="matricola", pg_type="VARCHAR(50)", nullable=False),
            "Cognome":          ColumnMapping(target="cognome", pg_type="VARCHAR(200)", nullable=False),
            "Nome":             ColumnMapping(target="nome", pg_type="VARCHAR(200)", nullable=False),
            "Codice Fiscale":   ColumnMapping(target="codice_fiscale", pg_type="VARCHAR(30)"),
            "Data Nascita":     ColumnMapping(target="data_nascita", pg_type="DATE", date_format="%d/%m/%Y"),
            "Data Assunzione":  ColumnMapping(target="data_assunzione", pg_type="DATE", date_format="%d/%m/%Y"),
            "Data Cessazione":  ColumnMapping(target="data_cessazione", pg_type="DATE", date_format="%d/%m/%Y"),
            "Qualifica":        ColumnMapping(target="qualifica", pg_type="VARCHAR(200)"),
            "Livello":          ColumnMapping(target="livello", pg_type="VARCHAR(50)"),
            "CCNL":             ColumnMapping(target="ccnl", pg_type="VARCHAR(200)"),
            "Reparto":          ColumnMapping(target="reparto", pg_type="VARCHAR(200)"),
            "Sede":             ColumnMapping(target="sede_lavoro", pg_type="VARCHAR(200)"),
            "Tipo Contratto":   ColumnMapping(target="tipo_contratto", pg_type="VARCHAR(100)"),
            "Ore Settimanali":  ColumnMapping(target="ore_settimanali", pg_type="NUMERIC(18,4)"),
        },
    ),
    "zucchetti_attendance": ERPTemplate(
        id="zucchetti_attendance",
        erp_name="Zucchetti",
        export_type="Presenze",
        description="Export presenze/timbrature da Zucchetti HR",
        instructions="In Zucchetti: Presenze > Cartellino > Seleziona periodo > Esporta",
        expected_columns={
            "Matricola":            ColumnMapping(target="matricola", pg_type="VARCHAR(50)", nullable=False),
            "Cognome":              ColumnMapping(target="cognome", pg_type="VARCHAR(200)"),
            "Nome":                 ColumnMapping(target="nome", pg_type="VARCHAR(200)"),
            "Data":                 ColumnMapping(target="data", pg_type="DATE", date_format="%d/%m/%Y", nullable=False),
            "Ore Ordinarie":        ColumnMapping(target="ore_ordinarie", pg_type="NUMERIC(18,4)"),
            "Ore Straordinario":    ColumnMapping(target="ore_straordinario", pg_type="NUMERIC(18,4)"),
            "Ore Assenza":          ColumnMapping(target="ore_assenza", pg_type="NUMERIC(18,4)"),
            "Tipo Assenza":         ColumnMapping(target="tipo_assenza", pg_type="VARCHAR(100)"),
            "Ore Ferie":            ColumnMapping(target="ore_ferie", pg_type="NUMERIC(18,4)"),
            "Ore Permesso":         ColumnMapping(target="ore_permesso", pg_type="NUMERIC(18,4)"),
        },
    ),
    "zucchetti_payslips": ERPTemplate(
        id="zucchetti_payslips",
        erp_name="Zucchetti",
        export_type="Cedolini",
        description="Export dati cedolino da Zucchetti Paghe",
        instructions="In Zucchetti: Paghe > Elaborazione > Riepilogo cedolini > Esporta",
        expected_columns={
            "Matricola":        ColumnMapping(target="matricola", pg_type="VARCHAR(50)", nullable=False),
            "Cognome":          ColumnMapping(target="cognome", pg_type="VARCHAR(200)"),
            "Nome":             ColumnMapping(target="nome", pg_type="VARCHAR(200)"),
            "Mese":             ColumnMapping(target="mese", pg_type="INTEGER"),
            "Anno":             ColumnMapping(target="anno", pg_type="INTEGER"),
            "Retribuzione Lorda": ColumnMapping(target="retribuzione_lorda", pg_type="NUMERIC(18,4)"),
            "Contributi INPS":  ColumnMapping(target="contributi_inps", pg_type="NUMERIC(18,4)"),
            "IRPEF":            ColumnMapping(target="irpef", pg_type="NUMERIC(18,4)"),
            "Addizionale Regionale": ColumnMapping(target="addizionale_regionale", pg_type="NUMERIC(18,4)"),
            "Addizionale Comunale":  ColumnMapping(target="addizionale_comunale", pg_type="NUMERIC(18,4)"),
            "Netto Pagato":     ColumnMapping(target="netto_pagato", pg_type="NUMERIC(18,4)"),
            "TFR Maturato":     ColumnMapping(target="tfr_maturato", pg_type="NUMERIC(18,4)"),
        },
    ),

    # ==============================================================
    # Danea Easyfatt
    # ==============================================================
    "danea_invoices": ERPTemplate(
        id="danea_invoices",
        erp_name="Danea Easyfatt",
        export_type="Fatture",
        description="Export fatture da Danea Easyfatt",
        instructions="In Easyfatt: Documenti > Fatture > Seleziona > Esporta in Excel/CSV",
        expected_columns={
            "Numero":           ColumnMapping(target="numero_fattura", pg_type="VARCHAR(50)", nullable=False),
            "Data":             ColumnMapping(target="data_fattura", pg_type="DATE", date_format="%d/%m/%Y"),
            "Cliente":          ColumnMapping(target="cliente", pg_type="VARCHAR(500)"),
            "P.IVA":            ColumnMapping(target="partita_iva", pg_type="VARCHAR(30)"),
            "Cod.Fiscale":      ColumnMapping(target="codice_fiscale", pg_type="VARCHAR(30)"),
            "Imponibile":       ColumnMapping(target="imponibile", pg_type="NUMERIC(18,4)"),
            "IVA":              ColumnMapping(target="importo_iva", pg_type="NUMERIC(18,4)"),
            "Totale":           ColumnMapping(target="totale", pg_type="NUMERIC(18,4)"),
            "Stato Pagamento":  ColumnMapping(target="stato_pagamento", pg_type="VARCHAR(50)"),
            "Data Pagamento":   ColumnMapping(target="data_pagamento", pg_type="DATE", date_format="%d/%m/%Y"),
            "Modalita Pagamento": ColumnMapping(target="modalita_pagamento", pg_type="VARCHAR(100)"),
            "Note":             ColumnMapping(target="note", pg_type="TEXT"),
        },
    ),
    "danea_products": ERPTemplate(
        id="danea_products",
        erp_name="Danea Easyfatt",
        export_type="Prodotti",
        description="Export anagrafica prodotti/servizi da Danea Easyfatt",
        instructions="In Easyfatt: Magazzino > Articoli > Esporta in Excel/CSV",
        expected_columns={
            "Codice":           ColumnMapping(target="codice_articolo", pg_type="VARCHAR(100)", nullable=False),
            "Descrizione":      ColumnMapping(target="descrizione", pg_type="VARCHAR(500)", nullable=False),
            "Categoria":        ColumnMapping(target="categoria", pg_type="VARCHAR(200)"),
            "Prezzo Vendita":   ColumnMapping(target="prezzo_vendita", pg_type="NUMERIC(18,4)"),
            "Prezzo Acquisto":  ColumnMapping(target="prezzo_acquisto", pg_type="NUMERIC(18,4)"),
            "Aliquota IVA":     ColumnMapping(target="aliquota_iva", pg_type="NUMERIC(18,4)"),
            "Unita Misura":     ColumnMapping(target="unita_misura", pg_type="VARCHAR(50)"),
            "Giacenza":         ColumnMapping(target="giacenza", pg_type="NUMERIC(18,4)"),
            "Scorta Minima":    ColumnMapping(target="scorta_minima", pg_type="NUMERIC(18,4)"),
            "Fornitore":        ColumnMapping(target="fornitore", pg_type="VARCHAR(500)"),
        },
    ),
    "danea_customers": ERPTemplate(
        id="danea_customers",
        erp_name="Danea Easyfatt",
        export_type="Clienti",
        description="Export anagrafica clienti da Danea Easyfatt",
        instructions="In Easyfatt: Anagrafiche > Clienti > Esporta in Excel/CSV",
        expected_columns={
            "Ragione Sociale":  ColumnMapping(target="ragione_sociale", pg_type="VARCHAR(500)", nullable=False),
            "Nome":             ColumnMapping(target="nome", pg_type="VARCHAR(200)"),
            "Cognome":          ColumnMapping(target="cognome", pg_type="VARCHAR(200)"),
            "P.IVA":            ColumnMapping(target="partita_iva", pg_type="VARCHAR(30)"),
            "Cod.Fiscale":      ColumnMapping(target="codice_fiscale", pg_type="VARCHAR(30)"),
            "Indirizzo":        ColumnMapping(target="indirizzo", pg_type="VARCHAR(500)"),
            "CAP":              ColumnMapping(target="cap", pg_type="VARCHAR(10)"),
            "Citta":            ColumnMapping(target="citta", pg_type="VARCHAR(100)"),
            "Provincia":        ColumnMapping(target="provincia", pg_type="VARCHAR(5)"),
            "Telefono":         ColumnMapping(target="telefono", pg_type="VARCHAR(50)"),
            "Email":            ColumnMapping(target="email", pg_type="VARCHAR(200)"),
            "PEC":              ColumnMapping(target="pec", pg_type="VARCHAR(200)"),
            "Codice SDI":       ColumnMapping(target="codice_sdi", pg_type="VARCHAR(10)"),
        },
    ),
}


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class ERPTemplatesService:
    """Manages ERP export templates and column matching."""

    def list_templates(self) -> List[Dict[str, Any]]:
        """Return summary list of all available templates, grouped by ERP."""
        result = []
        for tid, t in ERP_TEMPLATES.items():
            result.append({
                "id": t.id,
                "erp_name": t.erp_name,
                "export_type": t.export_type,
                "description": t.description,
                "instructions": t.instructions,
                "column_count": len(t.expected_columns),
            })
        return result

    def get_template(self, template_id: str) -> Optional[ERPTemplate]:
        return ERP_TEMPLATES.get(template_id)

    def match_columns(
        self, template_id: str, uploaded_columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy-match uploaded column names against template expected columns.
        Returns a list of {original_name, matched_erp_column, target, pg_type, nullable, confidence}.
        Unmatched uploaded columns get a generic mapping.
        """
        template = ERP_TEMPLATES.get(template_id)
        if not template:
            return []

        # Build a pool of expected columns to match against
        expected = list(template.expected_columns.keys())
        used_expected: set = set()
        results: List[Dict[str, Any]] = []

        for up_col in uploaded_columns:
            best_match = None
            best_score = 0.0

            for exp_col in expected:
                if exp_col in used_expected:
                    continue
                score = self._similarity(up_col, exp_col)
                if score > best_score:
                    best_score = score
                    best_match = exp_col

            if best_match and best_score >= 0.5:
                mapping = template.expected_columns[best_match]
                used_expected.add(best_match)
                results.append({
                    "original_name": up_col,
                    "matched_erp_column": best_match,
                    "suggested_name": mapping.target,
                    "pg_type": mapping.pg_type,
                    "nullable": mapping.nullable,
                    "confidence": round(best_score, 2),
                })
            else:
                # No match — provide generic mapping
                results.append({
                    "original_name": up_col,
                    "matched_erp_column": None,
                    "suggested_name": self._sanitize(up_col),
                    "pg_type": "TEXT",
                    "nullable": True,
                    "confidence": 0.0,
                })

        return results

    def apply_template(
        self, template_id: str, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Apply template to a DataFrame: rename columns, convert dates.
        Returns (transformed_df, column_mappings_applied).
        """
        template = ERP_TEMPLATES.get(template_id)
        if not template:
            return df, []

        matched = self.match_columns(template_id, list(df.columns))
        rename_map = {}
        applied = []

        for m in matched:
            orig = m["original_name"]
            target = m["suggested_name"]
            rename_map[orig] = target

            # Convert dates if template specifies a format
            if m["matched_erp_column"]:
                erp_col = m["matched_erp_column"]
                mapping = template.expected_columns.get(erp_col)
                if mapping and mapping.date_format and mapping.pg_type == "DATE":
                    try:
                        df[orig] = pd.to_datetime(
                            df[orig], format=mapping.date_format, errors="coerce"
                        )
                    except Exception:
                        pass

            applied.append(m)

        df = df.rename(columns=rename_map)
        return df, applied

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _similarity(self, a: str, b: str) -> float:
        """Compute similarity score between two column names."""
        # Normalize both
        na = self._normalize(a)
        nb = self._normalize(b)

        # Exact match after normalization
        if na == nb:
            return 1.0

        # SequenceMatcher on normalized
        return SequenceMatcher(None, na, nb).ratio()

    def _normalize(self, s: str) -> str:
        """Normalize a column name for comparison."""
        s = s.lower().strip()
        # Remove accents
        s = re.sub(r"[àáâã]", "a", s)
        s = re.sub(r"[èéêë]", "e", s)
        s = re.sub(r"[ìíîï]", "i", s)
        s = re.sub(r"[òóôõ]", "o", s)
        s = re.sub(r"[ùúûü]", "u", s)
        # Replace separators with space
        s = re.sub(r"[_\-./]", " ", s)
        # Collapse whitespace
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _sanitize(self, name: str) -> str:
        """Fallback column name sanitization."""
        s = self._normalize(name)
        s = re.sub(r"[^a-z0-9 ]", "", s)
        s = s.replace(" ", "_")
        s = re.sub(r"_+", "_", s).strip("_")
        if s and not s[0].isalpha():
            s = "col_" + s
        return s[:63] if s else "unnamed_col"
