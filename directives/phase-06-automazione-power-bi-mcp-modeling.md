# Fase 06: Automazione Power BI tramite MCP Modeling Server

## Panoramica
- **Obiettivo**: Integrare Microsoft Power BI Modeling MCP Server per automazione text-to-DAX e modifica report .pbix locali
- **Dipendenza**: Fase 05 (Backend completo con CRUD charts)
- **Complessità stimata**: Alta
- **Componenti coinvolti**: Backend, MCP, Power BI

## Contesto
Le Fasi 1-5 hanno completato la parte "Chat con i Dati" del sistema. Ora implementiamo la seconda funzionalità core: **automazione Power BI tramite conversazione naturale**.

Microsoft ha rilasciato (preview 2026) il **Power BI Modeling MCP Server**, che porta capacità semantic modeling di Power BI agli AI agent tramite standard MCP. Questo permette di:
- Leggere schema modelli Power BI (.pbix files)
- Generare codice DAX da linguaggio naturale
- Validare sintassi DAX
- Applicare modifiche a file .pbix (aggiungere misure, colonne, visualizzazioni, pagine)

**IMPORTANTE:** MCP Power BI è in preview, API possono cambiare. Implementare con graceful degradation e logging dettagliato.

Workflow:
1. User: "Aggiungi una misura DAX chiamata 'Vendite YTD' che calcola vendite da inizio anno"
2. Backend legge schema report .pbix via MCP
3. LLM genera DAX: `Vendite YTD = TOTALYTD(SUM(Sales[Amount]), Calendar[Date])`
4. MCP valida sintassi DAX
5. Frontend mostra preview modifiche (DAX code + descrizione)
6. User conferma
7. MCP applica modifica a file .pbix locale
8. User verifica in Power BI Desktop

Backup automatico file .pbix prima di ogni modifica per rollback in caso errore.

## Obiettivi Specifici
1. Configurare MCP Power BI Modeling Server (installazione, workspace path)
2. Creare `powerbi_mcp_manager.py` per gestione MCP Power BI subprocess
3. Creare `powerbi_service.py` con logiche text-to-DAX, schema reading, modification apply
4. Implementare backup automatico file .pbix (copia in `.bak` con timestamp)
5. Implementare endpoint `/api/powerbi/reports` (GET): lista file .pbix disponibili
6. Implementare endpoint `/api/powerbi/command` (POST): text-to-DAX generation + preview
7. Implementare endpoint `/api/powerbi/apply/{preview_id}` (POST): applica modifiche a .pbix
8. Implementare rollback automatico in caso di errore applicazione
9. Testare workflow completo su file .pbix test (creare sample report con Power BI Desktop)
10. Validare modifiche applicate aprendo .pbix in Power BI Desktop

## Specifiche Tecniche Dettagliate

### Area 1: Configurazione MCP Power BI Server

**Installazione MCP Power BI Modeling:**

```bash
# Installazione globale npm
npm install -g @microsoft/powerbi-modeling-mcp

# Verificare installazione
npx powerbi-modeling-mcp --help

# Output atteso: help message con opzioni server
```

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\mcp-config\powerbi-config.json`

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-modeling-mcp",
      "args": [
        "--workspace-path",
        "C:/Users/TF536AC/PowerBI/Reports"
      ],
      "env": {}
    }
  }
}
```

**NOTA:** Creare directory `C:\Users\TF536AC\PowerBI\Reports` se non esiste, e copiare almeno un file .pbix test.

**Creazione file .pbix test:**

1. Aprire Power BI Desktop
2. Get Data → PostgreSQL → connettere a `datachat_db` (credenziali da `.env`)
3. Importare tabella `public.orders`
4. Creare misura base:
   ```dax
   Total Sales = SUM(orders[sales])
   ```
5. Creare visual semplice (bar chart: category x Total Sales)
6. Salvare come `C:\Users\TF536AC\PowerBI\Reports\Superstore_Test.pbix`

---

### Area 2: Power BI MCP Manager

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\powerbi_mcp_manager.py`

```python
"""
Power BI MCP Manager - Gestione MCP Power BI Modeling Server
Comunicazione subprocess stdio + JSON-RPC 2.0
"""

import subprocess
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class PowerBIMCPClient:
    """Client MCP Power BI Modeling Server"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.workspace_path = Path(settings.mcp_powerbi_workspace_path)

        if not self.workspace_path.exists():
            logger.warning(f"Power BI workspace path not found: {self.workspace_path}")
            # Crea directory se non esiste
            self.workspace_path.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Avvia MCP Power BI server subprocess"""
        try:
            self.process = subprocess.Popen(
                [
                    "powerbi-modeling-mcp",
                    "--workspace-path",
                    str(self.workspace_path)
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False  # Binary mode
            )
            logger.info(f"MCP Power BI server avviato: workspace={self.workspace_path}")

        except FileNotFoundError:
            logger.error(
                "MCP Power BI server non trovato. "
                "Installare con: npm install -g @microsoft/powerbi-modeling-mcp"
            )
            raise
        except Exception as e:
            logger.error(f"Errore avvio MCP Power BI: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chiama tool MCP Power BI

        Tools disponibili (preview 2026, soggetti a modifica):
        - list_reports: lista file .pbix workspace
        - get_model_schema: schema modello Power BI (tabelle, colonne, misure)
        - add_measure: aggiungi misura DAX
        - update_measure: modifica misura esistente
        - validate_dax: valida sintassi DAX senza applicare
        - add_visual: aggiungi visualizzazione a pagina
        - create_page: crea nuova pagina report
        """
        if not self.process:
            raise RuntimeError("MCP Power BI server non avviato")

        self.request_id += 1

        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": self.request_id
        }

        try:
            # Invia richiesta
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json.encode("utf-8"))
            self.process.stdin.flush()

            # Leggi risposta
            response_line = self.process.stdout.readline()
            response = json.loads(response_line.decode("utf-8"))

            if "error" in response:
                error_msg = response["error"].get("message", str(response["error"]))
                raise Exception(f"MCP Power BI error: {error_msg}")

            return response.get("result", {})

        except Exception as e:
            logger.error(f"Errore chiamata MCP Power BI tool '{tool_name}': {e}")
            raise

    def list_reports(self) -> List[Dict[str, Any]]:
        """
        Lista file .pbix in workspace

        Returns:
            [
                {
                    "file_name": "Report.pbix",
                    "file_path": "C:/Users/.../Report.pbix",
                    "size_bytes": 12345,
                    "last_modified": "2026-02-17T10:00:00"
                },
                ...
            ]
        """
        result = self.call_tool("list_reports", {})
        return result.get("reports", [])

    def get_model_schema(self, report_path: str) -> Dict[str, Any]:
        """
        Recupera schema modello Power BI

        Returns:
            {
                "tables": [
                    {
                        "name": "orders",
                        "columns": [
                            {"name": "order_id", "type": "Text"},
                            {"name": "sales", "type": "Decimal"}
                        ],
                        "measures": [
                            {"name": "Total Sales", "expression": "SUM(orders[sales])"}
                        ]
                    }
                ],
                "relationships": [...]
            }
        """
        result = self.call_tool("get_model_schema", {"report_path": report_path})
        return result

    def validate_dax(self, dax_expression: str, report_path: str) -> Dict[str, Any]:
        """
        Valida sintassi DAX

        Returns:
            {
                "valid": bool,
                "errors": ["Error message"] | []
            }
        """
        result = self.call_tool("validate_dax", {
            "expression": dax_expression,
            "report_path": report_path
        })
        return result

    def add_measure(
        self,
        report_path: str,
        measure_name: str,
        dax_expression: str,
        table_name: str = "orders"  # Default table
    ) -> Dict[str, Any]:
        """
        Aggiungi misura DAX a modello

        Returns:
            {
                "success": bool,
                "measure_name": str,
                "message": str
            }
        """
        result = self.call_tool("add_measure", {
            "report_path": report_path,
            "measure_name": measure_name,
            "expression": dax_expression,
            "table_name": table_name
        })
        return result

    def shutdown(self):
        """Termina MCP Power BI server subprocess"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            logger.info("MCP Power BI server terminato")


# Singleton MCP Power BI client
powerbi_mcp_client = PowerBIMCPClient()
```

---

### Area 3: Power BI Service (Text-to-DAX + Automation)

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\powerbi_service.py`

```python
"""
Power BI Service - Text-to-DAX generation e automazione report
"""

import logging
import shutil
import uuid
from typing import Dict, Any, List, Optional, Literal
from pathlib import Path
from datetime import datetime

from app.services.llm_provider import llm_provider_manager
from app.services.powerbi_mcp_manager import powerbi_mcp_client
from app.config import settings

logger = logging.getLogger(__name__)


# Storage temporaneo preview modifiche (in-memory per POC, Redis in production)
_modification_previews: Dict[str, Dict[str, Any]] = {}


class PowerBIService:
    """Service automazione Power BI tramite text-to-DAX"""

    def __init__(self, llm_provider: str = "claude"):
        self.llm_provider = llm_provider

    def list_reports(self) -> List[Dict[str, Any]]:
        """
        Lista report Power BI disponibili in workspace

        Returns:
            [{"file_name": str, "file_path": str, "size_bytes": int, ...}]
        """
        try:
            reports = powerbi_mcp_client.list_reports()
            logger.info(f"Power BI reports found: {len(reports)}")
            return reports

        except Exception as e:
            logger.error(f"List reports error: {e}")
            return []

    def interpret_command(
        self,
        command: str,
        report_path: str
    ) -> Dict[str, Any]:
        """
        Interpreta comando NL e genera preview modifiche Power BI

        Args:
            command: Comando NL (es. "Aggiungi misura Vendite YTD")
            report_path: Path file .pbix

        Returns:
            {
                "preview_id": str,           # ID per conferma
                "interpretation": str,       # Spiegazione cosa verrà fatto
                "dax_code": str | None,      # Codice DAX generato
                "changes": [                 # Lista modifiche
                    {
                        "type": "measure" | "column" | "table" | "visual",
                        "action": "create" | "update" | "delete",
                        "details": {...}
                    }
                ],
                "validation": {
                    "valid": bool,
                    "errors": [str]
                },
                "success": bool
            }
        """
        try:
            # 1. Recupera schema modello Power BI
            schema = powerbi_mcp_client.get_model_schema(report_path)

            # 2. Genera DAX via LLM (text-to-DAX)
            dax_result = self._generate_dax(
                command=command,
                model_schema=schema
            )

            if not dax_result["success"]:
                return {
                    "preview_id": "",
                    "interpretation": dax_result.get("error", "DAX generation failed"),
                    "dax_code": None,
                    "changes": [],
                    "validation": {"valid": False, "errors": [dax_result.get("error", "Unknown")]},
                    "success": False
                }

            dax_code = dax_result["dax_code"]
            measure_name = dax_result["measure_name"]
            interpretation = dax_result["interpretation"]

            # 3. Valida DAX syntax
            validation = powerbi_mcp_client.validate_dax(
                dax_expression=dax_code,
                report_path=report_path
            )

            if not validation["valid"]:
                logger.warning(f"DAX validation failed: {validation['errors']}")

            # 4. Costruisci preview modifiche
            changes = [
                {
                    "type": "measure",
                    "action": "create",
                    "details": {
                        "measure_name": measure_name,
                        "dax_expression": dax_code,
                        "table": "orders"  # Default table
                    }
                }
            ]

            # 5. Crea preview ID e salva in storage temporaneo
            preview_id = str(uuid.uuid4())

            _modification_previews[preview_id] = {
                "report_path": report_path,
                "command": command,
                "dax_code": dax_code,
                "measure_name": measure_name,
                "changes": changes,
                "created_at": datetime.utcnow().isoformat()
            }

            logger.info(f"Command interpreted: preview_id={preview_id}, measure={measure_name}")

            return {
                "preview_id": preview_id,
                "interpretation": interpretation,
                "dax_code": dax_code,
                "changes": changes,
                "validation": validation,
                "success": True
            }

        except Exception as e:
            logger.error(f"Command interpretation error: {e}", exc_info=True)
            return {
                "preview_id": "",
                "interpretation": f"Errore: {str(e)}",
                "dax_code": None,
                "changes": [],
                "validation": {"valid": False, "errors": [str(e)]},
                "success": False
            }

    def _generate_dax(
        self,
        command: str,
        model_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera DAX code da comando NL

        Returns:
            {
                "dax_code": str,
                "measure_name": str,
                "interpretation": str,
                "success": bool
            }
        """
        # Costruisci context schema per LLM
        schema_context = self._format_schema_for_prompt(model_schema)

        prompt = f"""
Sei un esperto Power BI che genera codice DAX da comandi in linguaggio naturale.

Schema modello Power BI:
{schema_context}

Comando utente:
"{command}"

Genera:
1. Nome misura (inglese, PascalCase, es. "SalesYTD")
2. Espressione DAX completa e corretta
3. Breve spiegazione cosa fa la misura

Formato risposta:
MEASURE_NAME: [nome]
DAX_CODE:
[codice DAX]
EXPLANATION: [spiegazione 1 frase]
"""

        try:
            llm_result = llm_provider_manager.complete(
                prompt=prompt.strip(),
                provider=self.llm_provider,
                temperature=0.2,  # Deterministico per codice
                max_tokens=1000
            )

            content = llm_result["content"]

            # Parse risposta LLM
            measure_name = self._extract_field(content, "MEASURE_NAME:")
            dax_code = self._extract_field(content, "DAX_CODE:", "EXPLANATION:")
            explanation = self._extract_field(content, "EXPLANATION:")

            if not measure_name or not dax_code:
                raise ValueError("LLM response parsing failed")

            logger.info(f"DAX generated: {measure_name} = {dax_code[:50]}...")

            return {
                "dax_code": dax_code.strip(),
                "measure_name": measure_name.strip(),
                "interpretation": explanation.strip() if explanation else "Misura DAX creata",
                "success": True
            }

        except Exception as e:
            logger.error(f"DAX generation error: {e}")
            return {
                "dax_code": "",
                "measure_name": "",
                "interpretation": "",
                "success": False,
                "error": str(e)
            }

    def _format_schema_for_prompt(self, schema: Dict[str, Any]) -> str:
        """Formatta schema Power BI per prompt LLM"""
        lines = []

        for table in schema.get("tables", []):
            lines.append(f"Table: {table['name']}")

            # Columns
            for col in table.get("columns", []):
                lines.append(f"  - Column: {col['name']} ({col.get('type', 'Unknown')})")

            # Existing measures
            for measure in table.get("measures", []):
                lines.append(f"  - Measure: {measure['name']} = {measure.get('expression', '...')}")

        return "\n".join(lines)

    def _extract_field(self, text: str, start_marker: str, end_marker: Optional[str] = None) -> str:
        """Extract field from LLM response"""
        start_idx = text.find(start_marker)
        if start_idx == -1:
            return ""

        start_idx += len(start_marker)

        if end_marker:
            end_idx = text.find(end_marker, start_idx)
            if end_idx == -1:
                return text[start_idx:].strip()
            return text[start_idx:end_idx].strip()
        else:
            return text[start_idx:].strip()

    def apply_modifications(self, preview_id: str) -> Dict[str, Any]:
        """
        Applica modifiche previewed a file .pbix

        Args:
            preview_id: ID preview da interpret_command()

        Returns:
            {
                "success": bool,
                "report_path": str,
                "changes_applied": int,
                "backup_path": str | None,
                "error": str | None
            }
        """
        # 1. Recupera preview
        if preview_id not in _modification_previews:
            raise ValueError(f"Preview ID {preview_id} not found or expired")

        preview = _modification_previews[preview_id]
        report_path = preview["report_path"]
        dax_code = preview["dax_code"]
        measure_name = preview["measure_name"]

        # 2. Backup file .pbix
        backup_path = None
        if settings.mcp_powerbi_backup_enabled:
            try:
                backup_path = self._backup_report(report_path)
                logger.info(f"Backup created: {backup_path}")
            except Exception as e:
                logger.warning(f"Backup failed: {e}")

        # 3. Applica modifiche tramite MCP
        try:
            result = powerbi_mcp_client.add_measure(
                report_path=report_path,
                measure_name=measure_name,
                dax_expression=dax_code,
                table_name="orders"
            )

            if not result.get("success", False):
                raise Exception(result.get("message", "MCP add_measure failed"))

            logger.info(f"Modifications applied: {report_path}, measure={measure_name}")

            # 4. Cleanup preview
            del _modification_previews[preview_id]

            return {
                "success": True,
                "report_path": report_path,
                "changes_applied": 1,
                "backup_path": backup_path,
                "error": None
            }

        except Exception as e:
            logger.error(f"Apply modifications error: {e}")

            # Rollback se backup disponibile
            if backup_path and Path(backup_path).exists():
                try:
                    shutil.copy2(backup_path, report_path)
                    logger.info(f"Rollback applied: restored from {backup_path}")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")

            return {
                "success": False,
                "report_path": report_path,
                "changes_applied": 0,
                "backup_path": backup_path,
                "error": str(e)
            }

    def _backup_report(self, report_path: str) -> str:
        """
        Crea backup file .pbix

        Returns:
            Path file backup (.pbix.bak.TIMESTAMP)
        """
        report_path_obj = Path(report_path)

        if not report_path_obj.exists():
            raise FileNotFoundError(f"Report not found: {report_path}")

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{report_path}.bak.{timestamp}"

        shutil.copy2(report_path, backup_path)

        return backup_path


# Factory
def create_powerbi_service(llm_provider: str = "claude") -> PowerBIService:
    """Factory PowerBIService"""
    return PowerBIService(llm_provider=llm_provider)
```

---

### Area 4: API Endpoints Power BI

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\api\powerbi.py`

```python
"""
Power BI API endpoints
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal

from app.services.powerbi_service import create_powerbi_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/powerbi", tags=["powerbi"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class PowerBICommandRequest(BaseModel):
    """Request Power BI command"""
    command: str = Field(..., min_length=1, max_length=500)
    report_path: str = Field(..., description="Path file .pbix")
    llm_provider: Literal["claude", "azure"] = "claude"
    auto_apply: bool = Field(False, description="Applica automaticamente senza conferma")


class PowerBICommandResponse(BaseModel):
    """Response Power BI command"""
    success: bool
    preview_id: str
    interpretation: str
    dax_code: Optional[str]
    changes: List[Dict[str, Any]]
    validation: Dict[str, Any]


class ApplyModificationsResponse(BaseModel):
    """Response apply modifications"""
    success: bool
    report_path: str
    changes_applied: int
    backup_path: Optional[str]
    error: Optional[str]


class ReportInfo(BaseModel):
    """Power BI report info"""
    file_name: str
    file_path: str
    size_bytes: int
    last_modified: str


class ListReportsResponse(BaseModel):
    """Response list reports"""
    reports: List[ReportInfo]


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/reports", response_model=ListReportsResponse)
async def list_reports():
    """
    Lista report Power BI (.pbix) disponibili in workspace

    **Use case:** Frontend mostra lista report per selezione utente
    """
    try:
        powerbi_service = create_powerbi_service()
        reports = powerbi_service.list_reports()

        return ListReportsResponse(
            reports=[ReportInfo(**r) for r in reports]
        )

    except Exception as e:
        logger.error(f"List reports error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/command", response_model=PowerBICommandResponse)
async def power_bi_command(request: PowerBICommandRequest):
    """
    Esegui comando NL su report Power BI (text-to-DAX)

    **Workflow:**
    1. Interpreta comando NL
    2. Genera DAX code via LLM
    3. Valida sintassi DAX
    4. Ritorna preview modifiche

    **Se auto_apply=True:** applica direttamente (skip conferma)
    **Se auto_apply=False:** ritorna preview_id per conferma manuale

    **Performance target:** < 15s
    """
    try:
        powerbi_service = create_powerbi_service(llm_provider=request.llm_provider)

        # Interpreta comando e genera preview
        result = powerbi_service.interpret_command(
            command=request.command,
            report_path=request.report_path
        )

        # Se auto_apply=True, applica immediatamente
        if request.auto_apply and result["success"]:
            apply_result = powerbi_service.apply_modifications(result["preview_id"])

            if not apply_result["success"]:
                logger.warning(f"Auto-apply failed: {apply_result['error']}")
                # Continue con preview (user può confermare manualmente)

        return PowerBICommandResponse(**result)

    except Exception as e:
        logger.error(f"Power BI command error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply/{preview_id}", response_model=ApplyModificationsResponse)
async def apply_modifications(preview_id: str):
    """
    Applica modifiche previewed a file .pbix

    **Use case:** User visualizza preview DAX, clicca "Conferma" → chiamata a questo endpoint

    **Workflow:**
    1. Recupera preview da storage
    2. Backup file .pbix
    3. Applica modifiche via MCP Power BI
    4. Rollback automatico se errore
    """
    try:
        powerbi_service = create_powerbi_service()

        result = powerbi_service.apply_modifications(preview_id=preview_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return ApplyModificationsResponse(**result)

    except ValueError as e:
        # Preview ID non trovato o expired
        logger.error(f"Apply modifications error: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Apply modifications error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

**Aggiornare `main.py`:**

```python
# In backend/app/main.py, aggiungere:

from app.api import powerbi
from app.services.powerbi_mcp_manager import powerbi_mcp_client

# Lifecycle events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== DATACHAT BI PLATFORM STARTUP ===")

    # Avvia MCP servers
    mcp_postgres_client.start()
    powerbi_mcp_client.start()  # NUOVO

    logger.info("MCP servers started")

    yield

    # Shutdown
    logger.info("=== SHUTDOWN ===")
    mcp_postgres_client.shutdown()
    powerbi_mcp_client.shutdown()  # NUOVO

# Include router
app.include_router(powerbi.router)
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `mcp-config/powerbi-config.json` | Creare | Configurazione MCP Power BI server |
| `backend/app/services/powerbi_mcp_manager.py` | Creare | Client MCP Power BI (subprocess + JSON-RPC) |
| `backend/app/services/powerbi_service.py` | Creare | Text-to-DAX, automazione report, backup |
| `backend/app/api/powerbi.py` | Creare | API endpoints `/api/powerbi/*` |
| `backend/app/main.py` | Modificare | Lifecycle Power BI MCP server, include router |
| `.env` | Modificare | Aggiungere `MCP_POWERBI_WORKSPACE_PATH` |
| `C:\Users\TF536AC\PowerBI\Reports\Superstore_Test.pbix` | Creare | File .pbix test con Power BI Desktop |

## Dipendenze da Installare

### MCP Power BI Server (Node.js)

```bash
# Installazione globale
npm install -g @microsoft/powerbi-modeling-mcp

# Verificare
powerbi-modeling-mcp --help
```

### Backend (Python)

Nessuna nuova dipendenza Python necessaria.

## Variabili d'Ambiente

Aggiungere a `.env`:

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `MCP_POWERBI_WORKSPACE_PATH` | Path cartella con file .pbix | `C:/Users/TF536AC/PowerBI/Reports` |
| `MCP_POWERBI_BACKUP_ENABLED` | Abilita backup automatico .pbix | `true` |

## Criteri di Completamento

- [ ] MCP Power BI Modeling server installato (`powerbi-modeling-mcp --help` funziona)
- [ ] Directory workspace Power BI creata con almeno 1 file .pbix test
- [ ] File .pbix test contiene tabella `orders` e almeno 1 misura base
- [ ] `powerbi_mcp_manager.py` creato, subprocess MCP comunicazione funziona
- [ ] `powerbi_service.py` creato con text-to-DAX generation
- [ ] Endpoint `/api/powerbi/reports` lista file .pbix correttamente
- [ ] Endpoint `/api/powerbi/command` genera DAX e preview modifiche
- [ ] Endpoint `/api/powerbi/apply/{id}` applica modifiche a .pbix
- [ ] Backup automatico .pbix funziona (crea file `.bak.TIMESTAMP`)
- [ ] Rollback automatico funziona in caso errore applicazione
- [ ] Test workflow completo: command → preview → apply → verify in Power BI Desktop
- [ ] DAX validation MCP funziona (sintassi corretta passa, errata fallisce)

## Test di Verifica

### Test 1: MCP Power BI Server Startup

```bash
# Avviare backend
bash scripts/start_backend.sh

# Verificare log startup:
# INFO: MCP Power BI server avviato: workspace=C:/Users/.../PowerBI/Reports
```

### Test 2: List Reports

```bash
curl http://localhost:8000/api/powerbi/reports

# Output atteso:
# {
#   "reports": [
#     {
#       "file_name": "Superstore_Test.pbix",
#       "file_path": "C:/Users/.../Superstore_Test.pbix",
#       "size_bytes": 123456,
#       "last_modified": "2026-02-17T10:00:00"
#     }
#   ]
# }
```

### Test 3: Text-to-DAX Generation

```bash
curl -X POST http://localhost:8000/api/powerbi/command \
  -H "Content-Type: application/json" \
  -d '{
    "command": "Aggiungi una misura DAX chiamata Vendite YTD che calcola le vendite da inizio anno",
    "report_path": "C:/Users/TF536AC/PowerBI/Reports/Superstore_Test.pbix",
    "llm_provider": "claude",
    "auto_apply": false
  }'

# Output atteso:
# {
#   "success": true,
#   "preview_id": "abc-123-...",
#   "interpretation": "Creerò una misura DAX che calcola le vendite cumulative dall'inizio dell'anno...",
#   "dax_code": "SalesYTD = TOTALYTD(SUM(orders[sales]), orders[order_date])",
#   "changes": [
#     {
#       "type": "measure",
#       "action": "create",
#       "details": {
#         "measure_name": "SalesYTD",
#         "dax_expression": "TOTALYTD(...)",
#         "table": "orders"
#       }
#     }
#   ],
#   "validation": {
#     "valid": true,
#     "errors": []
#   }
# }

# Salvare preview_id per test successivo
```

### Test 4: Apply Modifications

```bash
PREVIEW_ID="abc-123-..."  # Da test 3

curl -X POST "http://localhost:8000/api/powerbi/apply/$PREVIEW_ID"

# Output atteso:
# {
#   "success": true,
#   "report_path": "C:/Users/.../Superstore_Test.pbix",
#   "changes_applied": 1,
#   "backup_path": "C:/Users/.../Superstore_Test.pbix.bak.20260217_103000",
#   "error": null
# }
```

### Test 5: Verify in Power BI Desktop

```bash
# 1. Aprire Power BI Desktop
# 2. File → Open → Superstore_Test.pbix
# 3. Navigare a Modeling → Measures
# 4. Verificare misura "SalesYTD" presente
# 5. Visualizzare DAX expression → deve matchare codice generato
# 6. (Opzionale) Aggiungere visual con SalesYTD per verificare funzionamento
```

### Test 6: Backup Verification

```bash
# Verificare file backup creato
ls -lh "C:/Users/TF536AC/PowerBI/Reports/*.bak.*"

# Output atteso: file .pbix.bak.TIMESTAMP con size uguale a .pbix originale
```

### Test 7: DAX Validation

```bash
# Test DAX sintatticamente errato
curl -X POST http://localhost:8000/api/powerbi/command \
  -H "Content-Type: application/json" \
  -d '{
    "command": "Crea misura con DAX invalido SUM(",
    "report_path": "C:/Users/.../Superstore_Test.pbix",
    "llm_provider": "claude"
  }' | jq '.validation'

# Output atteso:
# {
#   "valid": false,
#   "errors": ["Syntax error: incomplete expression"]
# }
```

### Test 8: Rollback Test (Simulato)

```python
# Test rollback manuale (modificare powerbi_service.py temporaneamente per forzare errore)

# Backup prima del test
import shutil
shutil.copy2(
    "C:/Users/.../Superstore_Test.pbix",
    "C:/Users/.../Superstore_Test_SAFE_BACKUP.pbix"
)

# Forzare errore in add_measure (es. DAX invalido)
# Verificare log:
# ERROR: Apply modifications error: ...
# INFO: Rollback applied: restored from ...

# Verificare file .pbix non corrotto
# Aprire in Power BI Desktop → deve essere identico a pre-modifica
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **MCP subprocess management:** Stesso pattern di `mcp_manager.py` (stdio + JSON-RPC)
2. **Preview storage:** In-memory dict per POC (Redis per production multi-user)
3. **Backup strategy:** Sempre backup prima modify, rollback automatico on error
4. **LLM prompt engineering:** Schema formattato per context, temperatura bassa (0.2) per codice
5. **Error handling defensive:** MCP Power BI in preview, gestire graceful degradation

### Convenzioni Naming

- **DAX measures:** PascalCase (es. `SalesYTD`, `TotalProfit`)
- **Backup files:** `.pbix.bak.YYYYMMDD_HHMMSS`
- **Preview IDs:** UUID v4 string
- **Change types:** `"measure"`, `"column"`, `"table"`, `"visual"`

### Errori Comuni da Evitare

1. **MCP Power BI non installato:** Verificare `npm list -g @microsoft/powerbi-modeling-mcp`
2. **Path Windows:** Usare forward slashes `/` in path (PowerShell compatible)
3. **File .pbix locked:** Power BI Desktop mantiene lock, chiudere prima modifiche
4. **DAX case-sensitive:** Nomi tabelle/colonne case-insensitive in DAX ma sensibili in schema
5. **Backup path collision:** Timestamp secondi può collidere, aggiungere milliseconds se necessario

### Troubleshooting

**Errore: "powerbi-modeling-mcp not found"**
```bash
# Verificare PATH npm global
npm config get prefix
# Aggiungere a PATH Windows se necessario

# Reinstallare
npm install -g @microsoft/powerbi-modeling-mcp
```

**Errore: "Report file locked"**
- Chiudere Power BI Desktop completamente
- Verificare processi `PBIDesktop.exe` in Task Manager
- Retry modifica

**DAX validation sempre fails**
- MCP Power BI preview potrebbe avere bug validation
- Testare DAX manualmente in Power BI Desktop
- Loggare DAX generato per debug

**Backup fails (permission denied)**
- Verificare write permissions su workspace directory
- Eseguire backend con privilegi adeguati

**MCP subprocess non risponde**
```python
# Debug MCP communication
import subprocess
proc = subprocess.Popen(["powerbi-modeling-mcp", "--workspace-path", "C:/..."], ...)
# Inviare test request manualmente
# Verificare stderr per errori
```

## Riferimenti

- **BRIEFING.md**: Sezione "MCP Servers" (Power BI Modeling), "Funzionalità 2 - Integrazione Power BI via MCP"
- **PRD.md**: Sezione 3.4 "Flusso 4: Automazione Power BI (Text-to-DAX)", Sezione 4.2 "API Endpoints Power BI Integration"
- **Fase precedente**: `phase-05-persistenza-chart-metadata-modifica-parametri.md` (backend completo)
- **Microsoft Power BI Modeling MCP**: https://github.com/microsoft/powerbi-modeling-mcp
- **DAX Reference**: https://learn.microsoft.com/en-us/dax/
- **Power BI Desktop**: https://powerbi.microsoft.com/desktop/
