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

# --- WELCOME / HELP HANDLER ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    full_name = message.from_user.first_name
    user_first_name = full_name.split()[0] if full_name else "Friend"
    
    welcome_text = (
        f"Hello {user_first_name}, I am Theo.\n"
        "The official assistant for the YouThopia Community.\n\n"
        "My Mission: To deliver God's word to you every morning.\n\n"
        "Features:\n"
        "• Daily Verse: Sent automatically at 6:00 AM\n"
        "• /verse - Receive instant encouragement\n"
        "• /ping - Check connection status\n\n"
        "To share with friends, simply add me to your Group Chat to receive daily updates there automatically."
    )

    bot.reply_to(message, welcome_text, parse_mode="Markdown")  

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