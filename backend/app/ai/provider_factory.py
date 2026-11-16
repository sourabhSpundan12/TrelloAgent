from typing import Dict, Optional, Type
from app.ai.llm_provider import (
    BaseLLMProvider,
    GoogleGenAIProvider,
    OpenAIProvider,
    LLMConfigurationError,
)
from app.ai.model_config import ProviderConfig, LLMProviderType
from app.core.logging import logger


class LLMProviderFactory:
    """Factory to instantiate and manage LLM provider implementations."""

    _REGISTRY: Dict[LLMProviderType, Type[BaseLLMProvider]] = {
        LLMProviderType.GOOGLE: GoogleGenAIProvider,
        LLMProviderType.OPENAI: OpenAIProvider,
    }

    @classmethod
    def register_provider(
        cls, provider_type: LLMProviderType, provider_cls: Type[BaseLLMProvider]
    ):
        """Allows registering custom provider implementations."""
        cls._REGISTRY[provider_type] = provider_cls

    @classmethod
    def create_provider(
        cls,
        provider_type: Optional[str] = None,
        config: Optional[ProviderConfig] = None,
    ) -> BaseLLMProvider:
        """
        Creates an LLM provider instance based on provider name or configuration.
        Defaults to current environment configuration if arguments are omitted.
        """
        if config is None:
            config = ProviderConfig.from_settings(provider_type)

        provider_cls = cls._REGISTRY.get(config.provider)
        if not provider_cls:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: '{config.provider}'. Available: {[p.value for p in cls._REGISTRY.keys()]}"
            )

        logger.debug(
            f"Instantiating LLM provider '{config.provider.value}' with model '{config.model_name}'"
        )
        return provider_cls(config)

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """Returns list of supported provider names."""
        return [p.value for p in cls._REGISTRY.keys()]

