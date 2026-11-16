import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.ai.model_config import ProviderConfig, LLMProviderType
from app.core.exceptions import PIIMaskingError
from app.core.logging import logger
from app.privacy.terminal_logger import inspect_provider_boundary, is_terminal_logging_enabled

T = TypeVar("T", bound=BaseModel)


class LLMConfigurationError(Exception):
    """Raised when an LLM provider is improperly configured or lacks credentials."""
    pass


class LLMExecutionError(Exception):
    """Raised when an LLM provider call fails during execution."""
    pass


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers integrated via LangChain."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def provider_name(self) -> str:
        return self.config.provider.value

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @abstractmethod
    def is_configured(self) -> bool:
        """Checks if the provider has all mandatory credentials configured."""
        pass

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Generates plain string response from the underlying LangChain model."""
        pass

    @abstractmethod
    async def generate_structured(self, prompt: str, schema_cls: Type[T]) -> T:
        """Generates validated structured output matching the target Pydantic model."""
        pass


class GoogleGenAIProvider(BaseLLMProvider):
    """Google Gemini LLM provider implemented via LangChain ChatGoogleGenerativeAI."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._llm = None
        if self.is_configured():
            self._init_llm()

    def is_configured(self) -> bool:
        return bool(self.config.api_key and self.config.api_key.strip())

    def _init_llm(self):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._llm = ChatGoogleGenerativeAI(
                model=self.config.model_name,
                google_api_key=self.config.api_key,
                temperature=self.config.temperature,
                timeout=self.config.timeout,
                max_output_tokens=self.config.max_tokens,
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChatGoogleGenerativeAI: {e}")
            raise LLMConfigurationError(f"Could not initialize Google GenAI: {e}")

    async def generate_text(self, prompt: str) -> str:
        if not self.is_configured():
            raise LLMConfigurationError("Gemini API key is not configured.")
        if not self._llm:
            self._init_llm()

        # Capture and inspect serialized provider input at the boundary
        if not inspect_provider_boundary("ChatGoogleGenerativeAI", self.config.model_name, prompt):
            raise PIIMaskingError("Security assertion failed: unmasked PII detected at Google GenAI boundary.")

        try:
            response = await self._llm.ainvoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"Error during Google GenAI text generation: {e}")
            raise LLMExecutionError(f"Google GenAI execution failed: {e}") from e

    async def generate_structured(self, prompt: str, schema_cls: Type[T]) -> T:
        if not self.is_configured():
            raise LLMConfigurationError("Gemini API key is not configured.")
        if not self._llm:
            self._init_llm()

        # Capture and inspect serialized provider input at the boundary
        if not inspect_provider_boundary("ChatGoogleGenerativeAI", self.config.model_name, prompt):
            raise PIIMaskingError("Security assertion failed: unmasked PII detected at Google GenAI boundary.")

        if is_terminal_logging_enabled():
            logger.info(
                f"[GoogleGenAIProvider] Invoking LangChain ChatGoogleGenerativeAI (model={self.config.model_name}) with sanitized payload."
            )

        try:
            structured_model = self._llm.with_structured_output(schema_cls)
            result = await structured_model.ainvoke(prompt)
            if is_terminal_logging_enabled():
                logger.info("[GoogleGenAIProvider] Safe structured response received from Gemini.")
            if isinstance(result, schema_cls):
                return result
            if isinstance(result, dict):
                return schema_cls(**result)
            raise LLMExecutionError(f"Unexpected response type from structured model: {type(result)}")
        except (LLMConfigurationError, LLMExecutionError):
            raise
        except Exception as e:
            logger.error(f"Error during Google GenAI structured output: {e}")
            raise LLMExecutionError(f"Google GenAI structured generation failed: {e}") from e


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider implemented via LangChain ChatOpenAI."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._llm = None
        if self.is_configured():
            self._init_llm()

    def is_configured(self) -> bool:
        return bool(self.config.api_key and self.config.api_key.strip())

    def _init_llm(self):
        try:
            from langchain_openai import ChatOpenAI

            self._llm = ChatOpenAI(
                model=self.config.model_name,
                api_key=self.config.api_key,
                temperature=self.config.temperature,
                timeout=self.config.timeout,
                max_tokens=self.config.max_tokens,
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChatOpenAI: {e}")
            raise LLMConfigurationError(f"Could not initialize OpenAI: {e}")

    async def generate_text(self, prompt: str) -> str:
        if not self.is_configured():
            raise LLMConfigurationError("OpenAI API key is not configured.")
        if not self._llm:
            self._init_llm()

        # Capture and inspect serialized provider input at the boundary
        if not inspect_provider_boundary("ChatOpenAI", self.config.model_name, prompt):
            raise PIIMaskingError("Security assertion failed: unmasked PII detected at OpenAI boundary.")

        try:
            response = await self._llm.ainvoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"Error during OpenAI text generation: {e}")
            raise LLMExecutionError(f"OpenAI execution failed: {e}") from e

    async def generate_structured(self, prompt: str, schema_cls: Type[T]) -> T:
        if not self.is_configured():
            raise LLMConfigurationError("OpenAI API key is not configured.")
        if not self._llm:
            self._init_llm()

        # Capture and inspect serialized provider input at the boundary
        if not inspect_provider_boundary("ChatOpenAI", self.config.model_name, prompt):
            raise PIIMaskingError("Security assertion failed: unmasked PII detected at OpenAI boundary.")

        if is_terminal_logging_enabled():
            logger.info(
                f"[OpenAIProvider] Invoking LangChain ChatOpenAI (model={self.config.model_name}) with sanitized payload."
            )

        try:
            structured_model = self._llm.with_structured_output(schema_cls)
            result = await structured_model.ainvoke(prompt)
            if is_terminal_logging_enabled():
                logger.info("[OpenAIProvider] Safe structured response received from OpenAI.")
            if isinstance(result, schema_cls):
                return result
            if isinstance(result, dict):
                return schema_cls(**result)
            raise LLMExecutionError(f"Unexpected response type from structured model: {type(result)}")
        except (LLMConfigurationError, LLMExecutionError):
            raise
        except Exception as e:
            logger.error(f"Error during OpenAI structured output: {e}")
            raise LLMExecutionError(f"OpenAI structured generation failed: {e}") from e

