import asyncio
from typing import Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.core.config import settings
from app.core.exceptions import PIIMaskingError
from app.core.logging import logger
from app.privacy.terminal_logger import inspect_provider_boundary, is_terminal_logging_enabled
from app.integrations.gemini.exceptions import (
    GeminiAPIError,
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    GeminiTimeoutError,
)
from app.integrations.gemini.prompts import SYSTEM_INSTRUCTION


class GeminiClient:
    """Wrapper client for the official Google Gen AI Python SDK (google-genai)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not self.api_key:
            raise GeminiNotConfiguredError()
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_structured_content(
        self,
        prompt: str,
        timeout_seconds: float = 15.0,
    ) -> str:
        """Invokes Gemini generate_content asynchronously with JSON output configuration."""
        client = self._get_client()

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1,
            response_mime_type="application/json",
        )

        # Capture and inspect serialized payload at the Google GenAI SDK boundary
        if not inspect_provider_boundary("GoogleGenAISDK", self.model, prompt):
            raise PIIMaskingError("Security assertion failed: unmasked PII detected at Gemini SDK boundary.")

        if is_terminal_logging_enabled():
            logger.info(
                f"[GeminiClient] Invoking Google GenAI SDK (model={self.model}) with sanitized prompt."
            )

        try:
            # Run synchronous SDK call in thread pool with strict timeout
            loop = asyncio.get_running_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config,
                    ),
                ),
                timeout=timeout_seconds,
            )

            if not response or not response.text:
                raise GeminiAPIError("Received empty response from Google Gemini API.")

            if is_terminal_logging_enabled():
                logger.info("[GeminiClient] Safe response received from Google GenAI SDK.")

            return response.text.strip()

        except asyncio.TimeoutError:
            logger.error(f"Gemini API request timed out after {timeout_seconds}s")
            raise GeminiTimeoutError(f"Gemini API timed out after {timeout_seconds}s")
        except APIError as e:
            err_msg = str(e)
            logger.error(f"Gemini API error: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota" in err_msg:
                raise GeminiRateLimitError("Gemini API rate limit or quota exceeded.")
            raise GeminiAPIError(f"Gemini API error: {err_msg}", details={"error": err_msg})
        except (GeminiNotConfiguredError, GeminiTimeoutError, GeminiRateLimitError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error communicating with Gemini API: {e}", exc_info=True)
            raise GeminiAPIError(f"Unexpected Gemini integration failure: {str(e)}")

