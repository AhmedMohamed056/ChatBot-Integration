const fs = require('fs');
const path = require('path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const logger = require('./utils/logger');
const { handleIncomingMessage } = require('./handlers/messageHandler');

const authPath = path.resolve(__dirname, '..', 'auth');

fs.mkdirSync(authPath, { recursive: true });

let clientInstance = null;
let initializationPromise = null;
let reconnectTimer = null;
let reconnectScheduled = false;

function createClient() {
  return new Client({
    authStrategy: new LocalAuth({
      clientId: 'support-bot',
      dataPath: authPath,
    }),
    puppeteer: {
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
      ],
    },
  });
}

function attachLifecycleHandlers(client) {
  client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    logger.info('WhatsApp QR code generated.');
  });

  client.once('authenticated', () => {
    logger.info('WhatsApp authentication succeeded.');
  });

  client.once('ready', () => {
    logger.info('WhatsApp client is ready.');
  });

  client.on('disconnected', (reason) => {
    logger.warn('WhatsApp client disconnected.', {
      reason,
    });

    clientInstance = null;
    initializationPromise = null;

    // A single delayed retry keeps reconnect behavior deterministic and avoids duplicate clients.
    if (!reconnectScheduled) {
      reconnectScheduled = true;

      reconnectTimer = setTimeout(async () => {
        reconnectTimer = null;
        reconnectScheduled = false;

        try {
          await startBot();
        } catch (error) {
          logger.error('Failed to reconnect WhatsApp client.', {
            error: error.message,
          });
        }
      }, 5000);
    }
  });

  client.once('auth_failure', (message) => {
    logger.error('WhatsApp authentication failed.', {
      message,
    });
  });

  client.on('loading_screen', (percent, message) => {
    logger.info('WhatsApp loading screen update.', {
      percent,
      message,
    });
  });

  client.on('change_state', (state) => {
    logger.info('WhatsApp state changed.', {
      state,
    });
  });

  client.on('error', (error) => {
    logger.error('WhatsApp client reported an error.', {
      error: error.message,
    });
  });

  client.on('message', async (message) => {
    try {
      await handleIncomingMessage(message, client);
    } catch (error) {
      logger.error('Unhandled error in message event.', {
        error: error.message,
      });
    }
  });
}

async function stopBot() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  reconnectScheduled = false;

  if (clientInstance) {
    try {
      await clientInstance.destroy();
    } catch (error) {
      logger.error('Failed to destroy WhatsApp client during shutdown.', {
        error: error.message,
      });
    }
  }

  clientInstance = null;
  initializationPromise = null;
}

async function startBot() {
  if (clientInstance) {
    return clientInstance;
  }

  if (initializationPromise) {
    return initializationPromise;
  }

  initializationPromise = (async () => {
    const client = createClient();
    attachLifecycleHandlers(client);

    const readyPromise = new Promise((resolve, reject) => {
      client.once('ready', () => {
        resolve();
      });

      client.once('auth_failure', (message) => {
        reject(new Error(message));
      });
    });

    try {
      await client.initialize();
      await readyPromise;

      clientInstance = client;
      logger.info('WhatsApp client initialized successfully.');
      return client;
    } catch (error) {
      try {
        await client.destroy();
      } catch (destroyError) {
        logger.error('Failed to destroy the WhatsApp client after initialization failure.', {
          error: destroyError.message,
        });
      }

      clientInstance = null;
      initializationPromise = null;

      throw error;
    }
  })();

  return initializationPromise;
}

module.exports = {
  startBot,
  stopBot,
};
