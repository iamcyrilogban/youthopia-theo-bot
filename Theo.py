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
from telebot.types  import Message
from dotenv import load_dotenv


##------ GROUP  CONFIGURATION & FILE MANAGEMENT-------
GROUPS_FILE = "groups.json"
VERSES_FILE = "encouraging_verses.json"


def load_groups():
    try:
        with open(GROUPS_FILE, "r")  as  f:
            return set(json.load(f)) # I used set here to avoid Duplicates
    except FileNotFoundError:
        return set()

#---FUNCTION TO SAVE A NEW GROUP ID----
def save_group(group_id):
    groups = load_groups()
    groups.add(group_id)
    with open(GROUPS_FILE, "w") as f:
        json.dump(list(groups), f)
        logging.info(f"Saved new group ID: {group_id}")
        
        
        
        
        
#--------DATABASE CONFIGURATION--------
MONGO_URI = os.getenv("MONGO_URI")

# 1. Connect to the Cloud
# 'tlsCAFile' tells Python to trust the security certificate of the cloud server.
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    
    # 2. Select the Database (The Cabinet)
    # We are opening a cabinet named "youthopia_db" inside the cloud.
    db = client["youthopia_db"]           
    
    # 3. Select the Collection (The Folder)
    # Inside the cabinet, we are grabbing a folder named "subscribed_groups".
    groups_col = db["subscribed_groups"]  
    
    print("✅ Connected to MongoDB successfully!")

except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    



# --- START OF KEEP-ALIVE SERVER ---
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
keep_alive()

#-----BOT SETUP CONFIGURATION---  
# Load variables from .env file
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


    
def get_random_verse():
    try:
        # 1. Open "encouraging_verses.json" file
        with open(VERSES_FILE, "r") as f:
            data = json.load(f)
            
            
            # 2. Get the list of "verses from the JSON FILE"
            # verse_list = data["verses"]
            
            if isinstance(data, list):
                verse_list = data
            else:
                verse_list = data["verses"]
                
            # 3. Pick one random reference
            selected_ref = random.choice(verse_list)
            
            # 4. Fetch the text from the API
            url = f"https://bible-api.com/{selected_ref.replace(' ',  '+')}?translation=kjv"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            
            return f"{api_data['reference']}\n\n{api_data['text'].strip()}"
    except Exception as e:
        logging.error(f"Error reading file or fetching verse: {e}")
        
        return "Psalm 23:1 \n\n The LORD is my shepherd, I lack nothing."
        

# --- MORNING SCHEDULER (Now Connected to DB) ---
def send_morning_verse():
    logging.info("Sending Morning Verse to all groups....")
    verse_text = get_random_verse()
    
    try:
        # FIXED: Now reading from MongoDB instead of the JSON file
        all_groups = groups_col.find()
        
        for group in all_groups:
            chat_id = group["_id"]
            try:
                bot.send_message(chat_id, f" Good Morning! Verse of the Day:\n\n{verse_text}", parse_mode="Markdown")
                time.sleep(0.5) 
                print(f"Sent to {chat_id}")
            except Exception as e:
                logging.error(f"Failed to send to {chat_id}: {e}")
                
    except Exception as e:
        logging.error(f"Database Read Error: {e}")

# --- SCHEDULER CONFIGURATION ---
schedule.every().day.at("05:00").do(send_morning_verse)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()
    
# --- RENDER SCHEDULER CONFIGURATION ---
# Note: Render servers are usually UTC.
# Nigeria (WAT) is UTC+1. So 05:00 UTC = 06:00 Nigeria time.
schedule.every().day.at("05:00").do(send_morning_verse)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start the scheduler in a separate thread
threading.Thread(target=run_scheduler, daemon=True).start()

# ---   BOT COMMANDS ---
@bot.message_handler(commands=["verse"])
def send_verse(message):
    bot.reply_to(message, get_random_verse(), parse_mode="Markdown")

@bot.message_handler(commands=["ping"])
def ping(message):
    bot.reply_to(message, "I am Alive, Kicking, and connected to the Cloud! ")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    full_name = message.from_user.first_name
    user_first_name = full_name.split()[0] if full_name else "Friend"
    
    
    
#-----WHEN BOT IS ADDED TO A GROUP-----
@bot.message_handler(content_types=["new_chat_members"])
def on_join(message):
    for new_member in message.new_chat_members:
        # Check if the new member is ME (the bot)
        if new_member.id == bot.get_me().id:
            chat_id = message.chat.id
            chat_name = message.chat.title
            
            # --- DATABASE LOGIC STARTS HERE ---
            # 1. Ask the DB: "Do we already have this ID?"
            if groups_col.count_documents({"_id": chat_id}) == 0:
                
                # 2. If NO, insert a new "card" into the folder
                groups_col.insert_one({
                    "_id": chat_id,
                    "name": chat_name,
                    "joined_at": message.date
                })
                print(f"Saved new group to DB: {chat_name}")
                
                bot.send_message(chat_id, "👋 Hello everyone! I am Theo. Thank you for welcoming me! I've added this group to my daily list. I will start sending encouraging scriptures here every morning at 6:00 AM! ")
            else:
                print(f"Group {chat_name} is already in the database.")
    
# --- WELCOME COMMAND ---
# Usage: /start or /help
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    # 1. Get the user's first name
    full_name = message.from_user.first_name
    if full_name:
        user_first_name = full_name.split()[0] 
    else:
        user_first_name = "Friend"
    
    # 2. make a welcome text
    welcome_text = (
        f"👋 *Hi {user_first_name}! I am Theo.* 🤖\n"
        f"The official assistant for the **YouThopia Community**.\n\n"
        "✝️ *My Mission:* To light up your phone with God's word every morning.\n\n"
        "📜 *What I can do:*\n"
        "• Send a Daily Verse automatically at 6:00 AM\n"
        "• /verse - Give you instant encouragement\n"
        "• /ping - Check my connection\n\n"
        "📢 *Want Encouraging verses for your friends?*\n"
        "Just add me to your **Group Chat**, and I'll start posting there automatically!"
    )

    # 3. Send message
    bot.reply_to(message, welcome_text, parse_mode="Markdown")  

# --- INFINITE RESTART LOOP ---
if __name__ == "__main__": 
    while True:
        try:
            bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Bot crashed: {e}")
            time.sleep(5)  # Wait 5 seconds before restarting
            continue
