const config = require('../config');

function normalizeId(id) {
  return typeof id === 'string' ? id : id?._serialized || '';
}

function extractPrompt(message) {
  const body = typeof message?.body === 'string' ? message.body : '';
  const trimmed = body.trim();

  if (trimmed.startsWith(config.BOT_PREFIX)) {
    return trimmed.slice(config.BOT_PREFIX.length).replace(/^\s+/, '').trim();
  }

  return trimmed
    .replace(/@\S+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function hasCommandPrefix(message) {
  const body = typeof message?.body === 'string' ? message.body.trim() : '';
  return body.startsWith(config.BOT_PREFIX);
}

async function expandContactIds(client, ids) {
  const expanded = new Set(ids.map(normalizeId).filter(Boolean));

  if (!expanded.size || typeof client.getContactLidAndPhone !== 'function') {
    return expanded;
  }

  try {
    const mappings = await client.getContactLidAndPhone([...expanded]);

    for (const mapping of mappings) {
      if (mapping?.lid) {
        expanded.add(normalizeId(mapping.lid));
      }

      if (mapping?.pn) {
        expanded.add(normalizeId(mapping.pn));
      }
    }
  } catch {
    // Keep the original ids when lid/phone expansion is unavailable.
  }

  return expanded;
}

async function resolveBotIds(client) {
  const botId = normalizeId(client?.info?.wid);
  const ids = botId ? [botId] : [];
  return expandContactIds(client, ids);
}

function idsOverlap(leftIds, rightIds) {
  for (const id of leftIds) {
    if (rightIds.has(id)) {
      return true;
    }
  }

  return false;
}

async function isBotMentioned(message, client) {
  const mentionedIds = Array.isArray(message?.mentionedIds) ? message.mentionedIds : [];

  if (!mentionedIds.length) {
    return false;
  }

  const botIds = await resolveBotIds(client);
  const mentionIds = await expandContactIds(
    client,
    mentionedIds.map(normalizeId),
  );

  if (idsOverlap(botIds, mentionIds)) {
    return true;
  }

  try {
    const mentions = await message.getMentions();

    for (const contact of mentions) {
      const contactIds = await expandContactIds(client, [normalizeId(contact.id)]);

      if (idsOverlap(botIds, contactIds)) {
        return true;
      }
    }
  } catch {
    // Fall back to the metadata-based mention check above.
  }

  return false;
}

async function shouldRespondToMessage(message, client) {
  if (!config.REQUIRE_MENTION) {
    return true;
  }

  if (hasCommandPrefix(message)) {
    return true;
  }

  return isBotMentioned(message, client);
}

module.exports = {
  extractPrompt,
  hasCommandPrefix,
  isBotMentioned,
  shouldRespondToMessage,
};
