import os
import logging
import asyncio

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from database import init_db
from handlers.basic import start, handle_api_key, version_cmd
from handlers.events import add_event, conv_handler
from handlers.agenda import agenda_cmd, agenda_callback
from tasks.scheduler import send_daily_summaries

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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("version", version_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key))

    # Event handlers
    application.add_handler(CommandHandler("add", add_event))
    application.add_handler(conv_handler)
    
    # Agenda handlers
    application.add_handler(CommandHandler("agenda", agenda_cmd))
    application.add_handler(CallbackQueryHandler(agenda_callback, pattern="^agenda_"))

    # Setup Daily Summary Job at 07:00 AM
    job_queue = application.job_queue
    if job_queue:
        # Note: scheduling using server time as per requirements
        import datetime as dt
        t = dt.time(hour=7, minute=0, second=0)
        job_queue.run_daily(send_daily_summaries, time=t)
        logger.info("Daily summary scheduled for 07:00 AM server time.")
    else:
        logger.warning("JobQueue is not initialized.")

    # Run the bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
