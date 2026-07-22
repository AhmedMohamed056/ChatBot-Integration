const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');
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

async function createClient() {
  console.log('[DEBUG] createClient: start');
  // whatsapp-web.js bundles its own nested puppeteer@24.x which expects a
  // different Chrome revision than the top-level puppeteer@25.x.  Resolve the
  // executable from the top-level puppeteer (the one `npx puppeteer browsers
  // install chrome` installs for) and pass it explicitly so the nested
  // puppeteer does not look for a missing Chrome build.
  const executablePath = await puppeteer.executablePath();
  console.log('[DEBUG] createClient: executablePath =', executablePath);

  const client = new Client({
    authStrategy: new LocalAuth({
      clientId: 'support-bot',
      dataPath: authPath,
    }),
    puppeteer: {
      executablePath,
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
      ],
    },
  });
  console.log('[DEBUG] createClient: Client constructed');
  return client;
}

function attachLifecycleHandlers(client) {
  client.on('qr', (qr) => {
    console.log('[DEBUG] qr event received');
    qrcode.generate(qr, { small: true });
    logger.info('WhatsApp QR code generated.');
  });

  client.once('authenticated', () => {
    console.log('[DEBUG] authenticated event received');
    logger.info('WhatsApp authentication succeeded.');
  });

  client.once('ready', () => {
    console.log('[DEBUG] ready event received');
    logger.info('WhatsApp client is ready.');
  });

  client.on('disconnected', (reason) => {
    console.log('[DEBUG] disconnected event received:', reason);
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
    const client = await createClient();
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
