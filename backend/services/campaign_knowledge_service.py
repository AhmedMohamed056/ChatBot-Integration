"""Campaign Knowledge Service - Phase 4 Supervisor Learning.

This service handles the extraction, storage, and retrieval of stable campaign facts
taught by supervisors. It integrates with the existing context injection architecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from db.models import Campaign, CampaignKnowledge
from db.platform_models import Supervisor
from db.repositories.campaign_knowledge_repository import CampaignKnowledgeRepository

@dataclass
class ExtractedKnowledge:
    """Represents knowledge extracted from a supervisor message."""

    fact_text: str
    category: str = "general"
    confidence: float = 1.0
    source_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_text": self.fact_text,
            "category": self.category,
            "confidence": self.confidence,
            "source_message": self.source_message
        }

@dataclass
class CampaignKnowledgeData:
    """Structured campaign knowledge for context injection."""

    campaign_id: Optional[int] = None
    knowledge_entries: List[str] = field(default_factory=list)
    categories: dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for context injection."""
        return {
            "campaign_id": self.campaign_id,
            "knowledge_entries": self.knowledge_entries,
            "categories": self.categories
        }

class CampaignKnowledgeService:
    """Service for managing supervisor-taught campaign knowledge.

    This service:
    - Extracts stable facts from supervisor messages
    - Stores them in the database associated with campaigns
    - Retrieves knowledge for context injection
    - Manages knowledge lifecycle (activation, deactivation, updates)
    """

    # Patterns for detecting stable facts in messages
    FACT_PATTERNS = [
        # Timing patterns
        (r"\b(at|in|on|by|from|to)\s+\d{1,2}\s*(AM|PM|am|pm)\b", "timing"),
        (r"\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)?\b", "timing"),
        (r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", "timing"),

        # Location patterns
        (r"\b(Gate|Door|Entrance|Exit|Building|Room|Hall|Floor|Level)\s+\w+", "location"),
        (r"\b(Address|Location|Place|Venue|Meeting Point|Assembly Point)\b", "location"),
        (r"\b\w+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Square|Plaza)\b", "location"),

        # Logistics patterns
        (r"\b(Bus|Buses|Van|Vans|Car|Cars|Transport|Vehicle)\s+\w+", "logistics"),
        (r"\b(VIP|Special|Priority|Standard|Regular)\s+\w+", "logistics"),

        # General fact patterns (declarative statements)
        (r"\b(Our|We|The|This)\s+\w+", "general"),
        (r"\b(Always|Every|All|Each|Any)\s+\w+", "general"),
    ]

    # Keywords that indicate a teaching intent
    TEACHING_KEYWORDS = [
        "remember", "note", "important", "fact", "know", "learn", "teach",
        "tell", "inform", "update", "set", "make", "is", "are", "was", "were",
        "اذكر", "تذكر", "مهم", "حقيقة", "علم", "تعلم", "أخبر", "أبلغ",
        "ضع", "اجعل", "هو", "هي", "هم", "كان", "كانت"
    ]

    def __init__(self, session: Session):
        self.session = session
        self.repository = CampaignKnowledgeRepository(session)

    def extract_knowledge_from_message(
        self,
        message: str,
        campaign: Optional[Campaign] = None,
        supervisor: Optional[Supervisor] = None
    ) -> List[ExtractedKnowledge]:
        """Extract potential knowledge facts from a supervisor message.

        Uses pattern matching and heuristics to identify stable facts
        that should be stored as campaign knowledge.

        Args:
            message: The supervisor's message text.
            campaign: Optional campaign context for validation.
            supervisor: Optional supervisor context.

        Returns:
            List of ExtractedKnowledge objects representing potential facts.
        """
        if not message or not message.strip():
            return []

        extracted = []
        message_lower = message.lower()

        # Check if message has teaching intent
        has_teaching_intent = any(
            keyword in message_lower
            for keyword in self.TEACHING_KEYWORDS
        )

        if not has_teaching_intent:
            # Even without explicit teaching keywords, check for declarative facts
            # that look like stable information
            pass

        # Apply fact patterns
        for pattern, category in self.FACT_PATTERNS:
            matches = re.finditer(pattern, message, re.IGNORECASE)
            for match in matches:
                fact_text = match.group(0).strip()

                # Skip very short matches
                if len(fact_text.split()) < 2:
                    continue

                # Check if this is a complete sentence or meaningful phrase
                if self._is_meaningful_fact(fact_text):
                    extracted.append(ExtractedKnowledge(
                        fact_text=fact_text,
                        category=category,
                        confidence=0.9,
                        source_message=message
                    ))

        # If we found pattern-based facts, return them
        if extracted:
            return extracted

        # Fallback: Try to extract complete sentences as facts
        sentences = re.split(r'[.!?]', message)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence.split()) >= 3:  # At least 3 words
                # Check if it's a declarative statement
                if self._is_declarative(sentence):
                    extracted.append(ExtractedKnowledge(
                        fact_text=sentence,
                        category="general",
                        confidence=0.7,
                        source_message=message
                    ))

        return extracted

    def _is_meaningful_fact(self, text: str) -> bool:
        """Check if text represents a meaningful fact."""
        # Skip questions
        if text.endswith('?') or text.lower().startswith(('what', 'when', 'where', 'who', 'why', 'how')):
            return False

        # Skip very short text
        if len(text.split()) < 2:
            return False

        # Skip greetings and common phrases
        common_phrases = ['hello', 'hi', 'hey', 'thanks', 'thank you', 'please', 'ok', 'okay']
        text_lower = text.lower()
        if any(phrase in text_lower for phrase in common_phrases):
            return False

        return True

    def _is_declarative(self, sentence: str) -> bool:
        """Check if a sentence is declarative (statement of fact)."""
        sentence_lower = sentence.lower()

        # Skip questions
        if sentence_lower.endswith('?'):
            return False

        # Skip imperative (commands)
        if sentence_lower.startswith(('please ', 'can you ', 'could you ', 'do you')):
            return False

        # Skip greetings
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
        if any(sentence_lower.startswith(g) for g in greetings):
            return False

        return True

    def store_knowledge(
        self,
        campaign_id: int,
        fact_text: str,
        category: str = "general",
        source_type: str = "supervisor",
        created_by_supervisor_id: Optional[int] = None
    ) -> Optional[CampaignKnowledge]:
        """Store a new knowledge fact for a campaign.

        Args:
            campaign_id: The campaign ID to associate with.
            fact_text: The fact text to store.
            category: Category for organizing knowledge.
            source_type: How this knowledge was acquired.
            created_by_supervisor_id: The supervisor who taught this.

        Returns:
            The created CampaignKnowledge entry, or None if failed.
        """
        # Check if this fact already exists
        if self.repository.exists(campaign_id, fact_text):
            return None

        return self.repository.create(
            campaign_id=campaign_id,
            fact_text=fact_text,
            category=category,
            source_type=source_type,
            created_by_supervisor_id=created_by_supervisor_id
        )

    def store_extracted_knowledge(
        self,
        extracted_knowledge: List[ExtractedKnowledge],
        campaign_id: int,
        created_by_supervisor_id: Optional[int] = None
    ) -> List[CampaignKnowledge]:
        """Store multiple extracted knowledge entries.

        Args:
            extracted_knowledge: List of ExtractedKnowledge to store.
            campaign_id: The campaign ID to associate with.
            created_by_supervisor_id: The supervisor who taught these.

        Returns:
            List of created CampaignKnowledge entries.
        """
        created = []
        for knowledge in extracted_knowledge:
            stored = self.store_knowledge(
                campaign_id=campaign_id,
                fact_text=knowledge.fact_text,
                category=knowledge.category,
                source_type="supervisor",
                created_by_supervisor_id=created_by_supervisor_id
            )
            if stored:
                created.append(stored)
        return created

    def get_campaign_knowledge(
        self,
        campaign_id: int,
        include_inactive: bool = False
    ) -> CampaignKnowledgeData:
        """Get all knowledge for a campaign formatted for context injection.

        Args:
            campaign_id: The campaign ID.
            include_inactive: Whether to include inactive knowledge entries.

        Returns:
            CampaignKnowledgeData with knowledge entries organized by category.
        """
        knowledge_entries = self.repository.get_all_by_campaign(
            campaign_id=campaign_id,
            is_active=not include_inactive
        )

        # Organize by category
        categories: dict[str, List[str]] = {}
        all_entries: List[str] = []

        for entry in knowledge_entries:
            if entry.category not in categories:
                categories[entry.category] = []
            categories[entry.category].append(entry.fact_text)
            all_entries.append(entry.fact_text)

        return CampaignKnowledgeData(
            campaign_id=campaign_id,
            knowledge_entries=all_entries,
            categories=categories
        )

    def get_knowledge_for_prompt(self, campaign_id: int) -> List[str]:
        """Get knowledge entries formatted for prompt injection.

        Returns a clean list of fact texts suitable for including in prompts.

        Args:
            campaign_id: The campaign ID.

        Returns:
            List of fact text strings.
        """
        return self.repository.get_active_knowledge_texts(campaign_id)

    def deactivate_knowledge(self, knowledge_id: int) -> bool:
        """Deactivate a knowledge entry.

        Args:
            knowledge_id: The knowledge entry ID.

        Returns:
            True if deactivated, False if not found.
        """
        return self.repository.deactivate(knowledge_id)

    def update_knowledge(
        self,
        knowledge_id: int,
        fact_text: Optional[str] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[CampaignKnowledge]:
        """Update a knowledge entry.

        Args:
            knowledge_id: The knowledge entry ID.
            fact_text: New fact text (optional).
            category: New category (optional).
            is_active: New active status (optional).

        Returns:
            The updated CampaignKnowledge entry, or None if not found.
        """
        return self.repository.update(
            knowledge_id=knowledge_id,
            fact_text=fact_text,
            category=category,
            is_active=is_active
        )

    def get_knowledge_count(self, campaign_id: int) -> int:
        """Get the count of active knowledge entries for a campaign.

        Args:
            campaign_id: The campaign ID.

        Returns:
            The count of active knowledge entries.
        """
        return self.repository.get_knowledge_count(campaign_id, is_active=True)

    def clear_campaign_knowledge(self, campaign_id: int) -> int:
        """Clear all knowledge entries for a campaign.

        Args:
            campaign_id: The campaign ID.

        Returns:
            The number of entries deleted.
        """
        knowledge_entries = self.repository.get_all_by_campaign(
            campaign_id=campaign_id,
            is_active=False  # Get all including inactive
        )

        count = 0
        for entry in knowledge_entries:
            self.repository.delete(entry.id)
            count += 1

        return count