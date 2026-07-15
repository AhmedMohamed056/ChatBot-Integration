const axios = require('axios');
const axiosRetry = require('axios-retry').default;
const config = require('./config');

const ragClient = axios.create({
  baseURL: config.RAG_API_URL,
  timeout: config.API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json'
  }
});

axiosRetry(ragClient, {
  retries: config.MAX_RETRIES,
  retryDelay: axiosRetry.exponentialDelay,
  retryCondition: (error) => {
    return axiosRetry.isRetryableError(error) || error.code === 'ECONNABORTED';
  }
});

module.exports = ragClient;
