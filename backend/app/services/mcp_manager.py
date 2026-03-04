"""
MCP Manager - Gestione MCP PostgreSQL Server
Implementa comunicazione via subprocess + JSON-RPC con il server MCP ufficiale
"""

import json
import logging
import subprocess
import threading
import queue
from typing import Dict, Any, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class MCPPostgreSQLClient:
    """
    Client MCP per PostgreSQL Server
    
    Comunica con @modelcontextprotocol/server-postgres via:
    - stdin: invio richieste JSON-RPC
    - stdout: ricezione risposte JSON-RPC
    """

    def __init__(self):
        self.process = None
        self._connected = False
        self._request_id = 0
        self._response_queue = queue.Queue()
        self._reader_thread = None
        self._lock = threading.Lock()
        self._use_fallback = False
        self._direct_conn = None

    def start(self):
        """Avvia il server MCP PostgreSQL usando la connection string di default"""
        connection_string = settings.mcp_postgres_connection_string
        self.connect_with_string(connection_string)

    def connect_with_string(self, connection_string: str, force_direct: bool = False):
        """Connetti al database con una connection string specifica
        
        Args:
            connection_string: PostgreSQL connection string
            force_direct: Se True, salta MCP e usa connessione diretta (per Supabase pooler)
        """
        if self._connected:
            self.shutdown()

        self._connection_string = connection_string
        
        # Forza connessione diretta per Supabase pooler (MCP non funziona bene)
        is_supabase = "pooler.supabase.com" in connection_string or "supabase.com" in connection_string
        
        if force_direct or is_supabase:
            logger.info(f"Using direct connection (force_direct={force_direct}, is_supabase={is_supabase})")
            self._use_direct_connection_with_string(connection_string)
            return
        
        try:
            self.process = subprocess.Popen(
                ["npx.cmd", "-y", "@modelcontextprotocol/server-postgres", connection_string],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=True
            )
            
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()
            
            self._initialize_connection()
            self._connected = True
            logger.info("MCP PostgreSQL server started")
            
        except Exception as e:
            logger.warning(f"MCP server failed, using direct connection: {e}")
            self._use_direct_connection_with_string(connection_string)

    def _use_direct_connection_with_string(self, connection_string: str):
        """Fallback: usa connessione diretta psycopg2 con connection string specifica"""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        self._direct_conn = psycopg2.connect(
            connection_string,
            cursor_factory=RealDictCursor
        )
        self._direct_conn.autocommit = True
        self._connected = True
        self._use_fallback = True
        logger.info("Using direct PostgreSQL connection (fallback)")

    def _use_direct_connection(self):
        """Fallback: usa connessione diretta psycopg2"""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        self._direct_conn = psycopg2.connect(
            settings.mcp_postgres_connection_string,
            cursor_factory=RealDictCursor
        )
        self._direct_conn.autocommit = True
        self._connected = True
        self._use_fallback = True
        logger.info("Using direct PostgreSQL connection (fallback)")

    def _ensure_connection(self):
        """Verifica che la connessione diretta sia ancora attiva, riconnetti se necessario"""
        if not self._use_fallback or self._direct_conn is None:
            return
        try:
            self._direct_conn.cursor().execute("SELECT 1")
        except Exception:
            logger.warning("Direct connection lost, reconnecting...")
            try:
                self._direct_conn.close()
            except Exception:
                pass
            conn_string = getattr(self, '_connection_string', None) or settings.mcp_postgres_connection_string
            self._use_direct_connection_with_string(conn_string)

    def _read_responses(self):
        """Thread che legge stdout del server MCP"""
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if line:
                    try:
                        response = json.loads(line.strip())
                        self._response_queue.put(response)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                break

    def _send_request(self, method, params=None):
        """Invia richiesta JSON-RPC al server MCP"""
        with self._lock:
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or {}
            }
            
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            
            try:
                return self._response_queue.get(timeout=30)
            except queue.Empty:
                raise TimeoutError(f"MCP request timeout: {method}")

    def _initialize_connection(self):
        """Inizializza connessione MCP"""
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "datachat-backend", "version": "0.1.0"}
        })
        logger.info(f"MCP initialized")

    def execute_query(self, sql):
        """Esegue query SQL"""
        if self._use_fallback:
            self._ensure_connection()
            with self._direct_conn.cursor() as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]
        
        response = self._send_request("tools/call", {
            "name": "query",
            "arguments": {"sql": sql}
        })
        
        if "error" in response:
            raise Exception(response["error"]["message"])
        
        # Parse MCP response: [{"type": "text", "text": "[{...}]"}]
        content = response.get("result", {}).get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_content = content[0].get("text", "[]")
            return json.loads(text_content)
        return []

    def list_tables(self, schema="public"):
        """Lista tabelle - usa query SQL via MCP"""
        sql = f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE' ORDER BY table_name"
        
        if self._use_fallback:
            self._ensure_connection()
            with self._direct_conn.cursor() as cur:
                cur.execute(sql)
                return [row["table_name"] for row in cur.fetchall()]
        
        # Via MCP: esegui query SQL
        rows = self.execute_query(sql)
        return [row.get("table_name") for row in rows if row.get("table_name")]

    def describe_table(self, table_name, schema="public"):
        """Recupera schema tabella - usa query SQL via MCP"""
        sql = f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = '{schema}' AND table_name = '{table_name}' ORDER BY ordinal_position"
        
        if self._use_fallback:
            self._ensure_connection()
            with self._direct_conn.cursor() as cur:
                cur.execute(sql)
                columns = [dict(row) for row in cur.fetchall()]
        else:
            # Via MCP
            columns = self.execute_query(sql)
        
        # Build DDL
        ddl_lines = [f"CREATE TABLE {schema}.{table_name} ("]
        for col in columns:
            nullable = "" if col.get("is_nullable") == "YES" else " NOT NULL"
            ddl_lines.append(f"  {col.get('column_name')} {col.get('data_type')}{nullable},")
        if ddl_lines[-1].endswith(","):
            ddl_lines[-1] = ddl_lines[-1].rstrip(",")
        ddl_lines.append(");")
        
        return {"table_name": table_name, "schema": schema, "columns": columns, "ddl": "\n".join(ddl_lines)}

    def get_schema_ddl(self, schema="public"):
        """Genera DDL completo"""
        tables = self.list_tables(schema)
        ddl_parts = []
        for table in tables:
            table_info = self.describe_table(table, schema)
            ddl_parts.append(table_info.get("ddl", ""))
        return "\n\n".join(ddl_parts)

    def shutdown(self):
        """Chiude il server MCP"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self._direct_conn:
            self._direct_conn.close()
        self._connected = False
        logger.info("MCP PostgreSQL server stopped")


mcp_postgres_client = MCPPostgreSQLClient()