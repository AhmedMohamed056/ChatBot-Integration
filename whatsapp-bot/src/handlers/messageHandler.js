const config = require('../config');
const logger = require('../utils/logger');
const { spawn } = require('child_process');
const path = require('path');
const { isGroupMessage, shouldProcessGroupMessage } = require('../middleware/groupFilter');
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

    // Check if this is a private chat (not a group)
    const isPrivateChat = !(await isGroupMessage(message));

    // For private chats: ALWAYS process, no filters required
    if (isPrivateChat) {
      logger.info('Private chat message - processing immediately without filters.');
    } else {
      // For group chats: apply existing group filters
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

    // Call the Python handle_incoming_message function
    const pythonExecutable = process.env.PYTHON_EXECUTABLE || "python";
    const pythonScript = path.join(__dirname, '..', 'whatsapp_handler.py');
    const pythonProcess = spawn(pythonExecutable, [pythonScript, phone, text]);

    let reply = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      reply += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    await new Promise((resolve, reject) => {
      pythonProcess.on('close', (code) => {
        if (errorOutput) {
          logger.error('Python subprocess stderr:', { data: errorOutput });
        }
        if (code !== 0) {
          logger.error('Python subprocess failed.', { code });
          reject(new Error(`Python subprocess failed with code ${code}`));
        } else {
          resolve();
        }
      });
    });

    // Send the reply back to WhatsApp
    if (reply) {
      await message.reply(reply.trim());
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
