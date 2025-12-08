import telebot
import requests
import schedule
import threading
import time

# Replace with your bot's token from BotFather
from dotenv import load_dotenv
import os
# Load variables from .env file
load_dotenv()


# # Check if the .env file is loaded correctly
# if os.getenv("BOT_TOKEN"): 
#     print("Successfully loaded token!")
# else:
#     print("Failed to load token.")
TOKEN = os.getenv("BOT_TOKEN")

# print(f"My bot token is: {TOKEN}")

bot = telebot.TeleBot(TOKEN)
CHAT_ID = "-1001904672000" 

# Function to get a random Bible verse
def get_random_verse():
    try:
       response = requests.get("https://bible-api.com/?random=1" ,  timeout= 10)
       response.raise_for_status()
       data = response.json()
       return f"{data['reference']}\n\n{data['text']}"
    except Exception as e:
       print (f"Error fetching verse: {e}")
       return  "I couldn't fetch a verse right now. Try again later."

# Function to send an automatic Bible verse every morning
def send_morning_verse():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(ascetime), - %(levelname)s -%(message)s")
    logging.info("Sending Morning Verse")
    verse = get_random_verse()
    bot.send_message(CHAT_ID, f"Hey, Good Morning! Here is Today's  Bible verse:\n\n{verse}")

# Schedule the message to run every day at 06:00 AM
schedule.every().day.at("06:00").do(send_morning_verse)


# Function to run the schedule in a separate thread
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every 60 seconds

# Start the scheduler in a new thread
threading.Thread(target=run_scheduler, daemon=True).start()

# Command to send a random Bible verse manually
@bot.message_handler(commands=["verse"])
def send_verse(message):
    bot.reply_to(message, get_random_verse())



@bot.message_handler(commands=["ping"])
def ping(message):

    bot.reply_to(message, "I am alive and Kicking ✔")


print("Bot is running....")
bot.polling(non_stop=True, timeout=60)

