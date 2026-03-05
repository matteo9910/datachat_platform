"""
Vanna Service IBRIDO - Combina Vanna RAG + MCP Server + Multi-Provider LLM

Architettura:
- Schema DB: DINAMICO via MCP (sempre aggiornato)
- Few-shot examples: ChromaDB (migliora accuracy)
- LLM: Multi-provider (Claude/Azure) via LLMProviderManager
- Esecuzione SQL: MCP Server (sicuro, read-only)
"""

import logging
import time
import os
from typing import Dict, Any, Optional, List

import httpx
from chromadb import Documents, EmbeddingFunction, Embeddings

from app.config import settings
from app.services.mcp_manager import mcp_postgres_client
from app.services.llm_provider import get_llm_provider_manager

logger = logging.getLogger(__name__)


class AzureOpenAIEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function per Azure OpenAI"""
    
    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint
        self.client = httpx.Client(timeout=60.0, verify=False)
        self._available = True
        # Test connectivity on init
        try:
            test_response = self.client.post(
                self.endpoint, 
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json={"input": ["test"]}
            )
            if test_response.status_code != 200:
                logger.warning(f"Azure Embeddings not available: {test_response.status_code} - {test_response.text[:200]}")
                self._available = False
        except Exception as e:
            logger.warning(f"Azure Embeddings not available: {e}")
            self._available = False
    
    def __call__(self, input: Documents) -> Embeddings:
        if not self._available:
            # Return zero vectors as fallback (ChromaDB will still work, just no semantic search)
            logger.warning("Using fallback zero embeddings (Azure not available)")
            return [[0.0] * 3072 for _ in input]  # text-embedding-3-large dimension
        
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        embeddings = []
        batch_size = 16
        for i in range(0, len(input), batch_size):
            batch = input[i:i+batch_size]
            try:
                response = self.client.post(self.endpoint, headers=headers, json={"input": batch})
                if response.status_code != 200:
                    logger.error(f"Embedding API error: {response.status_code}")
                    return [[0.0] * 3072 for _ in input]
                for item in response.json()["data"]:
                    embeddings.append(item["embedding"])
            except Exception as e:
                logger.error(f"Embedding request failed: {e}")
                return [[0.0] * 3072 for _ in input]
        
        return embeddings


class HybridVannaService:
    """
    Servizio Text-to-SQL IBRIDO con Multi-Provider LLM
    
    Combina:
    1. MCP Server: schema dinamico + esecuzione query
    2. ChromaDB: few-shot examples via RAG
    3. LLMProviderManager: supporta Claude e Azure OpenAI
    """

    def __init__(self, llm_provider: Optional[str] = None):
        """
        Args:
            llm_provider: "claude" | "azure" | None (usa default da settings)
        """
        self.llm_provider = llm_provider or settings.default_llm_provider
        self.chromadb_client = None
        self.sql_collection = None
        self.doc_collection = None
        self.embedding_function = None
        self._initialized = False
        self._initialize()

    def _initialize(self):
        """Inizializza ChromaDB per RAG"""
        try:
            import chromadb
            
            os.makedirs(settings.chromadb_persist_directory, exist_ok=True)
            
            # ChromaDB con Azure embeddings
            self.embedding_function = AzureOpenAIEmbeddingFunction(
                api_key=settings.azure_openai_api_key,
                endpoint=settings.azure_openai_embedding_endpoint
            )
            
            self.chromadb_client = chromadb.PersistentClient(path=settings.chromadb_persist_directory)
            
            # Collection per esempi SQL (question -> sql)
            self.sql_collection = self.chromadb_client.get_or_create_collection(
                name="sql_examples",
                embedding_function=self.embedding_function
            )
            
            # Collection per documentazione
            self.doc_collection = self.chromadb_client.get_or_create_collection(
                name="documentation",
                embedding_function=self.embedding_function
            )
            
            self._initialized = True
            logger.info(f"HybridVannaService initialized: ChromaDB + MCP + LLM provider={self.llm_provider}")
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            raise

    # =========================================================================
    # TRAINING METHODS (popolano ChromaDB)
    # =========================================================================
    
    def train_on_sql(self, question: str, sql: str):
        """Aggiunge coppia question->SQL a ChromaDB"""
        doc_id = f"sql_{hash(question + sql) % 10**8}"
        self.sql_collection.upsert(
            ids=[doc_id],
            documents=[question],
            metadatas=[{"sql": sql, "type": "sql_example"}]
        )
        logger.info(f"Trained SQL: {question[:50]}...")

    def train_on_documentation(self, documentation: str):
        """Aggiunge documentazione business a ChromaDB"""
        doc_id = f"doc_{hash(documentation) % 10**8}"
        self.doc_collection.upsert(
            ids=[doc_id],
            documents=[documentation],
            metadatas=[{"type": "documentation"}]
        )
        logger.info(f"Trained documentation: {len(documentation)} chars")

    # =========================================================================
    # SCHEMA METHODS (usano MCP - sempre aggiornati!)
    # =========================================================================
    
    def get_schema_from_mcp(self) -> str:
        """Ottiene schema LIVE dal database via MCP"""
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        return mcp_postgres_client.get_schema_ddl(schema="public")

    def get_tables_from_mcp(self) -> List[str]:
        """Lista tabelle via MCP"""
        if not mcp_postgres_client._connected:
            mcp_postgres_client.start()
        return mcp_postgres_client.list_tables(schema="public")

    # =========================================================================
    # RAG METHODS (recuperano esempi simili da ChromaDB)
    # =========================================================================
    
    def get_similar_examples(self, question: str, n_results: int = 5) -> List[Dict]:
        """Trova esempi SQL simili in ChromaDB"""
        results = self.sql_collection.query(
            query_texts=[question],
            n_results=n_results
        )
        
        examples = []
        if results and results["documents"] and results["metadatas"]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                examples.append({
                    "question": doc,
                    "sql": meta.get("sql", "")
                })
        return examples

    def get_relevant_documentation(self, question: str, n_results: int = 2) -> str:
        """Recupera documentazione rilevante da ChromaDB"""
        results = self.doc_collection.query(
            query_texts=[question],
            n_results=n_results
        )
        docs = []
        if results and results["documents"]:
            docs = results["documents"][0]
        return "\n\n".join(docs)

    # =========================================================================
    # SQL GENERATION (combina MCP schema + ChromaDB examples + LLM)
    # =========================================================================
    
    def generate_sql(self, question: str, llm_provider: Optional[str] = None, instructions: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Genera SQL con Chain-of-Thought reasoning strutturato.
        Usa il nuovo metodo che restituisce anche il ragionamento dettagliato.
        
        Args:
            question: Domanda NL
            llm_provider: Override provider (se None usa self.llm_provider)
            instructions: Optional list of instruction texts to inject into the prompt
        """
        # Usa sempre il metodo con reasoning
        return self.generate_sql_with_reasoning(question, llm_provider, instructions=instructions)

    def _build_messages_dynamic(self, question: str, schema: str, instructions: Optional[List[str]] = None) -> List[Dict]:
        """
        Costruisce i messages per l'LLM con CHAIN-OF-THOUGHT strutturato.
        Il modello deve ragionare esplicitamente prima di generare SQL.
        
        Args:
            question: User question
            schema: Database schema DDL
            instructions: Optional list of instruction texts to inject
        """
        
        # Build instructions block if any are provided
        instructions_block = ""
        if instructions:
            rules_text = "\n".join(f"- {inst}" for inst in instructions)
            instructions_block = f"""

=== SQL GENERATION RULES ===
The following rules and guidelines MUST be followed when generating SQL:
{rules_text}
"""

        system_message = f"""You are a SQL expert for PostgreSQL databases. Your task is to analyze user questions and generate accurate SQL queries.

=== DATABASE SCHEMA ===
The following is the ACTUAL schema of the connected database:

{schema}
{instructions_block}
=== YOUR TASK ===
For each question, you MUST think step-by-step and provide your reasoning in a structured JSON format.

=== OUTPUT FORMAT (JSON) ===
You MUST respond with ONLY a valid JSON object in this exact format:
{{
  "reasoning": {{
    "question_understanding": {{
      "original_question": "<the user's question>",
      "analysis_type": "<ranking|aggregation|time_series|comparison|lookup|distribution>",
      "what_user_wants": "<clear description of what the user is asking for>"
    }},
    "table_selection": {{
      "selected_table": "<main table name>",
      "why_this_table": "<explanation of why this table contains the needed data>",
      "join_tables": ["<other tables if JOIN needed>"]
    }},
    "column_selection": {{
      "metric_columns": ["<columns for calculations like SUM, COUNT>"],
      "dimension_columns": ["<columns for grouping>"],
      "filter_columns": ["<columns for WHERE conditions>"],
      "why_these_columns": "<explanation of column choices>"
    }},
    "query_logic": {{
      "aggregation_function": "<SUM|COUNT|AVG|MAX|MIN|none>",
      "grouping_needed": true|false,
      "grouping_columns": ["<columns for GROUP BY>"],
      "ordering": "<ASC|DESC|none>",
      "ordering_reason": "<why this order>",
      "limit_needed": true|false,
      "limit_value": <number or null>,
      "filters": ["<any WHERE conditions>"]
    }},
    "thought_process": [
      "<Step 1: Clear description of first reasoning step>",
      "<Step 2: Clear description of second reasoning step>",
      "<Step 3: Continue with more steps as needed>",
      "<Final step: Conclusion before generating SQL>"
    ]
  }},
  "sql": "<the complete SQL query>"
}}

IMPORTANT for thought_process:
- Write 4-7 detailed reasoning steps, each with a TITLE and DESCRIPTION
- Format each step as: "TITLE: Description with details"
- Use the user's language (Italian if question is in Italian)
- Be specific: mention actual table names, column names, and reasoning

Example thought_process for "confronta i prezzi medi per categoria":
[
  "Identificazione Tabelle e Colonne Rilevanti: Per confrontare i prezzi medi dei prodotti per categoria, utilizzo la tabella public_dim_products. Le colonne rilevanti sono category_name per la categoria e product_price per il prezzo.",
  "Raggruppamento per Categoria: E' necessario raggruppare i dati per category_name per calcolare il prezzo medio di ogni categoria.",
  "Calcolo Prezzo Medio: Per ogni gruppo (categoria), calcolo la media (AVG) della colonna product_price.",
  "Nessun Filtro Temporale Specificato: L'utente non ha specificato un periodo temporale, quindi utilizzo tutti i dati disponibili.",
  "Ordinamento Risultati: Ordino i risultati per prezzo medio in ordine decrescente per evidenziare le categorie con prezzi piu alti."
]

=== RULES ===
1. Use ONLY tables and columns from the schema above
2. Use PostgreSQL syntax
3. Think carefully about each step before writing SQL
4. The JSON must be valid and parseable
5. Do NOT include markdown code blocks, return raw JSON only"""

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": question}
        ]
        
        return messages
    
    def generate_sql_with_reasoning(self, question: str, llm_provider: Optional[str] = None, instructions: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Genera SQL con reasoning chain-of-thought strutturato.
        Restituisce sia la query che il ragionamento dettagliato.
        
        Args:
            question: User NL question
            llm_provider: Override provider
            instructions: Optional instruction texts to inject into prompt
        """
        import json
        provider = llm_provider or self.llm_provider
        
        try:
            schema_ddl = self.get_schema_from_mcp()
            messages = self._build_messages_dynamic(question, schema_ddl, instructions=instructions)
            
            llm_manager = get_llm_provider_manager()
            result = llm_manager.complete(
                messages=messages,
                provider=provider,
                temperature=settings.vanna_temperature,
                max_tokens=3000
            )
            
            content = result["content"].strip()
            
            # Prova a parsare come JSON
            reasoning = None
            sql = ""
            
            try:
                # Rimuovi eventuale markdown
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                parsed = json.loads(content)
                reasoning = parsed.get("reasoning", {})
                sql = parsed.get("sql", "")
                sql = self._clean_sql(sql)
                
            except json.JSONDecodeError:
                # Fallback: estrai SQL dal contenuto
                logger.warning("JSON parsing failed, extracting SQL from content")
                sql = self._clean_sql(content)
                reasoning = None
            
            logger.info(f"Generated SQL with reasoning via {provider}: {sql[:100]}...")
            
            return {
                "sql": sql,
                "reasoning": reasoning,
                "success": True,
                "error": None,
                "llm_provider": provider,
                "llm_latency_ms": result["latency_ms"],
                "llm_tokens": result["usage"]["total_tokens"]
            }
            
        except Exception as e:
            logger.error(f"SQL generation with reasoning error: {e}")
            return {
                "sql": "",
                "reasoning": None,
                "success": False,
                "error": str(e),
                "llm_provider": provider
            }

    def _build_messages(self, question: str, schema: str, examples: List[Dict], docs: str) -> List[Dict]:
        """Legacy method - kept for compatibility but not used"""
        return self._build_messages_dynamic(question, schema)

    def _clean_sql(self, sql: str) -> str:
        """Rimuove markdown e pulisce SQL"""
        sql = sql.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        return sql.strip()

    # =========================================================================
    # EXECUTION (usa MCP Server)
    # =========================================================================
    
    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """Esegue SQL via MCP Server"""
        try:
            if not mcp_postgres_client._connected:
                mcp_postgres_client.start()
            
            start_time = time.time()
            rows = mcp_postgres_client.execute_query(sql)
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.info(f"SQL executed via MCP: {len(rows)} rows, {execution_time_ms:.2f}ms")
            
            return {
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": execution_time_ms,
                "success": True,
                "error": None,
                "executed_via": "MCP Server"
            }
            
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "success": False,
                "error": str(e),
                "executed_via": "MCP Server"
            }

    def generate_and_execute(self, question: str, llm_provider: Optional[str] = None) -> Dict[str, Any]:
        """Pipeline completa: NL -> SQL -> Execute"""
        provider = llm_provider or self.llm_provider
        
        # Generate SQL
        gen_result = self.generate_sql(question, llm_provider=provider)
        
        if not gen_result["success"]:
            return {
                "question": question,
                "sql": "",
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "success": False,
                "error": gen_result.get("error"),
                "schema_source": "MCP Server",
                "examples_source": "ChromaDB RAG",
                "llm_provider": provider
            }
        
        sql = gen_result["sql"]
        
        # Execute via MCP
        exec_result = self.execute_sql(sql)
        
        return {
            "question": question,
            "sql": sql,
            "rows": exec_result["rows"],
            "row_count": exec_result["row_count"],
            "execution_time_ms": exec_result["execution_time_ms"],
            "success": exec_result["success"],
            "error": exec_result.get("error"),
            "schema_source": "MCP Server (live)",
            "examples_source": "ChromaDB RAG",
            "executed_via": exec_result.get("executed_via", "MCP Server"),
            "llm_provider": provider,
            "llm_latency_ms": gen_result.get("llm_latency_ms"),
            "llm_tokens": gen_result.get("llm_tokens")
        }

    def is_initialized(self) -> bool:
        return self._initialized

    def get_training_stats(self) -> Dict:
        """Statistiche sul training"""
        llm_manager = get_llm_provider_manager()
        return {
            "sql_examples": self.sql_collection.count(),
            "documentation_chunks": self.doc_collection.count(),
            "schema_source": "MCP Server (dynamic)",
            "llm_provider": self.llm_provider,
            "available_providers": llm_manager.list_available_providers()
        }


# Singleton cache per provider
_vanna_services: Dict[str, HybridVannaService] = {}


def get_vanna_service(llm_provider: Optional[str] = None) -> HybridVannaService:
    """
    Get or create Vanna service per provider
    
    Args:
        llm_provider: "claude" | "azure" | None (usa default)
    """
    global _vanna_services
    provider = llm_provider or settings.default_llm_provider
    
    if provider not in _vanna_services:
        _vanna_services[provider] = HybridVannaService(llm_provider=provider)
    
    return _vanna_services[provider]