# Phase 4 - Supervisor Learning Implementation

## Overview

This implementation enables supervisors to teach the assistant stable campaign facts that are automatically stored and used in future conversations with the highest priority.

## Goal

Allow supervisors to teach the assistant facts like:
- "Our buses leave at 6 AM"
- "Meeting point is Gate 4"
- "VIP buses use Gate B"

These facts are:
- Detected as stable campaign information
- Stored in the database associated with the campaign
- Automatically included in future conversations
- Given highest priority in the context injection order

## Knowledge Priority Order

As per requirements, the context injection priority is:

1. **Campaign Knowledge** (highest priority - supervisor-taught facts)
2. Campaign Snapshot
3. Conversation Memory
4. Calendar
5. RAG
6. General Knowledge

## Files Modified

### Database Models (`backend/db/models.py`)
- Added `CampaignKnowledge` model with fields:
  - `id`: Primary key
  - `campaign_id`: Foreign key to campaigns table
  - `fact_text`: The stable fact text
  - `category`: For organizing knowledge (timing, location, logistics, general)
  - `source_type`: How knowledge was acquired (supervisor, import, auto_extracted)
  - `is_active`: Whether this knowledge should be used
  - `version`: Version number for tracking updates
  - `created_by_supervisor_id`: Which supervisor created this
  - `created_at`, `updated_at`: Timestamps

### Repository (`backend/db/repositories/campaign_knowledge_repository.py`)
- New repository providing CRUD operations for CampaignKnowledge
- Methods:
  - `get_by_id()`: Get a knowledge entry by ID
  - `get_all_by_campaign()`: Get all knowledge for a campaign
  - `get_active_knowledge_texts()`: Get active knowledge texts for prompt injection
  - `get_by_category()`: Get knowledge by category
  - `create()`: Create a new knowledge entry
  - `update()`: Update an existing entry
  - `deactivate()`: Deactivate a knowledge entry
  - `delete()`: Delete a knowledge entry
  - `exists()`: Check if knowledge exists
  - `get_knowledge_count()`: Get count of knowledge entries

### Services

#### Campaign Knowledge Service (`backend/services/campaign_knowledge_service.py`)
- Handles extraction, storage, and retrieval of campaign knowledge
- Uses pattern matching to detect stable facts in messages
- Provides methods for:
  - Extracting knowledge from supervisor messages
  - Storing extracted knowledge
  - Retrieving knowledge for context injection
  - Managing knowledge lifecycle

#### Supervisor Learning Service (`backend/services/supervisor_learning_service.py`)
- Main service for handling supervisor teaching
- Detects teaching intent in messages
- Integrates with campaign knowledge service
- Provides learning summary and statistics

### AI Context Builder (`backend/ai_context_builder.py`)
- Added `campaign_knowledge` field to `AIContext` dataclass
- Added `_load_campaign_knowledge()` helper function
- Integrated campaign knowledge loading into `build_context()`
- Knowledge is loaded for both phone-based and supervisor-based contexts

### Prompt Builder (`backend/prompt_builder.py`)
- Added `_campaign_knowledge_section()` to build CAMPAIGN KNOWLEDGE section
- Integrated campaign knowledge section into `build_prompt()`
- **Campaign Knowledge section has HIGHEST priority** - placed before Supervisor, Visitor, Calendar, etc.
- Section includes clear instructions that these are authoritative facts that should override other information

### Tests (`backend/test_supervisor_learning.py`)
- Comprehensive test suite with 21 tests covering:
  - CampaignKnowledge model creation and relationships
  - Repository CRUD operations
  - Knowledge extraction from messages
  - Knowledge storage and retrieval
  - AIContext integration
  - PromptBuilder integration
  - Learning service functionality
  - Priority ordering validation

## Storage Design

### Database Table: `campaign_knowledge`

```sql
CREATE TABLE campaign_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    fact_text TEXT NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'general',
    source_type VARCHAR(50) NOT NULL DEFAULT 'supervisor',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_by_supervisor_id INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_supervisor_id) REFERENCES supervisors(id) ON DELETE SET NULL
);

INDEXES:
- ix_campaign_knowledge_campaign_id
- ix_campaign_knowledge_category
- ix_campaign_knowledge_active
- ix_campaign_knowledge_campaign_active
```

### Key Design Decisions

1. **Append-only with versioning**: Knowledge entries are never overwritten. Updates increment the version number.
2. **Soft deletion**: Knowledge can be deactivated rather than deleted, preserving history.
3. **Category organization**: Knowledge is organized by category for better management.
4. **Source tracking**: Tracks how knowledge was acquired (supervisor, import, auto_extracted).
5. **Campaign association**: Each knowledge entry is associated with a specific campaign.

## Knowledge Extraction

The system uses multiple approaches to extract knowledge from supervisor messages:

1. **Pattern matching**: Uses regex patterns to detect:
   - Timing information (times, dates)
   - Location information (gates, doors, addresses)
   - Logistics information (buses, vehicles, VIP)
   - General declarative statements

2. **Teaching intent detection**: Checks for keywords like:
   - "remember", "note", "important", "fact", "know", "learn", "teach"
   - Arabic equivalents

3. **Declarative statement detection**: Identifies complete sentences that are statements of fact.

## Usage Examples

### Supervisor teaches the assistant:

```python
# Supervisor sends message
message = "Our buses leave at 6 AM and return at 8 PM"

# System detects teaching intent and extracts knowledge
learning_service.process_learning_message(
    message=message,
    supervisor=supervisor,
    campaign=campaign
)

# Knowledge is stored in database
```

### Future conversation uses the knowledge:

```python
# Visitor asks a question
message = "What time do the buses leave?"

# AIContext includes campaign knowledge
ctx = build_context(
    message=message,
    phone=visitor_phone
)

# Prompt includes CAMPAIGN KNOWLEDGE section with highest priority
prompt = build_prompt(system_prompt, ctx)
```

### Prompt Example:

```
SYSTEM PROMPT
========================

CURRENT CONTEXT
CURRENT DATE / DAY
Current Date: 2026-07-30
Current Day: السبت
------------------------
LANGUAGE
Language: en
------------------------
CAMPAIGN KNOWLEDGE
Stable facts taught by the campaign supervisor. Use these with highest priority.
These are authoritative facts about the campaign that should override any other information.
Fact 1: Our buses leave at 6 AM
Fact 2: Meeting point is Gate 4
Fact 3: VIP buses use Gate B
------------------------
SUPERVISOR
You are speaking with an authorized campaign supervisor.
...
```

## Validation

All 21 tests pass, covering:
- Model creation and relationships
- Repository operations
- Knowledge extraction
- Storage and retrieval
- Context injection
- Priority ordering
- Learning service functionality

## Integration Points

The implementation integrates with existing architecture:
- Uses existing database session management
- Follows existing repository patterns
- Integrates with AIContextBuilder and PromptBuilder
- Reuses existing service patterns
- Compatible with existing supervisor context injection

## Future Enhancements

- Add API endpoints for manual knowledge management
- Add admin interface for viewing/editing knowledge
- Implement knowledge validation and approval workflow
- Add knowledge expiration/auto-deactivation
- Implement knowledge versioning and history tracking
- Add knowledge search and filtering capabilities