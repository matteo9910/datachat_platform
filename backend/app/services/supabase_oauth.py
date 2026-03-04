"""
Supabase OAuth 2.0 Client - Flusso OAuth con credenziali da .env
"""

import httpx
import secrets
import hashlib
import base64
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
from app.config import settings

logger = logging.getLogger(__name__)


class SupabaseOAuth:
    """Gestisce OAuth 2.0 con Supabase Management API"""
    
    OAUTH_AUTHORIZE = "https://api.supabase.com/v1/oauth/authorize"
    OAUTH_TOKEN = "https://api.supabase.com/v1/oauth/token"
    API_BASE = "https://api.supabase.com/v1"
    
    SCOPES = "all"
    
    def __init__(self):
        self._pending_auth: Dict[str, Dict] = {}
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._http = httpx.Client(timeout=30, verify=False)
    
    @property
    def client_id(self) -> Optional[str]:
        return getattr(settings, "supabase_oauth_client_id", None)
    
    @property
    def client_secret(self) -> Optional[str]:
        return getattr(settings, "supabase_oauth_client_secret", None)
    
    @property
    def redirect_uri(self) -> str:
        return getattr(settings, "supabase_oauth_redirect_uri", "http://localhost:5173/oauth/callback")
    
    def get_authorization_url(self) -> Dict[str, str]:
        """Genera URL per autorizzazione OAuth con PKCE"""
        if not self.client_id:
            raise ValueError("SUPABASE_OAUTH_CLIENT_ID not configured")
        
        code_verifier = secrets.token_urlsafe(43)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        
        state = secrets.token_urlsafe(16)
        
        self._pending_auth[state] = {"code_verifier": code_verifier}
        
        logger.info(f"OAuth init - client_id: {self.client_id[:8]}..., state: {state}")
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        
        auth_url = f"{self.OAUTH_AUTHORIZE}?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state}
    
    def exchange_code(self, code: str, state: str) -> Dict[str, Any]:
        """Scambia authorization code per access token"""
        logger.info(f"OAuth exchange - state: {state}")
        
        if state not in self._pending_auth:
            logger.error(f"State not found: {state}, available: {list(self._pending_auth.keys())}")
            raise ValueError("Invalid or expired state")
        
        code_verifier = self._pending_auth[state]["code_verifier"]
        del self._pending_auth[state]
        
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_header = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}",
            "Accept": "application/json"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier
        }
        
        logger.info("Exchanging code for token...")
        response = self._http.post(self.OAUTH_TOKEN, data=data, headers=headers)
        
        logger.info(f"Token response status: {response.status_code}")
        
        # Parse JSON
        try:
            tokens = response.json()
        except:
            raise Exception(f"Invalid response: {response.text}")
        
        # Check for access_token (success)
        if "access_token" in tokens:
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens.get("refresh_token")
            logger.info(f"OAuth successful! Token: {self._access_token[:20]}...")
            return tokens
        
        # Check for error
        if "error" in tokens:
            raise Exception(tokens.get("error_description", tokens["error"]))
        
        raise Exception(f"Unexpected response: {tokens}")
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """Lista tutti i progetti"""
        if not self._access_token:
            raise RuntimeError("Not authenticated")
        
        response = self._http.get(
            f"{self.API_BASE}/projects",
            headers={"Authorization": f"Bearer {self._access_token}"}
        )
        response.raise_for_status()
        return response.json()
    
    def get_project_api_keys(self, project_ref: str) -> Dict[str, str]:
        """Ottiene le API keys di un progetto"""
        if not self._access_token:
            raise RuntimeError("Not authenticated")
        
        response = self._http.get(
            f"{self.API_BASE}/projects/{project_ref}/api-keys",
            headers={"Authorization": f"Bearer {self._access_token}"}
        )
        response.raise_for_status()
        keys = response.json()
        
        result = {}
        for key in keys:
            result[key.get("name", "unknown")] = key.get("api_key", "")
        return result
    
    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None
    
    @property
    def access_token(self) -> Optional[str]:
        return self._access_token
    
    def disconnect(self):
        self._access_token = None
        self._refresh_token = None
        self._pending_auth = {}


supabase_oauth = SupabaseOAuth()
