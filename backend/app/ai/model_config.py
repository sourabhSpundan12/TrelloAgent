from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from app.core.config import settings


class LLMProviderType(str, Enum):
    GOOGLE = "google"
    OPENAI = "openai"


class ProviderConfig(BaseModel):
    """Configuration data model for LLM provider initialization."""
    provider: LLMProviderType = LLMProviderType.GOOGLE
    model_name: str
    api_key: Optional[str] = None
    temperature: float = 0.1
    timeout: int = 60
    max_tokens: Optional[int] = None

    @classmethod
    def from_settings(
        cls,
        provider_type: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> "ProviderConfig":
        prov_str = (provider_type or getattr(settings, "LLM_PROVIDER", "google")).lower().strip()
        
        # If model_name indicates provider (e.g. gpt-* -> openai)
        if model_name:
            if model_name.startswith("gpt-"):
                prov_str = "openai"
            elif model_name.startswith("gemini-"):
                prov_str = "google"

        if prov_str in ("google", "gemini"):
            api_key = getattr(settings, "GEMINI_API_KEY", "") or None
            resolved_model = (
                model_name
                or getattr(settings, "LLM_MODEL", None)
                or getattr(settings, "GEMINI_MODEL", None)
                or "gemini-1.5-flash"
            )
            return cls(
                provider=LLMProviderType.GOOGLE,
                model_name=resolved_model,
                api_key=api_key,
                temperature=getattr(settings, "LLM_TEMPERATURE", 0.1),
                timeout=getattr(settings, "LLM_TIMEOUT", 60),
                max_tokens=getattr(settings, "LLM_MAX_TOKENS", None),
            )
        elif prov_str == "openai":
            api_key = getattr(settings, "OPENAI_API_KEY", "") or None
            resolved_model = model_name or getattr(settings, "LLM_MODEL", None) or "gpt-4o-mini"
            return cls(
                provider=LLMProviderType.OPENAI,
                model_name=resolved_model,
                api_key=api_key,
                temperature=getattr(settings, "LLM_TEMPERATURE", 0.1),
                timeout=getattr(settings, "LLM_TIMEOUT", 60),
                max_tokens=getattr(settings, "LLM_MAX_TOKENS", None),
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider '{prov_str}'. Supported providers: google, openai"
            )

