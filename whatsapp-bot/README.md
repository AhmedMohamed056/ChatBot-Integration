# WhatsApp Bot

This project is the WhatsApp integration layer for the FastAPI backend.

## Project structure

- `src/` contains the application entry point and the main bot modules.
- `src/index.js` is the startup entry point for the service.
- `src/bot.js` is the bot bootstrap placeholder.
- `src/config.js` centralizes environment-based configuration and validates required values at startup.
- `src/ragClient.js` exposes a reusable Axios client configured from the environment.
- `src/handlers/` contains message handling modules.
- `src/commands/` contains command entry modules.
- `src/services/` contains integration service modules.
- `src/utils/` contains shared utilities such as the logger.
- `src/middleware/` contains request and message filtering middleware placeholders.
- `auth/` is reserved for authentication-related local files and should remain outside version control.

## Purpose of the core foundation files

### `config.js`

This file loads all variables from `.env`, validates the required settings, and exports a frozen configuration object for the rest of the service.

### `logger.js`

This file provides a reusable Winston-based logger that reads the configured log level and exports a shared logger instance.

### `ragClient.js`

This file provides a reusable Axios instance configured with the backend URL, timeout, and retry settings from configuration.

### `middleware/`

This folder contains middleware placeholders for filtering and rate-limiting behavior.

## Development

This project includes standard developer tooling to keep the codebase consistent.

### ESLint

ESLint is configured for Node.js, CommonJS, and ES2022 with the recommended rule set and the `import` plugin enabled.

### Prettier

Prettier is configured with the project formatting rules and is intended to keep JavaScript files consistent across the workspace.

### EditorConfig

EditorConfig is provided to keep indentation, line endings, and whitespace handling consistent across editors.

### Logs

The `logs/` directory is reserved for local runtime logs and is intentionally excluded from git tracking except for the placeholder `.gitkeep` file.
