# WhatsApp LID to Phone Number Resolution

## Problem

The WhatsApp bot was receiving sender IDs in LID format (e.g., `86496530956486@lid`) instead of actual phone numbers. When these LIDs were normalized (removing `@lid` suffix), they became `86496530956486`, which did NOT match the supervisor phone numbers stored in PostgreSQL (e.g., `201282692075`).

This caused authorization to fail because:
1. Supervisor Excel import stores phone as: `201282692075`
2. WhatsApp message.from contains: `86496530956486@lid`
3. Normalized: `86496530956486` ≠ `201282692075`

## Root Cause

WhatsApp Web (web.whatsapp.com) uses two types of identifiers:
- **Phone-based IDs**: `201282692075@c.us` (country code + number)
- **LIDs (Local IDs)**: `86496530956486@lid` (internal WhatsApp identifier)

The whatsapp-web.js library can expose either format depending on the WhatsApp Web session state.

## Solution

Implemented LID-to-phone resolution in `whatsapp-bot/src/handlers/messageHandler.js`:

### 1. Detection
```javascript
if (normalizedRawPhone.includes('@lid')) {
  // LID detected, needs resolution
}
```

### 2. Primary Resolution Method
Uses the whatsapp-web.js client's built-in `getContactLidAndPhone()` method:
```javascript
async function resolvePhoneFromLid(client, lid) {
  const normalizedLid = normalizeId(lid);
  const mappings = await client.getContactLidAndPhone([normalizedLid]);

  for (const mapping of mappings) {
    if (mapping?.pn) {
      return mapping.pn;  // Returns actual phone number
    }
  }
  return lid;
}
```

The `mapping.pn` field contains the actual phone number in format like `201282692075@c.us`.

### 3. Fallback Methods
If primary resolution fails:
- Try `message.getContact().number`
- Try `message.getContact().id` (if not LID)

### 4. Normalization
After resolution, the phone number is normalized:
```javascript
const phone = normalizePhone(resolvedPhone);
// Removes @c.us suffix and non-digits, resulting in: 201282692075
```

## Implementation Details

### Modified Files
- `whatsapp-bot/src/handlers/messageHandler.js`

### Key Functions Added
1. `normalizeId(id)` - Normalizes contact IDs
2. `resolvePhoneFromLid(client, lid)` - Resolves LID to phone number using whatsapp-web.js API

### Integration Point
In `handleIncomingMessage()`, after determining `rawPhone`:
```javascript
const rawPhone = isPrivateChat ? message.from : (message.author || message.from);
let resolvedPhone = rawPhone;

if (normalizedRawPhone.includes('@lid')) {
  const phoneNumber = await resolvePhoneFromLid(client, normalizedRawPhone);
  resolvedPhone = phoneNumber || resolvedPhone;
}

const phone = normalizePhone(resolvedPhone);
```

## Expected Flow

### Before Fix
```
WhatsApp message.from: 86496530956486@lid
→ normalizePhone(): 86496530956486
→ Backend lookup: NOT FOUND (supervisor has 201282692075)
→ Result: UNAUTHORIZED
```

### After Fix
```
WhatsApp message.from: 86496530956486@lid
→ Detect @lid: YES
→ resolvePhoneFromLid(): Returns 201282692075@c.us
→ normalizePhone(): 201282692075
→ Backend lookup: FOUND (matches supervisor)
→ Result: AUTHORIZED
```

## Debugging Output

The implementation includes comprehensive debugging:
- Prints all message._data fields
- Prints getContact() result
- Prints getChat() result
- Logs LID detection and resolution
- Logs final normalized phone number
- Logs payload sent to backend

## Testing

To verify the fix works:

1. Send a WhatsApp message from a supervisor whose phone is `201282692075` in PostgreSQL
2. Check logs for:
   - `Detected LID format, resolving to phone number...`
   - `LID resolved to phone number: { lid: ..., phone: ... }`
   - `Normalized phone: { normalizedPhone: 201282692075 }`
   - Backend should return a reply (not empty string)

## WhatsApp ID Formats Reference

| Format | Example | Description |
|--------|---------|-------------|
| Phone ID | `201282692075@c.us` | Standard phone-based ID |
| LID | `86496530956486@lid` | Local internal ID |
| Group ID | `1234567890@g.us` | Group chat ID |

The `getContactLidAndPhone()` API returns mappings with:
- `lid`: The LID (e.g., `86496530956486@lid`)
- `pn`: The phone number (e.g., `201282692075@c.us`)