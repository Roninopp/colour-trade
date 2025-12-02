import logging
import os
import random
import re
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler,
    CallbackQueryHandler,
    JobQueue
)

# --- Configuration ---
# Hardcoded as requested by the user.
# WARNING: Do not share this file. Your token is secret.
TELEGRAM_TOKEN = "7390844050:AAEB5vpDzhRelx0sf_CUGwMgLXd4ZBf61ks"
ADMIN_USER_ID = 6837532865 7903835201

# How often to send a prediction (in seconds)
POST_INTERVAL = 60  # 1 minute

# URL for the image you want to send with predictions
PREDICTION_IMAGE_URL = "https://envs.sh/JN2.jpg"

# Emojis for the reaction buttons
REACTIONS = ["😍", "😢", "🤩", "🤑", "🧡", "💸"]

# --- TRENDS ---
B = "Big 🔴"
S = "Small 🟢"

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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

async def generate_new_trend_logic(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        logger.warning(f"generate_new_trend_logic called for {chat_id} but state not found.")
        return
        
    state = context.application.bot_data['channel_states'][chat_id]
    
    chosen_trend_name = random.choice(list(PREDEFINED_TRENDS.keys()))
    prediction_list = PREDEFINED_TRENDS[chosen_trend_name].copy()
    
    state['current_trend_name'] = chosen_trend_name
    state['prediction_queue'] = prediction_list
    
    context.application.bot_data['channel_states'][chat_id] = state
    logger.info(f"Chat {chat_id}: New trend selected: {chosen_trend_name}.")


async def send_prediction_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    
    if 'channel_states' not in context.application.bot_data or chat_id not in context.application.bot_data['channel_states']:
        context.job.schedule_removal()
        return

    state = context.application.bot_data['channel_states'][chat_id]
    
    if not state.get('prediction_queue'):
        await generate_new_trend_logic(context, chat_id)
        state = context.application.bot_data['channel_states'][chat_id]

    try:
        prediction = state['prediction_queue'].pop(0)
        items_left = len(state['prediction_queue'])
    except (IndexError, AttributeError):
        await generate_new_trend_logic(context, chat_id)
        state = context.application.bot_data['channel_states'][chat_id]
        prediction = state['prediction_queue'].pop(0)
        items_left = len(state['prediction_queue'])

    # --- NEW PERIOD LOGIC ---
    # Get the current period, increment it for next time
    current_period = state.get('current_period', 0)
    next_period = current_period + 1
    state['current_period'] = next_period # Save for next loop
    context.application.bot_data['channel_states'][chat_id] = state
    # ------------------------

    try:
        reaction_buttons = []
        for emoji in REACTIONS:
            reaction_buttons.append(InlineKeyboardButton(text=f"{emoji} (0)", callback_data=emoji))

        how_to_play_button = InlineKeyboardButton(
            text="𝐇𝐎𝐖 𝐓𝐎 𝐏𝐋𝐀𝐘",
            url="https://t.me/goa_games_gods/21565"
        )
        
        keyboard = [
            [reaction_buttons[0], reaction_buttons[1], reaction_buttons[2]],
            [reaction_buttons[3], reaction_buttons[4], reaction_buttons[5]],
            [how_to_play_button]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        # --- UPDATED MESSAGE FORMAT ---
        message_caption = (
            f"📅 **Period:** {current_period}\n"
            f"📈 **Trend:** {state['current_trend_name']} (Step {10 - items_left}/10)\n\n"
            f"🤖 **Prediction:** **{prediction}**"
        )
        # ------------------------------
        
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=PREDICTION_IMAGE_URL,
            caption=message_caption,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        if "chat not found" in str(e).lower() or "bot was blocked" in str(e).lower():
            stop_all_jobs_for_chat(context, chat_id)

async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    clicked_emoji = query.data
    if clicked_emoji not in REACTIONS:
        return

    try:
        current_keyboard = query.message.reply_markup.inline_keyboard
        new_reaction_buttons = []
        how_to_play_button = None

        for row in current_keyboard:
            for button in row:
                if button.url:
                    how_to_play_button = button
                    continue
                
                button_emoji = button.callback_data
                button_text = button.text
                match = re.search(r"\((\d+)\)", button_text)
                count = int(match.group(1)) if match else 0
                
                if button_emoji == clicked_emoji:
                    count += 1
                    
                new_text = f"{button_emoji} ({count})"
                new_reaction_buttons.append(InlineKeyboardButton(text=new_text, callback_data=button_emoji))

        new_keyboard_layout = [
            [new_reaction_buttons[0], new_reaction_buttons[1], new_reaction_buttons[2]],
            [new_reaction_buttons[3], new_reaction_buttons[4], new_reaction_buttons[5]],
        ]
        if how_to_play_button:
            new_keyboard_layout.append([how_to_play_button])
            
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard_layout))
        
    except Exception as e:
        logger.warning(f"Failed to update reaction count: {e}")

def stop_all_jobs_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    bot_data = context.application.bot_data['channel_states']
    if chat_id in bot_data:
        state = bot_data[chat_id]
        if 'post_job' in state and state['post_job']:
            state['post_job'].schedule_removal()
        del bot_data[chat_id]
        logger.info(f"All jobs and state for chat {chat_id} stopped and removed.")
        return True
    return False

admin_filter = filters.User(user_id=ADMIN_USER_ID)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "**Welcome, Admin! (v2.8)**\n\n"
        "**New Feature:** You can now set the starting Period Number!\n\n"
        "**How to Use:**\n"
        "`/autotrade on @channel <StartNumber>`\n"
        "Example: `/autotrade on @mychannel 2024050`\n\n"
        "To stop: `/autotrade off @channel`"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def autotrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        command = context.args[0].lower()
        target_channel = context.args[1]
        
        # --- NEW: Get Period Number ---
        start_period = 0
        if command == "on":
            if len(context.args) > 2:
                try:
                    start_period = int(context.args[2])
                except ValueError:
                    await update.message.reply_text("Error: Period number must be an integer.")
                    return
            else:
                await update.message.reply_text("Usage for ON: `/autotrade on @channel <StartPeriodNumber>`", parse_mode='Markdown')
                return
        # ------------------------------

    except (IndexError, TypeError):
        await update.message.reply_text("Usage: `/autotrade <on/off> <@channel> [PeriodNum]`", parse_mode='Markdown')
        return

    try:
        if not target_channel.startswith('@'):
            chat_id = int(target_channel)
        else:
            chat_id = target_channel
    except ValueError:
        await update.message.reply_text("Invalid Channel ID.")
        return

    if 'channel_states' not in context.application.bot_data:
        context.application.bot_data['channel_states'] = {}
    channel_states = context.application.bot_data['channel_states']

    if command == "on":
        if chat_id in channel_states:
            await update.message.reply_text("Bot is already running there.")
            return

        try:
            chat = await context.bot.get_chat(chat_id)
            admins = await context.bot.get_chat_administrators(chat_id)
            if not any(admin.user.id == context.bot.id for admin in admins):
                 await update.message.reply_text(f"❌ Error: I am not an administrator in '{chat.title}'.")
                 return
        except Exception as e:
            await update.message.reply_text(f"❌ Error accessing channel: {e}")
            return

        await update.message.reply_text(f"Verifying...")
        
        channel_states[chat_id] = {
            'prediction_queue': [],
            'current_period': start_period  # Store the user's start number
        }
        
        post_job = context.application.job_queue.run_repeating(
            send_prediction_job,
            interval=POST_INTERVAL,
            first=1,
            chat_id=chat_id,
            name=f"post_{chat_id}"
        )
        
        channel_states[chat_id]['post_job'] = post_job
        
        await update.message.reply_text(f"✅ **Auto Trade Activated!**\nStarting at Period: **{start_period}**")

    elif command == "off":
        if chat_id not in channel_states:
            await update.message.reply_text("Bot is not running there.")
            return
            
        if stop_all_jobs_for_chat(context, chat_id):
            await update.message.reply_text(f"🛑 **Auto Trade Deactivated** for {target_channel}")
        else:
            await update.message.reply_text("Could not stop bot.")

async def unauthorized_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ You are not authorized.")

def main():
    if not TELEGRAM_TOKEN:
        logging.critical("TELEGRAM_TOKEN is not set!")
        return

    job_queue = JobQueue()
    application = Application.builder().token(TELEGRAM_TOKEN).job_queue(job_queue).build()
    
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(CommandHandler("help", start_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(CommandHandler("autotrade", autotrade_command, filters=filters.ChatType.PRIVATE & admin_filter))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~admin_filter), unauthorized_user_handler))
    application.add_handler(CallbackQueryHandler(reaction_handler))

    logger.info(f"Bot starting... (v2.8 - Period Number Feature)")
    application.run_polling()

if __name__ == '__main__':
    main()
```
