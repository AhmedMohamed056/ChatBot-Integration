const config = require('../config');
const logger = require('../utils/logger');
const { postInboundMessage } = require('../services/backendService');
const { isGroupMessage, shouldProcessGroupMessage } = require('../middleware/groupFilter');
const {
  hasCommandPrefix,
  isBotMentioned,
  shouldRespondToMessage,
  expandContactIds,
} = require('../middleware/mentionFilter');

function normalizePhone(value) {
  if (!value) return '';
  return String(value).split('@')[0].replace(/\D/g, '');
}

function normalizeId(id) {
  return typeof id === 'string' ? id : id?._serialized || '';
}

async function resolvePhoneFromLid(client, lid) {
  if (!lid || typeof client.getContactLidAndPhone !== 'function') {
    return lid;
  }

  try {
    const normalizedLid = normalizeId(lid);
    const mappings = await client.getContactLidAndPhone([normalizedLid]);

    for (const mapping of mappings) {
      if (mapping?.pn) {
        // Return the phone number if found
        return mapping.pn;
      }
    }
  } catch (error) {
    logger.info('Failed to resolve LID to phone:', { error: error.message, lid });
  }

  return lid;
}

async function handleIncomingMessage(message, client) {
  try {
    if (config.IGNORE_SELF && message?.fromMe) {
      return;
    }

    // Debug logs
    logger.info('=== DEBUG: Raw WhatsApp message data ===');
    logger.info('Raw WhatsApp sender (message.from):', { from: message?.from });
    logger.info('Raw WhatsApp author (message.author):', { author: message?.author });
    logger.info('Raw message.id:', { message_id: message?.id });
    logger.info('Raw message.id._serialized:', { message_id_serialized: message?.id?._serialized });
    logger.info('Raw chat id (message.from):', { chat_id: message?.from });

    // PRINT ALL AVAILABLE SENDER INFORMATION
    logger.info('=== FULL SENDER DEBUG ===');
    logger.info('message.from:', message?.from);
    logger.info('message.author:', message?.author);
    logger.info('message.id:', message?.id);
    logger.info('message._data:', JSON.stringify(message?._data, null, 2));
    logger.info('message._data.id:', message?._data?.id);
    logger.info('message._data.from:', message?._data?.from);
    logger.info('message._data.author:', message?._data?.author);
    logger.info('message._data.chat:', message?._data?.chat);
    logger.info('message._data.chatId:', message?._data?.chatId);
    logger.info('message._data.sender:', message?._data?.sender);
    logger.info('message._data.contact:', message?._data?.contact);

    // Inspect getContact()
    try {
      const contact = await message.getContact();
      logger.info('=== getContact() result ===');
      logger.info('contact:', JSON.stringify(contact, null, 2));
      logger.info('contact.id:', contact?.id);
      logger.info('contact.number:', contact?.number);
      logger.info('contact.pushname:', contact?.pushname);
      logger.info('contact.shortName:', contact?.shortName);
      logger.info('contact.userid:', contact?.userid);
    } catch (e) {
      logger.info('getContact() error:', e.message);
    }

    // Inspect getChat()
    try {
      const chat = await message.getChat();
      logger.info('=== getChat() result ===');
      logger.info('chat:', JSON.stringify(chat, null, 2));
    } catch (e) {
      logger.info('getChat() error:', e.message);
    }

    const isPrivateChat = !(await isGroupMessage(message));

    if (isPrivateChat) {
      logger.info('Private chat message - authorization decided by backend supervisors table.');
    } else {
      if (!(await shouldProcessGroupMessage(message))) {
        return;
      }

      const mentioned = await isBotMentioned(message, client);
      const shouldRespond = await shouldRespondToMessage(message, client);

      logger.info('Group message trigger check.', {
        groupId: message.from,
        mentioned,
        hasPrefix: hasCommandPrefix(message),
        shouldRespond,
      });

      if (!shouldRespond) {
        return;
      }
    }

    // For private chats, use message.from (sender's phone@c.us)
    // For groups, use message.author (sender's phone@c.us)
    const rawPhone = isPrivateChat ? message.from : (message.author || message.from);

    // RESOLVE LID TO PHONE NUMBER
    // If the rawPhone contains @lid, we need to resolve it to the actual phone number
    const normalizedRawPhone = normalizeId(rawPhone);
    let resolvedPhone = rawPhone;

    if (normalizedRawPhone.includes('@lid')) {
      logger.info('Detected LID format, resolving to phone number...', {
        lid: normalizedRawPhone,
      });
      const phoneNumber = await resolvePhoneFromLid(client, normalizedRawPhone);
      if (phoneNumber && phoneNumber !== normalizedRawPhone) {
        resolvedPhone = phoneNumber;
        logger.info('LID resolved to phone number:', {
          lid: normalizedRawPhone,
          phone: phoneNumber,
        });
      } else {
        logger.info('LID resolution failed, using contact.getContact() as fallback...', {
          lid: normalizedRawPhone,
        });
        // Fallback: try to get contact info
        try {
          const contact = await message.getContact();
          if (contact?.number) {
            resolvedPhone = contact.number;
            logger.info('Fallback: using contact.number:', {
              contactNumber: contact.number,
            });
          } else if (contact?.id && !contact.id.includes('@lid')) {
            resolvedPhone = contact.id;
            logger.info('Fallback: using contact.id:', {
              contactId: contact.id,
            });
          }
        } catch (e) {
          logger.info('Fallback failed, using raw phone:', {
            error: e.message,
          });
        }
      }
    }

    const phone = normalizePhone(resolvedPhone);
    const text = typeof message?.body === 'string' ? message.body.trim() : '';

    // Debug logs for phone normalization
    logger.info('Computed phone (raw):', { rawPhone });
    logger.info('Normalized phone:', { normalizedPhone: phone });

    if (!phone || !text) {
      return;
    }

    // Fix: external_message_id must be a string, use message.id._serialized
    const externalMessageId = message.id?._serialized || (message.id?.id ? String(message.id.id) : null);

    const payload = {
      phone,
      message: text,
      chat_type: isPrivateChat ? 'private' : 'group',
      external_chat_id: message.from,
      external_message_id: externalMessageId,
    };

    // Debug log for final payload
    logger.info('Payload sent to backend:', { payload });

    const data = await postInboundMessage(payload);
    const reply = typeof data?.reply === 'string' ? data.reply.trim() : '';

    // Empty reply = unauthorized ignore mode or no-op. Do not send anything.
    if (!reply) {
      if (isPrivateChat) {
        logger.info('Private message ignored (empty backend reply / unauthorized).', {
          phoneSuffix: phone.slice(-4),
        });
      }
      return;
    }

    await message.reply(reply);
    logger.info('Reply sent to WhatsApp.', {
      groupId: message.from,
      author: message.author || message.from,
    });
  } catch (error) {
    logger.error('Failed to process message.', {
      error: error.message,
      groupId: message?.from,
      author: message?.author || message?.from,
      body: message?.body,
    });

    // Never invent replies for private chats on transport failure —
    // that would look like an unauthorized assistant answering.
    try {
      const isPrivate = !(await isGroupMessage(message));
      if (!isPrivate) {
        await message.reply(
          'Sorry, I could not reach the support service right now. Please try again in a moment.',
        );
      }
    } catch (replyError) {
      logger.error('Failed to send error reply.', {
        error: replyError.message,
      });
    }
  }
}

module.exports = {
  handleIncomingMessage,
};
