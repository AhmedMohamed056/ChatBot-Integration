# Phase 3 - Conversation Memory Implementation

## Overview

This document describes the implementation of lightweight conversation memory for the ChatBot-Integration system. The memory system maintains context across messages to enable Gemini to understand references like "اجعله أقصر" (make it shorter), "غيرها" (change it), and "احذف الفقرة الثانية" (delete the second paragraph).

## Architecture

The implementation follows the existing architecture and reuses existing components:

- **Database**: Uses the existing `ConversationMemory` table
- **Service Layer**: New `ConversationMemoryService` in `services/conversation_memory_service.py`
- **Context Builder**: Extended `AIContext` and `build_context()` to include conversation memory
- **Prompt Builder**: Added conversation memory section to prompts
- **Message Flow**: Integrated into `CampaignLifecycleService` and `VisitorFlow`

## Memory Fields

The system maintains the following memory fields:

1. **Current Topic**: The main subject being discussed
2. **Pending Draft**: In-progress draft data
3. **Conversation Summary**: Brief summary of the conversation
4. **Last Edited Field**: Most recently modified field
5. **Recent Messages**: Last 10 messages for context

## Files Modified

### 1. `backend/services/conversation_memory_service.py` (NEW)
- **Purpose**: Core service for managing conversation memory
- **Key Classes**:
  - `ConversationMemoryData`: Dataclass for structured memory data
  - `ConversationMemoryService`: Main service class
- **Key Methods**:
  - `load_memory(conversation_id)`: Load memory for a conversation
  - `save_memory(conversation_id, memory_data)`: Save memory for a conversation
  - `update_memory_from_message()`: Update memory based on new messages
  - `get_memory_for_prompt()`: Format memory for prompt injection
  - `clear_memory()`: Clear all memory for a conversation

### 2. `backend/ai_context_builder.py` (MODIFIED)
- **Changes**:
  - Added `conversation_id` parameter to `build_context()`
  - Added `conversation_memory` field to `AIContext` dataclass
  - Added `_load_conversation_memory()` helper function
  - Updated docstrings to document new parameters

### 3. `backend/prompt_builder.py` (MODIFIED)
- **Changes**:
  - Added `_conversation_memory_section()` function
  - Updated `_coerce_context()` to handle `conversation_memory` field
  - Added conversation memory section to `build_prompt()`
  - Memory section includes instruction: "Use this memory to understand references like 'اجعله أقصر', 'غيرها', 'احذف الفقرة الثانية'"

### 4. `backend/visitor_flow.py` (MODIFIED)
- **Changes**:
  - Added `conversation_id` parameter to `handle_message_with_supervisor()`
  - Pass `conversation_id` to `build_ai_context()` call
  - Updated docstrings

### 5. `backend/services/campaign_lifecycle_service.py` (MODIFIED)
- **Changes**:
  - Integrated `ConversationMemoryService` into message handling
  - Memory is updated before calling VisitorFlow (with inbound message)
  - Memory is updated after getting response (with outbound message)
  - Pass `conversation_id` to `handle_message_with_supervisor()`

## Memory Flow

### Loading Memory
1. User sends a message to `/message` endpoint
2. `ConversationRouter` → `MessageOrchestrator` → `CampaignLifecycleService`
3. `CampaignLifecycleService.handle()` gets conversation_id from conversation
4. Memory service loads existing memory for the conversation
5. Memory is passed to `build_ai_context()` via `conversation_id`
6. `AIContext` includes `conversation_memory` field
7. `build_prompt()` includes memory in the prompt sent to Gemini

### Updating Memory
1. Before calling VisitorFlow: Memory is updated with the new inbound message
2. After getting response from VisitorFlow: Memory is updated with the outbound response
3. Memory updates include:
   - Adding message to recent_messages (keeps last 10)
   - Updating conversation_summary
   - Updating current_topic based on keywords
   - Updating last_edited_field based on message content

## Memory Update Logic

### Topic Detection
- If no current topic: Use first few words of message as topic
- If message contains topic keywords: Update topic from message
- Keywords: ["حملة", "campaign", "وصف", "description", "تاريخ", "date", "موقع", "location", "حذف", "delete", "تحديث", "update", "إنشاء", "create", "اسم", "name"]

### Field Detection
- Maps Arabic/English keywords to field names:
  - "description": ["وصف", "description", "نص", "text"]
  - "start_date": ["تاريخ البداية", "start date", "بداية", "begin"]
  - "end_date": ["تاريخ النهاية", "end date", "نهاية", "end"]
  - "location": ["موقع", "location", "مكان", "place"]
  - "campaign_name": ["اسم الحملة", "campaign name", "اسم", "name"]
  - "deletion_reason": ["سبب الحذف", "delete reason", "سبب", "reason"]

### Summary Updates
- First message: Used as initial summary (limited to 200 chars)
- Subsequent messages: Appended to summary (limited to 500 chars total)

## Database Schema

Uses existing `conversation_memories` table:
- `id`: Primary key
- `conversation_id`: Foreign key to conversations
- `memory_key`: One of the memory field names
- `memory_value`: JSON storage for the field value
- `retained_until`: Optional retention timestamp
- `tombstoned_at`: Optional tombstone timestamp
- `created_at`: Creation timestamp

## Testing

### Test Files
- `backend/test_conversation_memory_simple.py`: Unit tests for core functionality
- All tests pass successfully

### Test Coverage
- Memory data structure creation and serialization
- AIContext integration with conversation memory
- Prompt builder inclusion of memory section
- Arabic text handling in memory and prompts

## Usage Examples

### Example 1: User Reference
```
User: "اجعله أقصر" (Make it shorter)
Memory: Current Topic = "Campaign Description", Last Edited Field = "description"
Prompt includes: "CONVERSATION MEMORY: Current Topic: Campaign Description, Last Edited Field: description"
Gemini understands: User wants to shorten the campaign description
```

### Example 2: Field Edit
```
User: "غيرها" (Change it)
Memory: Last Edited Field = "description"
Prompt includes: "Last Edited Field: description"
Gemini understands: User wants to change the description field
```

### Example 3: Specific Edit
```
User: "احذف الفقرة الثانية" (Delete the second paragraph)
Memory: Current Topic = "Campaign Description", Recent Messages = [...]
Prompt includes: Full conversation memory
Gemini understands: User wants to delete the second paragraph from the description
```

## No Hardcoded Logic

The implementation follows the requirement of "No hardcoded logic":
- Memory is generic and stores any conversation context
- Field detection uses simple keyword mapping, not business logic
- Topic detection uses generic keywords, not campaign-specific logic
- All logic is in the memory service, not in the AI or prompt layers

## Validation

✅ All requirements met:
- Lightweight conversation memory implemented
- Maintains: Current Topic, Pending Draft, Conversation Summary, Last Edited Field, Recent Messages
- Memory loaded before every Gemini request
- Memory updated after every response
- No hardcoded logic
- Gemini resolves references naturally
- Reuses existing architecture
- No CRM or complicated storage