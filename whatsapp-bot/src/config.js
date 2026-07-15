const dotenv = require('dotenv');

dotenv.config();

const requiredEnvKeys = [
  'BOT_NAME',
  'BOT_PREFIX',
  'RAG_API_URL',
  'LOG_LEVEL',
  'API_TIMEOUT',
  'ALLOW_GROUPS',
  'REQUIRE_MENTION',
  'IGNORE_SELF',
  'IGNORE_STATUS',
  'MAX_RETRIES'
];

function readRequiredEnv(key) {
  const value = process.env[key];

  if (value === undefined || value === null || String(value).trim() === '') {
    throw new Error(`Missing required environment variable: ${key}`);
  }

  return value;
}

function parseBoolean(value, key) {
  const normalized = String(value).trim().toLowerCase();

  if (normalized === 'true') {
    return true;
  }

  if (normalized === 'false') {
    return false;
  }

  throw new Error(`Invalid boolean value for ${key}: ${value}`);
}

function parseInteger(value, key) {
  const parsed = Number.parseInt(String(value).trim(), 10);

  if (Number.isNaN(parsed)) {
    throw new Error(`Invalid integer value for ${key}: ${value}`);
  }

  return parsed;
}

requiredEnvKeys.forEach((key) => readRequiredEnv(key));

const config = Object.freeze({
  BOT_NAME: readRequiredEnv('BOT_NAME').trim(),
  BOT_PREFIX: readRequiredEnv('BOT_PREFIX').trim(),
  RAG_API_URL: readRequiredEnv('RAG_API_URL').trim(),
  LOG_LEVEL: readRequiredEnv('LOG_LEVEL').trim(),
  API_TIMEOUT: parseInteger(readRequiredEnv('API_TIMEOUT'), 'API_TIMEOUT'),
  ALLOW_GROUPS: parseBoolean(readRequiredEnv('ALLOW_GROUPS'), 'ALLOW_GROUPS'),
  ALLOWED_GROUP_IDS: (() => {
    const rawValue = process.env.ALLOWED_GROUP_IDS;

    if (rawValue === undefined || rawValue === null || String(rawValue).trim() === '') {
      return [];
    }

    return String(rawValue)
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean);
  })(),
  REQUIRE_MENTION: parseBoolean(readRequiredEnv('REQUIRE_MENTION'), 'REQUIRE_MENTION'),
  IGNORE_SELF: parseBoolean(readRequiredEnv('IGNORE_SELF'), 'IGNORE_SELF'),
  IGNORE_STATUS: parseBoolean(readRequiredEnv('IGNORE_STATUS'), 'IGNORE_STATUS'),
  MAX_RETRIES: parseInteger(readRequiredEnv('MAX_RETRIES'), 'MAX_RETRIES')
});

module.exports = config;
