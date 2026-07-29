const axios = require('axios');
const config = require('../config');

function apiBaseUrl() {
  const raw = process.env.RAG_API_URL || config.RAG_API_URL || 'http://localhost:8000';
  return raw.replace(/\/$/, '');
}

async function postInboundMessage(payload) {
  const url = `${apiBaseUrl()}/message`;
  const response = await axios.post(url, payload, {
    timeout: Number(process.env.BACKEND_TIMEOUT_MS || 60000),
    headers: { 'Content-Type': 'application/json' },
  });
  return response.data;
}

module.exports = {
  postInboundMessage,
};
