const config = require('../config');

function isStatusBroadcast(message) {
  return message?.from === 'status@broadcast';
}

async function isGroupMessage(message) {
  if (!message) {
    return false;
  }

  if (typeof message.from === 'string' && message.from.endsWith('@g.us')) {
    return true;
  }

  try {
    const chat = await message.getChat();
    return Boolean(chat?.isGroup);
  } catch {
    return false;
  }
}

function isAllowedGroup(message) {
  if (!config.ALLOWED_GROUP_IDS.length) {
    return true;
  }

  return config.ALLOWED_GROUP_IDS.includes(message.from);
}

async function shouldProcessGroupMessage(message) {
  if (config.IGNORE_STATUS && isStatusBroadcast(message)) {
    return false;
  }

  if (!config.ALLOW_GROUPS) {
    return false;
  }

  const inGroup = await isGroupMessage(message);

  if (!inGroup) {
    return false;
  }

  return isAllowedGroup(message);
}

module.exports = {
  isGroupMessage,
  isAllowedGroup,
  shouldProcessGroupMessage,
};
