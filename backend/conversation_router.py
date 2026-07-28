"""Conversation Router.

This module provides a centralized routing mechanism for incoming messages.
It determines which flow (VisitorFlow, SupervisorFlow, etc.) should handle
each message based on routing logic.

Current implementation: Routes to SupervisorFlow or VisitorFlow based on phone number.
"""

import sys
from pathlib import Path
import logging

# Add backend directory to path for imports
file_path = Path(__file__).resolve()
parent_dir = file_path.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from visitor_flow import VisitorFlow, VisitorFlowResult
from supervisor_flow import SupervisorFlow, SupervisorFlowResult
from config import is_supervisor
from backend.conversation_state_manager import ConversationStateManager

# Set up logging
logger = logging.getLogger(__name__)

class ConversationRouter:
    """Router for incoming conversation messages.

    Routes messages to the appropriate flow based on business logic.
    Routes to SupervisorFlow if phone is in supervisor list, otherwise to VisitorFlow.

    Architecture:
        POST /message
                │
                ▼
        ConversationRouter
                │
                ├──────── SupervisorFlow (if phone is supervisor)
                │
                └──────── VisitorFlow (if phone is visitor)
    """

    def __init__(self):
        """Initialize the ConversationRouter."""
        self._visitor_flow = VisitorFlow()
        self._supervisor_flow = SupervisorFlow(ConversationStateManager())
        self._state_manager = ConversationStateManager()

    def route_message(
        self,
        phone: str,
        message: str
    ) -> str:
        """Route an incoming message to the appropriate flow.

        Parameters
        ----------
        phone : str
            The sender's phone number.
        message : str
            The incoming message text.

        Returns
        -------
        str
            The reply text from the appropriate flow.

        Routing Rules:
        - If phone belongs to supervisor: SupervisorFlow.handle_message(...)
        - Else: VisitorFlow.handle_message(...)
        """
        # Log incoming phone
        logger.info(f"Incoming phone: {phone}")

        # Detect role
        if is_supervisor(phone):
            logger.info(f"Detected role: Supervisor")
            result: SupervisorFlowResult = self._supervisor_flow.handle_message(
                phone=phone,
                message=message
            )
            return result.reply
        else:
            logger.info(f"Detected role: Visitor")
            result: VisitorFlowResult = self._visitor_flow.handle_message(
                phone=phone,
                message=message
            )
            return result.reply
