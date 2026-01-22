# Theo - The YouThopia Bible Community

**Theo** is a robust, persistent Telegram bot engineered to automate daily spiritual engagement for the **YouThopia Bible Community**. 

Unlike simple scripts, Theo utilizes a multi-threaded architecture with MongoDB persistence to ensure reliability, handling daily scheduled broadcasts to multiple groups simultaneously without data loss.

---

## Key Features

### Core Functionality
* **Automated Scheduler:** Broadcasts a random Bible verse (WEB Translation) every morning at **06:00 AM (WAT) / 05:00 UTC**.
* **Persistent Storage:** Uses **MongoDB Atlas** to save registered groups. Data survives bot restarts, crashes, or updates.
* **Smart Fallback:** If the external Bible API fails, the bot seamlessly falls back to a local cache of encouraged verses.
* **Group Management:** Automatically detects when added/removed from groups and updates the database in real-time.

### Engineering Highlights
* **Connection Pooling:** Optimized MongoDB connection handling to prevent timeouts.
* **Fault Tolerance:** Implements `infinity_polling` and `try-catch` blocks to auto-recover from network failures.
* **Keep-Alive Server:** Integrated **Flask** web server running on a separate thread to prevent cloud provider sleep/timeout.
* **Log System:** Enhanced logging for debugging scheduler events and API errors.

---

## Tech Stack

* **Language:** Python 3.10+
* **Framework:** pyTelegramBotAPI (Telebot)
* **Database:** MongoDB (via PyMongo)
* **Server:** Flask (for health checks)
* **Scheduling:** Schedule Library
* **API:** Bible-API.com (World English Bible)

---

## Bot Commands

### User Commands
| Command | Description |
| :--- | :--- |
| `/start` | Initializes the bot and shows the main menu. |
| `/verse` | Fetches a random encouraging verse immediately. |
| `/ping` | Checks system status (Database connection & Latency). |
| `/help` | Displays usage instructions. |

### Admin & Debug Commands
| Command | Description |
| :--- | :--- |
| `/register` | **Critical Fix:** Manually registers an existing group into the DB if the bot was already a member. |
| `/force_verse` | Triggers the daily broadcast immediately (for testing). |
| `/reset_group` | Wipes a group from memory to test "New Member" welcome logic. |

---

## Project Structure

```text
├── Theo.py                 # Main application entry point
├── encouraging_verses.json # Fallback data for offline mode
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (Secrets)
└── README.md               # Documentation

```

---

## Deployment & Setup

### 1. Local Development

Clone the repository and install dependencies:

```bash
git clone [https://github.com/YOUR_USERNAME/theo-bot.git](https://github.com/YOUR_USERNAME/theo-bot.git)
cd theo-bot
pip install -r requirements.txt

```

Create a `.env` file in the root directory:

```ini
BOT_TOKEN=your_telegram_bot_token
MONGO_URI=your_mongodb_connection_string
ADMIN_ID=your_telegram_id

```

Run the bot:

```bash
python Theo.py

```

### 2. Deployment (Render/Heroku)

This bot is optimized for **Render.com**.

1. **Build Command:** `pip install -r requirements.txt`
2. **Start Command:** `python Theo.py`
3. **Environment Variables:** Add `BOT_TOKEN` and `MONGO_URI` in the dashboard settings.

**Important:** To keep the scheduler running 24/7 on free tiers, use an external uptime monitor (like UptimeRobot) to ping the bot's URL every 5 minutes.

---

## Troubleshooting

**Issue: Bot is in the group but not sending verses.**

* **Fix:** The bot likely missed the "join" event. Run the command **`/register`** inside the group to manually save it to the database.

**Issue: Bot stops working after 15 minutes.**

* **Fix:** Ensure the Flask Keep-Alive server is running and you have set up **UptimeRobot** to ping the server URL.

---

## License

This project is open-source and available for educational purposes.

**Developed for the YouThopia Bible Community.**
