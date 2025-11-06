import logging
import os
import random
import re # We need to import 're' for parsing the button text
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler,
    CallbackQueryHandler,
    JobQueue # <-- Import JobQueue
)

# --- Configuration ---
# Hardcoded as requested by the user.
# WARNING: Do not share this file. Your token is secret.
TELEGRAM_TOKEN = "7390844050:AAEB5vpDzhRelx0sf_CUGwMgLXd4ZBf61ks"
ADMIN_USER_ID = 6837532865

# How often to send a prediction (in seconds)
POST_INTERVAL = 60  # 1 minute

# URL for the image you want to send with predictions
PREDICTION_IMAGE_URL = "https://envs.sh/JN2.jpg"

# Emojis for the reaction buttons
REACTIONS = ["😍", "😢", "🤩", "🤑", "🧡", "💸"]

# --- NEW: 8 REAL TRENDS FROM SCREENSHOTS ---
# All old trend logic is GONE. This is the new brain.
# I have converted "Big" to "Big 🔴" and "Small" to "Small 🟢"

B = "Big 🔴"
S = "Small 🟢"

# These are the 8 trends you provided, in order
# Reading from top (newest) to bottom (oldest)
PREDEFINED_TRENDS = {
    "Trend 1": [S, S, B, S, S, S, B, B, B, B],
    "Trend 2": [S, B, S, B, B, B, S, B, B, B],
    "Trend 3": [B, B, S, B, S, B, S, S, B, B],
    "Trend 4": [B, B, B, S, B, B, S, S, B, B],
    "Trend 5": [S, B, S, B, S, S, B, S, S, S],
    "Trend 6": [B, B, S, S, S, S, S, B, B, S],
    "Trend 7": [B, S, S, B, B, B, S, B, S, B],
    "Trend 8": [S, S, S, B, S, B, S, B, S, S]
}
# ---------------------

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# This bot uses `context.application.bot_data` to store states
# `bot_data['channel_states']` will be our dictionary

async def generate_new_trend_logic(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    This is no longer a job. It's a helper function that
    selects one of the 8 predefined trends and sets the queue.
    """
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        logger.warning(f"generate_new_trend_logic called for {chat_id} but state not found.")
        return
        
    state = context.application.bot_data['channel_states'][chat_id]
    
    # 1. Randomly pick one of the 8 trend names
    chosen_trend_name = random.choice(list(PREDEFINED_TRENDS.keys()))
    
    # 2. Get the full 10-step list of predictions for that trend
    # We use .copy() to ensure we don't accidentally modify the original
    prediction_list = PREDEFINED_TRENDS[chosen_trend_name].copy()
    
    # 3. Set the state
    state['current_trend_name'] = chosen_trend_name
    state['prediction_queue'] = prediction_list
    
    context.application.bot_data['channel_states'][chat_id] = state
    
    logger.info(f"Chat {chat_id}: New trend selected: {chosen_trend_name}. Queue has 10 items.")


async def send_prediction_job(context: ContextTypes.DEFAULT_TYPE):
    """
    This job runs every 1 minute.
    It takes one prediction from the queue and posts it.
    If the queue is empty, it generates a new trend.
    """
    chat_id = context.job.chat_id
    
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        logger.error(f"send_prediction_job running for {chat_id} but state does not exist. Removing job.")
        context.job.schedule_removal()
        return

    state = context.application.bot_data['channel_states'][chat_id]
    
    # --- NEW LOGIC ---
    # If the queue is empty, it's time to generate a new 10-step trend.
    if not state.get('prediction_queue'):
        logger.warning(f"Chat {chat_id}: Prediction queue is empty. Generating a new 10-step trend.")
        await generate_new_trend_logic(context, chat_id)
        state = context.application.bot_data['channel_states'][chat_id] # Re-fetch state

    try:
        # Get the next prediction from the front of the queue
        prediction = state['prediction_queue'].pop(0)
        items_left = len(state['prediction_queue'])
        
    except (IndexError, AttributeError):
        # This should theoretically not happen, but it's good to be safe
        logger.error(f"Chat {chat_id}: Tried to pop from empty/invalid queue. Forcing new trend.")
        await generate_new_trend_logic(context, chat_id)
        state = context.application.bot_data['channel_states'][chat_id]
        prediction = state['prediction_queue'].pop(0)
        items_left = len(state['prediction_queue'])

    # Format and send message
    try:
        # 1. Create the reaction buttons, all with a count of 0
        reaction_buttons = []
        for emoji in REACTIONS:
            # The text is "😍 (0)" and the data is just "😍"
            reaction_buttons.append(InlineKeyboardButton(text=f"{emoji} (0)", callback_data=emoji))

        # 2. Define the "How to Play" button
        how_to_play_button = InlineKeyboardButton(
            text="𝐇𝐎𝐖 𝐓𝐎 𝐏𝐋𝐀𝐘",
            url="https://t.me/goa_games_gods/21565"
        )
        
        # 3. Arrange buttons in a grid (3x2)
        keyboard = [
            [reaction_buttons[0], reaction_buttons[1], reaction_buttons[2]], # 😍 😢 🤩
            [reaction_buttons[3], reaction_buttons[4], reaction_buttons[5]], # 🤑 🧡 💸
            [how_to_play_button] # 4th row
        ]
        markup = InlineKeyboardMarkup(keyboard)

        # 4. Format the message caption (text that goes with the image)
        message_caption = (
            f"📈 Trend: {state['current_trend_name']} (Step {10 - items_left}/10)\n\n"
            f"🤖 Prediction: **{prediction}**"
        )
        
        # 5. Send the image with the caption and button
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=PREDICTION_IMAGE_URL, # The image URL
            caption=message_caption,    # The text
            parse_mode='Markdown',
            reply_markup=markup       # The button
        )
        
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        if "chat not found" in str(e).lower() or "bot was blocked" in str(e).lower():
            logger.warning(f"Bot probably kicked from {chat_id}. Stopping all jobs for this chat.")
            stop_all_jobs_for_chat(context, chat_id)

async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This is the new function that handles when a user clicks a reaction button.
    """
    query = update.callback_query
    # Immediately answer the button press, so the user's app doesn't show a loading icon
    await query.answer() 
    
    clicked_emoji = query.data
    
    # Make sure this is a reaction button, not some other button
    if clicked_emoji not in REACTIONS:
        return

    try:
        current_keyboard = query.message.reply_markup.inline_keyboard
        new_reaction_buttons = []
        how_to_play_button = None

        # Loop over all buttons to find the one that was clicked and update its count
        for row in current_keyboard:
            for button in row:
                if button.url:
                    # This is the "HOW TO PLAY" button, just save it
                    how_to_play_button = button
                    continue
                
                # This is a reaction button
                button_emoji = button.callback_data
                button_text = button.text
                
                # Parse the text (e.g., "😍 (5)") to get the count
                match = re.search(r"\((\d+)\)", button_text)
                count = int(match.group(1)) if match else 0
                
                # If this is the button that was clicked, add 1 to the count
                if button_emoji == clicked_emoji:
                    count += 1
                    
                # Create the new button text
                new_text = f"{button_emoji} ({count})"
                new_reaction_buttons.append(InlineKeyboardButton(text=new_text, callback_data=button_emoji))

        # Re-build the keyboard layout with the new buttons
        new_keyboard_layout = [
            [new_reaction_buttons[0], new_reaction_buttons[1], new_reaction_buttons[2]],
            [new_reaction_buttons[3], new_reaction_buttons[4], new_reaction_buttons[5]],
        ]
        if how_to_play_button:
            new_keyboard_layout.append([how_to_play_button])
            
        new_markup = InlineKeyboardMarkup(new_keyboard_layout)
        
        # Edit the original message to show the new keyboard
        await query.edit_message_reply_markup(reply_markup=new_markup)
        
    except Exception as e:
        # This can fail if two people click at the exact same time. It's okay.
        logger.warning(f"Failed to update reaction count: {e}")


def stop_all_jobs_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Helper function to stop and remove all jobs and state for a chat."""
    bot_data = context.application.bot_data['channel_states']
    if chat_id in bot_data:
        state = bot_data[chat_id]
        
        # --- REMOVED trend_job ---
        if 'post_job' in state and state['post_job']:
            state['post_job'].schedule_removal()
        
        del bot_data[chat_id]
        logger.info(f"All jobs and state for chat {chat_id} stopped and removed.")
        return True
    return False

# --- Admin Command Handlers (Must be run in DM) ---
admin_filter = filters.User(user_id=ADMIN_USER_ID)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message to the admin."""
    welcome_text = (
        "**Welcome, Admin! (v2.7.1)**\n\n"
        "This version fixes the `SyntaxError` from my last message.\n"
        "It now uses the **8 real 10-step trends** you provided.\n"
        "It will post one step every minute, then automatically start a new trend.\n\n"
        "**How to Use:**\n"
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
        # The queue is left empty on purpose.
        # send_prediction_job will see it's empty and call generate_new_trend_logic.
        channel_states[chat_id] = {
            'prediction_queue': []
        }
        
        # --- MODIFIED ---
        # We only schedule ONE job now: the 1-minute posting job.
        # It will handle its own logic.
        post_job = context.application.job_queue.run_repeating(
            send_prediction_job,
            interval=POST_INTERVAL,
            first=1,
            chat_id=chat_id,
            name=f"post_{chat_id}"
        )
        
        # Store job in state
        channel_states[chat_id]['post_job'] = post_job
        
        logger.info(f"Started 1-minute post job for chat {chat_id} ({channel_name})")
        await update.message.reply_text(f"✅ **Auto Trade Activated!**\nI will start posting in **{channel_name}** using the new 8-trend logic.")

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
    """Replies to any non-admin who tries to use this bot."""
    await update.message.reply_text("⛔ You are not authorized to use this bot.")

def main():
    """Run the bot."""
    if not TELEGRAM_TOKEN:
        logging.critical("TELEGRAM_TOKEN is not set! Bot cannot start.")
        return

    # We must explicitly create a JobQueue and pass it to the builder
    job_queue = JobQueue()
    application = Application.builder().token(TELEGRAM_TOKEN).job_queue(job_queue).build()
    
    # Register admin-only commands, usable only in private DMs
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(CommandHandler("help", start_command, filters=filters.ChatType.PRIVATE & admin_filder))
    application.add_handler(CommandHandler("autotrade", autotrade_command, filters=filters.ChatType.PRIVATE & admin_filter))

    # Register a handler for any other message from non-admins in DMs
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~admin_filter), unauthorized_user_handler))
    
    # It will listen for *all* button presses from *all* users
    application.add_handler(CallbackQueryHandler(reaction_handler))

    # Start the Bot
    logger.info(f"Bot starting... (v2.7.1 - 8 Real Trends, SyntaxFix)")
    logger.info(f"Admin user ID set to: {ADMIN_USER_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()
