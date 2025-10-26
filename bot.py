import logging
import os
import random
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue, Filters

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

# This dictionary will hold the state for each channel
# Key: chat_id, Value: dict of jobs, trend info, etc.
# { CHAT_ID: { 'post_job': Job, 'trend_job': Job, 'current_trend_name': str, 
#              'prediction_queue': list, 'last_value': str, 'period': int } }
channel_states = {}

def generate_new_trend_logic(chat_id: int):
    """
    This job runs every 3 minutes.
    It decides the "trend" for the next 3 posts and creates the 
    prediction queue.
    """
    global channel_states
    if chat_id not in channel_states:
        logger.warning(f"generate_new_trend_logic called for {chat_id} but state not found. Stopping.")
        return

    state = channel_states[chat_id]
    
    # Define the possible trends
    trends = ["Dragon", "Zig-Zag", "Double-Up", "Random-Flip"]
    chosen_trend = random.choice(trends)
    
    state['current_trend_name'] = chosen_trend
    queue = []
    last_val = state.get('last_value', "Small 🟢") # Get last value or default
    
    # Generate the 3 predictions for the next 3 minutes
    if chosen_trend == "Dragon":
        # A 3-post streak of the same value
        val = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        queue = [val, val, val]
        last_val = val
        
    elif chosen_trend == "Zig-Zag":
        # A 3-post alternating streak
        val1 = "Big 🔴" if last_val == "Small 🟢" else "Small 🟢"
        val2 = "Small 🟢" if val1 == "Big 🔴" else "Big 🔴"
        queue = [val1, val2, val1]
        last_val = val1
        
    elif chosen_trend == "Double-Up":
        # Two of one, one of the other
        val1 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val2 = "Small 🟢" if val1 == "Big 🔴" else "Big 🔴"
        queue = [val1, val1, val2]
        last_val = val2

    elif chosen_trend == "Random-Flip":
        # Three totally random coin flips
        val1 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val2 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        val3 = "Big 🔴" if random.random() > 0.5 else "Small 🟢"
        queue = [val1, val2, val3]
        last_val = val3

    state['prediction_queue'] = queue
    state['last_value'] = last_val
    channel_states[chat_id] = state
    
    logger.info(f"Chat {chat_id}: New trend selected: {chosen_trend}. Queue: {queue}")


def send_prediction_job(context: CallbackContext):
    """
    This job runs every 1 minute.
    It takes one prediction from the queue and posts it.
    """
    global channel_states
    chat_id = context.job.context
    
    if chat_id not in channel_states:
        logger.error(f"send_prediction_job running for {chat_id} but state does not exist. Removing job.")
        context.job.schedule_removal()
        return

    state = channel_states[chat_id]
    
    # If queue is empty (e.g., timing mismatch), force-generate a new one.
    if not state.get('prediction_queue'):
        logger.warning(f"Chat {chat_id}: Prediction queue was empty. Forcing new trend generation.")
        generate_new_trend_logic(chat_id)
        state = channel_states[chat_id] # Re-fetch state

    try:
        # Get the next prediction from the front of the queue
        prediction = state['prediction_queue'].pop(0)
    except IndexError:
        logger.error(f"Chat {chat_id}: Tried to pop from empty queue even after check. Skipping post.")
        return

    # Update state
    state['period'] += 1
    channel_states[chat_id] = state
    
    # Format and send message
    try:
        message_text = (
            f"--- Period {state['period']} ---\n"
            f"📈 Trend: {state['current_trend_name']}\n\n"
            f"🤖 Prediction: **{prediction}**\n\n"
            f"⚠️ *Disclaimer: For educational/entertainment purposes only.*"
        )
        context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        # If bot was kicked or blocked, stop all jobs for this chat
        if "chat not found" in str(e).lower() or "bot was blocked" in str(e).lower():
            logger.warning(f"Bot probably kicked from {chat_id}. Stopping all jobs for this chat.")
            stop_all_jobs_for_chat(chat_id)

def stop_all_jobs_for_chat(chat_id: int):
    """Helper function to stop and remove all jobs and state for a chat."""
    global channel_states
    if chat_id in channel_states:
        state = channel_states[chat_id]
        if state.get('post_job'):
            state['post_job'].schedule_removal()
        if state.get('trend_job'):
            state['trend_job'].schedule_removal()
        del channel_states[chat_id]
        logger.info(f"All jobs and state for chat {chat_id} stopped and removed.")
        return True
    return False

# --- Admin Command Handlers (Must be run in DM) ---
admin_filter = Filters.user(user_id=ADMIN_USER_ID)

def start_command(update: Update, context: CallbackContext):
    """Sends a welcome message to the admin."""
    welcome_text = (
        "**Welcome, Admin!**\n\n"
        "This is your Trend Simulator Bot.\n\n"
        "**DISCLAIMER:**\n"
        "This bot is for educational purposes. All 'predictions' are **randomly generated** by a simulator. "
        "It **CANNOT** predict real games. Do not use this for financial decisions.\n\n"
        "**How to Use:**\n"
        "1. Add this bot as an **Administrator** to your channel (it needs 'Post messages' permission).\n"
        "2. Get your channel's username (e.g., `@mychannel`) or its ID (e.g., `-100123456789`).\n"
        "3. Send me commands here in our DM:\n\n"
        "`/autotrade on @mychannel`\n"
        "`/autotrade off @mychannel`\n\n"
        "(You can also use the Channel ID instead of the username)."
    )
    update.message.reply_text(welcome_text, parse_mode='Markdown')

def autotrade_command(update: Update, context: CallbackContext):
    """Handles the /autotrade on/off <channel> commands."""
    global channel_states
    
    try:
        command = context.args[0].lower()
        target_channel = context.args[1]
    except (IndexError, TypeError):
        update.message.reply_text("Usage: `/autotrade <on/off> <@channel_username or channel_id>`", parse_mode='Markdown')
        return

    # Normalize channel ID
    try:
        # If it's a username, it works as is. If it's a number, cast to int.
        if not target_channel.startswith('@'):
            chat_id = int(target_channel)
        else:
            chat_id = target_channel
    except ValueError:
        update.message.reply_text("Invalid Channel ID. It must be a username (e.g., `@mychannel`) or a number (e.g., `-100123456789`).")
        return

    # --- Turn ON ---
    if command == "on":
        if chat_id in channel_states:
            update.message.reply_text("Bot is already running in that channel.")
            return

        # Check if bot is an admin in the target channel
        try:
            chat = context.bot.get_chat(chat_id)
            channel_name = chat.title
            admins = context.bot.get_chat_administrators(chat_id)
            if not any(admin.user.id == context.bot.id for admin in admins):
                 update.message.reply_text(f"❌ Error: I am not an administrator in '{channel_name}'. Please add me as an admin with 'Post messages' permission first.")
                 return
        except Exception as e:
            logger.error(f"Error checking admin status in {chat_id}: {e}")
            update.message.reply_text(f"❌ Error: Could not access channel '{target_channel}'. Make sure the username/ID is correct and I am a member.")
            return

        # All checks passed, let's start
        update.message.reply_text(f"Verifying... please wait.")
        
        # Initialize state
        channel_states[chat_id] = {
            'period': 20240101001,
            'last_value': "Small 🟢",
            'prediction_queue': []
        }
        
        # 1. Run the trend generator *first* to populate the queue
        generate_new_trend_logic(chat_id)
        
        # 2. Schedule the 1-minute posting job
        post_job = context.job_queue.run_repeating(
            send_prediction_job,
            interval=POST_INTERVAL,
            first=1, # Start after 1 second
            context=chat_id,
            name=f"post_{chat_id}"
        )
        
        # 3. Schedule the 3-minute trend-changing job
        trend_job = context.job_queue.run_repeating(
            generate_new_trend_logic,
            interval=TREND_CHANGE_INTERVAL,
            first=TREND_CHANGE_INTERVAL, # Run after 3 mins
            context=chat_id,
            name=f"trend_{chat_id}"
        )
        
        # Store jobs in state to manage them
        channel_states[chat_id]['post_job'] = post_job
        channel_states[chat_id]['trend_job'] = trend_job
        
        logger.info(f"Started all jobs for chat {chat_id} ({channel_name})")
        update.message.reply_text(f"✅ **Auto Trade Activated!**\nI will start posting in **{channel_name}** every {POST_INTERVAL} seconds.")

    # --- Turn OFF ---
    elif command == "off":
        if chat_id not in channel_states:
            update.message.reply_text("Bot is not currently running in that channel.")
            return
            
        if stop_all_jobs_for_chat(chat_id):
            update.message.reply_text(f"🛑 **Auto Trade Deactivated** for channel: {target_channel}")
        else:
            update.message.reply_text("Could not stop bot. State not found.")
            
    else:
        update.message.reply_text("Usage: `/autotrade <on/off> <@channel_username or channel_id>`", parse_mode='Markdown')

def unauthorized_user_handler(update: Update, context: CallbackContext):
    """Replies to any non-admin who tries to use the bot."""
    update.message.reply_text("⛔ You are not authorized to use this bot.")

def main():
    """Run the bot."""
    if not TELEGRAM_TOKEN:
        logging.critical("TELEGRAM_TOKEN is not set! Bot cannot start.")
        return

    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Register admin-only commands, usable only in private DMs
    dp.add_handler(CommandHandler("start", start_command, filters=Filters.private & admin_filter))
    dp.add_handler(CommandHandler("help", start_command, filters=Filters.private & admin_filter))
    dp.add_handler(CommandHandler("autotrade", autotrade_command, filters=Filters.private & admin_filter))

    # Register a handler for any other message from non-admins in DMs
    dp.add_handler(MessageHandler(Filters.private & (~admin_filter), unauthorized_user_handler))

    # Start the Bot
    updater.start_polling()
    logger.info(f"Bot started polling as user ID {updater.bot.id}...")
    logger.info(f"Admin user ID set to: {ADMIN_USER_ID}")

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()

