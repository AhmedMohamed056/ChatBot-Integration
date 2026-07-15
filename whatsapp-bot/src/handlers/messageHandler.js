const config = require('../config');
const logger = require('../utils/logger');
const ragClient = require('../ragClient');
const { shouldProcessGroupMessage } = require('../middleware/groupFilter');
const {
  extractPrompt,
  hasCommandPrefix,
  isBotMentioned,
  shouldRespondToMessage,
} = require('../middleware/mentionFilter');

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

    const prompt = extractPrompt(message);

    if (!prompt) {
      await message.reply(
        `Hi! Mention me or use ${config.BOT_PREFIX} with your question.\nExample: @${config.BOT_NAME} what is your return policy?\nOr: ${config.BOT_PREFIX} what is your return policy?`,
      );
      return;
    }

    logger.info('Processing group message.', {
      groupId: message.from,
      author: message.author || message.from,
      prompt,
    });

    const response = await ragClient.post('', {
      message: prompt,
      session_id: message.author || message.from,
    });

    const reply = response?.data?.reply;

    if (reply) {
      await message.reply(reply);
      logger.info('Group reply sent.', {
        groupId: message.from,
        author: message.author || message.from,
      });
    }
  } catch (error) {
    logger.error('Failed to process group message.', {
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
