import logging
import os
import random
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler
)

# --- Configuration ---
# Hardcoded as requested by the user.
# WARNING: Do not share this file. Your token is secret.
TELEGRAM_TOKEN = "7390844050:AAEB5vpDzhRelx0sf_CUGwMgLXd4ZBf61ks"
ADMIN_USER_ID = 6837532865

# How often to send a prediction (in seconds)
POST_INTERVAL = 60  # 1 minute
# How often to change the underlying trend (in seconds)
TREND_CHANGE_INTERVAL = 180  # 3 minutes
# ---------------------

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# This bot uses `context.application.bot_data` to store states
# It's a dictionary available everywhere
# `bot_data['channel_states']` will be our dictionary

async def generate_new_trend_logic(context: ContextTypes.DEFAULT_TYPE):
    """
    This job runs every 3 minutes.
    It decides the "trend" for the next 3 posts and creates the 
    prediction queue.
    """
    chat_id = context.job.chat_id
    
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        logger.warning(f"generate_new_trend_logic called for {chat_id} but state not found. Stopping.")
        return

    state = context.application.bot_data['channel_states'][chat_id]
    
    # Define the possible trends
    trends = ["Dragon", "Zig-Zag", "Double-Up", "Random-Flip"]
    chosen_trend = random.choice(trends)
    
    state['current_trend_name'] = chosen_trend
    queue = []
    last_val = state.get('last_value', "Small 🟢") # Get last value or default
    
    # Generate the 3 predictions for the next 3 minutes
    if chosen_trend == "Dragon":
        val = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        queue = [val, val, val]
        last_val = val
        
    elif chosen_trend == "Zig-Zag":
        val1 = "Big 🔴" if last_val == "Small 🟢" else "Small 🟢"
        val2 = "Small 🟢" if val1 == "Big 🔴" else "Big 🔴"
        queue = [val1, val2, val1]
        last_val = val1
        
    elif chosen_trend == "Double-Up":
        val1 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val2 = "Small 🟢" if val1 == "Big 🔴" else "Big 🔴"
        queue = [val1, val1, val2]
        last_val = val2

    elif chosen_trend == "Random-Flip":
        val1 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val2 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val3 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        queue = [val1, val2, val3]
        last_val = val3

    state['prediction_queue'] = queue
    state['last_value'] = last_val
    context.application.bot_data['channel_states'][chat_id] = state
    
    logger.info(f"Chat {chat_id}: New trend selected: {chosen_trend}. Queue: {queue}")


async def send_prediction_job(context: ContextTypes.DEFAULT_TYPE):
    """
    This job runs every 1 minute.
    It takes one prediction from the queue and posts it.
    """
    chat_id = context.job.chat_id
    
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        logger.error(f"send_prediction_job running for {chat_id} but state does not exist. Removing job.")
        context.job.schedule_removal()
        return

    state = context.application.bot_data['channel_states'][chat_id]
    
    # If queue is empty (e.g., timing mismatch), force-generate a new one.
    if not state.get('prediction_queue'):
        logger.warning(f"Chat {chat_id}: Prediction queue was empty. Forcing new trend generation.")
        # We can't await here, so we create a fake context to pass
        fake_job = type('FakeJob', (object,), {'chat_id': chat_id})
        fake_context = type('FakeContext', (object,), {'application': context.application, 'job': fake_job})
        await generate_new_trend_logic(fake_context)
        state = context.application.bot_data['channel_states'][chat_id] # Re-fetch state

    try:
        # Get the next prediction from the front of the queue
        prediction = state['prediction_queue'].pop(0)
    except (IndexError, AttributeError):
        logger.error(f"Chat {chat_id}: Tried to pop from empty/invalid queue. Forcing new trend.")
        fake_job = type('FakeJob', (object,), {'chat_id': chat_id})
        fake_context = type('FakeContext', (object,), {'application': context.application, 'job': fake_job})
        await generate_new_trend_logic(fake_context)
        state = context.application.bot_data['channel_states'][chat_id]
        prediction = state['prediction_queue'].pop(0)

    # Update state
    state['period'] += 1
    context.application.bot_data['channel_states'][chat_id] = state
    
    # Format and send message
    try:
        message_text = (
            f"--- Period {state['period']} ---\n"
            f"📈 Trend: {state['current_trend_name']}\n\n"
            f"🤖 Prediction: **{prediction}**\n\n"
            f"⚠️ *Disclaimer: For educational/entertainment purposes only.*"
        )
        await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        if "chat not found" in str(e).lower() or "bot was blocked" in str(e).lower():
            logger.warning(f"Bot probably kicked from {chat_id}. Stopping all jobs for this chat.")
            stop_all_jobs_for_chat(context, chat_id)

def stop_all_jobs_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Helper function to stop and remove all jobs and state for a chat."""
    bot_data = context.application.bot_data['channel_states']
    if chat_id in bot_data:
        state = bot_data[chat_id]
        if state.get('post_job'):
            state['post_job'].schedule_removal()
        if state.get('trend_job'):
            state['trend_job'].schedule_removal()
        del bot_data[chat_id]
        logger.info(f"All jobs and state for chat {chat_id} stopped and removed.")
        return True
    return False

# --- Admin Command Handlers (Must be run in DM) ---
admin_filter = filters.User(user_id=ADMIN_USER_ID)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message to the admin."""
    welcome_text = (
        "**Welcome, Admin! (v2.0)**\n\n"
        "This is your Trend Simulator Bot, now on the new library.\n"
        "This version IS compatible with Python 3.12 and should work.\n\n"
        "**DISCLAIMER:**\n"
        "This bot is for educational purposes. All 'predictions' are **randomly generated**.\n"
        "**How to Use (Same as before):**\n"
        "1. Add bot as **Admin** to your channel.\n"
        "2. Send me commands here in our DM:\n\n"
        "`/autotrade on @mychannel`\n"
        "`/autotrade off @mychannel`"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def autotrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /autotrade on/off <channel> commands."""
    try:
        command = context.args[0].lower()
        target_channel = context.args[1]
    except (IndexError, TypeError):
        await update.message.reply_text("Usage: `/autotrade <on/off> <@channel_username or channel_id>`", parse_mode='Markdown')
        return

    # Normalize channel ID
    try:
        if not target_channel.startswith('@'):
            chat_id = int(target_channel)
        else:
            chat_id = target_channel
    except ValueError:
        await update.message.reply_text("Invalid Channel ID. Must be `@username` or a number.")
        return

    # Initialize 'channel_states' in bot_data if it's not there
    if 'channel_states' not in context.application.bot_data:
        context.application.bot_data['channel_states'] = {}
        
    channel_states = context.application.bot_data['channel_states']

    # --- Turn ON ---
    if command == "on":
        if chat_id in channel_states:
            await update.message.reply_text("Bot is already running in that channel.")
            return

        # Check if bot is an admin
        try:
            chat = await context.bot.get_chat(chat_id)
            channel_name = chat.title
            admins = await context.bot.get_chat_administrators(chat_id)
            if not any(admin.user.id == context.bot.id for admin in admins):
                 await update.message.reply_text(f"❌ Error: I am not an administrator in '{channel_name}'. Please add me as an admin first.")
                 return
        except Exception as e:
            logger.error(f"Error checking admin status in {chat_id}: {e}")
            await update.message.reply_text(f"❌ Error: Could not access channel '{target_channel}'. Make sure the username/ID is correct and I am a member.")
            return

        await update.message.reply_text(f"Verifying... please wait.")
        
        # Initialize state
        channel_states[chat_id] = {
            'period': 20240101001,
            'last_value': "Small 🟢",
            'prediction_queue': []
        }
        
        # 1. Run trend generator to populate queue
        fake_job = type('FakeJob', (object,), {'chat_id': chat_id})
        fake_context = type('FakeContext', (object,), {'application': context.application, 'job': fake_job})
        await generate_new_trend_logic(fake_context)
        
        # 2. Schedule the 1-minute posting job
        post_job = context.application.job_queue.run_repeating(
            send_prediction_job,
            interval=POST_INTERVAL,
            first=1,
            chat_id=chat_id,
            name=f"post_{chat_id}"
        )
        
        # 3. Schedule the 3-minute trend-changing job
        trend_job = context.application.job_queue.run_repeating(
            generate_new_trend_logic,
            interval=TREND_CHANGE_INTERVAL,
            first=TREND_CHANGE_INTERVAL,
            chat_id=chat_id,
            name=f"trend_{chat_id}"
        )
        
        # Store jobs in state
        channel_states[chat_id]['post_job'] = post_job
        channel_states[chat_id]['trend_job'] = trend_job
        
        logger.info(f"Started all jobs for chat {chat_id} ({channel_name})")
        await update.message.reply_text(f"✅ **Auto Trade Activated!**\nI will start posting in **{channel_name}**.")

    # --- Turn OFF ---
    elif command == "off":
        if chat_id not in channel_states:
            await update.message.reply_text("Bot is not currently running in that channel.")
            return
            
        if stop_all_jobs_for_chat(context, chat_id):
            await update.message.reply_text(f"🛑 **Auto Trade Deactivated** for channel: {target_channel}")
        else:
            await update.message.reply_text("Could not stop bot. State not found.")
            
    else:
        await update.message.reply_text("Usage: `/autotrade <on/off> <@channel_username or channel_id>`", parse_mode='Markdown')

async def unauthorized_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies to any non-admin who tries to use the bot."""
    await update.message.reply_text("⛔ You are not authorized to use this bot.")

def main():
    """Run the bot."""
    if not TELEGRAM_TOKEN:
        logging.critical("TELEGRAM_TOKEN is not set! Bot cannot start.")
        return

    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register admin-only commands, usable only in private DMs
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(CommandHandler("help", start_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(CommandHandler("autotrade", autotrade_command, filters=filters.ChatType.PRIVATE & admin_filter))

    # Register a handler for any other message from non-admins in DMs
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~admin_filter), unauthorized_user_handler))

    # Start the Bot
    logger.info(f"Bot starting... (v2.0 for Python 3.12)")
    logger.info(f"Admin user ID set to: {ADMIN_USER_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()

