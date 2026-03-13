# Morgen Calendar Telegram Bot 🗓️

[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue?style=flat-square&logo=telegram)](https://t.me/morgen_calendar_bot)



A high-performance Telegram bot built for power users of the [Morgen Calendar](https://www.morgen.so/). This bot bridges the gap between your instant messaging and your schedule, allowing you to manage your life without breaking your flow.

## Motivation 🚀

**Because life moves faster than your calendar app.**

Let’s be real: life is too short to open a bloated calendar app, wait for it to sync, navigate to next Tuesday, find an empty slot, and fill out a 10-field form just to remember a "Quick coffee with Sarah." 

**Commit instantly. Tweak later.** 

The killer app of this bot is **disarming speed**. Just shoot a quick message—like "/add Coffee with Sarah tomorrow 10:00"—and boom, it's locked in. No friction, no distractions. You stay in the zone, your commitment is captured, and you can always polish the details later on your desktop. This is for the people who want their tools to keep up with their thoughts.

## Features ✨

- **Natural Language Parsing**: Intelligent date and time detection for quick event entry.
- **Bi-directional Wizard**: An interactive `/new` flow for when you need more structure.
- **Schedulable Daily Agendas**: Receive a curated summary of your day at a specific time you choose (e.g., every morning at 07:00 AM) to always stay in control of your schedule.
- **On-Demand Schedule**: Effortlessly view `/agenda` for today or tomorrow via interactive buttons.
- **Multi-Calendar Support**: Resolve target calendars by name or number, or stick to your preferred default.
- **Internationalization**: Full support for English and Italian users.
- **Rate-Limit Resilience**: Graceful handling of Morgen API limits with user-friendly retry feedback.
- **Privacy First**: Secure API key management with easy logout/data deletion.

## Usage and Commands 🛠️

### Getting Started

1. Open [@morgen_calendar_bot](https://t.me/morgen_calendar_bot) on Telegram.
2. Run `/start`.
3. The bot will prompt you for your **Morgen API Key**. You can find this in your Morgen Desktop app under `Settings > API`.
4. Once linked, you're ready to fly.

### Commands Reference

| Command | Purpose | Arguments | Example |
| :--- | :--- | :--- | :--- |
| `/add` | **Lightning-fast** event creation. | `<Title> <Date> <Time> [Duration/End] [Calendar]` | `/add Gym today 07:00 1H Personal` |
| `/new` | Interactive event wizard. | None (guided flow) | `/new` → Follow the buttons! |
| `/agenda` | View your upcoming schedule. | None (interactive) | `/agenda` → Click `Today` or `Tomorrow` |
| `/calendars` | List your writable calendars. | None | `/calendars` |
| `/settings` | Manage preferences & Daily Summary. | None (menu-driven) | `/settings` |
| `/daily_settings` | Shortcut to Daily Agenda setup. | None | `/daily_settings` |
| `/language` | Shortcut to change language. | None | `/language` |
| `/logout` | Wipe your data and disconnect. | None | `/logout` |
| `/version` | Show current bot version. | None | `/version` |
| `/cancel` | Stop any active conversation. | None | `/cancel` |

#### The `/add` Power Cheat Sheet

- **Relative Dates**: Supports `today`, `tomorrow`, or day names like `monday`.
- **Durations**: Use `PT30M` for 30 mins, `1H` for 1 hour, or specify an end time like `15:30`.
- **Calendars**: Use the name (e.g., `Work`) or the number from `/calendars` (e.g., `1`).

## Known Limitations ⚠️

While powerful, this bot is under active development. Current caveats include:

- **Timezone Locking**: The bot currently defaults to `Europe/Rome` (`UTC+1`/`UTC+2`) for internal processing. Multi-timezone user support is a planned feature.
- **Markdown Sensitivity**: Telegram's MarkdownV2 can be picky; event titles with special characters (like `_` or `*`) may occasionally format unexpectedly in the agenda.
- **HTML Entities**: While the bot attempts to unescape entities, complex HTML in event descriptions might not always render perfectly in summaries.
- **Rate Limits**: Heavy users fetching very large agendas across many calendars may hit Morgen API rate limits (the bot will notify you to wait).

---

*Built with ❤️ for the Morgen community.*

**Note on Development**: This codebase is partially but proudly **vibe-coded**. 🌊

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
