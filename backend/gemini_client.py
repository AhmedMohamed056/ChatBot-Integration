"""
Standalone Gemini client for communicating with the Gemini API.

This module provides a clean, reusable client for generating text responses
from the Gemini API without any business logic.
"""

import logging
import os
from typing import Optional
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import requests

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

        try:
            # Build generation config
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                system_instruction=system_prompt,
                http_options=types.HttpOptions(timeout=60000),  # 60s in ms
            )

            # Generate content using the new SDK
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )

            # Extract text from response
            if not response or not response.text:
                logger.error("Empty response from Gemini API")
                raise GeminiResponseError("Empty response from Gemini API")

            return response.text

        except genai_errors.ClientError as e:
            # Client-side errors (invalid request, auth, etc.)
            error_str = str(e).lower()
            if "api key" in error_str or "authentication" in error_str or "permission" in error_str:
                logger.error(f"Authentication failed: {e}")
                raise GeminiAuthenticationError(f"Authentication failed: {e}") from e
            logger.error(f"Client error: {e}")
            raise GeminiClientError(f"Client error: {e}") from e

        except genai_errors.ServerError as e:
            # Server-side errors (rate limit, quota, service unavailable)
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str or "resource exhausted" in error_str:
                logger.error(f"Rate limit exceeded: {e}")
                raise GeminiRateLimitError(f"Rate limit exceeded: {e}") from e
            logger.error(f"Server error: {e}")
            raise GeminiClientError(f"Server error: {e}") from e

        except genai_errors.APIError as e:
            # Generic API errors
            logger.error(f"API error: {e}")
            raise GeminiClientError(f"API error: {e}") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"Network timeout: {e}")
            raise GeminiTimeoutError(f"Network timeout: {e}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise GeminiNetworkError(f"Connection error: {e}") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            raise GeminiNetworkError(f"Network error: {e}") from e

        except ValueError as e:
            # Handle JSON decode errors or similar
            logger.error(f"Invalid response format: {e}")
            raise GeminiResponseError(f"Invalid response format: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise GeminiClientError(f"Unexpected error: {e}") from e