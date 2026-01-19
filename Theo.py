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

# --- BOT CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize Bot
bot = telebot.TeleBot(TOKEN)

# --- DATABASE CONNECTION ---
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client["youthopia_db"]           
    groups_col = db["subscribed_groups"]  
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")

# --- KEEP-ALIVE SERVER (For Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "I am alive"

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_http_server)
    t.start()

# Start Keep Alive
keep_alive()

# --- HELPER FUNCTIONS ---

def main_menu_keyboard():
    """Creates the professional menu buttons"""
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_verse = telebot.types.KeyboardButton("Get Verse")
    btn_ping = telebot.types.KeyboardButton("Check Status")
    btn_help = telebot.types.KeyboardButton("Help")
    markup.add(btn_verse, btn_ping, btn_help)
    return markup

def get_random_verse():
    try:
        # Load local file just to get the list of verses
        with open("encouraging_verses.json", "r") as f:
            data = json.load(f)
            
            if isinstance(data, list):
                verse_list = data
            else:
                verse_list = data["verses"]
            
            # Pick one random reference
            selected_ref = random.choice(verse_list)
            
            # Fetch the text from the API
            url = f"https://bible-api.com/{selected_ref.replace(' ', '+')}?translation=kjv"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            
            return f"{api_data['reference']}\n\n{api_data['text'].strip()}"
    except Exception as e:
        logging.error(f"Error reading file or fetching verse: {e}")
        return "Psalm 23:1 \n\n The LORD is my shepherd, I lack nothing."

def send_morning_verse():
    logging.info("Sending Morning Verse to all groups....")
    verse_text = get_random_verse()
    
    try:
        # Get all groups from MongoDB
        all_groups = groups_col.find()
        
        for group in all_groups:
            chat_id = group["_id"]
            try:
                bot.send_message(chat_id, f"🌅 Good Morning! Verse of the Day:\n\n{verse_text}", parse_mode="Markdown")
                time.sleep(0.5) 
                print(f"Sent to {chat_id}")
            except Exception as e:
                logging.error(f"Failed to send to {chat_id}: {e}")
                
    except Exception as e:
        logging.error(f"Database Read Error: {e}")

# --- SCHEDULER ---
# Run every day at 05:00 UTC (Which is 06:00 Nigeria Time)
schedule.every().day.at("05:00").do(send_morning_verse)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()

# --- BOT COMMANDS ---

@bot.message_handler(commands=["verse"])
def send_verse(message):
    bot.reply_to(message, get_random_verse(), parse_mode="Markdown")

@bot.message_handler(commands=["ping"])
def ping(message):
    bot.reply_to(message, "⚡ I am Alive, Kicking, and connected to the Cloud!")

# --- NEW GROUP HANDLER ---
@bot.message_handler(content_types=["new_chat_members"])
def on_join(message):
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            chat_id = message.chat.id
            chat_name = message.chat.title
            
            # Check DB
            if groups_col.count_documents({"_id": chat_id}) == 0:
                groups_col.insert_one({
                    "_id": chat_id,
                    "name": chat_name,
                    "joined_at": message.date
                })
                print(f"Saved new group to DB: {chat_name}")
                bot.send_message(chat_id, "👋 Hello everyone! I am Theo. I've added this group to my daily list for 6:00 AM verses! 🌅")
            else:
                print(f"Group {chat_name} is already in the database.")

# --- START COMMAND (Greeting & Menu) ---
@bot.message_handler(commands=['start'])
def send_start(message):
    full_name = message.from_user.first_name
    user_first_name = full_name.split()[0] if full_name else "Friend"
    
    # FIXED: Added correct quotation marks for multi-line string
    start_text = (
        f"Hello {user_first_name}.\n"
        "I am Theo.\n"
        "The official assistant for the YouThopia Bible Community.\n\n"
        "My Mission: To deliver God's word to you every morning.\n\n"
        "Features:\n"
        "• Daily Verse: Sent automatically at 6:00 AM\n"
        "• /verse - Receive instant encouragement\n"
        "• /ping - Check connection status\n\n"
        "To share with friends, simply add me to your Group Chat to receive daily updates there automatically."
    )
    
    # Sends the text AND the buttons
    bot.reply_to(message, start_text, reply_markup=main_menu_keyboard())

# --- HELP COMMAND (Instructions) ---
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "Usage Instructions:\n\n"
        "1. Personal Use:\n"
        "Tap the 'Get Verse' button for instant scripture.\n\n"
        "2. Group Schedule:\n"
        "Add me to any Telegram group. I will automatically register the group and send a verse every day at 06:00 AM.\n\n"
        "System Commands:\n"
        "/verse - Fetch a random scripture\n"
        "/ping - Check server status\n"
        "/start - Restart the bot menu"
    )
    bot.reply_to(message, help_text)

# --- HANDLE BUTTON CLICKS ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    text = message.text
    
    if text == "Get Verse":
        bot.reply_to(message, get_random_verse(), parse_mode="Markdown")
        
    elif text == "Check Status":
        bot.reply_to(message, "⚡ System is Online. Connected to Cloud Database.")
        
    elif text == "Help":
        # Call the help function defined above
        send_help(message)
        
    elif message.chat.type == "private":
        bot.reply_to(message, "I did not recognize that command. Please use the menu below.", reply_markup=main_menu_keyboard())

# --- START POLLING ---
if __name__ == "__main__": 
    print("🤖 Theo is running...")
    while True:
        try:
            bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Bot crashed: {e}")
            time.sleep(5)
            continue