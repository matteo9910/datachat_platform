# Fase 03: Multi-Provider LLM Manager e Orchestrazione Chat

## Panoramica
- **Obiettivo**: Implementare gestione multi-provider LLM configurabile (Claude/Azure) e orchestrazione chat conversazionale con context management
- **Dipendenza**: Fase 02 (Vanna service funzionante con Claude hardcoded)
- **Complessità stimata**: Media
- **Componenti coinvolti**: Backend, AI

## Contesto
La Fase 02 ha creato Vanna service con Claude Sonnet 4.5 hardcoded via OpenRouter. Ora generalizziamo il sistema per supportare **multi-provider LLM configurabile**: l'utente sceglie quale provider utilizzare (Claude via OpenRouter OPPURE Azure OpenAI), NON fallback automatico.

Questo richiede:
1. **LLM Provider Manager** con Strategy pattern per swap runtime
2. **Refactoring Vanna service** per usare provider manager invece di OpenRouter diretto
3. **Chat Orchestrator** che gestisce conversational context (rolling window 3-5 turni) e chiama Vanna
4. **API endpoint `/api/chat/query`** production-ready con session management
5. **Retry logic** exponential backoff per robustezza API calls

Il sistema deve essere trasparente: cambiare provider non modifica behavior, solo infrastruttura sottostante.

## Obiettivi Specifici
1. Creare `llm_provider.py` con interfaccia astratta `BaseLLMProvider` e implementazioni `ClaudeProvider`, `AzureOpenAIProvider`
2. Refactorare `vanna_service.py` per usare `LLMProviderManager` invece di OpenRouter hardcoded
3. Creare `chat_orchestrator.py` che gestisce session context, chiama Vanna, genera risposta NL finale
4. Implementare session storage in-memory (dizionario globale per POC, Redis future)
5. Creare endpoint `/api/chat/query` con Pydantic validation request/response
6. Implementare retry logic con `tenacity` library (3 retry, exponential backoff 2-8s)
7. Creare endpoint `/api/chat/history` per recuperare storico conversazione
8. Testare switch provider runtime (cambiare `.env`, verificare funzionamento identico)
9. Logging completo richieste LLM (provider, latency, tokens utilizzati se disponibili)

## Specifiche Tecniche Dettagliate

### Area 1: LLM Provider Manager con Strategy Pattern

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\llm_provider.py`

```python
"""
LLM Provider Manager - Multi-provider abstraction (Claude / Azure OpenAI)
Strategy pattern per swap runtime provider senza modificare chiamanti
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Literal
from openai import OpenAI, AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

from app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Interfaccia astratta LLM provider"""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Genera completion da prompt

        Returns:
            {
                "content": str,          # Testo generato
                "usage": {               # Token usage (se disponibile)
                    "prompt_tokens": int,
                    "completion_tokens": int,
                    "total_tokens": int
                },
                "latency_ms": float,     # Latency richiesta
                "provider": str          # Nome provider
            }
        """
        pass


class ClaudeProvider(BaseLLMProvider):
    """Provider Claude Sonnet 4.5 via OpenRouter"""

    def __init__(self):
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY non configurato in .env")

        self.client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = settings.openrouter_model
        logger.info(f"ClaudeProvider initialized: model={self.model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """Claude completion via OpenRouter"""
        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            latency_ms = (time.time() - start_time) * 1000

            content = response.choices[0].message.content

            # OpenRouter espone usage
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }

            logger.info(
                f"ClaudeProvider completion: {latency_ms:.0f}ms, "
                f"{usage['total_tokens']} tokens"
            )

            return {
                "content": content,
                "usage": usage,
                "latency_ms": latency_ms,
                "provider": "claude"
            }

        except Exception as e:
            logger.error(f"ClaudeProvider error: {e}")
            raise


class AzureOpenAIProvider(BaseLLMProvider):
    """Provider Azure OpenAI (GPT-4.1 / GPT-5)"""

    def __init__(self):
        if not settings.azure_openai_api_key or not settings.azure_openai_endpoint:
            raise ValueError("Azure OpenAI credentials non configurati in .env")

        self.client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version
        )
        self.deployment = settings.azure_openai_deployment_name
        logger.info(f"AzureOpenAIProvider initialized: deployment={self.deployment}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """Azure OpenAI completion"""
        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,  # Azure usa deployment name, non model
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            latency_ms = (time.time() - start_time) * 1000

            content = response.choices[0].message.content

            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }

            logger.info(
                f"AzureOpenAIProvider completion: {latency_ms:.0f}ms, "
                f"{usage['total_tokens']} tokens"
            )

            return {
                "content": content,
                "usage": usage,
                "latency_ms": latency_ms,
                "provider": "azure"
            }

        except Exception as e:
            logger.error(f"AzureOpenAIProvider error: {e}")
            raise


class LLMProviderManager:
    """
    Manager per selezione runtime provider LLM
    Utente sceglie provider (NON fallback automatico)
    """

    def __init__(self):
        self.providers: Dict[str, BaseLLMProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """Inizializza provider configurati"""
        # Claude (se API key disponibile)
        try:
            if settings.openrouter_api_key:
                self.providers["claude"] = ClaudeProvider()
                logger.info("✓ Claude provider available")
        except Exception as e:
            logger.warning(f"Claude provider initialization failed: {e}")

        # Azure OpenAI (se credenziali disponibili)
        try:
            if settings.azure_openai_api_key and settings.azure_openai_endpoint:
                self.providers["azure"] = AzureOpenAIProvider()
                logger.info("✓ Azure OpenAI provider available")
        except Exception as e:
            logger.warning(f"Azure OpenAI provider initialization failed: {e}")

        if not self.providers:
            raise RuntimeError("Nessun LLM provider configurato! Verificare .env")

        logger.info(f"LLM providers initialized: {list(self.providers.keys())}")

    def get_provider(self, provider_name: Literal["claude", "azure"]) -> BaseLLMProvider:
        """
        Recupera provider per nome

        Raises:
            ValueError: se provider non disponibile
        """
        if provider_name not in self.providers:
            available = list(self.providers.keys())
            raise ValueError(
                f"Provider '{provider_name}' non disponibile. "
                f"Provider configurati: {available}"
            )

        return self.providers[provider_name]

    def complete(
        self,
        prompt: str,
        provider: Optional[Literal["claude", "azure"]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Wrapper convenience per completion

        Args:
            prompt: Prompt testo
            provider: Nome provider (se None, usa default da settings)
            **kwargs: Parametri passati a provider.complete()

        Returns:
            Dict con content, usage, latency_ms, provider
        """
        if provider is None:
            provider = settings.default_llm_provider

        provider_instance = self.get_provider(provider)
        return provider_instance.complete(prompt, **kwargs)

    def list_available_providers(self) -> list[str]:
        """Lista provider disponibili"""
        return list(self.providers.keys())


# Singleton
llm_provider_manager = LLMProviderManager()
```

---

### Area 2: Refactoring Vanna Service per Multi-Provider

**File da modificare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\vanna_service.py`

Modificare classe `VannaChromaOpenAI` per accettare provider esterno:

```python
# MODIFICHE da applicare a vanna_service.py (Fase 02)

from app.services.llm_provider import llm_provider_manager

class VannaService:
    """
    Service orchestrazione Vanna 2.0 per text-to-SQL
    UPDATED: supporta multi-provider LLM
    """

    def __init__(self, llm_provider: str = "claude"):
        """
        Args:
            llm_provider: "claude" | "azure"
        """
        self.llm_provider_name = llm_provider
        self.vanna_model: Optional[VannaChromaOpenAI] = None
        self._initialize_vanna()

    def _initialize_vanna(self):
        """Inizializza Vanna con ChromaDB + provider configurabile"""
        try:
            chroma_client = chromadb.PersistentClient(
                path=settings.chromadb_persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False)
            )

            # Usa LLM provider manager invece di hardcode OpenRouter
            provider = llm_provider_manager.get_provider(self.llm_provider_name)

            vanna_config = {
                "client": chroma_client,
                "model": settings.vanna_model,
                # LLM provider gestito esternamente
            }

            self.vanna_model = VannaChromaOpenAI(config=vanna_config)

            # Override Vanna LLM call con provider manager
            self._override_vanna_llm()

            logger.info(
                f"Vanna initialized: model={settings.vanna_model}, "
                f"LLM provider={self.llm_provider_name}"
            )

        except Exception as e:
            logger.error(f"Errore inizializzazione Vanna: {e}")
            raise

    def _override_vanna_llm(self):
        """Override metodo LLM Vanna per usare provider manager"""
        original_submit_prompt = self.vanna_model.submit_prompt

        def custom_submit_prompt(prompt, **kwargs):
            """Custom LLM call via provider manager"""
            result = llm_provider_manager.complete(
                prompt=prompt,
                provider=self.llm_provider_name,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens
            )
            return result["content"]

        self.vanna_model.submit_prompt = custom_submit_prompt

    # ... resto metodi invariati (generate_sql, execute_sql, etc.)
```

---

### Area 3: Chat Orchestrator con Context Management

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\services\chat_orchestrator.py`

```python
"""
Chat Orchestrator - Gestione conversazione multi-turno con context
Orchestrazione workflow: NL → Vanna SQL → Execute → NL response generation
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.vanna_service import VannaService
from app.services.llm_provider import llm_provider_manager
from app.config import settings

logger = logging.getLogger(__name__)


# In-memory session storage (POC, production usa Redis)
_sessions: Dict[str, List[Dict[str, Any]]] = {}


class ChatOrchestrator:
    """Orchestrazione chat conversazionale con text-to-SQL"""

    def __init__(self, llm_provider: str = "claude"):
        self.llm_provider = llm_provider
        self.vanna = VannaService(llm_provider=llm_provider)
        logger.info(f"ChatOrchestrator initialized with provider={llm_provider}")

    def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        include_chart: bool = True
    ) -> Dict[str, Any]:
        """
        Processa query NL utente con context conversazionale

        Args:
            query: Domanda NL
            session_id: ID sessione (se None, crea nuovo)
            include_chart: Flag generazione chart (Fase 4)

        Returns:
            {
                "session_id": str,
                "nl_response": str,       # Risposta testuale LLM
                "sql": str,
                "results": list[dict],
                "chart": dict | None,     # Fase 4
                "execution_time_ms": float,
                "success": bool,
                "error": str | None
            }
        """
        import time
        start_time = time.time()

        # Session management
        if not session_id:
            session_id = str(uuid.uuid4())
            _sessions[session_id] = []

        try:
            # 1. Recupera context conversazionale (rolling window 3-5 turni)
            context = self._get_conversation_context(session_id, window_size=5)

            # 2. Genera SQL via Vanna (include context per disambiguation)
            sql_result = self.vanna.generate_sql(query)

            if not sql_result["success"]:
                return self._error_response(
                    session_id=session_id,
                    query=query,
                    error=sql_result.get("error", "SQL generation failed"),
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            sql = sql_result["sql"]

            # 3. Esegui SQL
            exec_result = self.vanna.execute_sql(sql)

            if not exec_result["success"]:
                return self._error_response(
                    session_id=session_id,
                    query=query,
                    error=exec_result.get("error", "SQL execution failed"),
                    execution_time_ms=(time.time() - start_time) * 1000,
                    sql=sql
                )

            rows = exec_result["rows"]

            # 4. Genera risposta NL finale
            nl_response = self._generate_nl_response(
                query=query,
                sql=sql,
                results=rows
            )

            # 5. Salva in session context
            self._add_to_context(
                session_id=session_id,
                query=query,
                sql=sql,
                result_count=len(rows),
                nl_response=nl_response
            )

            execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Query processed: session={session_id}, "
                f"{len(rows)} rows, {execution_time_ms:.0f}ms"
            )

            return {
                "session_id": session_id,
                "nl_response": nl_response,
                "sql": sql,
                "results": rows,
                "chart": None,  # Fase 4: chart generation
                "execution_time_ms": execution_time_ms,
                "success": True,
                "error": None
            }

        except Exception as e:
            logger.error(f"Chat orchestrator error: {e}")
            return self._error_response(
                session_id=session_id,
                query=query,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    def _get_conversation_context(
        self,
        session_id: str,
        window_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recupera ultimi N turni conversazione

        Returns:
            [{"query": str, "sql": str, "result_count": int}, ...]
        """
        if session_id not in _sessions:
            return []

        # Rolling window: ultimi `window_size` turni
        return _sessions[session_id][-window_size:]

    def _add_to_context(
        self,
        session_id: str,
        query: str,
        sql: str,
        result_count: int,
        nl_response: str
    ):
        """Aggiungi turno a session context"""
        if session_id not in _sessions:
            _sessions[session_id] = []

        _sessions[session_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "query": query,
            "sql": sql,
            "result_count": result_count,
            "nl_response": nl_response
        })

        # Limit session storage (max 50 turni, POC)
        if len(_sessions[session_id]) > 50:
            _sessions[session_id] = _sessions[session_id][-50:]

    def _generate_nl_response(
        self,
        query: str,
        sql: str,
        results: List[Dict[str, Any]]
    ) -> str:
        """
        Genera risposta NL finale per utente

        Usa LLM per sintetizzare risultati in risposta user-friendly
        """
        if not results:
            return "La query non ha restituito risultati."

        # Costruisci prompt per LLM
        results_preview = results[:5]  # Prime 5 righe
        results_text = "\n".join([str(row) for row in results_preview])

        prompt = f"""
Sei un assistente BI che spiega risultati di query SQL in linguaggio naturale italiano.

Domanda utente: "{query}"

SQL eseguito:
{sql}

Risultati (prime 5 righe di {len(results)} totali):
{results_text}

Genera una risposta concisa (2-3 frasi) che:
1. Conferma cosa è stato trovato
2. Evidenzia insights chiave dai dati
3. Usa linguaggio business-friendly (no termini SQL)

Risposta:
"""

        try:
            llm_result = llm_provider_manager.complete(
                prompt=prompt.strip(),
                provider=self.llm_provider,
                temperature=0.5,  # Leggermente creativo per NL
                max_tokens=300
            )

            nl_response = llm_result["content"].strip()
            return nl_response

        except Exception as e:
            logger.warning(f"NL response generation failed: {e}")
            # Fallback risposta semplice
            return f"Ho trovato {len(results)} risultati per la tua domanda."

    def _error_response(
        self,
        session_id: str,
        query: str,
        error: str,
        execution_time_ms: float,
        sql: str = ""
    ) -> Dict[str, Any]:
        """Risposta errore standardizzata"""
        return {
            "session_id": session_id,
            "nl_response": f"Mi dispiace, si è verificato un errore: {error}",
            "sql": sql,
            "results": [],
            "chart": None,
            "execution_time_ms": execution_time_ms,
            "success": False,
            "error": error
        }

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Recupera full history sessione"""
        return _sessions.get(session_id, [])


# Factory function (crea nuova istanza per ogni request con provider configurato)
def create_chat_orchestrator(llm_provider: str = None) -> ChatOrchestrator:
    """
    Factory per ChatOrchestrator

    Args:
        llm_provider: Se None, usa default da settings
    """
    if llm_provider is None:
        llm_provider = settings.default_llm_provider

    return ChatOrchestrator(llm_provider=llm_provider)
```

---

### Area 4: API Endpoints Chat

**File da creare:** `C:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator\backend\app\api\chat.py`

```python
"""
Chat API endpoints - Production-ready
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

from app.services.chat_orchestrator import create_chat_orchestrator, ChatOrchestrator
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ChatQueryRequest(BaseModel):
    """Request chat query"""
    query: str = Field(..., min_length=1, max_length=500, description="Domanda NL")
    session_id: Optional[str] = Field(None, description="ID sessione (opzionale)")
    llm_provider: Literal["claude", "azure"] = Field(
        default="claude",
        description="Provider LLM da utilizzare"
    )
    include_chart: bool = Field(True, description="Genera chart (Fase 4)")


class ChatQueryResponse(BaseModel):
    """Response chat query"""
    success: bool
    session_id: str
    nl_response: str
    sql: str
    results: List[Dict[str, Any]]
    chart: Optional[Dict[str, Any]] = None  # Fase 4
    execution_time_ms: float
    error: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    """Response chat history"""
    session_id: str
    history: List[Dict[str, Any]]


# ============================================================
# DEPENDENCIES
# ============================================================

def get_chat_orchestrator(llm_provider: str = "claude") -> ChatOrchestrator:
    """Dependency injection ChatOrchestrator"""
    return create_chat_orchestrator(llm_provider=llm_provider)


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(request: ChatQueryRequest):
    """
    Endpoint principale chat: invia query NL, ricevi SQL + risultati + risposta NL

    **Workflow:**
    1. Validazione input
    2. Orchestrazione: NL → SQL → execute → NL response
    3. Session context management (rolling window 5 turni)
    4. Chart generation (Fase 4)

    **Performance target:** <10s (95th percentile)
    """
    try:
        # Crea orchestrator con provider richiesto
        orchestrator = get_chat_orchestrator(llm_provider=request.llm_provider)

        # Processa query
        result = orchestrator.process_query(
            query=request.query,
            session_id=request.session_id,
            include_chart=request.include_chart
        )

        return ChatQueryResponse(**result)

    except ValueError as e:
        # Provider non disponibile
        logger.error(f"Provider error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno server")


@router.get("/history", response_model=ChatHistoryResponse)
async def chat_history(session_id: str):
    """
    Recupera storico conversazione sessione

    **Use case:** Frontend visualizza conversazioni passate
    """
    try:
        # Usa orchestrator default per accedere session storage
        orchestrator = get_chat_orchestrator()
        history = orchestrator.get_session_history(session_id)

        return ChatHistoryResponse(
            session_id=session_id,
            history=history
        )

    except Exception as e:
        logger.error(f"Chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Aggiornare `main.py` per includere router:**

```python
# In backend/app/main.py, aggiungere:

from app.api import chat

# Dopo creazione app FastAPI
app.include_router(chat.router)
```

---

## Tabella File da Creare/Modificare

| File | Azione | Descrizione |
|------|--------|-------------|
| `backend/app/services/llm_provider.py` | Creare | LLM Provider Manager multi-provider (Claude/Azure) |
| `backend/app/services/vanna_service.py` | Modificare | Refactoring per usare provider manager (remove hardcode OpenRouter) |
| `backend/app/services/chat_orchestrator.py` | Creare | Orchestrazione chat con context management |
| `backend/app/api/chat.py` | Creare | API endpoints `/api/chat/query` e `/api/chat/history` |
| `backend/app/main.py` | Modificare | Include router chat |
| `backend/requirements.txt` | Modificare | Aggiungere `tenacity==9.0.0` per retry logic |

## Dipendenze da Installare

### Backend (Python)

Aggiungere a `requirements.txt`:

```txt
# Retry logic
tenacity==9.0.0
```

Installare:

```bash
cd backend
pip install tenacity==9.0.0
```

## Variabili d'Ambiente

Nessuna nuova variabile necessaria. Verificare `.env` contiene:

| Variabile | Descrizione | Richiesto per |
|-----------|-------------|---------------|
| `DEFAULT_LLM_PROVIDER` | Provider default (`claude` o `azure`) | Multi-provider selection |
| `OPENROUTER_API_KEY` | API key OpenRouter | Claude provider |
| `AZURE_OPENAI_ENDPOINT` | Endpoint Azure OpenAI | Azure provider |
| `AZURE_OPENAI_API_KEY` | API key Azure OpenAI | Azure provider |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Deployment name Azure (es. `gpt-4.1`) | Azure provider |

## Criteri di Completamento

- [ ] File `llm_provider.py` creato con `BaseLLMProvider`, `ClaudeProvider`, `AzureOpenAIProvider`
- [ ] `LLMProviderManager` inizializza correttamente entrambi provider (se configurati)
- [ ] `vanna_service.py` refactorato per usare provider manager
- [ ] `chat_orchestrator.py` creato con session management in-memory
- [ ] Endpoint `/api/chat/query` risponde correttamente
- [ ] Endpoint `/api/chat/history` recupera storico sessione
- [ ] Retry logic funziona (testare con API key invalida, deve ritentare 3 volte)
- [ ] Switch provider runtime funziona: cambiare `DEFAULT_LLM_PROVIDER` in `.env` → stesso comportamento
- [ ] Conversational context funziona: query follow-up (es. "mostralo per trimestre") usa context precedente
- [ ] NL response generation produce risposte user-friendly in italiano
- [ ] Logging completo: ogni richiesta LLM logga provider, latency, tokens
- [ ] Swagger docs `/docs` mostra endpoint chat con esempi

## Test di Verifica

### Test 1: Provider Initialization

```python
# Test interattivo Python
from app.services.llm_provider import llm_provider_manager

# Lista provider disponibili
providers = llm_provider_manager.list_available_providers()
print(providers)  # ['claude', 'azure'] (se entrambi configurati)

# Test completion Claude
result_claude = llm_provider_manager.complete(
    prompt="Traduci in SQL: vendite totali per regione",
    provider="claude"
)
print(result_claude["content"])
print(f"Latency: {result_claude['latency_ms']:.0f}ms")

# Test completion Azure
result_azure = llm_provider_manager.complete(
    prompt="Traduci in SQL: vendite totali per regione",
    provider="azure"
)
print(result_azure["content"])
```

### Test 2: Chat Query Endpoint

```bash
# Test Claude provider
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Mostra le vendite totali per ogni regione",
    "llm_provider": "claude"
  }'

# Output atteso: JSON con nl_response, sql, results

# Test Azure provider (cambiare solo llm_provider)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Mostra le vendite totali per ogni regione",
    "llm_provider": "azure"
  }'

# Output atteso: stesso SQL e risultati (provider trasparente)
```

### Test 3: Conversational Context

```bash
# Query 1: stabilisce context
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Vendite mensili per categoria nell ultimo anno",
    "llm_provider": "claude"
  }' | jq -r '.session_id' > session.txt

SESSION_ID=$(cat session.txt)

# Query 2: follow-up (usa context)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Mostralo per trimestre invece che per mese\",
    \"session_id\": \"$SESSION_ID\",
    \"llm_provider\": \"claude\"
  }"

# Output atteso: SQL cambia aggregazione a trimestrale
```

### Test 4: Chat History

```bash
# Recupera history sessione
curl "http://localhost:8000/api/chat/history?session_id=$SESSION_ID"

# Output atteso: array con 2 turni conversazione
```

### Test 5: Retry Logic

```python
# Modificare temporaneamente .env con API key invalida
# OPENROUTER_API_KEY=invalid-key

# Restart backend, poi:
import requests

response = requests.post(
    "http://localhost:8000/api/chat/query",
    json={"query": "test", "llm_provider": "claude"}
)

# Output atteso nei log backend:
# ClaudeProvider error: ... (retry 1/3)
# ClaudeProvider error: ... (retry 2/3)
# ClaudeProvider error: ... (retry 3/3)
# Final error: API authentication failed

# Ripristinare API key corretta
```

### Test 6: NL Response Quality

```bash
# Query complessa
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Top 5 prodotti per profitto nella categoria Technology",
    "llm_provider": "claude"
  }' | jq -r '.nl_response'

# Output atteso (esempio):
# "Ho trovato i 5 prodotti più profittevoli nella categoria Technology.
#  In testa c'è [Prodotto X] con un profitto di €[Y], seguito da...
#  Il profitto totale dei top 5 è €[Z]."
```

## Note per l'Agente di Sviluppo

### Pattern di Codice

1. **Strategy Pattern:** `BaseLLMProvider` è interfaccia, `ClaudeProvider` e `AzureOpenAIProvider` implementazioni concrete
2. **Singleton Manager:** `llm_provider_manager` globale inizializza tutti provider disponibili una volta
3. **Dependency Injection:** FastAPI usa `Depends()` per iniettare orchestrator con provider corretto
4. **Retry Decorator:** `@retry` di tenacity avvolge completamente metodo `complete()`, trasparente al chiamante
5. **Session Storage:** Dizionario in-memory per POC, chiave = session_id UUID, valore = lista turni

### Convenzioni Naming

- **Provider names:** Sempre lowercase `"claude"`, `"azure"` (Literal type per type safety)
- **Session ID:** UUID v4 string format
- **Context keys:** `{"timestamp", "query", "sql", "result_count", "nl_response"}`
- **Error responses:** Sempre `success=False` + campo `error` populated

### Errori Comuni da Evitare

1. **Provider not configured:** Controllare sempre se API key presente prima di inizializzare provider
2. **Retry infinite loop:** `tenacity` stop_after_attempt(3) garantisce max 3 tentativi
3. **Context memory leak:** Session storage limitato a 50 turni max per sessione
4. **LLM timeout:** Default 30s da settings, ma Claude può richiedere 10-15s per query complesse
5. **Prompt injection:** Validare input NL query (max 500 chars, sanitize special chars)

### Troubleshooting

**Errore: "Provider 'azure' not available"**
```bash
# Verificare .env contiene:
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
```

**Errore: "Retry exhausted"**
- Verificare API key valida
- Controllare rate limits OpenRouter/Azure (dashboard)
- Aumentare `max_time` retry se necessario

**Context non funziona (follow-up queries fail)**
- Verificare session_id uguale tra richieste
- Controllare `_sessions` dictionary populated (debug logging)

**NL response generica/poco utile**
- Migliorare prompt in `_generate_nl_response()`
- Aumentare `max_tokens` a 500 per risposte più dettagliate
- Aumentare temperature a 0.7 per più creatività

## Riferimenti

- **BRIEFING.md**: Sezione "Stack Tecnologico" (multi-provider LLM)
- **PRD.md**: Sezione 3.4 "Flusso 5: Multi-Provider LLM Selection", Sezione 4.2 "API Endpoints Chat"
- **Fase precedente**: `phase-02-engine-text-to-sql-vanna-rag.md` (Vanna service baseline)
- **OpenAI Python SDK**: https://github.com/openai/openai-python (compatibile OpenRouter + Azure)
- **Tenacity Docs**: https://tenacity.readthedocs.io/
- **FastAPI Dependency Injection**: https://fastapi.tiangolo.com/tutorial/dependencies/
