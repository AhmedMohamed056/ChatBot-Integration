"""
Standalone Gemini client for communicating with the Gemini API.

This module provides a clean, reusable client for generating text responses
from the Gemini API without any business logic.
"""

import logging
import os
import socket
import time
from typing import Optional
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

try:  # httpx is the transport the google-genai SDK actually uses
    import httpx
except Exception:  # pragma: no cover - httpx is a hard dep of google-genai
    httpx = None

try:  # requests kept only for backwards-compatible exception matching
    import requests
except Exception:  # pragma: no cover
    requests = None

# Custom Exceptions
class GeminiClientError(Exception):
    """Base exception for all Gemini client errors."""
    pass

class GeminiAuthenticationError(GeminiClientError):
    """Exception raised when authentication fails."""
    pass

class GeminiRateLimitError(GeminiClientError):
    """Exception raised when rate limits are exceeded."""
    pass

class GeminiResponseError(GeminiClientError):
    """Exception raised when the response is invalid or empty."""
    pass

class GeminiTimeoutError(GeminiClientError):
    """Exception raised when a request times out."""
    pass

class GeminiNetworkError(GeminiClientError):
    """Exception raised for network-related failures."""
    pass

# Set up logging
logger = logging.getLogger(__name__)

# --- Tunables (override via environment) -----------------------------------
# Read timeout for a single Gemini request, in milliseconds. The google-genai
# SDK expects this value in ms. Kept generous because a large supervisor prompt
# can take a while, but bounded so a stuck socket never hangs the reply.
DEFAULT_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "90000"))
# How many times to attempt a single generate() call before giving up. Retries
# only fire for transient failures (timeout / network / server / empty).
DEFAULT_MAX_ATTEMPTS = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")))


def _is_timeout_error(exc: BaseException) -> bool:
    """Best-effort detection of a read/connect timeout across transports.

    The google-genai SDK uses httpx, whose timeouts (and the stdlib socket
    "The read operation timed out" message underneath) are NOT
    ``requests.exceptions.Timeout``. We match by type first, then fall back to
    the message so no timeout is ever misfiled as an opaque "Unexpected error".
    """
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return True
    if requests is not None and isinstance(exc, requests.exceptions.Timeout):
        return True
    msg = str(exc).lower()
    return "timed out" in msg or "timeout" in msg or "deadline exceeded" in msg


def _is_network_error(exc: BaseException) -> bool:
    """Best-effort detection of a connection/transport failure (not a timeout)."""
    if httpx is not None and isinstance(exc, httpx.TransportError):
        return True
    if requests is not None and isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, (ConnectionError, socket.gaierror)):
        return True
    msg = str(exc).lower()
    return "connection" in msg or "network" in msg or "temporarily unavailable" in msg


class GeminiClient:
    """
    A standalone client for communicating with the Gemini API.

    This client handles:
    - Initialization of the Gemini SDK
    - Sending requests with system and user prompts
    - Error handling for various failure scenarios
    - Returning plain text responses

    Example usage:
        client = GeminiClient()
        response = client.generate(
            system_prompt="You are a helpful assistant.",
            user_prompt="Say Hello"
        )
        print(response)
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the Gemini client.

        Args:
            api_key: Optional API key. If not provided, will be read from
                    GOOGLE_API_KEY environment variable.
            model_name: Optional model name. If not provided, will be read from
                      GOOGLE_MODEL environment variable, or default to gemini-2.5-flash.

        Raises:
            GeminiAuthenticationError: If API key is not provided and not found in environment.
        """
        self.api_key = (api_key or os.getenv("GOOGLE_API_KEY") or "").strip() or None

        if not self.api_key:
            logger.error("GOOGLE_API_KEY is not provided and not found in environment variables")
            raise GeminiAuthenticationError(
                "GOOGLE_API_KEY is not provided and not found in environment variables"
            )

        # Get model name from environment or use default
        self.model_name = model_name or os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

        try:
            # The new google-genai SDK uses a Client object; the model name is
            # passed per-request rather than bound at construction time.
            self.client = genai.Client(api_key=self.api_key)
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini SDK: {e}")
            raise GeminiAuthenticationError(f"Failed to initialize Gemini SDK: {e}") from e

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 2048
    ) -> str:
        """
        Generate a response from the Gemini API.

        Args:
            system_prompt: The system prompt to prepend to the conversation.
            user_prompt: The user's input prompt.
            temperature: The temperature for response generation (0.0-1.0).
            max_output_tokens: Maximum number of tokens in the response.

        Returns:
            Plain text response from Gemini.

        Raises:
            GeminiAuthenticationError: If authentication fails.
            GeminiRateLimitError: If rate limits are exceeded.
            GeminiTimeoutError: If the request times out.
            GeminiNetworkError: If there's a network failure.
            GeminiResponseError: If the response is empty or invalid.
            GeminiClientError: For any other unexpected errors.
        """
        if not self._initialized:
            logger.error("Client not initialized. Call __init__ first.")
            raise GeminiClientError("Client not initialized. Call __init__ first.")

        config = self._build_config(system_prompt, temperature, max_output_tokens)

        # Retry only transient failures (timeout / network / server / empty).
        # Authentication, rate-limit, and client (bad-request) errors are
        # permanent for this call and re-raise immediately.
        last_exc: Optional[Exception] = None
        for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=config,
                )

                if not response or not response.text:
                    raise GeminiResponseError("Empty response from Gemini API")

                return response.text

            except (GeminiAuthenticationError, GeminiRateLimitError):
                raise

            except genai_errors.ClientError as e:
                error_str = str(e).lower()
                if "api key" in error_str or "authentication" in error_str or "permission" in error_str:
                    logger.error(f"Authentication failed: {e}")
                    raise GeminiAuthenticationError(f"Authentication failed: {e}") from e
                # Bad request — retrying won't help.
                logger.error(f"Client error: {e}")
                raise GeminiClientError(f"Client error: {e}") from e

            except genai_errors.ServerError as e:
                error_str = str(e).lower()
                if "quota" in error_str or "rate" in error_str or "resource exhausted" in error_str:
                    logger.error(f"Rate limit exceeded: {e}")
                    raise GeminiRateLimitError(f"Rate limit exceeded: {e}") from e
                last_exc = GeminiClientError(f"Server error: {e}")
                logger.warning(f"Server error (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")

            except GeminiResponseError as e:
                last_exc = e
                logger.warning(f"Empty response (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")

            except Exception as e:
                # Classify by transport signature so a real timeout is never
                # buried as an opaque "Unexpected error" again.
                if _is_timeout_error(e):
                    last_exc = GeminiTimeoutError(f"Request timed out: {e}")
                    logger.warning(f"Timeout (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")
                elif _is_network_error(e):
                    last_exc = GeminiNetworkError(f"Network error: {e}")
                    logger.warning(f"Network error (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")
                elif isinstance(e, genai_errors.APIError):
                    last_exc = GeminiClientError(f"API error: {e}")
                    logger.warning(f"API error (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")
                elif isinstance(e, ValueError):
                    # Malformed response body — permanent for this call.
                    logger.error(f"Invalid response format: {e}")
                    raise GeminiResponseError(f"Invalid response format: {e}") from e
                else:
                    last_exc = GeminiClientError(f"Unexpected error: {e}")
                    logger.warning(f"Unexpected error (attempt {attempt}/{DEFAULT_MAX_ATTEMPTS}): {e}")

            # Backoff before the next attempt (skip after the final attempt).
            if attempt < DEFAULT_MAX_ATTEMPTS:
                time.sleep(min(2 ** (attempt - 1), 4))

        # All attempts exhausted — surface the classified error.
        assert last_exc is not None
        logger.error(f"Gemini request failed after {DEFAULT_MAX_ATTEMPTS} attempt(s): {last_exc}")
        raise last_exc

    def _build_config(
        self, system_prompt: str, temperature: float, max_output_tokens: int
    ) -> "types.GenerateContentConfig":
        """Build the per-request generation config.

        For ``flash`` models we disable "thinking" (thinking_budget=0). Flash
        thinking adds significant latency for no quality gain on these short
        assistant replies and is a common cause of the read timeout.
        """
        kwargs: dict = dict(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_prompt,
            http_options=types.HttpOptions(timeout=DEFAULT_TIMEOUT_MS),
        )
        if "flash" in (self.model_name or "").lower():
            try:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:  # noqa: BLE001 - older SDKs lack ThinkingConfig
                pass
        return types.GenerateContentConfig(**kwargs)