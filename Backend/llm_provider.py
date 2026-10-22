"""
llm_provider.py - Configurable LLM provider for grounded Q&A.

Supports Google Gemini (default) via the google-genai SDK.
All configuration is via environment variables -- no secrets in source.

Environment variables
---------------------
GEMINI_API_KEY   : Required. Your Google AI Studio API key.
GEMINI_MODEL     : Optional. Defaults to "gemini-2.0-flash".
LLM_TIMEOUT_SECS : Optional. Timeout for LLM calls in seconds. Default 60.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_TIMEOUT = 60  # seconds


class LLMConfigError(RuntimeError):
    """Raised when the LLM is not configured (missing API key etc.)."""


class LLMProviderError(RuntimeError):
    """Raised when the LLM call fails (network, rate-limit, etc.)."""


class LLMProvider:
    """
    Thin wrapper around Google Gemini for grounded legal Q&A.

    Usage:
        provider = LLMProvider()           # reads env vars
        answer = provider.generate(prompt) # returns text
    """

    def __init__(self) -> None:
        self._api_key: str | None = os.environ.get("GEMINI_API_KEY")
        self._model_name: str = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._timeout: int = int(os.environ.get("LLM_TIMEOUT_SECS", str(DEFAULT_TIMEOUT)))
        self._client = None

    @property
    def is_configured(self) -> bool:
        """True when the API key is present."""
        return bool(self._api_key and self._api_key.strip())

    def _ensure_client(self) -> None:
        """Lazily initialise the Gemini client."""
        if self._client is not None:
            return

        if not self.is_configured:
            raise LLMConfigError(
                "GEMINI_API_KEY environment variable is not set. "
                "Get a free key at https://aistudio.google.com/apikey "
                "and add it to your .env file."
            )

        try:
            from google import genai  # type: ignore
            self._client = genai.Client(api_key=self._api_key)
        except ImportError:
            raise LLMConfigError(
                "The google-genai package is not installed. "
                "Run: pip install google-genai"
            )
        except Exception as exc:
            raise LLMConfigError(f"Failed to initialise Gemini client: {exc}")

    def generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        """
        Send a prompt to Gemini and return the text response.

        Parameters
        ----------
        prompt : str
            The full prompt including system instructions and context.
        temperature : float
            Sampling temperature (0.0 = deterministic, 1.0 = creative).

        Returns
        -------
        str : The generated text.

        Raises
        ------
        LLMConfigError  : API key missing or client init failed.
        LLMProviderError: Network/API error during generation.
        """
        self._ensure_client()

        try:
            from google.genai import types  # type: ignore

            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                ),
            )

            if not response or not response.text:
                raise LLMProviderError(
                    "Gemini returned an empty response. The question may have "
                    "been blocked by safety filters."
                )

            return response.text

        except LLMProviderError:
            raise
        except Exception as exc:
            logger.exception("Gemini API call failed")
            raise LLMProviderError(
                f"LLM generation failed: {type(exc).__name__}: {exc}"
            ) from exc

    @property
    def model_name(self) -> str:
        return self._model_name
