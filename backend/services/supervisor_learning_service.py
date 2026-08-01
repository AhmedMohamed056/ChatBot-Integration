"""Supervisor Learning Service - Phase 4 Supervisor Learning.

This service enables supervisors to teach the assistant stable campaign facts.
It integrates with the existing supervisor context injection architecture.

The learning flow:
1. Supervisor sends a message with teaching intent
2. Service extracts stable facts from the message
3. Facts are stored in the campaign_knowledge table
4. Future conversations automatically include these facts with highest priority

Knowledge Priority Order (as per requirements):
1. Campaign Knowledge (highest priority - supervisor-taught facts)
2. Campaign Snapshot
3. Conversation Memory
4. Calendar
5. RAG
6. General Knowledge
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from db.models import Campaign
from db.platform_models import Supervisor
from db.repositories.campaign_knowledge_repository import CampaignKnowledgeRepository
from services.campaign_knowledge_service import CampaignKnowledgeService, ExtractedKnowledge
from services.supervisor_context_service import SupervisorContext

logger = logging.getLogger(__name__)

class SupervisorLearningService:
    """Service for handling supervisor teaching and learning.

    This service:
    - Detects when a supervisor is teaching the assistant
    - Extracts stable facts from teaching messages
    - Stores facts in the campaign knowledge database
    - Provides integration with the existing message flow
    """

    # Keywords that explicitly indicate teaching intent
    TEACHING_INTENT_KEYWORDS = [
        # English
        "remember", "note this", "important fact", "learn this", "teach me",
        "tell the assistant", "the assistant should know", "fact:", "note:",
        "remember:", "important:", "know that", "keep in mind", "always remember",

        # Arabic
        "تذكر", "اذكر", "مهم", "حقيقة", "علم", "تعلم", "أخبر المساعد",
        "يجب أن يعرف المساعد", "حقيقة:", "ملاحظة:", "تذكر:", "مهم:",
        "ضع في اعتبارك", "تذكر دائما"
    ]

    # Phrases that indicate the supervisor is providing stable information
    STABLE_INFO_PATTERNS = [
        "our buses", "our bus", "the buses", "the bus",
        "meeting point", "assembly point", "gathering point",
        "vip buses", "special buses", "priority buses",
        "leave at", "depart at", "start at", "begin at",
        "gate", "door", "entrance", "location", "place",
        "every", "always", "all", "each", "any"
    ]

    def __init__(self, session: Session):
        self.session = session
        self.knowledge_service = CampaignKnowledgeService(session)
        self.repository = CampaignKnowledgeRepository(session)

    def should_learn_from_message(
        self,
        message: str,
        supervisor: Optional[Supervisor] = None,
        campaign: Optional[Campaign] = None
    ) -> bool:
        """Determine if a message contains teaching intent.

        Args:
            message: The supervisor's message text.
            supervisor: The supervisor object (optional, for context).
            campaign: The campaign object (optional, for context).

        Returns:
            True if the message appears to be teaching the assistant.
        """
        if not message or not message.strip():
            return False

        message_lower = message.strip().lower()

        # Skip questions immediately
        if message_lower.endswith('?'):
            return False

        # Check for explicit teaching keywords
        for keyword in self.TEACHING_INTENT_KEYWORDS:
            if keyword in message_lower:
                return True

        # If message is a declarative statement (not a question or command)
        if self._is_teaching_statement(message):
            return True

        # Check for stable information patterns (only if not a question)
        for pattern in self.STABLE_INFO_PATTERNS:
            if pattern in message_lower:
                return True

        return False

    def _is_teaching_statement(self, message: str) -> bool:
        """Check if a message is a teaching statement rather than a question or command."""
        message_lower = message.strip().lower()

        # Skip questions
        if message_lower.endswith('?'):
            return False

        # Skip commands/imperatives - check for command verbs at the start
        command_verbs = [
            'please ', 'can you ', 'could you ', 'would you ', 'will you ',
            'should ', 'do you ', 'does ', 'did ', 'is it ', 'are you ',
            'update ', 'change ', 'modify ', 'edit ', 'delete ', 'remove ',
            'create ', 'add ', 'set ', 'make ', 'send ', 'reply ', 'fix '
        ]
        for verb in command_verbs:
            if message_lower.startswith(verb):
                return False

        # Skip greetings and acknowledgments
        greetings = ['hello', 'hi', 'hey', 'thanks', 'thank you', 'ok', 'okay', 'yes', 'no']
        if any(message_lower.startswith(g + ' ') or message_lower == g for g in greetings):
            return False

        # Skip short messages
        if len(message.split()) < 3:
            return False

        # Check if the message contains command-like verbs anywhere
        # If it does, it's likely a command, not teaching
        command_words = ['update', 'change', 'modify', 'edit', 'delete', 'remove',
                        'create', 'add', 'set', 'make', 'send', 'reply', 'fix']
        message_words = message_lower.split()
        if any(word in message_words for word in command_words):
            return False

        # If it contains declarative phrases, it's likely teaching
        declarative_phrases = [
            'our ', 'the ', 'this ', 'that ', 'these ', 'those ',
            'is ', 'are ', 'was ', 'were ', 'has ', 'have ', 'at ', 'in ',
            'on ', 'by ', 'from ', 'to '
        ]
        for phrase in declarative_phrases:
            if phrase in message_lower:
                return True

        return False

    def extract_and_store_knowledge(
        self,
        message: str,
        supervisor: Supervisor,
        campaign: Optional[Campaign] = None
    ) -> List[ExtractedKnowledge]:
        """Extract knowledge from a supervisor message and store it.

        Args:
            message: The supervisor's message text.
            supervisor: The supervisor who sent the message.
            campaign: The campaign to associate knowledge with (optional).

        Returns:
            List of ExtractedKnowledge that were stored.
        """
        if not campaign:
            # Get the supervisor's campaign
            campaign = self._get_supervisor_campaign(supervisor)

        if not campaign:
            logger.warning(f"No campaign found for supervisor {supervisor.id}, cannot store knowledge")
            return []

        # Extract knowledge from the message
        extracted = self.knowledge_service.extract_knowledge_from_message(
            message=message,
            campaign=campaign,
            supervisor=supervisor
        )

        if not extracted:
            return []

        # Store the extracted knowledge
        stored = self.knowledge_service.store_extracted_knowledge(
            extracted_knowledge=extracted,
            campaign_id=campaign.id,
            created_by_supervisor_id=supervisor.id
        )

        logger.info(f"Stored {len(stored)} knowledge entries for campaign {campaign.id}")

        return extracted

    def _get_supervisor_campaign(self, supervisor: Supervisor) -> Optional[Campaign]:
        """Get the campaign owned by a supervisor."""
        from sqlalchemy import select
        return self.session.scalar(
            select(Campaign).where(Campaign.owner_supervisor_id == supervisor.id)
        )

    def process_learning_message(
        self,
        message: str,
        supervisor: Supervisor,
        campaign: Optional[Campaign] = None
    ) -> dict[str, Any]:
        """Process a supervisor message for learning.

        This is the main entry point for the learning service. It:
        1. Checks if the message contains teaching intent
        2. Extracts knowledge if it does
        3. Stores the knowledge
        4. Returns a result summary

        Args:
            message: The supervisor's message text.
            supervisor: The supervisor who sent the message.
            campaign: The campaign context (optional).

        Returns:
            Dictionary with learning results including:
            - learned: bool indicating if learning occurred
            - knowledge_stored: number of knowledge entries stored
            - extracted_facts: list of extracted facts
        """
        result = {
            "learned": False,
            "knowledge_stored": 0,
            "extracted_facts": [],
            "message": ""
        }

        # Check if this message should trigger learning
        if not self.should_learn_from_message(message, supervisor, campaign):
            result["message"] = "No teaching intent detected"
            return result

        # Extract and store knowledge
        extracted = self.extract_and_store_knowledge(
            message=message,
            supervisor=supervisor,
            campaign=campaign
        )

        result["learned"] = True
        result["knowledge_stored"] = len(extracted)
        result["extracted_facts"] = [k.fact_text for k in extracted]
        result["message"] = f"Learned {len(extracted)} new facts"

        return result

    def get_learning_summary(self, campaign_id: int) -> dict[str, Any]:
        """Get a summary of what has been learned for a campaign.

        Args:
            campaign_id: The campaign ID.

        Returns:
            Dictionary with learning summary including:
            - total_facts: number of active knowledge entries
            - facts_by_category: breakdown by category
            - recent_facts: most recently added facts
        """
        knowledge_entries = self.repository.get_all_by_campaign(
            campaign_id=campaign_id,
            is_active=True
        )

        # Count by category
        facts_by_category: dict[str, int] = {}
        for entry in knowledge_entries:
            category = entry.category or "general"
            facts_by_category[category] = facts_by_category.get(category, 0) + 1

        # Get recent facts (last 5)
        recent_facts = [
            entry.fact_text
            for entry in sorted(knowledge_entries, key=lambda x: x.created_at, reverse=True)[:5]
        ]

        return {
            "total_facts": len(knowledge_entries),
            "facts_by_category": facts_by_category,
            "recent_facts": recent_facts
        }

    def integrate_with_supervisor_context(
        self,
        supervisor_context: SupervisorContext,
        message: str
    ) -> dict[str, Any]:
        """Integrate learning with supervisor context.

        This method can be called during supervisor message processing
        to automatically extract and store knowledge.

        Args:
            supervisor_context: The supervisor context.
            message: The supervisor's message.

        Returns:
            Learning result dictionary.
        """
        from db.platform_models import Supervisor

        # Get supervisor from context
        supervisor = self.session.get(Supervisor, supervisor_context.phone)
        if not supervisor:
            return {"learned": False, "message": "Supervisor not found"}

        # Get campaign from context
        campaign_id = supervisor_context.campaign_id
        campaign = None
        if campaign_id:
            campaign = self.session.get(Campaign, campaign_id)

        return self.process_learning_message(
            message=message,
            supervisor=supervisor,
            campaign=campaign
        )