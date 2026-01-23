import os
import threading
import time
import requests
import schedule
import telebot
import json
import random
import logging
import re  # <--- CRITICAL IMPORT
from flask import Flask
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone

# --- CONFIGURATION ---
load_dotenv()
# TOKEN = os.getenv("BOT_TOKEN")
TOKEN = "8322842073:AAEikbYlaKB1cU5xQ9jwaUusVF3NUWG1PHY"
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

# --- SMART LISTENING CONFIGURATION ---
# 1. The Book List Pattern
BIBLE_BOOKS_PATTERN = (
    r"\b("
    r"Genesis|Gen?|Gn|"
    r"Exodus|Exod?|Ex|"
    r"Leviticus|Lev?|Lv|"
    r"Numbers|Num?|Nm|"
    r"Deuteronomy|Deut?|Dt|"
    r"Joshua|Josh?|Jsh|"
    r"Judges|Judg?|Jdg|"
    r"Ruth|Rth|"
    r"1\s?Samuel|1\s?Sam?|1\s?Sm|"
    r"2\s?Samuel|2\s?Sam?|2\s?Sm|"
    r"1\s?Kings?|1\s?Kgs|"
    r"2\s?Kings?|2\s?Kgs|"
    r"1\s?Chronicles?|1\s?Chr?|"
    r"2\s?Chronicles?|2\s?Chr?|"
    r"Ezra|Ezr|"
    r"Nehemiah|Neh|"
    r"Esther|Esth?|"
    r"Job|Jb|"
    r"Psalms?|Ps|"
    r"Proverbs?|Prov?|Pr|"
    r"Ecclesiastes|Eccl?|Qoh|"
    r"Song\s?of\s?Solomon|Song?|Canticles|"
    r"Isaiah|Isa?|"
    r"Jeremiah|Jer?|"
    r"Lamentations|Lam?|"
    r"Ezekiel|Ezek?|"
    r"Daniel|Dan?|Dn|"
    r"Hosea|Hos|"
    r"Joel|Jl|"
    r"Amos|Am|"
    r"Obadiah|Obad?|Ob|"
    r"Jonah|Jon|"
    r"Micah|Mic|"
    r"Nahum|Nah?|"
    r"Habakkuk|Hab?|"
    r"Zephaniah|Zeph?|"
    r"Haggai|Hag?|"
    r"Zechariah|Zech?|"
    r"Malachi|Mal?|"
    r"Matthew|Matt?|Mt|"
    r"Mark|Mk|"
    r"Luke|Lk|"
    r"John|Jn|"
    r"Acts?|Ac|"
    r"Romans|Rom?|Rm|"
    r"1\s?Corinthians?|1\s?Cor?|"
    r"2\s?Corinthians?|2\s?Cor?|"
    r"Galatians|Gal?|"
    r"Ephesians|Eph?|"
    r"Philippians|Phil?|Php|"
    r"Colossians|Col?|"
    r"1\s?Thessalonians?|1\s?Thess?|1\s?Th|"
    r"2\s?Thessalonians?|2\s?Thess?|2\s?Th|"
    r"1\s?Timothy|1\s?Tim?|1\s?Ti|"
    r"2\s?Timothy|2\s?Tim?|2\s?Ti|"
    r"Titus|Tit|"
    r"Philemon|Philem?|Phlm|"
    r"Hebrews|Heb?|"
    r"James|Jas|"
    r"1\s?Peter|1\s?Pet?|1\s?Pt|"
    r"2\s?Peter|2\s?Pet?|2\s?Pt|"
    r"1\s?John|1\s?Jn|"
    r"2\s?John|2\s?Jn|"
    r"3\s?John|3\s?Jn|"
    r"Jude|Jd|"
    r"Revelation|Rev?|Apoc"
    r")\b"
)

# 2. The Full Regex: Book + Chapter + Separator + Verse
VERSE_REGEX = re.compile(
    BIBLE_BOOKS_PATTERN + r"\s+(\d+)\s*(:|v|vs|verse|\.)\s*(\d+)",
    re.IGNORECASE 
)

# UPDATED: Default verse is now a Dictionary so buttons work even if API fails
DEFAULT_VERSE = {
    "reference": "Psalm 23:1",
    "text": "The LORD is my shepherd, I lack nothing."
}

# --- INITIALIZE BOT ---
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# --- OPTIMIZATION: GET BOT ID ONCE ---
try:
    BOT_INFO = bot.get_me()
    BOT_ID = BOT_INFO.id
    logger.info(f"Bot Identity Verified: {BOT_INFO.first_name} (ID: {BOT_ID})")
except Exception as e:
    logger.critical(f"Failed to get Bot ID: {e}")
    BOT_ID = 0

# --- DATABASE CLASSES ---

class MockDatabase:
    """A Fake Database for Local Testing (Used when Real DB fails)"""
    def __init__(self):
        self.groups = []
        logger.warning("WARNING: RUNNING IN DUMMY MODE (Mock DB). Data will be lost on restart.")

    def add_group(self, chat_id, chat_name, joined_date):
        for g in self.groups:
            if g["_id"] == chat_id:
                return False
        self.groups.append({"_id": chat_id, "name": chat_name, "joined_at": joined_date})
        logger.info(f"Mock DB: Added group {chat_name}")
        return True

    def remove_group(self, chat_id):
        initial_len = len(self.groups)
        self.groups = [g for g in self.groups if g["_id"] != chat_id]
        return len(self.groups) < initial_len

    def get_all_groups(self):
        return self.groups

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
            # Try removing as Int and String to be safe
            result_int = self.groups_col.delete_one({"_id": chat_id})
            result_str = self.groups_col.delete_one({"_id": str(chat_id)})
            
            if result_int.deleted_count > 0 or result_str.deleted_count > 0:
                logger.info(f"Removed group {chat_id} from database")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing group from database: {e}")
            return False

# --- SMART DATABASE SWITCH ---
# FIX: Prevents "Zombie Mode" on production.
db_handler = None

if not MONGO_URI:
    # Scenario 1: No Link provided (Local Testing / Random Editor)
    logger.warning("⚠️ MONGO_URI not found. Using MockDatabase (Data will be lost on restart).")
    db_handler = MockDatabase()
else:
    # Scenario 2: Link provided (Production / Render)
    try:
        db_handler = Database(MONGO_URI)
    except Exception as e:
        # If the Real DB fails, we MUST crash so the server restarts.
        # Do not switch to MockDB here, or you will lose user data!
        logger.critical(f"❌ Failed to connect to Real MongoDB: {e}")
        raise e  # Stops the bot completely

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
        if isinstance(db_handler, Database):
            db_handler.client.admin.command('ping')
            db_status = "connected"
        else:
            db_status = "mock_mode"
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
    """Creates the professional menu buttons with Subscribe option"""
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    btn_verse = telebot.types.KeyboardButton("Get Verse")
    btn_sub = telebot.types.KeyboardButton("Subscribe")
    btn_ping = telebot.types.KeyboardButton("Check Status")
    btn_help = telebot.types.KeyboardButton("Help")
    
    markup.add(btn_verse, btn_sub, btn_ping, btn_help)
    return markup

def get_verse_markup(verse_data, current_translation="web"):
    """Creates Inline Buttons for Sharing and Translation Switching"""
    markup = telebot.types.InlineKeyboardMarkup()
    
    # 1. Share Button (Uses Telegram Share URL)
    # Reverted to clean share without promotional header
    share_text = f"{verse_data['reference']} ({current_translation.upper()})\n\n{verse_data['text']}"
    
    share_url = f"https://t.me/share/url?url={requests.utils.quote(share_text)}"
    markup.add(telebot.types.InlineKeyboardButton("📤 Share with Friends", url=share_url))
    
    # 2. Translation Buttons
    ref = verse_data['reference']
    
    # Create row of buttons. Highlight the current one with brackets []
    btn_web = telebot.types.InlineKeyboardButton(
        "[WEB]" if current_translation == "web" else "WEB", 
        callback_data=f"trans|web|{ref}"
    )
    btn_kjv = telebot.types.InlineKeyboardButton(
        "[KJV]" if current_translation == "kjv" else "KJV", 
        callback_data=f"trans|kjv|{ref}"
    )
    btn_bbe = telebot.types.InlineKeyboardButton(
        "[BBE]" if current_translation == "bbe" else "BBE", 
        callback_data=f"trans|bbe|{ref}"
    )
    
    markup.row(btn_web, btn_kjv, btn_bbe)
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

def fetch_verse_from_api(reference, translation="web"):
    try:
        formatted_ref = reference.replace(' ', '+')
        url = f"{BIBLE_API_URL}/{formatted_ref}?translation={translation}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json() # Returns the raw data dictionary
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_random_verse():
    verse_list = load_verse_references()
    
    # Try 3 times to get a verse
    for _ in range(3):
        # Pick reference
        selected_ref = random.choice(verse_list) if verse_list else "John 3:16"
        # Fetch data
        verse_data = fetch_verse_from_api(selected_ref)
        if verse_data:
            return verse_data # Returns dictionary: {'reference': '...', 'text': '...'}
        time.sleep(0.5)
    
    # Fallback if API fails (Uses the Dictionary now)
    return DEFAULT_VERSE

def send_morning_verse():
    logger.info("Starting morning verse broadcast...")
    data = get_random_verse()
    
    # Prepare text and buttons
    text = f"*{data['reference']}* (WEB)\n\n{data['text'].strip()}"
    markup = get_verse_markup(data, "web")
    
    all_groups = db_handler.get_all_groups()
    success_count = 0
    
    for group in all_groups:
        chat_id = group["_id"]
        try:
            bot.send_message(chat_id, f"*Good Morning!*\n\n{text}", reply_markup=markup)
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

# --- UNIFIED REGISTER COMMAND ---
@bot.message_handler(commands=["register"])
def register(m):
    """Fix for: 'I am in the group but bot is silent'"""
    
    # 1. Safety Check (If DB is missing completely)
    if db_handler is None:
        bot.reply_to(m, "Critical Error: Database not initialized.")
        return

    # 2. Check if this is a private chat (The Bouncer)
    if m.chat.type == "private":
        bot.reply_to(m, "This command is for Groups only.\n\nAdd me to a Group and type /register there to set up daily verses!")
        return

    # 3. Proceed with registration if it's a group (The Guest List)
    if db_handler.add_group(m.chat.id, m.chat.title, m.date):
        bot.reply_to(m, "Success! This group is now registered for daily verses.")
    else:
        bot.reply_to(m, "This group is already registered. Use /force_verse to test.")

@bot.message_handler(commands=["force_verse"])
def force_verse(m):
    """Secured Test command - Only the Admin can use this"""
    
    # SECURITY CHECK: Is this the Admin?
    if m.from_user.id != ADMIN_ID:
        # Log the attempt so you know someone tried it
        logger.warning(f"Unauthorized broadcast attempt by {m.from_user.first_name} (ID: {m.from_user.id})")
        # Ignore them (Security through silence)
        return

    bot.reply_to(m, "Authorized. Sending verse blast now...")
    send_morning_verse()

@bot.message_handler(commands=["reset_group"])
def reset_group(m):
    """Safely removes group/user from DB (Admins Only in Groups)"""
    try:
        # 1. Private Chat Logic (Users can always unsubscribe themselves)
        if m.chat.type == "private":
            if db_handler.remove_group(m.chat.id):
                bot.reply_to(m, "Memory wiped! You are unsubscribed.")
            else:
                bot.reply_to(m, "You were not subscribed.")
            return

        # 2. Group Chat Logic (SECURITY CHECK)
        # Check if the user is an Admin or Creator
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
        
        # Allow if they are Admin, Creator, OR if it is YOU (The Bot Owner)
        if member.status not in ['administrator', 'creator'] and m.from_user.id != ADMIN_ID:
            bot.reply_to(m, "❌ Permission Denied. Only Group Admins can run this command.")
            return

        # 3. Perform Removal
        if db_handler.remove_group(m.chat.id):
            bot.reply_to(m, "🗑️ Memory wiped! This group is unsubscribed.")
        else:
            bot.reply_to(m, "⚠️ Group was not in database.")

    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@bot.message_handler(commands=["verse"])
def send_verse(message):
    try:
        # 1. Get Dictionary Data
        data = get_random_verse()
        
        # 2. Format Text
        msg_text = f"*{data['reference']}* (WEB)\n\n{data['text'].strip()}"
        
        # 3. Create Buttons using the helper function
        markup = get_verse_markup(data, "web")
        
        # 4. Send with Buttons
        bot.reply_to(message, msg_text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in /verse command: {e}")
        bot.reply_to(message, "Error fetching verse.")

@bot.message_handler(commands=["ping"])
def ping(message):
    try:
        if isinstance(db_handler, Database):
            db_handler.client.admin.command('ping')
            db_status = "Connected"
        else:
            db_status = "Mock DB (Test Mode)"
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
        # --- CRITICAL FIX: Use Cached BOT_ID ---
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("trans|"))
def handle_translation_switch(call):
    """Updates the verse text when a translation button is clicked"""
    try:
        # Parse the data we hid in the button: "trans|kjv|John 3:16"
        _, new_trans, ref = call.data.split("|", 2)
        
        # Fetch the NEW translation
        new_data = fetch_verse_from_api(ref, new_trans)
        
        if new_data:
            # Create the new text
            new_text = f"*{new_data['reference']}* ({new_trans.upper()})\n\n{new_data['text'].strip()}"
            
            # Update the message in the chat (Edit Message)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=new_text,
                parse_mode="Markdown",
                reply_markup=get_verse_markup(new_data, new_trans) # Update buttons too
            )
            bot.answer_callback_query(call.id, f"Switched to {new_trans.upper()}")
            
    except Exception as e:
        logger.error(f"Translation switch failed: {e}")
        bot.answer_callback_query(call.id, "Failed to switch translation.")

# --- PASSIVE LISTENER HANDLER (MUST BE ABOVE HANDLE_TEXT) ---
@bot.message_handler(func=lambda m: VERSE_REGEX.search(m.text))
def handle_passive_verse(message):
    """
    Listens for patterns like 'John 3:16' or 'Matt 3 vs 4'
    and replies with the scripture automatically.
    """
    try:
        # 1. Find the match in the user's text
        match = VERSE_REGEX.search(message.text)
        if not match: return

        # 2. Extract the parts (Book, Chapter, Separator, Verse)
        # Group 1 is Book, Group 2 is Chapter, Group 4 is Verse
        book = match.group(1)
        chapter = match.group(2)
        verse_num = match.group(4)
        
        # 3. Construct a clean reference (e.g., "Matthew 3:16")
        reference = f"{book} {chapter}:{verse_num}"
        
        # 4. Fetch from API
        # We pass the constructed reference to your existing function
        data = fetch_verse_from_api(reference)
        
        if data:
            # 5. Send Reply (Using your existing Button Helper)
            # We use 'reply_to_message_id' so Theo quotes the specific message
            text = f"*{data['reference']}* (WEB)\n\n{data['text'].strip()}"
            markup = get_verse_markup(data, "web")
            
            bot.reply_to(message, text, reply_markup=markup)
            
            # Log it so you know it's working
            logger.info(f"Auto-detected verse: {reference} from {message.from_user.first_name}")
            
    except Exception as e:
        # If it wasn't a real verse (e.g. 'Matrix 1:1'), just stay silent
        logger.warning(f"Passive listener error: {e}")

# --- TEXT HANDLER (MUST BE LAST) ---
@bot.message_handler(func=lambda m: True)
def handle_text(m):
    text = m.text
    
    if text == "Get Verse": 
        send_verse(m)
    elif text == "Check Status": 
        ping(m)
    elif text == "Help": 
        send_help(m)
        
    elif text == "Subscribe":
        # If in a group, use Title. If Private DM, use First Name.
        name = m.chat.title or m.from_user.first_name or "Subscriber"
        
        # Save to database (Treating the User ID just like a Group ID)
        if db_handler.add_group(m.chat.id, name, m.date):
            bot.reply_to(m, "Subscribed! You will receive daily verses in your DM every morning.")
        else:
            bot.reply_to(m, "You are already subscribed!")
            
    elif m.chat.type == "private":
         bot.reply_to(m, "I didn't recognize that command. Use the buttons below.", reply_markup=main_menu_keyboard())

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