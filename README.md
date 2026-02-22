# Morgen Calendar Telegram Bot

An asynchronous, robust Telegram Bot that integrates with the Morgen Calendar API. You can self-host this bot via Docker and interact with your calendars seamlessly.

## Features

- **Multi-User Structure**: Uses SQLite down to securely hold users and Morgen API keys.
- **Natural Interaction**: Uses structured (`/add`) or interactive (`/new`) methods to build events.
- **Agenda Fetching**: Use `/agenda` to see what is scheduled for Today or Tomorrow.
- **Daily Summaries**: Every morning at 07:00 AM, the bot will message you the agenda for the day.
- **Completely Asynchronous**: Uses `aiosqlite`, `httpx`, and `python-telegram-bot` for robust non-blocking capabilities.

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

Once authenticated:
- Use `/add YYYY-MM-DD HH:MM Duration_in_minutes Event Title` for rapid action.
- Use `/new` to spawn interactive inline keyboards.
- Use `/agenda` to browse local events.

Have fun and stay organized!