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

function normalizePhone(value) {
  if (!value) return '';
  return String(value).split('@')[0].replace(/\D/g, '');
}

async function tryCampaignUpdate(message) {
  const phone = normalizePhone(message.author || message.from);
  const body = typeof message?.body === 'string' ? message.body.trim() : '';

  if (!phone || !body) {
    return false;
  }

  try {
    const response = await ragClient.post('/campaign/update', {
      phone,
      message: body,
    });

    if (response?.data?.ok) {
      if (response.data.stored) {
        await message.reply('تم حفظ تحديث الحملة.');
      }
      logger.info('Campaign update processed.', {
        phone,
        stored: response.data.stored,
        reason: response.data.reason,
      });
      return true;
    }
  } catch (error) {
    if (error?.response?.status === 404) {
      return false;
    }
    logger.error('Campaign update request failed.', {
      phone,
      error: error.message,
    });
  }

  return false;
}

function parseLearnCommand(body) {
  const trimmed = typeof body === 'string' ? body.trim() : '';

  if (!trimmed.toLowerCase().startsWith('!learn')) {
    return null;
  }

  const payload = trimmed.replace(/^!learn\b/i, '').trim();

  if (!payload) {
    return null;
  }

  const separatorMatch = payload.match(/^(.*?)(?:\s*\|\s*|\s*=>\s*)(.*)$/s);

  if (!separatorMatch) {
    return null;
  }

  const question = separatorMatch[1].trim();
  const answer = separatorMatch[2].trim();

  if (!question || !answer) {
    return null;
  }

  return { question, answer };
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

    if (await tryCampaignUpdate(message)) {
      return;
    }

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

    const rawBody = typeof message?.body === 'string' ? message.body.trim() : '';
    const learnCommand = parseLearnCommand(rawBody);

    if (learnCommand) {
      const response = await ragClient.post('/learn', {
        question: learnCommand.question,
        answer: learnCommand.answer,
        source: 'whatsapp_admin',
      });

      const reply = response?.data?.message || 'Knowledge saved successfully.';
      await message.reply(reply);
      logger.info('WhatsApp knowledge saved.', {
        groupId: message.from,
        author: message.author || message.from,
        question: learnCommand.question,
      });
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

    const response = await ragClient.post('/chat', {
      message: prompt,
      session_id: message.author || message.from,
      source: 'whatsapp',
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
