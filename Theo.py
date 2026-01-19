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

# Setup Enhanced Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler() # Render captures stdout/stderr automatically
    ]
)
logger = logging.getLogger(__name__)

# --- CONSTANTS ---
BIBLE_API_URL = "https://bible-api.com"
BIBLE_TRANSLATION = "kjv"
MORNING_VERSE_TIME = "05:00"  # UTC (06:00 Nigeria Time)
VERSES_FILE = "encouraging_verses.json"
DEFAULT_VERSE = "Psalm 23:1\n\nThe LORD is my shepherd, I lack nothing."

# --- INITIALIZE BOT ---
# We set parse_mode="Markdown" here so we don't have to type it every time
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

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
            logger.info("✅ Connected to MongoDB successfully!")
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
# We wrap this in a try/except to prevent the whole script from failing instantly on local start
try:
    db_handler = Database(MONGO_URI)
except Exception as e:
    logger.critical(f"CRITICAL DATABASE FAILURE: {e}")
    # We continue so Flask can still start (for debugging), but bot features will fail.

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
        # Check database connection
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
    """Run Flask server in a separate thread"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

def keep_alive():
    """Start the keep-alive server"""
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    logger.info(f"Keep-alive server started")

# --- HELPER FUNCTIONS ---

def main_menu_keyboard():
    """Creates the professional menu buttons"""
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_verse = telebot.types.KeyboardButton("📖 Get Verse")
    btn_ping = telebot.types.KeyboardButton("⚡ Check Status")
    btn_help = telebot.types.KeyboardButton("❓ Help")
    markup.add(btn_verse, btn_ping, btn_help)
    return markup

def load_verse_references():
    """Load verse references from local JSON file"""
    try:
        with open(VERSES_FILE, "r") as f:
            data = json.load(f)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "verses" in data:
                return data["verses"]
            else:
                logger.error("Invalid JSON structure in verses file")
                return []
    except FileNotFoundError:
        logger.error(f"Verses file not found: {VERSES_FILE}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in verses file: {e}")
        return []

def fetch_verse_from_api(reference):
    """Fetch verse text from Bible API"""
    try:
        formatted_ref = reference.replace(' ', '+')
        url = f"{BIBLE_API_URL}/{formatted_ref}?translation={BIBLE_TRANSLATION}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        api_data = response.json()
        
        return f"📖 *{api_data['reference']}*\n\n{api_data['text'].strip()}"
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed for {reference}: {e}")
        return None
    except (KeyError, ValueError) as e:
        logger.error(f"Invalid API response for {reference}: {e}")
        return None

def get_random_verse():
    """Get a random Bible verse"""
    verse_list = load_verse_references()
    
    if not verse_list:
        logger.warning("No verses available, returning default verse")
        return f"📖 {DEFAULT_VERSE}"
    
    # Try up to 3 times to get a valid verse
    for _ in range(3):
        selected_ref = random.choice(verse_list)
        verse_text = fetch_verse_from_api(selected_ref)
        
        if verse_text:
            return verse_text
        
        time.sleep(0.5)  # Brief pause before retry
    
    # Fallback to default verse
    logger.warning("Failed to fetch verse from API, using default")
    return f"📖 {DEFAULT_VERSE}"

def send_morning_verse():
    """Send morning verse to all subscribed groups"""
    logger.info("Starting morning verse broadcast...")
    verse_text = get_random_verse()
    
    all_groups = db_handler.get_all_groups()
    success_count = 0
    fail_count = 0
    
    for group in all_groups:
        chat_id = group["_id"]
        try:
            bot.send_message(
                chat_id,
                f"🌅 *Good Morning!*\n\n_Verse of the Day:_\n\n{verse_text}"
                # parse_mode="Markdown" is handled by default now
            )
            success_count += 1
            time.sleep(0.5)  # Rate limiting
            logger.info(f"Sent morning verse to {chat_id}")
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403:  # Bot was kicked/blocked
                logger.warning(f"Bot removed from group {chat_id}, cleaning up database")
                db_handler.remove_group(chat_id)
            else:
                logger.error(f"Failed to send to {chat_id}: {e}")
            fail_count += 1
        except Exception as e:
            logger.error(f"Unexpected error sending to {chat_id}: {e}")
            fail_count += 1
    
    logger.info(f"Morning verse broadcast complete. Success: {success_count}, Failed: {fail_count}")

# --- SCHEDULER ---
schedule.every().day.at(MORNING_VERSE_TIME).do(send_morning_verse)

def run_scheduler():
    """Run the scheduler in a loop"""
    logger.info(f"Scheduler started. Morning verses at {MORNING_VERSE_TIME} UTC")
    while True:
        schedule.run_pending()
        time.sleep(60)

# --- BOT COMMAND HANDLERS ---

@bot.message_handler(commands=["start"])
def send_start(message):
    """Handle /start command"""
    full_name = message.from_user.first_name or "Friend"
    user_first_name = full_name.split()[0]
    
    start_text = (
        f"👋 *Hello {user_first_name}!*\n\n"
        "I am *Theo*, the official assistant for the YouThopia Bible Community.\n\n"
        "🎯 *My Mission:*\n"
        "To deliver God's word to you every morning at 6:00 AM.\n\n"
        "✨ *Features:*\n"
        "• Daily Verse delivered automatically\n"
        "• /verse - Get instant encouragement\n"
        "• /ping - Check my connection status\n\n"
        "💡 *Tip:* Add me to your group chat to receive daily updates there automatically!"
    )
    
    bot.reply_to(message, start_text, reply_markup=main_menu_keyboard())

@bot.message_handler(commands=["help"])
def send_help(message):
    """Handle /help command"""
    help_text = (
        "📚 *Usage Instructions*\n\n"
        "*Personal Use:*\n"
        "Tap the '📖 Get Verse' button for instant scripture.\n\n"
        "*Group Schedule:*\n"
        "Add me to any Telegram group. I will automatically register and send verses daily at 06:00 AM.\n\n"
        "*Commands:*\n"
        "• /verse - Fetch a random scripture\n"
        "• /ping - Check server status\n"
        "• /start - Restart the bot\n"
        "• /help - Show this message"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=["verse"])
def send_verse(message):
    """Handle /verse command"""
    try:
        verse = get_random_verse()
        bot.reply_to(message, verse)
    except Exception as e:
        logger.error(f"Error in /verse command: {e}")
        bot.reply_to(message, "Sorry, I encountered an error fetching a verse. Please try again.")

@bot.message_handler(commands=["ping"])
def ping(message):
    """Handle /ping command"""
    try:
        # Check database connection
        db_handler.client.admin.command('ping')
        db_status = "✅ Connected"
    except:
        db_status = "❌ Disconnected"
    
    response = (
        f"⚡ *System Status*\n\n"
        f"Bot: ✅ Online\n"
        f"Database: {db_status}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    bot.reply_to(message, response)

@bot.message_handler(content_types=["new_chat_members"])
def on_join(message):
    """Handle bot being added to a group"""
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            chat_id = message.chat.id
            chat_name = message.chat.title or "Unknown Group"
            
            is_new = db_handler.add_group(chat_id, chat_name, message.date)
            
            if is_new:
                welcome_text = (
                    "👋 *Hello everyone!*\n\n"
                    "I am Theo, your daily Bible verse companion.\n\n"
                    "I've added this group to receive daily verses at 6:00 AM! 🌅\n\n"
                    "Use /help to see what I can do."
                )
            else:
                welcome_text = (
                    "👋 *Welcome back!*\n\n"
                    "This group is already registered for daily verses.\n\n"
                    "Use /help for more information."
                )
            
            bot.send_message(chat_id, welcome_text)

@bot.message_handler(content_types=["left_chat_member"])
def on_leave(message):
    """Handle bot being removed from a group"""
    # Note: Telebot still supports 'left_chat_member' for backwards compatibility
    # If this triggers, it means someone removed the bot.
    if message.left_chat_member.id == bot.get_me().id:
        chat_id = message.chat.id
        db_handler.remove_group(chat_id)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    """Handle all other messages"""
    text = message.text
    
    if text in ["📖 Get Verse", "Get Verse"]:
        send_verse(message)
    elif text in ["⚡ Check Status", "Check Status"]:
        ping(message)
    elif text in ["❓ Help", "Help"]:
        send_help(message)
    elif message.chat.type == "private":
        bot.reply_to(
            message,
            "I didn't recognize that command. Please use the menu below or type /help.",
            reply_markup=main_menu_keyboard()
        )

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    logger.info("🤖 Starting Theo Bot...")
    
    # Start keep-alive server
    keep_alive()
    
    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start bot polling with reconnection logic
    logger.info("✅ Theo is now running and ready to serve!")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}")
            time.sleep(5)
            logger.info("Attempting to restart polling...")
            continue