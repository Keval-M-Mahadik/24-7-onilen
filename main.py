import os
import json
import time
import threading
from flask import Flask
import requests
from urllib.parse import quote_plus

# ==========================================
# RENDER PORT FIX (Port Scan Error समाधान)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot status: Active"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_server, daemon=True).start()

# ==========================================
# CONFIGURATION
# ==========================================
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN", "8771414496:AAFBw-cGZhExTMbkZcvecolcDxAV9nzpjt8")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "8766550714:AAE2rUWxhf9jSIPCMIddkiNd7yz-3wKDxvM")

ADMIN_USER_IDS = {8613123407}


app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running successfully!"

def run_server():
    # Use port assigned by Render or default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Start web server in a background thread
threading.Thread(target=run_server, daemon=True).start()

PASSWORD_DB_FILE = "activation_passwords.json"

# Wrong password = 1 hour cooldown
WRONG_PASSWORD_COOLDOWN = 60 * 60


# ============================================================
# AUTHORIZED API CONFIGURATION
# ============================================================
#
# Put only APIs that you own or are explicitly authorized
# to query.
#
# Example:
#
# "Example API": {
#     "url": "https://your-domain.example/search?query=",
#     "prompt": "Send your authorized reference:"
# }
#
# ============================================================

API_CONFIG = {


    "🪪 Aadhaar Info ": {
            "url": "https://travelers-creature-sarah-rogers.trycloudflare.com/search?q=",
            "prompt": "🪪 Send a 12 Digit Aadhaar Number to Get🪪 information 💀"
        },
    
    "📞 Number Info ": {
            "url": "https://www.sahil.godstress.site/api/leak?key=NXTKIMAKICHUT&number=",
            "prompt": "📞Send a 10 Digit Indian Number (With+91) to Get🪪 information 💀     Example (+919712073901)"
        },
    
    "📍PIN Code Lookup": {
            "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
            "prompt": "📍 Send PIN code to get information 💀 (number)"
        },
    "🚘 Vehicle Info": {
                "url": "https://parivahan-x.paskhinpf9.workers.dev/?vehicle=",
                "prompt": "🚘 Send Vehicle Number 2.0 to get information💀(write in small letters)"
            },
    
    "🚘 Vehicle Info 2.0": {
            "url": "https://parivahan-x.paskhinpf9.workers.dev/?vehicle=",
            "prompt": "🚘 Send Vehicle Number 2.0 to get information💀(write in small letters)"
        },
    
    "🤖 Telegram ID / Username ": {
            "url": "https://anon-tg-info.vercel.app/telegram?key=temp1750&username=",
            "prompt": "🤖 Send the authorized Telegram username:"
        },
    
    "🆔 PAN Info ": {
            "url": "https://paninfo.noob73613.workers.dev/pan?pan=",
            "prompt": "🆔 Send the authorized PAN reference:"
        },
    
    "📱 Telegram Chat ID ": {
            "url": "https://anon-tg-info.vercel.app/tgReg_beta?userid=",
            "prompt": "📱 Send the authorized Chat ID:"
        },
    
    "💳 IFSC Info ": {
            "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
            "prompt": "💳 Send the IFSC code number:-"
        },
    
    "🏦 UPI INFO ": {
            "url": "https://upi-id-to-info-by-abhigyan.onrender.com/upi/<UPI_ID>",
            "prompt": "🏦 Send the authorized UPI ID:"
        },
    
    "🇵🇰 Pakistan Number Info ": {
            "url": "https://YOUR-AUTHORIZED-API.example/pakistan-number?query=",
            "prompt": "coming soon"
        },
    
    "📧 Advanced Email Info ": {
            "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
            "prompt": "📧 Send the authorized email:"
        },
    
    "📈 GST Info Advanced": {
            "url": "https://YOUR-AUTHORIZED-API.example/gst?query=",
            "prompt": "coming soon"
        },
    
    "🌐 IP Address Info": {
            "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
            "prompt": "🌐 Send the IP address:"
        },
    
    "👤 Instagram Username Info": {
            "url": "https://anon-social-info.vercel.app/igdl?&url=",
            "prompt": "coming soon"
        }
}


# ============================================================
# HTTP SESSION / PERFORMANCE
# ============================================================

# requests.Session() reuses TCP/TLS connections, which is noticeably
# faster when the bot handles many Telegram/API requests.
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})

# requests' adapter uses a connection pool for concurrent Telegram/API calls.
from requests.adapters import HTTPAdapter
HTTP.mount(
    "https://",
    HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
)
HTTP.mount(
    "http://",
    HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
)

TELEGRAM_CONNECT_TIMEOUT = 5
TELEGRAM_READ_TIMEOUT = 35
API_CONNECT_TIMEOUT = 3
API_READ_TIMEOUT = 12


# ============================================================
# TELEGRAM API
# ============================================================

USER_TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + USER_BOT_TOKEN
)

ADMIN_TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + ADMIN_BOT_TOKEN
)


# ============================================================
# USER STATE
# ============================================================

# Example:
#
# USER_STATE[12345] = {
#     "activation": True
# }
#
# or:
#
# USER_STATE[12345] = {
#     "api_name": "Example API"
# }

USER_STATE = {}


# ============================================================
# ACTIVATION / PASSWORD STATE
# ============================================================

# Example password record:
# {
#   "123456789": {
#       "password": "Ab7Kp9Qx2Lm4Rt8Z",
#       "used": false,
#       "created_at": 1780000000
#   }
# }
#
# Passwords are assigned to ONE Telegram user ID.
# The password is never sent back by the USER bot.
#
# This file makes passwords survive a program restart.
ACTIVATION_PASSWORDS = {}
ACTIVATED_USERS = set()

# chat_id -> expiry timestamp
PASSWORD_COOLDOWNS = {}


def load_activation_data():
    """Load activation passwords and activated users from disk."""
    global ACTIVATION_PASSWORDS, ACTIVATED_USERS

    try:
        with open(PASSWORD_DB_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        ACTIVATION_PASSWORDS = data.get("passwords", {})
        activated = data.get("activated_users", [])

        ACTIVATED_USERS = set(int(user_id) for user_id in activated)

    except FileNotFoundError:
        ACTIVATION_PASSWORDS = {}
        ACTIVATED_USERS = set()

    except Exception as error:
        print("Could not load activation database:", error)
        ACTIVATION_PASSWORDS = {}
        ACTIVATED_USERS = set()


def save_activation_data():
    """Save activation data atomically."""
    data = {
        "passwords": ACTIVATION_PASSWORDS,
        "activated_users": sorted(ACTIVATED_USERS)
    }

    temp_file = PASSWORD_DB_FILE + ".tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        # Replace old file after successful write.
        import os
        os.replace(temp_file, PASSWORD_DB_FILE)

    except Exception as error:
        print("Could not save activation database:", error)


def generate_activation_password(length=16):
    """Generate a cryptographically strong password."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def normalize_user_id(value):
    """Validate a Telegram numeric user ID."""
    value = str(value).strip()

    if not value.isdigit():
        return None

    try:
        user_id = int(value)
    except ValueError:
        return None

    if user_id <= 0:
        return None

    return user_id


def admin_generate_password(target_user_id):
    """
    Generate exactly one new password for a target Telegram user.

    If that user already has an unused password, it is replaced so each
    user has only one currently valid password.
    """
    target_user_id = normalize_user_id(target_user_id)

    if target_user_id is None:
        return None, "Invalid Telegram user ID."

    if target_user_id in ACTIVATED_USERS:
        return None, "That user is already activated. Deactivate them first."

    password = generate_activation_password()

    ACTIVATION_PASSWORDS[str(target_user_id)] = {
        "password": password,
        "used": False,
        "created_at": int(time.time())
    }

    save_activation_data()

    return password, None


def admin_revoke_password(target_user_id):
    """Remove the currently assigned password for a user."""
    target_user_id = normalize_user_id(target_user_id)

    if target_user_id is None:
        return False, "Invalid Telegram user ID."

    record = ACTIVATION_PASSWORDS.pop(str(target_user_id), None)

    if record is None:
        return False, "No password record exists for that user."

    save_activation_data()
    return True, "Password revoked."


def password_matches_user(chat_id, entered_password):
    """
    Return True only when:
      1. the password belongs to this exact Telegram user ID;
      2. the password has not already been used;
      3. the password matches exactly.

    This prevents one user's password from activating another user.
    """
    record = ACTIVATION_PASSWORDS.get(str(chat_id))

    if not record:
        return False

    if record.get("used") is True:
        return False

    return entered_password == record.get("password")


# ============================================================
# SEND MESSAGE
# ============================================================


# ============================================================

def send_message(chat_id, text, keyboard=None):

    url = USER_TELEGRAM_API + "/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard is not None:

        data["reply_markup"] = json.dumps(
            keyboard,
            ensure_ascii=False
        )

    try:

        response = HTTP.post(
            url,
            data=data,
            timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT)
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as error:

        # Error appears only in terminal.
        print("Telegram error:", error)

        return None

    except Exception as error:

        print(
            "Telegram unexpected error:",
            error
        )

        return None


# ============================================================
# GET TELEGRAM UPDATES
# ============================================================

def get_updates(offset=None):

    url = USER_TELEGRAM_API + "/getUpdates"

    params = {
        "timeout": 30
    }

    if offset is not None:
        params["offset"] = offset

    try:

        response = HTTP.get(
            url,
            params=params,
            timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT)
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as error:

        print(
            "getUpdates error:",
            error
        )

        return None

    except Exception as error:

        print(
            "Unexpected getUpdates error:",
            error
        )

        return None


# ============================================================
# ACTIVATION KEYBOARD
# ============================================================

def activation_keyboard():

    return {

        "keyboard": [
            [
                "🔐 Activate Bot"
            ]
        ],

        "resize_keyboard": True,

        "one_time_keyboard": False
    }


# ============================================================
# MAIN KEYBOARD
# ============================================================

def main_keyboard():

    buttons = list(
        API_CONFIG.keys()
    )

    keyboard = []

    # Two buttons per row
    for i in range(
        0,
        len(buttons),
        2
    ):

        keyboard.append(
            buttons[i:i + 2]
        )

    keyboard.append([
        "🔒 Deactivate"
    ])

    keyboard.append([
        "❌ Cancel"
    ])

    return {

        "keyboard": keyboard,

        "resize_keyboard": True,

        "one_time_keyboard": False
    }


# ============================================================
# FORMAT TIME
# ============================================================

def format_remaining_time(seconds):

    seconds = max(
        0,
        int(seconds)
    )

    hours = seconds // 3600

    minutes = (
        seconds % 3600
    ) // 60

    secs = seconds % 60

    if hours > 0:

        return (
            f"{hours}h "
            f"{minutes}m "
            f"{secs}s"
        )

    if minutes > 0:

        return (
            f"{minutes}m "
            f"{secs}s"
        )

    return f"{secs}s"


# ============================================================
# CHECK PASSWORD COOLDOWN
# ============================================================

def is_on_password_cooldown(chat_id):

    expiry = PASSWORD_COOLDOWNS.get(
        chat_id
    )

    # No cooldown
    if expiry is None:

        return False, 0

    remaining = (
        expiry - time.time()
    )

    # Cooldown expired
    if remaining <= 0:

        PASSWORD_COOLDOWNS.pop(
            chat_id,
            None
        )

        return False, 0

    return True, int(
        remaining
    )


# ============================================================
# START ACTIVATION
# ============================================================

def start_activation(chat_id):

    # Already activated
    if chat_id in ACTIVATED_USERS:

        send_message(
            chat_id,
            "✅ You are already activated.",
            main_keyboard()
        )

        return

    # Check cooldown
    cooldown, remaining = (
        is_on_password_cooldown(
            chat_id
        )
    )

    if cooldown:

        send_message(
            chat_id,
            "🔒 Activation temporarily locked.\n\n"
            f"⏳ Try again in: "
            f"{format_remaining_time(remaining)}",
            activation_keyboard()
        )

        return

    # Put user into activation state
    USER_STATE[chat_id] = {
        "activation": True
    }

    send_message(
        chat_id,
        "🔐 Activation Required\n\n"
        "Please enter your activation password.\n\n"
        "⚠️ If the password is incorrect, "
        "activation will be locked for 1 hour.\n\n"
        "Send /cancel to cancel.",
        activation_keyboard()
    )


# ============================================================
# PROCESS ACTIVATION PASSWORD
# ============================================================

def process_activation_password(
    chat_id,
    text
):

    # Cancel
    if text == "/cancel":
        USER_STATE.pop(chat_id, None)

        send_message(
            chat_id,
            "❌ Activation cancelled.",
            activation_keyboard()
        )
        return

    # Check cooldown again
    cooldown, remaining = is_on_password_cooldown(chat_id)

    if cooldown:
        USER_STATE.pop(chat_id, None)

        send_message(
            chat_id,
            "🔒 Activation is locked.\n\n"
            f"⏳ Try again in: "
            f"{format_remaining_time(remaining)}",
            activation_keyboard()
        )
        return

    # ========================================================
    # CORRECT PASSWORD
    # ========================================================

    if password_matches_user(chat_id, text):

        record = ACTIVATION_PASSWORDS.get(str(chat_id))

        # Mark the password as permanently used BEFORE activation
        # is reported successful. It cannot be reused by this or
        # another Telegram user.
        record["used"] = True
        record["used_at"] = int(time.time())

        ACTIVATED_USERS.add(chat_id)
        PASSWORD_COOLDOWNS.pop(chat_id, None)
        USER_STATE.pop(chat_id, None)

        save_activation_data()

        send_message(
            chat_id,
            "✅ Activation Successful!\n\n"
            "🔓 Bot unlocked.\n\n"
            "Select a feature:",
            main_keyboard()
        )

        return

    # ========================================================
    # WRONG / UNASSIGNED / ALREADY-USED PASSWORD
    # ========================================================

    PASSWORD_COOLDOWNS[chat_id] = (
        time.time()
        + WRONG_PASSWORD_COOLDOWN
    )

    USER_STATE.pop(chat_id, None)

    send_message(
        chat_id,
        "❌ Invalid activation password.\n\n"
        "🔒 The password is either not assigned to this Telegram "
        "account, incorrect, or has already been used.\n\n"
        "⏳ Try again after the 1-hour cooldown.",
        activation_keyboard()
    )


# ============================================================
# ESCAPE HTML
# ============================================================

def escape_html(text):

    text = str(text)

    text = text.replace(
        "&",
        "&amp;"
    )

    text = text.replace(
        "<",
        "&lt;"
    )

    text = text.replace(
        ">",
        "&gt;"
    )

    return text


# ============================================================
# CALL AUTHORIZED API
# ============================================================

def call_api(
    api_name,
    api_url,
    query
):

    if not api_url:

        return {
            "api": api_name,
            "status": "not_configured"
        }

    # Prevent placeholder API calls
    if "YOUR-AUTHORIZED-API.example" in api_url:

        print(
            api_name,
            "is not configured."
        )

        return {
            "api": api_name,
            "status": "not_configured"
        }

    try:

        encoded_query = quote_plus(
            query
        )

        request_url = (
            api_url
            + encoded_query
        )

        print()
        print("=" * 60)
        print(
            "API:",
            api_name
        )
        print(
            "Request:",
            request_url
        )
        print("=" * 60)

        response = HTTP.get(
            request_url,
            timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT)
        )

        response.raise_for_status()

        try:

            result = response.json()

        except ValueError:

            print(
                api_name,
                "returned non-JSON response"
            )

            return {
                "api": api_name,
                "status": "error"
            }

        return {

            "api": api_name,

            "status": "success",

            "result": result
        }

    except requests.exceptions.Timeout:

        print(
            api_name,
            "timeout"
        )

        return {
            "api": api_name,
            "status": "timeout"
        }

    except requests.exceptions.HTTPError as error:

        print(
            api_name,
            "HTTP error:",
            error
        )

        return {
            "api": api_name,
            "status": "http_error"
        }

    except requests.exceptions.RequestException as error:

        print(
            api_name,
            "request error:",
            error
        )

        return {
            "api": api_name,
            "status": "error"
        }

    except Exception as error:

        print(
            api_name,
            "unexpected error:",
            error
        )

        return {
            "api": api_name,
            "status": "error"
        }


# ============================================================
# SEND LONG MESSAGE
# ============================================================

def send_long_message(
    chat_id,
    text,
    keyboard=None
):

    max_length = 3900

    if len(text) <= max_length:

        send_message(
            chat_id,
            text,
            keyboard
        )

        return

    start = 0

    while start < len(text):

        chunk = text[
            start:start + max_length
        ]

        send_message(
            chat_id,
            chunk
        )

        start += max_length


    if keyboard is not None:

        send_message(
            chat_id,
            "✅ Finished.",
            keyboard
        )


# ============================================================
# PROCESS TELEGRAM UPDATE
# ============================================================

def process_update(update):

    if "message" not in update:
        return

    message = update["message"]

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return

    text = message.get(
        "text",
        ""
    )

    if not isinstance(
        text,
        str
    ):
        return

    text = text.strip()


    # ========================================================
    # /START
    # ========================================================

    if text == "/start":

        USER_STATE.pop(
            chat_id,
            None
        )

        if chat_id in ACTIVATED_USERS:

            send_message(
                chat_id,
                "✅ You are already activated.\n\n"
                "Select a feature:",
                main_keyboard()
            )

        else:

            cooldown, remaining = (
                is_on_password_cooldown(
                    chat_id
                )
            )

            if cooldown:

                send_message(
                    chat_id,
                    "🔒 Bot is temporarily locked.\n\n"
                    f"⏳ Try again in: "
                    f"{format_remaining_time(remaining)}",
                    activation_keyboard()
                )

            else:

                send_message(
                    chat_id,
                    "👋 Welcome!\n\n"
                    "🔒 This bot is locked.\n\n"
                    "Tap 🔐 Activate Bot to continue.",
                    activation_keyboard()
                )

        return


    # ========================================================
    # ACTIVATION BUTTON
    # ========================================================

    if text == "🔐 Activate Bot":

        start_activation(
            chat_id
        )

        return


    # ========================================================
    # ACTIVATION PASSWORD STATE
    # ========================================================

    if chat_id in USER_STATE:

        state = USER_STATE.get(
            chat_id,
            {}
        )

        if state.get(
            "activation"
        ):

            process_activation_password(
                chat_id,
                text
            )

            return


    # ========================================================
    # LOCKED USER
    # ========================================================

    if chat_id not in ACTIVATED_USERS:

        cooldown, remaining = (
            is_on_password_cooldown(
                chat_id
            )
        )

        if cooldown:

            send_message(
                chat_id,
                "🔒 Bot is locked.\n\n"
                f"⏳ Try again in: "
                f"{format_remaining_time(remaining)}",
                activation_keyboard()
            )

        else:

            send_message(
                chat_id,
                "🔒 Bot is locked.\n\n"
                "Please tap 🔐 Activate Bot first.",
                activation_keyboard()
            )

        return


    # ========================================================
    # CANCEL
    # ========================================================

    if text in (
        "/cancel",
        "❌ Cancel"
    ):

        USER_STATE.pop(
            chat_id,
            None
        )

        send_message(
            chat_id,
            "❌ Cancelled.\n\n"
            "Select a feature:",
            main_keyboard()
        )

        return


    # ========================================================
    # DEACTIVATE
    # ========================================================

    if text == "🔒 Deactivate":

        ACTIVATED_USERS.discard(
            chat_id
        )

        USER_STATE.pop(
            chat_id,
            None
        )

        send_message(
            chat_id,
            "🔒 Bot deactivated.\n\n"
            "Tap 🔐 Activate Bot to unlock it again.",
            activation_keyboard()
        )

        return


    # ========================================================
    # API BUTTON
    # ========================================================

    # ========================================================
    # API BUTTON
    # ========================================================

    # Telegram button text can contain leading/trailing spaces.
    # Match it after stripping whitespace so buttons such as
    # " 🎲Aadhaar Info " still work reliably.
    api_name = next(
        (name for name in API_CONFIG if name.strip() == text.strip()),
        None
    )

    if api_name is not None:

        config = API_CONFIG[api_name]

        USER_STATE[chat_id] = {
            "api_name": api_name
        }

        send_message(
            chat_id,
            config["prompt"]
            + "\n\n"
            + "Send /cancel to cancel.",
            main_keyboard()
        )

        return


    # ========================================================
    # API QUERY
    # ========================================================

    if chat_id in USER_STATE:

        state = USER_STATE.get(
            chat_id,
            {}
        )

        # Activation state is handled above. Any remaining state should
        # represent an API selection awaiting its query.
        api_name = state.get("api_name")

        if not api_name:
            USER_STATE.pop(chat_id, None)

            send_message(
                chat_id,
                "❓ Please select a feature.",
                main_keyboard()
            )

            return

        query = text.strip()

        if not query:

            send_message(
                chat_id,
                "❌ Query cannot be empty."
            )

            return

        config = API_CONFIG.get(api_name)

        if not config:

            USER_STATE.pop(
                chat_id,
                None
            )

            send_message(
                chat_id,
                "❌ API configuration unavailable.",
                main_keyboard()
            )

            return


        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        send_message(
            chat_id,
            "⏳ Searching..."
        )


        # ----------------------------------------------------
        # CALL API
        # ----------------------------------------------------

        result = call_api(
            api_name,
            config["url"],
            query
        )


        # ----------------------------------------------------
        # HIDE ERRORS FROM TELEGRAM
        # ----------------------------------------------------

        if result.get(
            "status"
        ) != "success":

            USER_STATE.pop(
                chat_id,
                None
            )

            send_message(
                chat_id,
                "❌ No result available.",
                main_keyboard()
            )

            return


        # ----------------------------------------------------
        # API RESULT
        # ----------------------------------------------------

        api_result = result.get(
            "result"
        )


        # ----------------------------------------------------
        # FORMAT JSON
        # ----------------------------------------------------

        try:

            formatted = json.dumps(
                api_result,
                indent=2,
                ensure_ascii=False
            )

        except Exception:

            formatted = str(
                api_result
            )


        formatted = escape_html(
            formatted
        )


        response_text = (
            "<pre>"
            + formatted
            + "</pre>"
        )


        # ----------------------------------------------------
        # SEND RESULT
        # ----------------------------------------------------

        send_long_message(
            chat_id,
            response_text,
            main_keyboard()
        )


        # ----------------------------------------------------
        # CLEAR STATE
        # ----------------------------------------------------

        USER_STATE.pop(
            chat_id,
            None
        )

        return


    # ========================================================
    # UNKNOWN MESSAGE
    # ========================================================

    send_message(
        chat_id,
        "❓ Please select an option from the menu.",
        main_keyboard()
    )



# ============================================================
# ADMIN BOT
# ============================================================

def admin_send_message(chat_id, text):
    """Send a message only through the separate ADMIN bot."""
    url = ADMIN_TELEGRAM_API + "/sendMessage"

    try:
        response = HTTP.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT)
        )

        response.raise_for_status()
        return response.json()

    except Exception as error:
        print("Admin Telegram error:", error)
        return None


def admin_get_updates(offset=None):
    """Read updates from the separate ADMIN bot."""
    url = ADMIN_TELEGRAM_API + "/getUpdates"

    params = {
        "timeout": 30
    }

    if offset is not None:
        params["offset"] = offset

    try:
        response = HTTP.get(
            url,
            params=params,
            timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT)
        )

        response.raise_for_status()
        return response.json()

    except Exception as error:
        print("Admin getUpdates error:", error)
        return None


def admin_help(chat_id):
    admin_send_message(
        chat_id,
        "🛠 ADMIN PANEL\n\n"
        "/generate USER_ID - Generate a unique password\n"
        "/list - Show password records\n"
        "/revoke USER_ID - Revoke unused password\n"
        "/deactivate USER_ID - Deactivate a user\n"
        "/help - Show this menu\n\n"
        "🔐 Passwords are shown only in this ADMIN bot.\n"
        "👤 The USER bot never displays generated passwords."
    )


def admin_list_passwords(chat_id):
    if not ACTIVATION_PASSWORDS:
        admin_send_message(
            chat_id,
            "📭 No activation password records."
        )
        return

    lines = ["🔐 ACTIVATION PASSWORDS", ""]

    for user_id, record in ACTIVATION_PASSWORDS.items():
        status = "USED" if record.get("used") else "UNUSED"
        password = record.get("password", "unknown")

        lines.append(
            f"👤 User ID: {user_id}\n"
            f"🔑 Password: {password}\n"
            f"📌 Status: {status}\n"
        )

    admin_send_message(chat_id, "\n".join(lines))


def process_admin_update(update):
    if "message" not in update:
        return

    message = update["message"]
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if chat_id is None or not isinstance(text, str):
        return

    # Admin access is checked against the Telegram user ID.
    if chat_id not in ADMIN_USER_IDS:
        admin_send_message(
            chat_id,
            "⛔ You are not authorized to use the admin bot."
        )
        return

    text = text.strip()

    if text in ("/start", "/help"):
        admin_help(chat_id)
        return

    if text == "/list":
        admin_list_passwords(chat_id)
        return

    if text.startswith("/generate"):
        parts = text.split(maxsplit=1)

        if len(parts) != 2:
            admin_send_message(
                chat_id,
                "Usage:\n/generate USER_ID\n\n"
                "Example:\n/generate 123456789"
            )
            return

        target_user_id = normalize_user_id(parts[1])

        if target_user_id is None:
            admin_send_message(chat_id, "❌ Invalid Telegram user ID.")
            return

        password, error = admin_generate_password(target_user_id)

        if error:
            admin_send_message(
                chat_id,
                "❌ " + error
            )
            return

        admin_send_message(
            chat_id,
            "✅ NEW ACTIVATION PASSWORD\n\n"
            f"👤 User ID: {target_user_id}\n"
            f"🔑 Password: {password}\n\n"
            "⚠️ This password is valid ONLY for this Telegram user.\n"
            "⚠️ It becomes permanently invalid after one successful use.\n"
            "🔒 The USER bot will never display this password."
        )
        return

    if text.startswith("/revoke"):
        parts = text.split(maxsplit=1)

        if len(parts) != 2:
            admin_send_message(
                chat_id,
                "Usage:\n/revoke USER_ID"
            )
            return

        ok, message_text = admin_revoke_password(parts[1])

        admin_send_message(
            chat_id,
            ("✅ " if ok else "❌ ") + message_text
        )
        return

    if text.startswith("/deactivate"):
        parts = text.split(maxsplit=1)

        if len(parts) != 2:
            admin_send_message(
                chat_id,
                "Usage:\n/deactivate USER_ID"
            )
            return

        target_user_id = normalize_user_id(parts[1])

        if target_user_id is None:
            admin_send_message(chat_id, "❌ Invalid Telegram user ID.")
            return

        ACTIVATED_USERS.discard(target_user_id)
        USER_STATE.pop(target_user_id, None)
        save_activation_data()

        admin_send_message(
            chat_id,
            f"🔒 User {target_user_id} has been deactivated.\n\n"
            "Generate a NEW password if they need to activate again."
        )
        return

    admin_send_message(
        chat_id,
        "❓ Unknown command.\n\nUse /help."
    )


def admin_bot_loop():
    """Long-polling loop for the separate ADMIN bot."""
    print("Admin bot polling active.")

    offset = None

    while True:
        try:
            result = admin_get_updates(offset)

            if result is None:
                time.sleep(3)
                continue

            if not result.get("ok"):
                print("Admin Telegram API error:", result)
                time.sleep(3)
                continue

            for update in result.get("result", []):
                update_id = update.get("update_id")

                if update_id is not None:
                    offset = update_id + 1

                try:
                    process_admin_update(update)
                except Exception as error:
                    print("Admin processing error:", error)

        except Exception as error:
            print("Admin loop error:", error)
            time.sleep(3)


# ============================================================
# MAIN
# ============================================================

def main():
    load_activation_data()


    # ========================================================
    # CHECK BOT TOKEN
    # ========================================================

    if (
        not USER_BOT_TOKEN
        or
        USER_BOT_TOKEN == "PUT_USER_BOT_TOKEN_HERE"
    ):

        print(
            "ERROR: Set BOT_TOKEN in the code first."
        )

        return


    # ========================================================
    # CHECK BOT TOKENS
    # ========================================================

    if (
        not USER_BOT_TOKEN
        or USER_BOT_TOKEN == "PUT_USER_BOT_TOKEN_HERE"
        or not ADMIN_BOT_TOKEN
        or ADMIN_BOT_TOKEN == "PUT_ADMIN_BOT_TOKEN_HERE"
    ):
        print("ERROR: Set both bot tokens first.")
        return


    # ========================================================
    # TEST TELEGRAM CONNECTION
    # ========================================================

    try:

        response = HTTP.get(
            USER_TELEGRAM_API + "/getMe",
            timeout=(TELEGRAM_CONNECT_TIMEOUT, 10)
        )

        response.raise_for_status()

        bot_info = response.json()

        if not bot_info.get("ok"):

            print(
                "ERROR: Telegram token is invalid."
            )

            return

        username = (
            bot_info
            .get(
                "result",
                {}
            )
            .get(
                "username",
                "unknown"
            )
        )

        print(
            "Connected to Telegram bot:",
            username
        )

    except Exception as error:

        print(
            "Could not connect to Telegram:",
            error
        )

        return


    # Start the admin poller only after configuration and
    # user-bot connectivity have been validated.
    admin_thread = threading.Thread(
        target=admin_bot_loop,
        name="admin-bot",
        daemon=True
    )
    admin_thread.start()


    # ========================================================
    # START
    # ========================================================

    print("=" * 60)

    print(
        "Telegram Bot Started"
    )

    print("=" * 60)

    print(
        "API buttons:",
        len(API_CONFIG)
    )

    print(
        "Activation system: ENABLED"
    )

    print(
        "Wrong password cooldown: 1 hour"
    )

    print(
        "Errors hidden from Telegram"
    )

    print(
        "Long polling active"
    )

    print("=" * 60)


    offset = None


    # ========================================================
    # LONG POLLING LOOP
    # ========================================================

    while True:

        try:

            result = get_updates(
                offset
            )

            if result is None:

                time.sleep(3)

                continue


            if not result.get(
                "ok"
            ):

                print(
                    "Telegram API error:",
                    result
                )

                time.sleep(3)

                continue


            updates = result.get(
                "result",
                []
            )


            for update in updates:

                update_id = update.get(
                    "update_id"
                )


                if update_id is not None:

                    offset = (
                        update_id + 1
                    )


                try:

                    process_update(
                        update
                    )

                except Exception as error:

                    print(
                        "Processing error:",
                        error
                    )


        except KeyboardInterrupt:

            print(
                "\nBot stopped."
            )

            break


        except Exception as error:

            print(
                "Main loop error:",
                error
            )

            time.sleep(3)


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":

    main()
