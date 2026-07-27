"""Visitor Flow Orchestrator.

This module is responsible ONLY for coordinating the existing components:
- AIContextBuilder
- PromptBuilder
- build_visitor_system_prompt()
- GeminiClient

It deliberately does NOT contain any business logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ai_context_builder import build_context as build_ai_context
from gemini_client import GeminiClient, GeminiClientError
from prompts import build_visitor_system_prompt
from prompt_builder import build_prompt

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class VisitorFlowResult:
    """Result of handling a visitor message.

    Attributes
    ----------
    reply : str
        The response text to return to the visitor.
    handled : bool
        Whether the message was successfully processed.
    """
    reply: str
    handled: bool

class VisitorFlow:
    """Orchestrator for visitor message flow.

    Coordinates the existing components to process incoming visitor messages:

    Incoming Visitor Message
            ↓
    Build AIContext
            ↓
    Load Visitor System Prompt
            ↓
    Build Dynamic Prompt
            ↓
    Call GeminiClient
            ↓
    Return Reply

    This class contains NO business logic - it only orchestrates existing components.
    """

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize the VisitorFlow orchestrator.

        Parameters
        ----------
        gemini_client : GeminiClient, optional
            A pre-initialized GeminiClient instance. If not provided,
            a new one will be created on first use.
        """
        self._gemini_client = gemini_client

    def _get_gemini_client(self) -> Optional[GeminiClient]:
        """Get or create the GeminiClient instance."""
        if self._gemini_client is None:
            try:
                self._gemini_client = GeminiClient()
            except Exception as exc:
                logger.error(f"Failed to initialize GeminiClient: {exc}")
                return None
        return self._gemini_client

    def handle_message(
        self,
        phone: str,
        message: str
    ) -> VisitorFlowResult:
        """Handle an incoming visitor message.

        Orchestrates the complete flow:
        1. Build AIContext using AIContextBuilder
        2. Load Visitor System Prompt
        3. Build Dynamic Prompt using PromptBuilder
        4. Call GeminiClient
        5. Return VisitorFlowResult

        Parameters
        ----------
        phone : str
            The visitor's phone number.
        message : str
            The incoming message text.

        Returns
        -------
        VisitorFlowResult
            The result containing the reply and whether it was handled successfully.
        """
        try:
            # Step 1: Build AIContext
            logger.info("Building AIContext")
            ai_context = build_ai_context(message=message, phone=phone)

            # Step 2: Load Visitor System Prompt
            logger.info("Loading Visitor System Prompt")
            system_prompt = build_visitor_system_prompt()

            # Step 3: Build Dynamic Prompt (includes system_prompt + context + user message)
            logger.info("Building Prompt")
            full_prompt = build_prompt(system_prompt=system_prompt, context=ai_context)

            # Step 4: Call GeminiClient
            # Note: build_prompt already includes the system prompt, so we pass empty system_prompt
            # to avoid duplication. The full_prompt contains everything needed.
            logger.info("Calling Gemini")
            gemini_client = self._get_gemini_client()
            if gemini_client is None:
                logger.error("GeminiClient is not available")
                return VisitorFlowResult(
                    reply="أعتذر، حدث خطأ أثناء معالجة الطلب.",
                    handled=False
                )

            response = gemini_client.generate(
                system_prompt="",
                user_prompt=full_prompt
            )

            # Step 5: Return Reply
            logger.info("Reply generated successfully")
            return VisitorFlowResult(
                reply=response,
                handled=True
            )

        except GeminiClientError as exc:
            logger.error(f"GeminiClient error: {exc}")
            return VisitorFlowResult(
                reply="أعتذر، حدث خطأ أثناء معالجة الطلب.",
                handled=False
            )
        except Exception as exc:
            logger.error(f"Unexpected error in VisitorFlow: {exc}")
            return VisitorFlowResult(
                reply="أعتذر، حدث خطأ أثناء معالجة الطلب.",
                handled=False
            )

