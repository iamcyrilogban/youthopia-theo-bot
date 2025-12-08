import os
import threading
import time
import requests
import schedule
import telebot
import logging
from flask import Flask
from dotenv import load_dotenv

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

# Start the server immediately so Render sees the open port
keep_alive()
# --- END OF KEEP-ALIVE SERVER ---

# Load variables from .env file
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)
CHAT_ID = "-1001904672000"

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Function to get a random Bible verse
def get_random_verse():
    try:
        response = requests.get("https://bible-api.com/?random=1", timeout=10)
        response.raise_for_status()
        data = response.json()
        return f"{data['reference']}\n\n{data['text']}"
    except Exception as e:
        logging.error(f"Error fetching verse: {e}")
        return "I couldn't fetch a verse right now. Try again later."

# Function to send an automatic Bible verse every morning
def send_morning_verse():
    logging.info("Sending Morning Verse")
    verse = get_random_verse()
    bot.send_message(CHAT_ID, f"Hey, Good Morning! Here is Today's Bible verse:\n\n{verse}")

# --- SCHEDULER CONFIGURATION ---
# Note: Render servers are usually UTC.
# Nigeria (WAT) is UTC+1. So 05:00 UTC = 06:00 Nigeria time.
schedule.every().day.at("05:00").do(send_morning_verse)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start the scheduler in a separate thread
threading.Thread(target=run_scheduler, daemon=True).start()

# --- BOT COMMANDS ---
@bot.message_handler(commands=["verse"])
def send_verse(message):
    bot.reply_to(message, get_random_verse())

@bot.message_handler(commands=["ping"])
def ping(message):
    bot.reply_to(message, "I am Alive and Kicking ✔")

print("Bot is running....")
bot.polling(non_stop=True, timeout=60)
