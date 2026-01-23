import os
import threading
import time
import requests
import schedule
import telebot
import json
import random
import logging
from flask import Flask
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
# Add ADMIN_ID to your .env file to secure the force_verse command
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Setup Enhanced Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- CONSTANTS ---
BIBLE_API_URL = "https://bible-api.com"
BIBLE_TRANSLATION = "web"
MORNING_VERSE_TIME = "05:00"  # UTC (06:00 Nigeria Time)
VERSES_FILE = "encouraging_verses.json"
DEFAULT_VERSE = "Psalm 23:1\n\nThe LORD is my shepherd, I lack nothing."

# --- INITIALIZE BOT ---
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# --- OPTIMIZATION: GET BOT ID ONCE ---
# This fixes the bug where the bot doesn't respond when added to groups
# because it was trying to fetch its ID too slowly.
try:
    BOT_INFO = bot.get_me()
    BOT_ID = BOT_INFO.id
    logger.info(f"Bot Identity Verified: {BOT_INFO.first_name} (ID: {BOT_ID})")
except Exception as e:
    logger.critical(f"Failed to get Bot ID: {e}")
    BOT_ID = 0

# --- DATABASE CONNECTION ---
class Database:
    """Database handler with connection pooling and error handling"""
    
    def __init__(self, uri):
        self.client = None
        self.db = None
        self.groups_col = None
        self.connect(uri)
    
    def connect(self, uri):
        try:
            self.client = MongoClient(
                uri,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50
            )
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client["youthopia_db"]
            self.groups_col = self.db["subscribed_groups"]
            logger.info("Connected to MongoDB successfully!")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def add_group(self, chat_id, chat_name, joined_date):
        """Add a new group to the database"""
        try:
            if self.groups_col.count_documents({"_id": chat_id}) == 0:
                self.groups_col.insert_one({
                    "_id": chat_id,
                    "name": chat_name,
                    "joined_at": joined_date,
                    "created_at": datetime.now(timezone.utc)
                })
                logger.info(f"Added new group: {chat_name} ({chat_id})")
                return True
            logger.info(f"Group {chat_name} already exists in database")
            return False
        except Exception as e:
            logger.error(f"Error adding group to database: {e}")
            return False
    
    def get_all_groups(self):
        """Retrieve all subscribed groups"""
        try:
            return list(self.groups_col.find())
        except Exception as e:
            logger.error(f"Error fetching groups from database: {e}")
            return []
    
    def remove_group(self, chat_id):
        """Remove a group from the database"""
        try:
            result = self.groups_col.delete_one({"_id": chat_id})
            if result.deleted_count > 0:
                logger.info(f"Removed group {chat_id} from database")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing group from database: {e}")
            return False

# Initialize database
try:
    db_handler = Database(MONGO_URI)
except Exception as e:
    logger.critical(f"CRITICAL DATABASE FAILURE: {e}")

# --- KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return {
        "status": "online",
        "bot": "Theo",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        db_handler.client.admin.command('ping')
        db_status = "connected"
    except:
        db_status = "disconnected"
    
    return {
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

def keep_alive():
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    logger.info("Keep-alive server started")

# --- HELPER FUNCTIONS ---

def main_menu_keyboard():
    """Creates the professional menu buttons"""
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_verse = telebot.types.KeyboardButton("Get Verse")
    btn_ping = telebot.types.KeyboardButton("Check Status")
    btn_help = telebot.types.KeyboardButton("Help")
    markup.add(btn_verse, btn_ping, btn_help)
    return markup

def load_verse_references():
    try:
        with open(VERSES_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "verses" in data:
                return data["verses"]
            else:
                return []
    except:
        return []

def fetch_verse_from_api(reference):
    try:
        formatted_ref = reference.replace(' ', '+')
        url = f"{BIBLE_API_URL}/{formatted_ref}?translation={BIBLE_TRANSLATION}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        api_data = response.json()
        
        return f"*{api_data['reference']}*\n\n{api_data['text'].strip()}"
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_random_verse():
    verse_list = load_verse_references()
    
    if not verse_list:
        return f"{DEFAULT_VERSE}"
    
    for _ in range(3):
        selected_ref = random.choice(verse_list)
        verse_text = fetch_verse_from_api(selected_ref)
        if verse_text:
            return verse_text
        time.sleep(0.5)
    
    return f"{DEFAULT_VERSE}"

def send_morning_verse():
    logger.info("Starting morning verse broadcast...")
    verse_text = get_random_verse()
    
    all_groups = db_handler.get_all_groups()
    success_count = 0
    
    for group in all_groups:
        chat_id = group["_id"]
        try:
            bot.send_message(
                chat_id,
                f"*Good Morning!*\n\nVerse of the Day:\n\n{verse_text}"
            )
            success_count += 1
            time.sleep(0.5)
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code in [403, 400]:
                db_handler.remove_group(chat_id)
            else:
                logger.error(f"Failed to send to {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Error sending to {chat_id}: {e}")
    
    logger.info(f"Broadcast complete. Success: {success_count}")

# --- SCHEDULER ---
schedule.every().day.at(MORNING_VERSE_TIME).do(send_morning_verse)

def run_scheduler():
    logger.info(f"Scheduler started. Morning verses at {MORNING_VERSE_TIME} UTC")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(60)

# --- BOT COMMAND HANDLERS ---

@bot.message_handler(commands=["start"])
def send_start(message):
    full_name = message.from_user.first_name or "Friend"
    user_first_name = full_name.split()[0]
    
    start_text = (
        f"Hello {user_first_name}!\n\n"
        "I am Theo, the official assistant for the YouThopia Bible Community.\n\n"
        "My Mission:\n"
        "To deliver God's word to you every morning at 6:00 AM.\n\n"
        "Features:\n"
        "- Daily Verse delivered automatically\n"
        "- /verse - Get instant encouragement\n"
        "- /ping - Check my connection status\n\n"
        "Tip: Add me to your group chat to receive daily updates there automatically!"
    )
    
    bot.reply_to(message, start_text, reply_markup=main_menu_keyboard())

@bot.message_handler(commands=["help"])
def send_help(message):
    help_text = (
        "Usage Instructions:\n\n"
        "1. Personal Use:\n"
        "Tap the 'Get Verse' button for instant scripture.\n\n"
        "2. Group Schedule:\n"
        "Add me to any Telegram group. I will automatically register and send verses daily at 06:00 AM.\n\n"
        "System Commands:\n"
        "/verse - Fetch a random scripture\n"
        "/ping - Check Online Status\n"
        "/register - Manually register this group for daily verses\n"
        "/start - Restart the bot menu"
    )
    bot.reply_to(message, help_text)


@bot.message_handler(commands=["register"])
def register(m):
    """Fix for: 'I am in the group but bot is silent'"""
    # 1. Check if this is a private chat (The Bouncer)
    if m.chat.type == "private":
        bot.reply_to(m, "This command is for Groups only.\n\nAdd me to a Group and type /register there to set up daily verses!")
        return

    # 2. Proceed with registration if it's a group (The Guest List)
    if db_handler.add_group(m.chat.id, m.chat.title, m.date):
        bot.reply_to(m, "Success! This group is now registered for daily verses.")
    else:
        bot.reply_to(m, "This group is already registered. Use /force_verse to test.")

# --- CRITICAL FIX 1: MANUAL REGISTER COMMAND ---
@bot.message_handler(commands=["register"])
def register_group(message):
    """Fix for groups that aren't receiving verses"""
    if db_handler.add_group(message.chat.id, message.chat.title, message.date):
        bot.reply_to(message, "Success! This group is now registered for daily verses.")
    else:
        bot.reply_to(message, "This group is already registered. Use /force_verse to test.")

# --- CRITICAL FIX 2: FORCE VERSE COMMAND ---
@bot.message_handler(commands=["force_verse"])
def force_verse(message):
    """Test command to verify sending works"""
    bot.reply_to(message, "Sending verse blast now...")
    send_morning_verse()

# --- CRITICAL FIX 3: RESET GROUP COMMAND ---
@bot.message_handler(commands=["reset_group"])
def reset_group(message):
    """Fix for testing welcome messages"""
    if db_handler.remove_group(message.chat.id):
        bot.reply_to(message, "Memory wiped! Remove me and add me again to see the 'Hello' message.")
    else:
        bot.reply_to(message, "Group was not in database.")

@bot.message_handler(commands=["verse"])
def send_verse(message):
    try:
        verse = get_random_verse()
        bot.reply_to(message, verse)
    except Exception as e:
        logger.error(f"Error in /verse command: {e}")
        bot.reply_to(message, "Error fetching verse.")

@bot.message_handler(commands=["ping"])
def ping(message):
    try:
        db_handler.client.admin.command('ping')
        db_status = "Connected"
    except:
        db_status = "Disconnected"
    
    response = (
        "System Status\n\n"
        "Bot: Online\n"
        f"Database: {db_status}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
    )
    bot.reply_to(message, response)

@bot.message_handler(content_types=["new_chat_members"])
def on_join(message):
    for new_member in message.new_chat_members:
        # --- CRITICAL FIX 4: Use Cached BOT_ID ---
        if new_member.id == BOT_ID:
            chat_id = message.chat.id
            chat_name = message.chat.title or "Unknown Group"
            
            is_new = db_handler.add_group(chat_id, chat_name, message.date)
            
            if is_new:
                welcome_text = (
                    "Hello everyone!\n\n"
                    "Thank you for adding me to your community.\n\n"
                    "I am Theo, your daily Bible verse companion.\n\n"
                    "I've added this group to receive daily verses at 6:00 AM!\n\n"
                    "Use /help to see what I can do."
                )
            else:
                welcome_text = (
                    "Welcome back!\n\n"
                    "This group is already registered for daily verses.\n\n"
                    "Use /help for more information."
                )
            
            bot.send_message(chat_id, welcome_text)

@bot.message_handler(content_types=["left_chat_member"])
def on_leave(message):
    # Use Cached BOT_ID
    if message.left_chat_member.id == BOT_ID:
        chat_id = message.chat.id
        db_handler.remove_group(chat_id)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    text = message.text
    
    if text == "Get Verse":
        send_verse(message)
    elif text == "Check Status":
        ping(message)
    elif text == "Help":
        send_help(message)
    elif message.chat.type == "private":
        bot.reply_to(
            message,
            "I didn't recognize that command. Please use the menu below or type /help.",
            reply_markup=main_menu_keyboard()
        )

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    logger.info("Starting Theo Bot...")

    # --- MENU CONFIGURATION (Small Caps Style) ---
    desc_verse = "ɢᴇᴛ ᴀ ʀᴀɴᴅᴏᴍ ᴠᴇʀsᴇ"
    desc_help = "sʜᴏᴡ ᴜsᴀɢᴇ ɪɴsᴛʀᴜᴄᴛɪᴏɴs"
    desc_ping = "ᴄʜᴇᴄᴋ ᴄᴏɴɴᴇᴄᴛɪᴏɴ sᴛᴀᴛᴜs"
    desc_start = "ʀᴇsᴛᴀʀᴛ ʙᴏᴛ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴ"
    desc_reg = "ʀᴇɢɪsᴛᴇʀ ɢʀᴏᴜᴘ ғᴏʀ ᴅᴀɪʟʏ ᴠᴇʀsᴇs"

    # --- SMART MENU SYSTEM ---
    try:
        # 1. Menu for Private Chats (Hides /register)
        bot.set_my_commands(
            commands=[
                telebot.types.BotCommand("verse", desc_verse),
                telebot.types.BotCommand("help", desc_help),
                telebot.types.BotCommand("ping", desc_ping),
                telebot.types.BotCommand("start", desc_start)
            ],
            scope=telebot.types.BotCommandScopeAllPrivateChats()
        )

        # 2. Menu for Groups (Shows /register)
        bot.set_my_commands(
            commands=[
                telebot.types.BotCommand("verse", desc_verse),
                telebot.types.BotCommand("register", desc_reg),
                telebot.types.BotCommand("help", desc_help),
                telebot.types.BotCommand("ping", desc_ping)
            ],
            scope=telebot.types.BotCommandScopeAllGroupChats()
        )
        logger.info("Smart menus set successfully")
    except Exception as e:
        logger.error(f"Failed to set menus: {e}")

    # Start keep-alive server
    keep_alive()
    
    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start bot polling
    logger.info("Theo is now running and ready to serve!")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}")
            time.sleep(5)
            logger.info("Attempting to restart polling...")
            continue