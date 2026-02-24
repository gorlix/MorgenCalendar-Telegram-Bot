# Morgen Calendar Telegram Bot

An asynchronous, robust Telegram Bot that integrates with the Morgen Calendar API. You can self-host this bot via Docker and interact with your calendars seamlessly.

## Features

- **Multi-User Structure**: Uses SQLite down to securely hold users and Morgen API keys.
- **Internationalization (i18n)**: Supports multiple languages (English and Italian) via JSON locale files, saving user preferences automatically to the database.
- **Enhanced Onboarding**: A centralized `/start` dashboard features quick-action buttons for Guided Creation, Quick Add, Agenda, and Settings.
- **Centralized Settings Menu**: Use `/settings` as a hub to manage both language and daily agenda preferences in one place using inline buttons.
- **Daily Summaries (Agenda)**: The bot sends an automated daily agenda summary at a user-defined time, managed securely per-user via APScheduler.
- **Quick Event Creation**: Uses a fast natural syntax (`/add`) or an interactive wizard (`/new`) to build events.
- **Agenda Fetching**: Use `/agenda` to see what is scheduled for Today or Tomorrow.
- **Docker & Tech Stack**: Uses Python 3.11 with `aiosqlite`, `httpx`, and `python-telegram-bot` for robust non-blocking capabilities, all containerized for easy self-hosting.

## Setup Requirements

1. **Telegram Bot Token**: Get one from [@BotFather](https://t.me/BotFather) on Telegram.
2. **Docker & Docker Compose**: Ensure these are installed on your server or local machine.

## Deployment Instructions

1. Clone this repository (or copy the project files to your server).
2. Inside the root directory, export your Telegram token into your shell environment (or create a `.env` file if supported by your compose version):
   ```bash
   export TELEGRAM_TOKEN="your_token_here"
   ```
3. Boot up the bot using Docker Compose:
   ```bash
   docker-compose up -d --build
   ```

*(Note: The `docker-compose.yml` mounts a `./data` folder to persist your `morgen_bot.db` SQLite database across container restarts.)*

## Usage Details

When you start the bot via `/start` on Telegram, it will ask for your **Morgen API Key**. You can find it at:
https://platform.morgen.so/developers-api

Once authenticated, the `/start` command acts as your interactive dashboard. You can also use commands directly:
- **Quick Event**: Use `/add <Title> <DD-MM> <HH:MM> [Duration]` for rapid action (e.g., `/add Lunch with Anna 24-02 13:00 1H30M`).
- **Guided Event**: Use `/new` to spawn an interactive step-by-step inline keyboard wizard.
- **Agenda**: Use `/agenda` to browse local events for today or tomorrow.
- **Settings**: Use `/settings` to manage your preferred language and configure automated daily summaries.

Have fun and stay organized!
## Architecture
The application uses a modular architecture where `main.py` acts as the central entrypoint, while specific functionality is isolated within the `handlers/` and `tasks/` packages.

### ⚠️ Important Note on Morgen API Rate Limits

The Morgen API enforces a strict rate limit to ensure system stability: **100 points every 15 minutes**.

Fetching calendar events is an "expensive" operation (costs 10 points per calendar batch). While this bot uses advanced "smart batching" to minimize point usage, users with a large number of connected calendars (e.g., 10+) who spam the `/agenda` command might temporarily deplete their points.

If this happens, the bot is not broken! It will simply notify you to wait a few minutes until the points reset. You can read more about these constraints built into the platform in the official documentation: https://docs.morgen.so/rate-limits
