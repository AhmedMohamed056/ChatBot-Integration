"""Test Suite for Phase 4 - Supervisor Learning Implementation.

This test suite validates:
1. CampaignKnowledge model and repository
2. Knowledge extraction from supervisor messages
3. Integration with AIContext and PromptBuilder
4. Priority-based context injection
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import models and services
from db.base import Base
from db.models import Campaign, CampaignKnowledge
from db.platform_models import Supervisor
from db.repositories.campaign_knowledge_repository import CampaignKnowledgeRepository
from services.campaign_knowledge_service import (
    CampaignKnowledgeService,
    CampaignKnowledgeData,
    ExtractedKnowledge
)
from services.supervisor_learning_service import SupervisorLearningService
from ai_context_builder import AIContext, build_context
from prompt_builder import build_prompt

# Test database setup
class TestDatabase:
    """In-memory SQLite database for testing."""

    @classmethod
    def create_session(cls):
        """Create a new test database session."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        return Session()

    @classmethod
    def setup_test_data(cls, session):
        """Create test data for the test suite."""
        # Create a test supervisor
        supervisor = Supervisor(
            phone_number="+201234567890",
            display_name="Test Supervisor",
            is_active=True
        )
        session.add(supervisor)
        session.commit()
        session.refresh(supervisor)

        # Create a test campaign
        campaign = Campaign(
            campaign_name="Test Campaign",
            owner_supervisor_id=supervisor.id,
            status="active"
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        return supervisor, campaign

# =============================================================================
# Test Cases
# =============================================================================

class TestCampaignKnowledgeModel(unittest.TestCase):
    """Test the CampaignKnowledge SQLAlchemy model."""

    def setUp(self):
        self.session = TestDatabase.create_session()
        self.supervisor, self.campaign = TestDatabase.setup_test_data(self.session)

    def tearDown(self):
        self.session.close()

    def test_campaign_knowledge_creation(self):
        """Test creating a CampaignKnowledge entry."""
        knowledge = CampaignKnowledge(
            campaign_id=self.campaign.id,
            fact_text="Our buses leave at 6 AM",
            category="timing",
            source_type="supervisor",
            created_by_supervisor_id=self.supervisor.id,
            version=1
        )
        self.session.add(knowledge)
        self.session.commit()

        # Verify the entry was created
        retrieved = self.session.get(CampaignKnowledge, knowledge.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.fact_text, "Our buses leave at 6 AM")
        self.assertEqual(retrieved.category, "timing")
        self.assertEqual(retrieved.campaign_id, self.campaign.id)
        self.assertTrue(retrieved.is_active)

    def test_campaign_knowledge_relationship(self):
        """Test the relationship between Campaign and CampaignKnowledge."""
        knowledge = CampaignKnowledge(
            campaign_id=self.campaign.id,
            fact_text="Meeting point is Gate 4",
            category="location"
        )
        self.session.add(knowledge)
        self.session.commit()

        # Verify the relationship
        self.session.refresh(self.campaign)
        self.assertEqual(len(self.campaign.knowledge_entries), 1)
        self.assertEqual(self.campaign.knowledge_entries[0].fact_text, "Meeting point is Gate 4")

class TestCampaignKnowledgeRepository(unittest.TestCase):
    """Test the CampaignKnowledgeRepository."""

    def setUp(self):
        self.session = TestDatabase.create_session()
        self.supervisor, self.campaign = TestDatabase.setup_test_data(self.session)
        self.repository = CampaignKnowledgeRepository(self.session)

    def tearDown(self):
        self.session.close()

    def test_create_knowledge(self):
        """Test creating knowledge through repository."""
        knowledge = self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="VIP buses use Gate B",
            category="logistics",
            source_type="supervisor",
            created_by_supervisor_id=self.supervisor.id
        )

        self.assertIsNotNone(knowledge)
        self.assertEqual(knowledge.fact_text, "VIP buses use Gate B")
        self.assertEqual(knowledge.version, 1)

    def test_get_all_by_campaign(self):
        """Test retrieving all knowledge for a campaign."""
        # Create multiple knowledge entries
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Fact 1",
            category="general"
        )
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Fact 2",
            category="timing"
        )
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Fact 3",
            category="location",
            is_active=False  # Inactive
        )

        # Get all active knowledge
        active_knowledge = self.repository.get_all_by_campaign(
            campaign_id=self.campaign.id,
            is_active=True
        )
        self.assertEqual(len(active_knowledge), 2)

        # Get all including inactive
        all_knowledge = self.repository.get_all_by_campaign(
            campaign_id=self.campaign.id,
            is_active=False
        )
        self.assertEqual(len(all_knowledge), 3)

    def test_get_active_knowledge_texts(self):
        """Test retrieving active knowledge texts."""
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Our buses leave at 6 AM"
        )
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Meeting point is Gate 4"
        )
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Inactive fact",
            is_active=False
        )

        texts = self.repository.get_active_knowledge_texts(self.campaign.id)
        self.assertEqual(len(texts), 2)
        self.assertIn("Our buses leave at 6 AM", texts)
        self.assertIn("Meeting point is Gate 4", texts)
        self.assertNotIn("Inactive fact", texts)

    def test_deactivate_knowledge(self):
        """Test deactivating a knowledge entry."""
        knowledge = self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Test fact"
        )

        result = self.repository.deactivate(knowledge.id)
        self.assertTrue(result)

        # Verify it's deactivated
        retrieved = self.repository.get_by_id(knowledge.id)
        self.assertFalse(retrieved.is_active)

    def test_exists(self):
        """Test checking if knowledge exists."""
        self.repository.create(
            campaign_id=self.campaign.id,
            fact_text="Existing fact"
        )

        self.assertTrue(self.repository.exists(self.campaign.id, "Existing fact"))
        self.assertFalse(self.repository.exists(self.campaign.id, "Non-existent fact"))

class TestCampaignKnowledgeService(unittest.TestCase):
    """Test the CampaignKnowledgeService."""

    def setUp(self):
        self.session = TestDatabase.create_session()
        self.supervisor, self.campaign = TestDatabase.setup_test_data(self.session)
        self.service = CampaignKnowledgeService(self.session)

    def tearDown(self):
        self.session.close()

    def test_extract_knowledge_from_message(self):
        """Test extracting knowledge from supervisor messages."""
        # Test with timing information
        message = "Our buses leave at 6 AM and return at 8 PM"
        extracted = self.service.extract_knowledge_from_message(message)

        self.assertGreater(len(extracted), 0)
        self.assertTrue(any("6 AM" in k.fact_text for k in extracted))

        # Test with location information
        message = "Meeting point is Gate 4"
        extracted = self.service.extract_knowledge_from_message(message)
        self.assertGreater(len(extracted), 0)

    def test_store_knowledge(self):
        """Test storing knowledge."""
        knowledge = self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Test fact to store",
            category="general",
            created_by_supervisor_id=self.supervisor.id
        )

        self.assertIsNotNone(knowledge)
        self.assertEqual(knowledge.fact_text, "Test fact to store")

    def test_duplicate_knowledge_not_stored(self):
        """Test that duplicate knowledge is not stored."""
        # Store first time
        knowledge1 = self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Duplicate fact"
        )
        self.assertIsNotNone(knowledge1)

        # Try to store again
        knowledge2 = self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Duplicate fact"
        )
        self.assertIsNone(knowledge2)

    def test_get_knowledge_for_prompt(self):
        """Test retrieving knowledge formatted for prompts."""
        self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Fact 1"
        )
        self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Fact 2"
        )

        knowledge = self.service.get_knowledge_for_prompt(self.campaign.id)
        self.assertEqual(len(knowledge), 2)
        self.assertIn("Fact 1", knowledge)
        self.assertIn("Fact 2", knowledge)

    def test_get_campaign_knowledge(self):
        """Test getting structured campaign knowledge."""
        self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Timing fact",
            category="timing"
        )
        self.service.store_knowledge(
            campaign_id=self.campaign.id,
            fact_text="Location fact",
            category="location"
        )

        knowledge_data = self.service.get_campaign_knowledge(self.campaign.id)
        self.assertEqual(knowledge_data.campaign_id, self.campaign.id)
        self.assertEqual(len(knowledge_data.knowledge_entries), 2)
        self.assertIn("timing", knowledge_data.categories)
        self.assertIn("location", knowledge_data.categories)

class TestSupervisorLearningService(unittest.TestCase):
    """Test the SupervisorLearningService."""

    def setUp(self):
        self.session = TestDatabase.create_session()
        self.supervisor, self.campaign = TestDatabase.setup_test_data(self.session)
        self.service = SupervisorLearningService(self.session)

    def tearDown(self):
        self.session.close()

    def test_should_learn_from_message(self):
        """Test detecting teaching intent in messages."""
        # Should learn from teaching messages
        self.assertTrue(self.service.should_learn_from_message(
            "Remember: Our buses leave at 6 AM"
        ))
        self.assertTrue(self.service.should_learn_from_message(
            "Note this: Meeting point is Gate 4"
        ))
        self.assertTrue(self.service.should_learn_from_message(
            "Our buses leave at 6 AM"
        ))

        # Should not learn from questions
        self.assertFalse(self.service.should_learn_from_message(
            "What time do the buses leave?"
        ))

        # Should not learn from short messages
        self.assertFalse(self.service.should_learn_from_message(
            "OK"
        ))

    def test_process_learning_message(self):
        """Test processing a learning message."""
        result = self.service.process_learning_message(
            message="Our buses leave at 6 AM",
            supervisor=self.supervisor,
            campaign=self.campaign
        )

        self.assertTrue(result["learned"])
        self.assertGreater(result["knowledge_stored"], 0)
        self.assertGreater(len(result["extracted_facts"]), 0)

    def test_get_learning_summary(self):
        """Test getting a learning summary."""
        # Add some knowledge first
        self.service.process_learning_message(
            message="Our buses leave at 6 AM",
            supervisor=self.supervisor,
            campaign=self.campaign
        )
        self.service.process_learning_message(
            message="Meeting point is Gate 4",
            supervisor=self.supervisor,
            campaign=self.campaign
        )

        summary = self.service.get_learning_summary(self.campaign.id)
        self.assertGreater(summary["total_facts"], 0)
        self.assertIn("recent_facts", summary)

class TestAIContextIntegration(unittest.TestCase):
    """Test integration with AIContextBuilder."""

    def setUp(self):
        self.session = TestDatabase.create_session()
        self.supervisor, self.campaign = TestDatabase.setup_test_data(self.session)

        # Add knowledge to the campaign
        from db.repositories.campaign_knowledge_repository import CampaignKnowledgeRepository
        repo = CampaignKnowledgeRepository(self.session)
        repo.create(
            campaign_id=self.campaign.id,
            fact_text="Our buses leave at 6 AM",
            category="timing"
        )
        repo.create(
            campaign_id=self.campaign.id,
            fact_text="Meeting point is Gate 4",
            category="location"
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_ai_context_includes_campaign_knowledge(self):
        """Test that AIContext includes campaign_knowledge field."""
        ctx = AIContext()
        self.assertIsNone(ctx.campaign_knowledge)

        ctx_with_knowledge = AIContext(
            campaign_knowledge=["Fact 1", "Fact 2"]
        )
        self.assertEqual(len(ctx_with_knowledge.campaign_knowledge), 2)

    def test_build_context_with_campaign_knowledge(self):
        """Test that build_context loads campaign knowledge."""
        # This test would need mocking or a real database
        # For now, just verify the field exists
        ctx = build_context(
            message="Test message",
            phone="+201234567890"  # This would trigger campaign lookup
        )
        # campaign_knowledge field should exist
        self.assertTrue(hasattr(ctx, 'campaign_knowledge'))

class TestPromptBuilderIntegration(unittest.TestCase):
    """Test integration with PromptBuilder."""

    def test_campaign_knowledge_section_in_prompt(self):
        """Test that campaign knowledge appears in prompts."""
        ctx = AIContext(
            campaign_knowledge=["Our buses leave at 6 AM", "Meeting point is Gate 4"],
            raw_message="What time do buses leave?"
        )

        prompt = build_prompt("You are a helpful assistant.", ctx)

        # Verify campaign knowledge section is present
        self.assertIn("CAMPAIGN KNOWLEDGE", prompt)
        self.assertIn("Our buses leave at 6 AM", prompt)
        self.assertIn("Meeting point is Gate 4", prompt)
        self.assertIn("highest priority", prompt)

    def test_campaign_knowledge_priority(self):
        """Test that campaign knowledge has highest priority in prompt."""
        ctx = AIContext(
            campaign_knowledge=["Fact 1"],
            supervisor={"supervisor_name": "Test", "phone": "+123"},
            visitor={"visitor_name": "Visitor", "phone": "+456"},
            raw_message="Test"
        )

        prompt = build_prompt("System prompt", ctx)

        # Campaign knowledge should appear before supervisor and visitor
        knowledge_pos = prompt.find("CAMPAIGN KNOWLEDGE")
        supervisor_pos = prompt.find("SUPERVISOR")
        visitor_pos = prompt.find("VISITOR")

        self.assertLess(knowledge_pos, supervisor_pos)
        self.assertLess(knowledge_pos, visitor_pos)

    def test_empty_campaign_knowledge_not_included(self):
        """Test that empty campaign knowledge is not included in prompt."""
        ctx = AIContext(
            campaign_knowledge=None,
            raw_message="Test"
        )

        prompt = build_prompt("System prompt", ctx)
        self.assertNotIn("CAMPAIGN KNOWLEDGE", prompt)

    def test_empty_campaign_knowledge_list_not_included(self):
        """Test that empty campaign knowledge list is not included in prompt."""
        ctx = AIContext(
            campaign_knowledge=[],
            raw_message="Test"
        )

        prompt = build_prompt("System prompt", ctx)
        self.assertNotIn("CAMPAIGN KNOWLEDGE", prompt)

# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("Phase 4 - Supervisor Learning Implementation Tests")
    print("=" * 80)
    print()

    # Run all tests
    unittest.main(verbosity=2)