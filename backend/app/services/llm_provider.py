"""
LLM Provider Manager - Multi-provider abstraction (Claude / Azure OpenAI)
Strategy pattern per swap runtime provider senza modificare chiamanti
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Interfaccia astratta LLM provider"""

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Genera completion da messages

        Args:
            messages: Lista di messaggi [{"role": "user/system/assistant", "content": "..."}]
            temperature: Temperatura generazione
            max_tokens: Max tokens risposta

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

    @abstractmethod
    def complete_text(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Convenience method per singolo prompt testuale"""
        pass


class ClaudeProvider(BaseLLMProvider):
    """Provider Claude Sonnet via OpenRouter"""

    def __init__(self):
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY non configurato in .env")

        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.model = settings.openrouter_model
        self.http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            verify=False
        )
        logger.info(f"ClaudeProvider initialized: model={self.model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True
    )
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """Claude completion via OpenRouter"""
        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        try:
            response = self.http_client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()

            latency_ms = (time.time() - start_time) * 1000
            content = result["choices"][0]["message"]["content"]

            usage = result.get("usage", {})
            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

            logger.info(
                f"ClaudeProvider completion: {latency_ms:.0f}ms, "
                f"{usage_dict['total_tokens']} tokens"
            )

            return {
                "content": content,
                "usage": usage_dict,
                "latency_ms": latency_ms,
                "provider": "claude"
            }

        except Exception as e:
            logger.error(f"ClaudeProvider error: {e}")
            raise

    def complete_text(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Convenience method per singolo prompt"""
        return self.complete(
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )


class AzureOpenAIProvider(BaseLLMProvider):
    """Provider Azure OpenAI (GPT-4.1)"""

    def __init__(self):
        if not settings.azure_openai_api_key:
            raise ValueError("AZURE_OPENAI_API_KEY non configurato in .env")

        self.api_key = settings.azure_openai_api_key
        # Costruisci endpoint corretto per chat completions
        base = settings.azure_openai_endpoint or ""
        # Rimuovi path esistente se presente
        if "/openai/deployments/" in base:
            base = base.split("/openai/deployments/")[0]
        
        self.endpoint = base.rstrip("/")
        self.deployment = settings.azure_openai_deployment_name or "gpt-4.1"
        self.api_version = settings.azure_openai_api_version or "2024-02-15-preview"
        # Usa timeout object invece di float per compatibilita Windows
        self.http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            verify=False
        )
        
        logger.info(f"AzureOpenAIProvider initialized: deployment={self.deployment}, endpoint={self.endpoint}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True
    )
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """Azure OpenAI completion"""
        start_time = time.time()

        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        data = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        try:
            response = self.http_client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

            latency_ms = (time.time() - start_time) * 1000
            content = result["choices"][0]["message"]["content"]

            usage = result.get("usage", {})
            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

            logger.info(
                f"AzureOpenAIProvider completion: {latency_ms:.0f}ms, "
                f"{usage_dict['total_tokens']} tokens"
            )

            return {
                "content": content,
                "usage": usage_dict,
                "latency_ms": latency_ms,
                "provider": "azure"
            }

        except Exception as e:
            logger.error(f"AzureOpenAIProvider error: {e}")
            raise

    def complete_text(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Convenience method per singolo prompt"""
        return self.complete(
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )


class GPT52Provider(BaseLLMProvider):
    """Provider Azure OpenAI GPT-5.2 (Latest Model)"""

    def __init__(self):
        if not settings.azure_gpt52_api_key:
            raise ValueError("AZURE_GPT52_API_KEY non configurato in .env")

        self.api_key = settings.azure_gpt52_api_key
        self.endpoint = (settings.azure_gpt52_endpoint or "").rstrip("/")
        self.deployment = settings.azure_gpt52_deployment_name or "gpt-5.2"
        self.api_version = settings.azure_gpt52_api_version or "2024-12-01-preview"
        self.http_client = httpx.Client(
            timeout=httpx.Timeout(90.0, connect=10.0),
            verify=False
        )
        
        logger.info(f"GPT52Provider initialized: deployment={self.deployment}, endpoint={self.endpoint}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True
    )
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """GPT-5.2 completion via Azure OpenAI"""
        start_time = time.time()

        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        # GPT-5.2 usa max_completion_tokens invece di max_tokens
        data = {
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            **kwargs
        }

        try:
            response = self.http_client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

            latency_ms = (time.time() - start_time) * 1000
            content = result["choices"][0]["message"]["content"]

            usage = result.get("usage", {})
            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

            logger.info(
                f"GPT52Provider completion: {latency_ms:.0f}ms, "
                f"{usage_dict['total_tokens']} tokens"
            )

            return {
                "content": content,
                "usage": usage_dict,
                "latency_ms": latency_ms,
                "provider": "gpt52"
            }

        except Exception as e:
            logger.error(f"GPT52Provider error: {e}")
            raise

    def complete_text(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Convenience method per singolo prompt"""
        return self.complete(
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )


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
                logger.info("Claude provider available")
        except Exception as e:
            logger.warning(f"Claude provider initialization failed: {e}")

        # Azure OpenAI GPT-4.1 (se credenziali disponibili)
        try:
            if settings.azure_openai_api_key:
                self.providers["azure"] = AzureOpenAIProvider()
                logger.info("Azure OpenAI GPT-4.1 provider available")
        except Exception as e:
            logger.warning(f"Azure OpenAI provider initialization failed: {e}")

        # Azure OpenAI GPT-5.2 (se credenziali disponibili)
        try:
            if settings.azure_gpt52_api_key:
                self.providers["gpt52"] = GPT52Provider()
                logger.info("Azure OpenAI GPT-5.2 provider available")
        except Exception as e:
            logger.warning(f"GPT-5.2 provider initialization failed: {e}")

        if not self.providers:
            raise RuntimeError("Nessun LLM provider configurato! Verificare .env")

        logger.info(f"LLM providers initialized: {list(self.providers.keys())}")

    def get_provider(self, provider_name: str) -> BaseLLMProvider:
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
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Wrapper convenience per completion con messages

        Args:
            messages: Lista messaggi
            provider: Nome provider (se None, usa default da settings)
            **kwargs: Parametri passati a provider.complete()
        """
        if provider is None:
            provider = settings.default_llm_provider

        provider_instance = self.get_provider(provider)
        return provider_instance.complete(messages, **kwargs)

    def complete_text(
        self,
        prompt: str,
        provider: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Wrapper convenience per completion con singolo prompt

        Args:
            prompt: Prompt testo
            provider: Nome provider (se None, usa default da settings)
        """
        if provider is None:
            provider = settings.default_llm_provider

        provider_instance = self.get_provider(provider)
        return provider_instance.complete_text(prompt, **kwargs)

    def list_available_providers(self) -> List[str]:
        """Lista provider disponibili"""
        return list(self.providers.keys())


# Singleton - inizializzato lazy al primo uso
_llm_provider_manager: Optional[LLMProviderManager] = None


def get_llm_provider_manager() -> LLMProviderManager:
    """Get or create LLM provider manager singleton"""
    global _llm_provider_manager
    if _llm_provider_manager is None:
        _llm_provider_manager = LLMProviderManager()
    return _llm_provider_manager