import json
import os
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

# 1. SETUP: Load the password and connect to the Cloud
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())

# 2. TARGET: Select the destination (The Cloud Database)
# This is where we tell it: "Create 'youthopia_db' if it doesn't exist."
db = client["youthopia_db"]
groups_col = db["subscribed_groups"]

# 3. SOURCE: Open the old file on your computer
try:
    with open("groups.json", "r") as f:
        old_data = json.load(f) # Reads the list: [12345, 67890]
        
    print(f"📂 Found {len(old_data)} groups in your local file.")
    
    # 4. THE LOOP: Move them one by one
    count = 0
    for chat_id in old_data:
        
        # 5. THE UPSERT (Crucial Step!)
        # "update_one" with "upsert=True" means:
        # "If this ID exists, update it. If NOT, create it."
        # This prevents duplicates safely.
        groups_col.update_one(
            {"_id": chat_id}, 
            {
                "$set": {
                    "name": "Imported Group",  # We don't know the real name, so we use a placeholder
                    "joined_at": "2024-Migrated"
                }
            },
            upsert=True
        )
        count += 1
        print(f" -> Moved ID: {chat_id}")
        
    print(f"✅ SUCCESS! Moved {count} groups to MongoDB.")
    print("🚀 NOW you can go check the MongoDB Website!")

except FileNotFoundError:
    print("⚠️ I couldn't find 'groups.json'. Are you sure it's in this folder?")