import asyncio
import logging
import os

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)

from database import get_users_with_agenda, init_db
from handlers.agenda import agenda_callback, agenda_cmd
from handlers.basic import (
    onboarding_conv_handler,
    quick_event_callback,
    start,
    version_cmd,
)
from handlers.events import add_event, conv_handler, list_calendars_cmd
from handlers.settings import logout_conv_handler, master_settings_conv_handler
from tasks.scheduler import update_user_agenda_job

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Initializes the bot, attaches handlers, and starts the polling loop.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN environment variable not set.")
        return

    # Ensure DB is created before starting
    # We run this synchronously in the main thread just to initialize
    asyncio.run(init_db())

    # Build the application
    application = ApplicationBuilder().token(token).build()

    # Basic handlers
    application.add_handler(onboarding_conv_handler)
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("version", version_cmd))
    application.add_handler(
        CallbackQueryHandler(quick_event_callback, pattern="^dashboard_quick$")
    )

    # Event handlers
    application.add_handler(CommandHandler("add", add_event))
    application.add_handler(CommandHandler("calendars", list_calendars_cmd))
    application.add_handler(conv_handler)

    # Settings handler
    application.add_handler(logout_conv_handler)
    application.add_handler(master_settings_conv_handler)

    # Agenda handlers
    application.add_handler(CommandHandler("agenda", agenda_cmd))
    application.add_handler(
        CallbackQueryHandler(agenda_cmd, pattern="^dashboard_agenda$")
    )
    application.add_handler(CallbackQueryHandler(agenda_callback, pattern="^agenda_"))

    # Setup Per-User Daily Summary Jobs
    job_queue = application.job_queue
    if job_queue:
        users_with_agendas = asyncio.run(get_users_with_agenda())
        logger.info(
            f"Scheduling agenda jobs for {len(users_with_agendas)} opted-in users..."
        )
        for u in users_with_agendas:
            update_user_agenda_job(
                job_queue=job_queue,
                user_id=u["telegram_user_id"],
                is_enabled=u["agenda_enabled"],
                time_str=u["agenda_time"],
            )
    else:
        logger.warning("JobQueue is not initialized. Background jobs will not run.")

    # Run the bot
    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
