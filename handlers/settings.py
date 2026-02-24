import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from database import get_user, upsert_user
from tasks.scheduler import update_user_agenda_job
from i18n import get_text

logger = logging.getLogger(__name__)

# States for the conversation
MASTER_MENU = 1
DAILY_MENU = 2
ASK_TIME = 3
LANG_MENU = 4

async def send_master_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """
    Renders the Master Settings Menu.
    """
    user_id = update.effective_user.id
    msg = await get_text("settings_master_title", user_id)
    
    keyboard = [
        [InlineKeyboardButton(await get_text("settings_btn_daily", user_id), callback_data="goto_daily")],
        [InlineKeyboardButton(await get_text("settings_btn_language", user_id), callback_data="goto_lang")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def master_settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /settings"""
    logger.info("master_settings_start triggered")
    await send_master_settings(update, context, is_callback=False)
    return MASTER_MENU

async def master_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /settings callbacks to submenus"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "goto_daily":
        await send_settings_dashboard(update, context, is_callback=True)
        return DAILY_MENU
    elif query.data == "goto_lang":
        await send_language_menu(update, context, is_callback=True)
        return LANG_MENU
    
    return MASTER_MENU

async def return_to_master(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Back button handler"""
    await update.callback_query.answer()
    await send_master_settings(update, context, is_callback=True)
    return MASTER_MENU

async def send_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """
    Renders Language selection dashboard.
    """
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton(await get_text("language_btn_en", user_id), callback_data="lang_en"),
         InlineKeyboardButton(await get_text("language_btn_it", user_id), callback_data="lang_it")],
        [InlineKeyboardButton(await get_text("settings_btn_back", user_id), callback_data="back_master")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await get_text("language_prompt", user_id)
    
    if is_callback:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Saves the selected language inside the submenu.
    """
    query = update.callback_query
    await query.answer()

    lang = query.data.split("_")[1]
    user_id = update.effective_user.id
    
    # Save the new language
    await upsert_user(user_id, language=lang)
    
    # Fetch the translated success string in the NEW language and redraw the menu
    msg = await get_text("language_updated", user_id)
    
    keyboard = [
        [InlineKeyboardButton(await get_text("language_btn_en", user_id), callback_data="lang_en"),
         InlineKeyboardButton(await get_text("language_btn_it", user_id), callback_data="lang_it")],
        [InlineKeyboardButton(await get_text("settings_btn_back", user_id), callback_data="back_master")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(f"{msg}\n\n" + await get_text("language_prompt", user_id), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return LANG_MENU

async def send_settings_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """
    Renders the Daily Settings Dashboard based on current DB strings.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    
    if not user_record or not user_record.get("morgen_api_key"):
        msg = await get_text("new_please_link", user_id)
        if is_callback:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END
        
    is_enabled = user_record.get("agenda_enabled", 1) == 1
    current_time = user_record.get("agenda_time", "07:00")
    
    # Get i18n UI strings
    toggle_text = await get_text("settings_btn_disable", user_id) if is_enabled else await get_text("settings_btn_enable", user_id)
    time_btn_text = await get_text("settings_btn_time", user_id, time=current_time)
    
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data="set_toggle")],
        [InlineKeyboardButton(time_btn_text, callback_data="set_time")],
        [InlineKeyboardButton(await get_text("settings_btn_back", user_id), callback_data="back_master")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "🟢 " + await get_text("settings_status_enabled", user_id) if is_enabled else "🔴 " + await get_text("settings_status_disabled", user_id)
    
    dashboard_msg = await get_text("settings_dashboard", user_id, status=status_emoji, time=current_time)
    
    if is_callback:
        await update.callback_query.edit_message_text(dashboard_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(dashboard_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# Kept as alias for direct command usage
async def daily_settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point alias for /daily_settings"""
    await send_settings_dashboard(update, context, is_callback=False)
    return DAILY_MENU

async def language_settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point alias for /language"""
    await send_language_menu(update, context, is_callback=False)
    return LANG_MENU

async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle enabled status"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    current_status = user_record.get("agenda_enabled", 1) == 1
    new_status = not current_status
    
    # Update DB
    await upsert_user(user_id, agenda_enabled=new_status)
    
    # Update Job Queue
    if context.application.job_queue:
        update_user_agenda_job(
            context.application.job_queue, 
            user_id, 
            new_status, 
            user_record.get("agenda_time", "07:00")
        )
        
    # Redraw dashboard
    await send_settings_dashboard(update, context, is_callback=True)
    return DAILY_MENU

async def ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask user to type new time"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    msg = await get_text("settings_ask_time", user_id)
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return ASK_TIME

async def process_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the written time"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        msg = await get_text("new_invalid_time", user_id)
        await update.message.reply_text(msg)
        return ASK_TIME
        
    try:
        from datetime import datetime
        datetime.strptime(text, "%H:%M")
    except ValueError:
        msg = await get_text("new_invalid_time", user_id)
        await update.message.reply_text(msg)
        return ASK_TIME
        
    time_str = text.zfill(5)
    user_record = await get_user(user_id)
    is_enabled = user_record.get("agenda_enabled", 1) == 1
    
    # Update DB
    await upsert_user(user_id, agenda_time=time_str)
    
    # Update Job Queue
    if context.application.job_queue:
        update_user_agenda_job(
            context.application.job_queue, 
            user_id, 
            is_enabled, 
            time_str
        )
        
    success_msg = await get_text("settings_time_success", user_id, time=time_str)
    await update.message.reply_text(success_msg, parse_mode=ParseMode.MARKDOWN)
    
    # Redraw Dashboard as new message
    await send_settings_dashboard(update, context, is_callback=False)
    return DAILY_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel settings inline interaction"""
    user_id = update.effective_user.id
    msg = await get_text("settings_cancelled", user_id)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
        
    return ConversationHandler.END

master_settings_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("settings", master_settings_start),
        CommandHandler("daily_settings", daily_settings_start),
        CommandHandler("language", language_settings_start),
        CallbackQueryHandler(master_settings_start, pattern="^dashboard_settings$")
    ],
    states={
        MASTER_MENU: [
            CallbackQueryHandler(master_callback, pattern="^(goto_daily|goto_lang)$")
        ],
        DAILY_MENU: [
            CallbackQueryHandler(handle_toggle, pattern="^set_toggle$"),
            CallbackQueryHandler(ask_time, pattern="^set_time$"),
            CallbackQueryHandler(return_to_master, pattern="^back_master$")
        ],
        ASK_TIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_time)
        ],
        LANG_MENU: [
            CallbackQueryHandler(handle_language_selection, pattern="^lang_"),
            CallbackQueryHandler(return_to_master, pattern="^back_master$")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
