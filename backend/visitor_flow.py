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
from typing import Any, Optional

from ai_context_builder import build_context as build_ai_context
from gemini_client import GeminiClient, GeminiClientError
from prompts import build_visitor_system_prompt
from prompt_builder import build_prompt
from services.supervisor_context_service import SupervisorContext

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
                from database import get_setting
                from services.runtime_settings import apply_runtime_env

                apply_runtime_env()
                api_key = get_setting("gemini_api_key") or None
                model = get_setting("gemini_model") or None
                self._gemini_client = GeminiClient(api_key=api_key, model_name=model)
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
            from services.calendar_answer_service import try_calendar_answer

            calendar_reply = try_calendar_answer(message)
            if calendar_reply:
                return VisitorFlowResult(reply=calendar_reply, handled=True)

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

    def handle_message_with_supervisor(
        self,
        phone: str,
        message: str,
        supervisor_context: SupervisorContext,
        conversation_id: Optional[int] = None
    ) -> VisitorFlowResult:
        """Handle an incoming message from an authorized supervisor with context injection.

        This method is specifically for authorized WhatsApp supervisors and injects
        their supervisor context into every Gemini request.

        Orchestrates the complete flow:
        1. Build AIContext using AIContextBuilder with supervisor context
        2. Load Visitor System Prompt
        3. Build Dynamic Prompt using PromptBuilder
        4. Call GeminiClient
        5. Return VisitorFlowResult

        Parameters
        ----------
        phone : str
            The supervisor's phone number.
        message : str
            The incoming message text.
        supervisor_context : SupervisorContext
            The supervisor context object containing name, phone, campaign info, etc.
        conversation_id : Optional[int]
            Optional conversation ID for loading conversation memory.

        Returns
        -------
        VisitorFlowResult
            The result containing the reply and whether it was handled successfully.
        """
        try:
            from services.calendar_answer_service import try_calendar_answer

            calendar_reply = try_calendar_answer(message)
            if calendar_reply:
                return VisitorFlowResult(reply=calendar_reply, handled=True)

            # Step 1: Build AIContext with supervisor context and conversation memory
            logger.info("Building AIContext with supervisor context and conversation memory")
            ai_context = build_ai_context(
                message=message,
                phone=phone,
                supervisor=supervisor_context,
                conversation_id=conversation_id
            )

            # Step 2: Load Visitor System Prompt
            logger.info("Loading Visitor System Prompt")
            system_prompt = build_visitor_system_prompt()

            # Step 3: Build Dynamic Prompt (includes system_prompt + context + user message)
            logger.info("Building Prompt with supervisor context and conversation memory")
            full_prompt = build_prompt(system_prompt=system_prompt, context=ai_context)

            # Step 4: Call GeminiClient
            # Note: build_prompt already includes the system prompt, so we pass empty system_prompt
            # to avoid duplication. The full_prompt contains everything needed.
            logger.info("Calling Gemini with supervisor context and conversation memory")
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
            logger.info("Reply generated successfully with supervisor context and conversation memory")
            return VisitorFlowResult(
                reply=response,
                handled=True
            )

        except GeminiClientError as exc:
            logger.error(f"GeminiClient error with supervisor context: {exc}")
            return VisitorFlowResult(
                reply="أعتذر، حدث خطأ أثناء معالجة الطلب.",
                handled=False
            )
        except Exception as exc:
            logger.error(f"Unexpected error in VisitorFlow with supervisor context: {exc}")
            return VisitorFlowResult(
                reply="أعتذر، حدث خطأ أثناء معالجة الطلب.",
                handled=False
            )

