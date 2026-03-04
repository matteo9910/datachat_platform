"""
Supabase MCP Client - Connessione al server MCP HTTP nativo di Supabase
Supporta autenticazione via Personal Access Token (PAT) o REST API fallback
"""

import httpx
import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SupabaseMCPClient:
    """Client per Supabase via server MCP HTTP nativo"""

    MCP_BASE = "https://mcp.supabase.com/mcp"

    def __init__(self):
        self._connected = False
        self._project_ref: Optional[str] = None
        self._access_token: Optional[str] = None
        self._session_id: Optional[str] = None
        self._mcp_url: Optional[str] = None
        self._http_client: Optional[httpx.Client] = None
        self._request_id = 0
        self._tables_cache: List[str] = []
        self._using_rest_fallback = False
        self._using_mcp = False

    def connect_with_pat(self, project_ref: str, personal_access_token: str) -> bool:
        """Connetti via MCP usando Personal Access Token"""
        self._project_ref = project_ref
        self._access_token = personal_access_token
        self._mcp_url = f"{self.MCP_BASE}?project_ref={project_ref}"
        
        self._http_client = httpx.Client(
            timeout=30.0,
            verify=False,
            headers={
                "Authorization": f"Bearer {personal_access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        
        try:
            # Initialize MCP session
            init_response = self._send_mcp_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "datachat-backend", "version": "0.5.0"}
            }, include_session=False)
            
            self._connected = True
            self._using_mcp = True
            self._using_rest_fallback = False
            
            # Cache tables
            self._load_tables_mcp()
            
            logger.info(f"Connected to Supabase MCP: {project_ref} ({len(self._tables_cache)} tables)")
            return True
            
        except Exception as e:
            logger.error(f"MCP connection failed: {e}")
            raise

    def connect_with_service_key(self, project_ref: str, service_role_key: str) -> bool:
        """Connetti via REST API usando service_role key"""
        self._project_ref = project_ref
        self._access_token = service_role_key
        rest_url = f"https://{project_ref}.supabase.co/rest/v1"
        
        self._http_client = httpx.Client(
            timeout=30.0,
            verify=False,
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        
        # Test connection
        response = self._http_client.get(rest_url + "/", headers={"Accept": "application/openapi+json"})
        response.raise_for_status()
        data = response.json()
        
        paths = data.get("paths", {})
        self._tables_cache = [p.strip("/") for p in paths.keys() if p != "/" and not p.startswith("/rpc")]
        
        self._connected = True
        self._using_mcp = False
        self._using_rest_fallback = True
        self._mcp_url = rest_url
        
        logger.info(f"Connected to Supabase REST API: {project_ref} ({len(self._tables_cache)} tables)")
        return True

    def _send_mcp_request(self, method: str, params: Optional[Dict] = None, include_session: bool = True) -> Dict[str, Any]:
        """Invia richiesta JSON-RPC al server MCP HTTP"""
        if not self._http_client or not self._mcp_url:
            raise RuntimeError("Client not connected")
        
        self._request_id += 1
        request = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        
        headers = dict(self._http_client.headers)
        if include_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        
        response = self._http_client.post(self._mcp_url, json=request, headers=headers)
        
        # Salva session ID dalla risposta
        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]
        
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            raise Exception(result["error"].get("message", "Unknown MCP error"))
        
        return result

    def _load_tables_mcp(self):
        """Carica lista tabelle via MCP"""
        try:
            response = self._send_mcp_request("tools/call", {
                "name": "list_tables",
                "arguments": {"schemas": ["public"]}
            })
            
            content = response.get("result", {}).get("content", [])
            if content and isinstance(content, list):
                text = content[0].get("text", "[]")
                # Parse JSON dalla risposta
                try:
                    tables_data = json.loads(text)
                    if isinstance(tables_data, list):
                        self._tables_cache = [t.get("name") for t in tables_data if t.get("name")]
                except:
                    pass
        except Exception as e:
            logger.warning(f"Failed to load tables via MCP: {e}")

    def list_tables(self, schema: str = "public") -> List[str]:
        """Lista le tabelle"""
        return self._tables_cache

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Esegue una query SQL"""
        if self._using_rest_fallback:
            return self._execute_rest_query(sql)
        
        # Via MCP
        try:
            response = self._send_mcp_request("tools/call", {
                "name": "execute_sql",
                "arguments": {"query": sql}
            })
            
            content = response.get("result", {}).get("content", [])
            if content and isinstance(content, list):
                text = content[0].get("text", "[]")
                # Estrai JSON dalla risposta wrapped
                import re
                match = re.search(r'<untrusted-data[^>]*>\n(.*?)\n</untrusted-data', text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except:
                        pass
                # Prova parse diretto
                try:
                    return json.loads(text)
                except:
                    return [{"result": text}]
            return []
        except Exception as e:
            logger.error(f"MCP query failed: {e}")
            return []

    def _execute_rest_query(self, sql: str) -> List[Dict[str, Any]]:
        """Esegue query via REST API"""
        sql_lower = sql.lower().strip()
        table_match = re.search(r"from\s+(?:public\.)?(\w+)", sql_lower)
        if not table_match:
            return []
        
        table_name = table_match.group(1)
        url = f"{self._mcp_url}/{table_name}"
        params = {}
        
        limit_match = re.search(r"limit\s+(\d+)", sql_lower)
        if limit_match:
            params["limit"] = limit_match.group(1)
        
        try:
            response = self._http_client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"REST query failed: {e}")
            return []

    def describe_table(self, table_name: str, schema: str = "public") -> Dict[str, Any]:
        """Recupera schema tabella"""
        if self._using_rest_fallback:
            # Via REST API - inferisci dai dati
            url = f"{self._mcp_url}/{table_name}"
            try:
                response = self._http_client.get(url, params={"limit": "1"})
                data = response.json() if response.status_code == 200 else []
            except:
                data = []
            
            columns = []
            if data:
                for col_name, value in data[0].items():
                    col_type = "text"
                    if isinstance(value, int): col_type = "integer"
                    elif isinstance(value, float): col_type = "numeric"
                    elif isinstance(value, bool): col_type = "boolean"
                    columns.append({"column_name": col_name, "data_type": col_type, "is_nullable": "YES"})
        else:
            # Via MCP
            sql = f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = '{schema}' AND table_name = '{table_name}'"
            columns = self.execute_query(sql)
        
        ddl_lines = [f"CREATE TABLE {schema}.{table_name} ("]
        for col in columns:
            nullable = "" if col.get("is_nullable") == "YES" else " NOT NULL"
            ddl_lines.append(f"  {col.get('column_name')} {col.get('data_type')}{nullable},")
        if ddl_lines[-1].endswith(","):
            ddl_lines[-1] = ddl_lines[-1].rstrip(",")
        ddl_lines.append(");")
        
        return {"table_name": table_name, "schema": schema, "columns": columns, "ddl": "\n".join(ddl_lines)}

    def get_schema_ddl(self, schema: str = "public") -> str:
        """Genera DDL completo"""
        tables = self.list_tables(schema)
        ddl_parts = [self.describe_table(t, schema).get("ddl", "") for t in tables]
        return "\n\n".join(ddl_parts)

    def disconnect(self):
        """Disconnetti"""
        if self._http_client:
            self._http_client.close()
        self._connected = False
        self._project_ref = None
        self._access_token = None
        self._session_id = None
        self._mcp_url = None
        self._http_client = None
        self._tables_cache = []
        self._using_mcp = False
        self._using_rest_fallback = False
        logger.info("Disconnected from Supabase")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def project_ref(self) -> Optional[str]:
        return self._project_ref
    
    @property
    def is_using_mcp(self) -> bool:
        return self._using_mcp
    
    @property
    def is_using_rest_fallback(self) -> bool:
        return self._using_rest_fallback


MCPSupabaseClient = SupabaseMCPClient
SupabaseRestClient = SupabaseMCPClient
mcp_supabase_client = SupabaseMCPClient()
