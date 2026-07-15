const dotenv = require('dotenv');
const config = require('./config');
const logger = require('./utils/logger');
const { startBot, stopBot } = require('./bot');

dotenv.config();

let botClient = null;
let shuttingDown = false;

async function shutdown(signal) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  logger.warn(`Received ${signal}. Shutting down WhatsApp bot...`);

  try {
    await stopBot();
    logger.info('WhatsApp bot shutdown completed.');
  } catch (error) {
    logger.error('Error while stopping WhatsApp bot during shutdown.', {
      error: error.message,
    });
  }

  process.exit(0);
}

async function main() {
  try {
    logger.info('Starting WhatsApp bot...', {
      botName: config.BOT_NAME,
      botPrefix: config.BOT_PREFIX,
    });

    botClient = await startBot();
    logger.info('WhatsApp bot started successfully.');
  } catch (error) {
    logger.error('Fatal startup error while initializing WhatsApp bot.', {
      error: error.message,
    });
    process.exit(1);
  }
}

process.on('SIGINT', () => {
  shutdown('SIGINT');
});

process.on('SIGTERM', () => {
  shutdown('SIGTERM');
});

main();
