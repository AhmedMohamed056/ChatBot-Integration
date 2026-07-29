const config = require('../config');
const logger = require('../utils/logger');
const { postInboundMessage } = require('../services/backendService');
const { isGroupMessage, shouldProcessGroupMessage } = require('../middleware/groupFilter');
const {
  hasCommandPrefix,
  isBotMentioned,
  shouldRespondToMessage,
} = require('../middleware/mentionFilter');

function normalizePhone(value) {
  if (!value) return '';
  return String(value).split('@')[0].replace(/\D/g, '');
}

async function handleIncomingMessage(message, client) {
  try {
    if (config.IGNORE_SELF && message?.fromMe) {
      return;
    }

    logger.info('Incoming WhatsApp message.', {
      from: message?.from,
      author: message?.author,
      body: message?.body,
      mentionedIds: message?.mentionedIds || [],
      fromMe: message?.fromMe,
    });

    const isPrivateChat = !(await isGroupMessage(message));

    if (isPrivateChat) {
      logger.info('Private chat message - processing immediately without filters.');
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

    const phone = normalizePhone(message.author || message.from);
    const text = typeof message?.body === 'string' ? message.body.trim() : '';

    if (!phone || !text) {
      return;
    }

    const payload = {
      phone,
      message: text,
      chat_type: isPrivateChat ? 'private' : 'group',
      external_chat_id: message.from,
      external_message_id: message.id?._serialized || message.id || null,
    };

    const data = await postInboundMessage(payload);
    const reply = typeof data?.reply === 'string' ? data.reply.trim() : '';

    if (reply) {
      await message.reply(reply);
      logger.info('Reply sent to WhatsApp.', {
        groupId: message.from,
        author: message.author || message.from,
      });
    }
  } catch (error) {
    logger.error('Failed to process message.', {
      error: error.message,
      groupId: message?.from,
      author: message?.author || message?.from,
      body: message?.body,
    });

    try {
      await message.reply(
        'Sorry, I could not reach the support service right now. Please try again in a moment.',
      );
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
