import os
import json
import time
import hmac
import hashlib
import threading
import requests
import qrcode
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify
from urllib.parse import quote_plus
from requests.adapters import HTTPAdapter

# ==========================================
# FLASK SETUP
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running successfully!"

@app.route('/health')
def health():
    try:
        active = sum(1 for exp in ACTIVATED_USERS.values() if exp > time.time())
        total = len(ACTIVATED_USERS)
    except Exception:
        active = total = 0
    return jsonify({
        "status": "ok",
        "ts": int(time.time()),
        "uptime_users_active": active,
        "uptime_users_total": total,
        "banned": len(BANNED_USERS),
        "maintenance": MAINTENANCE_MODE,
    })

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/test-min')
def test_min():
    out = {}
    for code in ("ltc", "trx", "usdttrc20", "btc", "eth"):
        mn, mf = get_min_amount(code, "usd")
        out[code] = {"min_amount": mn, "min_fiat_usd": mf}
    return jsonify(out)

@app.route('/test-currencies')
def test_currencies():
    lst = fetch_all_currencies()
    return jsonify({
        "count": len(lst),
        "sample": [{"code": c["code"], "name": c["name"]} for c in lst[:25]]
    })

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)

threading.Thread(target=run_server, daemon=True).start()

# ==========================================
# CONFIGURATION
# ==========================================
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN", "8771414496:AAEZYXZa3TXHPcJoEYxHmI105c60F8VSYxo")
ADMIN_BOT_TOKEN_1 = os.getenv("ADMIN_BOT_TOKEN_1", "8916442795:AAETD7lL1snL27ab0RVVzpMPBWvnJ7_Xyn4")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "ZQRJG4Z-5PQ48ZM-M5C8PVH-V01CXT0")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "Gsx0umqAvAcrfOGfEOguqrL9UjhmoHoH")

IPN_CALLBACK_URL = os.getenv("IPN_CALLBACK_URL", "https://24-7-onilen.onrender.com/nowpayments_webhook")
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1"

# ==========================================
# ADMIN AUTH CONFIG
# ==========================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "mahesh@321").strip()
OWNER_ID = os.getenv("OWNER_ID", "6326027750").strip()

# ==========================================
# 24/7 KEEP-ALIVE
# ==========================================
SELF_URL = os.getenv("SELF_URL", "https://24-7-onilen.onrender.com")
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "600"))

# ==========================================
# STORAGE
# ==========================================
ADMINS_FILE     = os.getenv("ADMINS_FILE",     "admins.json")
PASSWORD_FILE   = os.getenv("PASSWORD_FILE",   "admin_password.json")
BANNED_FILE     = os.getenv("BANNED_FILE",     "banned.json")
NOTES_FILE      = os.getenv("NOTES_FILE",      "user_notes.json")
ADMIN_LOG_FILE  = os.getenv("ADMIN_LOG_FILE",  "admin_log.json")
LASTSEEN_FILE   = os.getenv("LASTSEEN_FILE",   "last_seen.json")

DYNAMIC_ADMINS = set()
CURRENT_PASSWORD = ADMIN_PASSWORD

BANNED_USERS = {}
USER_NOTES = {}
ADMIN_LOG = []
LAST_SEEN = {}
MAINTENANCE_MODE = False
ADMIN_LOG_MAX = 500

# ==========================================
# PERSISTENCE
# ==========================================
def _safe_load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"⚠️ load {path} failed: {e}")
        return default

def _safe_save(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"⚠️ save {path} failed: {e}")

def load_password():
    global CURRENT_PASSWORD
    data = _safe_load(PASSWORD_FILE, {})
    if data.get("password"):
        CURRENT_PASSWORD = str(data["password"])
        print("🔐 Loaded persisted admin password.")

def save_password():
    _safe_save(PASSWORD_FILE, {"password": CURRENT_PASSWORD})

def load_admins():
    global DYNAMIC_ADMINS
    data = _safe_load(ADMINS_FILE, [])
    DYNAMIC_ADMINS = set(int(x) for x in data)
    if OWNER_ID:
        try:
            DYNAMIC_ADMINS.add(int(OWNER_ID))
            print(f"👑 OWNER_ID {OWNER_ID} auto-added as admin.")
        except ValueError:
            print(f"⚠️ OWNER_ID not numeric: {OWNER_ID}")
    save_admins()
    print(f"✅ Loaded {len(DYNAMIC_ADMINS)} admins.")

def save_admins():
    _safe_save(ADMINS_FILE, sorted(list(DYNAMIC_ADMINS)))

def load_banned():
    global BANNED_USERS
    raw = _safe_load(BANNED_FILE, {})
    BANNED_USERS = {int(k): v for k, v in raw.items()}
    print(f"🚫 Loaded {len(BANNED_USERS)} banned users.")

def save_banned():
    _safe_save(BANNED_FILE, {str(k): v for k, v in BANNED_USERS.items()})

def load_notes():
    global USER_NOTES
    raw = _safe_load(NOTES_FILE, {})
    USER_NOTES = {int(k): v for k, v in raw.items()}
    print(f"📝 Loaded notes for {len(USER_NOTES)} users.")

def save_notes():
    _safe_save(NOTES_FILE, {str(k): v for k, v in USER_NOTES.items()})

def load_log():
    global ADMIN_LOG
    ADMIN_LOG = _safe_load(ADMIN_LOG_FILE, [])
    if not isinstance(ADMIN_LOG, list):
        ADMIN_LOG = []

def save_log():
    _safe_save(ADMIN_LOG_FILE, ADMIN_LOG[-ADMIN_LOG_MAX:])

def load_lastseen():
    global LAST_SEEN
    raw = _safe_load(LASTSEEN_FILE, {})
    LAST_SEEN = {int(k): float(v) for k, v in raw.items()}

def save_lastseen():
    _safe_save(LASTSEEN_FILE, {str(k): v for k, v in LAST_SEEN.items()})

def log_admin(by, action, target=""):
    entry = {"ts": int(time.time()), "by": int(by), "action": str(action), "target": str(target)}
    ADMIN_LOG.append(entry)
    if len(ADMIN_LOG) > ADMIN_LOG_MAX:
        del ADMIN_LOG[:-ADMIN_LOG_MAX]
    save_log()

# ==========================================
# ROLES
# ==========================================
def is_owner(chat_id):
    return bool(OWNER_ID) and str(chat_id) == OWNER_ID

def is_admin(chat_id):
    return chat_id in DYNAMIC_ADMINS

def get_role(chat_id):
    if is_owner(chat_id): return "owner"
    if is_admin(chat_id): return "admin"
    return "user"

def role_badge(chat_id):
    r = get_role(chat_id)
    return {"owner": "👑 Owner", "admin": "🛡 Admin", "user": "👤 User"}[r]

def is_banned(chat_id):
    return chat_id in BANNED_USERS

# ==========================================
# IMAGES
# ==========================================
WELCOME_IMG = os.getenv("WELCOME_IMG", "images/welcome.png")
OSINT_IMG   = os.getenv("OSINT_IMG",   "images/osint.png")
PAYMENT_IMG = os.getenv("PAYMENT_IMG", "images/payment.png")
IMAGE_CACHE = {}

def cache_image(path):
    if not os.path.exists(path):
        print(f"⚠️ Image not found: {path}")
        return
    try:
        with Image.open(path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            IMAGE_CACHE[path] = buf.getvalue()
            print(f"✅ Cached: {path} ({len(IMAGE_CACHE[path])/1024:.1f} KB)")
    except Exception as e:
        print(f"❌ Compress fail {path}: {e}")
        try:
            with open(path, "rb") as f:
                IMAGE_CACHE[path] = f.read()
        except Exception as raw_e:
            print(f"❌ Raw load fail {path}: {raw_e}")

cache_image(WELCOME_IMG)
cache_image(OSINT_IMG)
cache_image(PAYMENT_IMG)

# ==========================================
# PLANS
# ==========================================
PLANS = {
    "plan_1": {"name": "1 Month",  "price_usd": 13.00, "days": 30},
    "plan_2": {"name": "3 Months", "price_usd": 18.00, "days": 90},
    "plan_3": {"name": "6 Months", "price_usd": 25.00, "days": 180},
    "plan_4": {"name": "1 Year",   "price_usd": 35.00, "days": 365},
}

DB_FILE = os.getenv("DB_FILE", "activation_data.json")
db_lock = threading.Lock()

MIN_AMOUNT_CACHE = {}
MIN_AMOUNT_CACHE_TTL = 600
CURRENCY_CACHE = {"list": [], "ts": 0}
CURRENCY_CACHE_TTL = 3600
CURRENCY_PAGE_SIZE = 20

FIAT_FALLBACK = [
    ("usd", "US Dollar"), ("eur", "Euro"), ("gbp", "British Pound"),
    ("inr", "Indian Rupee"), ("aud", "Australian Dollar"), ("cad", "Canadian Dollar"),
    ("jpy", "Japanese Yen"), ("cny", "Chinese Yuan"), ("chf", "Swiss Franc"),
    ("sgd", "Singapore Dollar"), ("hkd", "Hong Kong Dollar"), ("nzd", "New Zealand Dollar"),
    ("krw", "South Korean Won"), ("brl", "Brazilian Real"), ("mxn", "Mexican Peso"),
    ("zar", "South African Rand"), ("rub", "Russian Ruble"), ("try", "Turkish Lira"),
    ("aed", "UAE Dirham"), ("sar", "Saudi Riyal"), ("qar", "Qatari Riyal"),
    ("kwd", "Kuwaiti Dinar"), ("bhd", "Bahraini Dinar"), ("omr", "Omani Rial"),
    ("pkr", "Pakistani Rupee"), ("bdt", "Bangladeshi Taka"), ("lkr", "Sri Lankan Rupee"),
    ("npr", "Nepalese Rupee"), ("idr", "Indonesian Rupiah"), ("myr", "Malaysian Ringgit"),
    ("thb", "Thai Baht"), ("php", "Philippine Peso"), ("vnd", "Vietnamese Dong"),
    ("ngn", "Nigerian Naira"), ("kes", "Kenyan Shilling"), ("ghs", "Ghanaian Cedi"),
    ("egp", "Egyptian Pound"), ("mad", "Moroccan Dirham"), ("dzd", "Algerian Dinar"),
    ("tnd", "Tunisian Dinar"), ("ils", "Israeli Shekel"), ("pln", "Polish Zloty"),
    ("sek", "Swedish Krona"), ("nok", "Norwegian Krone"), ("dkk", "Danish Krone"),
    ("czk", "Czech Koruna"), ("huf", "Hungarian Forint"), ("ron", "Romanian Leu"),
    ("uah", "Ukrainian Hryvnia"), ("ars", "Argentine Peso"), ("clp", "Chilean Peso"),
    ("cop", "Colombian Peso"), ("pen", "Peruvian Sol"), ("twd", "New Taiwan Dollar"),
    ("irr", "Iranian Rial"), ("iqd", "Iraqi Dinar"), ("jod", "Jordanian Dinar"),
    ("afn", "Afghan Afghani"), ("mmk", "Myanmar Kyat"), ("khr", "Cambodian Riel"),
    ("bgn", "Bulgarian Lev"), ("hrk", "Croatian Kuna"), ("isk", "Icelandic Krona"),
    ("kzt", "Kazakhstani Tenge"), ("uzs", "Uzbekistani Som"), ("azn", "Azerbaijani Manat"),
    ("gel", "Georgian Lari"), ("amd", "Armenian Dram"), ("rsd", "Serbian Dinar"),
    ("mnt", "Mongolian Tugrik"), ("etb", "Ethiopian Birr"), ("ugx", "Ugandan Shilling"),
    ("tzs", "Tanzanian Shilling"), ("xof", "West African CFA Franc"),
]

POPULAR_CODES = [
    "btc", "eth", "usdttrc20", "usdterc20", "usdc", "ltc", "trx", "bnb",
    "sol", "doge", "xrp", "ada", "matic", "ton", "shib", "dai", "busd",
]

# ============================================================
# LANGUAGE / i18n
# ============================================================
LANGUAGES = {
    "en": "🇬🇧 English", "hi": "🇮🇳 हिन्दी", "bn": "🇧🇩 বাংলা", "ur": "🇵🇰 اردو",
    "ar": "🇸🇦 العربية", "es": "🇪🇸 Español", "fr": "🇫🇷 Français", "de": "🇩🇪 Deutsch",
    "pt": "🇧🇷 Português", "ru": "🇷🇺 Русский", "zh": "🇨🇳 中文", "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어", "id": "🇮🇩 Indonesia", "tr": "🇹🇷 Türkçe", "fa": "🇮🇷 فارسی",
    "it": "🇮🇹 Italiano", "vi": "🇻🇳 Tiếng Việt", "th": "🇹🇭 ไทย", "ta": "🇮🇳 தமிழ்",
    "te": "🇮🇳 తెలుగు", "mr": "🇮🇳 मराठी", "gu": "🇮🇳 ગુજરાતી", "pa": "🇮🇳 ਪੰਜਾਬੀ",
    "ml": "🇮🇳 മലയാളം", "nl": "🇳🇱 Nederlands", "pl": "🇵🇱 Polski", "uk": "🇺🇦 Українська",
    "ro": "🇷🇴 Română", "sw": "🇰🇪 Kiswahili", "ms": "🇲🇾 Bahasa Melayu", "fil": "🇵🇭 Filipino",
}

TEXTS = {
    "en": {
        "welcome": ("✨ <b>W E L C O M E</b> ✨\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🤖 <b>Premium OSINT Bot</b>\n🔓 Unlock powerful intelligence tools\n"
                    "⚡ Fast  •  🔒 Secure  •  🎯 Reliable"),
        "locked": "🔒 <b>A C C E S S   D E N I E D</b>\n━━━━━━━━━━━━━━━━━━━━━━━",
        "buy_plan": "💎 Purchase a plan below to unlock full access.",
        "select_feature": ("🛠 <b>M A I N   M E N U</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                           "👇 <b>Select a feature to begin:</b>"),
        "already_active": "✅ <b>You're already activated!</b>",
        "status_active": "✅ Status: <b>Active</b>",
        "status_inactive": "❌ Status: <b>Inactive / Expired</b>",
        "expiry": "⏳ Expiry",
        "cancelled": "❌ <b>Cancelled.</b>",
        "deactivated": "🔒 Bot deactivated.",
        "deactivated_msg": ("🔒 <b>Bot Deactivated</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "💎 Purchase a plan below to reactivate."),
        "select_plan": ("💎 <b>P R E M I U M   P L A N S</b> 💎\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "👇 <b>Choose the plan that suits you best:</b>"),
        "checking": "🔎 <i>Checking available currencies...</i>",
        "no_crypto": "❌ No currencies available right now.",
        "generating": "⏳ <i>Generating your payment invoice...</i>",
        "payment_confirmed": ("✅ <b>P A Y M E N T   C O N F I R M E D</b>\n"
                              "━━━━━━━━━━━━━━━━━━━━━━━"),
        "activated_days": "🎉 Your bot has been activated for <b>{days} days</b>!",
        "payment_api_error": "❌ <b>Payment API Error</b>",
        "try_again": "🔄 Please try again or contact admin.",
        "select_currency": ("💰 <b>PAYMENT METHOD</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "📦 Plan: <b>{plan}</b>\n💵 Price: <b>${price} USD</b>\n\n"
                            "👇 <b>Choose a currency to pay with:</b>"),
        "choose_language": "🌐 <b>Please choose your language:</b>",
        "language_set": "✅ Language updated successfully.",
        "send_cancel": "💡 <i>Send /cancel to cancel anytime.</i>",
        "searching": "🔎 <i>Searching...</i>",
        "no_result": "❌ No result or API error occurred.",
        "select_option": "❓ Please select an option from the menu.",
        "search_currency": "🔍 Search",
        "all_currencies": "📋 All",
        "back": "🔙 Back",
        "cancel_btn": "❌ Cancel",
        "deactivate_btn": "🔒 Deactivate",
        "check_status_btn": "🔄 Status",
        "lang_btn": "🌐 Language",
        "not_available": "❌ That currency is not available.",
        "payment_timeout": "⏱ Payment API timed out. Please try again.",
        "send_currency_code": ("🔍 <b>Currency Search</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                               "Type a currency code or name:\n"
                               "<i>e.g. BTC, ETH, USDT, Euro, INR</i>"),
        "found_currencies": "🎯 Found <b>{n}</b> matching currencies:",
        "no_match": "❌ No matching currency found. Try another code.",
        "send_amount": ("💰 <b>PAYMENT DETAILS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "💵 Amount: <b>{amount} {currency}</b>\n📮 Send to the address below:"),
        "popular": "⭐ <b>Popular currencies:</b>",
        "plan_1": "1 Month", "plan_2": "3 Months",
        "plan_3": "6 Months", "plan_4": "1 Year",
        "bumped_note": "ℹ️ Amount adjusted to meet the network minimum.",
        "currency_unsupported": "⚠️ This currency may not be supported for payments. Please try another.",
        "maintenance": ("🛠 <b>UNDER MAINTENANCE</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "The bot is temporarily unavailable.\nPlease try again later."),
        "banned_msg": ("🚫 <b>ACCESS BLOCKED</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                       "Your account has been suspended.\nContact support if you believe this is a mistake."),
        "admin_granted": ("🎁 <b>PLAN ACTIVATED</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                          "An admin has activated your plan.\n"
                          "📦 Plan: <b>{plan}</b>\n"
                          "➕ Days added: <b>{days}</b>\n"
                          "⏳ New expiry: <code>{expiry}</code>\n\n"
                          "Enjoy full access!"),
    },
    "hi": {
        "welcome": ("✨ <b>स्वागत है</b> ✨\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🤖 <b>प्रीमियम OSINT बॉट</b>\n🔓 शक्तिशाली इंटेलिजेंस टूल्स अनलॉक करें\n"
                    "⚡ तेज़  •  🔒 सुरक्षित  •  🎯 विश्वसनीय"),
        "locked": "🔒 <b>पहुँच अस्वीकृत</b>\n━━━━━━━━━━━━━━━━━━━━━━━",
        "buy_plan": "💎 पूर्ण पहुँच के लिए नीचे एक प्लान खरीदें।",
        "select_feature": ("🛠 <b>मुख्य मेनू</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                           "👇 <b>शुरू करने के लिए एक सुविधा चुनें:</b>"),
        "already_active": "✅ <b>आप पहले से सक्रिय हैं!</b>",
        "status_active": "✅ स्थिति: <b>सक्रिय</b>",
        "status_inactive": "❌ स्थिति: <b>निष्क्रिय / समाप्त</b>",
        "expiry": "⏳ समाप्ति",
        "cancelled": "❌ <b>रद्द किया गया।</b>",
        "deactivated": "🔒 बॉट निष्क्रिय कर दिया गया।",
        "deactivated_msg": ("🔒 <b>बॉट निष्क्रिय</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "💎 दोबारा सक्रिय करने के लिए प्लान खरीदें।"),
        "select_plan": ("💎 <b>प्रीमियम प्लान</b> 💎\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "👇 <b>अपने अनुसार प्लान चुनें:</b>"),
        "checking": "🔎 <i>उपलब्ध मुद्राएँ जाँच रहे हैं...</i>",
        "no_crypto": "❌ अभी कोई मुद्रा उपलब्ध नहीं है।",
        "generating": "⏳ <i>भुगतान इनवॉइस बना रहे हैं...</i>",
        "payment_confirmed": "✅ <b>भुगतान की पुष्टि हो गई!</b>\n━━━━━━━━━━━━━━━━━━━━━━━",
        "activated_days": "🎉 आपका बॉट <b>{days} दिनों</b> के लिए सक्रिय कर दिया गया है!",
        "payment_api_error": "❌ <b>भुगतान API त्रुटि</b>",
        "try_again": "🔄 कृपया पुनः प्रयास करें या एडमिन से संपर्क करें।",
        "select_currency": ("💰 <b>भुगतान विधि</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "📦 प्लान: <b>{plan}</b>\n💵 मूल्य: <b>${price} USD</b>\n\n"
                            "👇 <b>भुगतान के लिए मुद्रा चुनें:</b>"),
        "choose_language": "🌐 <b>कृपया अपनी भाषा चुनें:</b>",
        "language_set": "✅ भाषा सफलतापूर्वक अपडेट हो गई।",
        "send_cancel": "💡 <i>रद्द करने के लिए /cancel भेजें।</i>",
        "searching": "🔎 <i>खोज रहे हैं...</i>",
        "no_result": "❌ कोई परिणाम नहीं या API त्रुटि।",
        "select_option": "❓ कृपया मेनू से एक विकल्प चुनें।",
        "search_currency": "🔍 खोजें",
        "all_currencies": "📋 सभी",
        "back": "🔙 वापस",
        "cancel_btn": "❌ रद्द करें",
        "deactivate_btn": "🔒 निष्क्रिय करें",
        "check_status_btn": "🔄 स्थिति",
        "lang_btn": "🌐 भाषा",
        "not_available": "❌ वह मुद्रा उपलब्ध नहीं है।",
        "payment_timeout": "⏱ भुगतान API का समय समाप्त। पुनः प्रयास करें।",
        "send_currency_code": ("🔍 <b>मुद्रा खोज</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                               "मुद्रा कोड या नाम लिखें:\n<i>जैसे BTC, ETH, USDT, Euro, INR</i>"),
        "found_currencies": "🎯 <b>{n}</b> मिलती-जुलती मुद्राएँ मिलीं:",
        "no_match": "❌ कोई मेल खाती मुद्रा नहीं मिली।",
        "send_amount": ("💰 <b>भुगतान विवरण</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "💵 राशि: <b>{amount} {currency}</b>\n📮 नीचे दिए पते पर भेजें:"),
        "popular": "⭐ <b>लोकप्रिय मुद्राएँ:</b>",
        "plan_1": "1 महीना", "plan_2": "3 महीने",
        "plan_3": "6 महीने", "plan_4": "1 वर्ष",
        "bumped_note": "ℹ️ नेटवर्क न्यूनतम के अनुसार राशि समायोजित की गई।",
        "currency_unsupported": "⚠️ यह मुद्रा भुगतान के लिए समर्थित नहीं हो सकती।",
        "maintenance": ("🛠 <b>रखरखाव जारी</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "बॉट अस्थायी रूप से अनुपलब्ध है।\nकृपया बाद में पुनः प्रयास करें।"),
        "banned_msg": ("🚫 <b>पहुँच अवरुद्ध</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                       "आपका खाता निलंबित कर दिया गया है।"),
        "admin_granted": ("🎁 <b>प्लान सक्रिय किया गया</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                          "एडमिन ने आपका प्लान सक्रिय कर दिया है।\n"
                          "📦 प्लान: <b>{plan}</b>\n"
                          "➕ दिन जोड़े: <b>{days}</b>\n"
                          "⏳ नई समाप्ति: <code>{expiry}</code>\n\n"
                          "पूर्ण पहुँच का आनंद लें!"),
    },
}

for lang_code in LANGUAGES:
    if lang_code not in TEXTS:
        TEXTS[lang_code] = TEXTS["en"]

def t(lang, key, **kwargs):
    lang = lang if lang in TEXTS else "en"
    template = TEXTS[lang].get(key) or TEXTS["en"].get(key) or key
    try:
        return template.format(**kwargs)
    except Exception:
        return template

def normalize_text(s):
    if not isinstance(s, str):
        return ""
    for ch in ("\ufe0f", "\u200b", "\u200c", "\u200d", "\u00a0", "\u2060"):
        s = s.replace(ch, "")
    return s.strip().lower()

def is_button(text, key, lang):
    candidates = {
        normalize_text(t(lang, key)),
        normalize_text(TEXTS["en"].get(key, "")),
    }
    return normalize_text(text) in candidates

# ============================================================
# API CONFIG
# ============================================================
API_CONFIG = {
    "🪪 Aadhaar Info ": {"url": "https://travelers-creature-sarah-rogers.trycloudflare.com/search?q=", "prompt": "🪪 Send a 12 Digit Aadhaar Number to Get🪪 information 💀"},
    "📞 Number Info ": {"url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=", "prompt": "📞Send a 10 Digit Indian Number (Without +91) to Get🪪 information 💀     Example (9712073901)"},
    "📍PIN Code Lookup": {"url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=", "prompt": "📍 Send PIN code to get information 💀 (number)"},
    "🚘 Vehicle Info": {"url": "https://parivahan-x.paskhinpf9.workers.dev/?vehicle=", "prompt": "🚘 Send Vehicle Number 2.0 to get information💀(write in small letters)"},
    "🤖 Telegram ID / Username ": {"url": "https://anon-tg-info.vercel.app/telegram?key=temp1750&username=", "prompt": "🤖 Send the authorized Telegram username:"},
    "🆔 PAN Info ": {"url": "https://paninfo.noob73613.workers.dev/pan?pan=", "prompt": "🆔 Send the authorized PAN reference:"},
    "📱 Telegram Chat ID ": {"url": "https://anon-tg-info.vercel.app/tgReg_beta?userid=", "prompt": "📱 Send the authorized Chat ID:"},
    "💳 IFSC Info ": {"url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=", "prompt": "💳 Send the IFSC code number:-"},
    "🏦 UPI INFO ": {"url": "https://upi-id-to-info-by-abhigyan.onrender.com/upi/", "prompt": "🏦 Send the authorized UPI ID:"},
    "📧 Advanced Email Info ": {"url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=", "prompt": "📧 Send the authorized email:"},
    "🌐 IP Address Info": {"url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=", "prompt": "🌐 Send the IP address:"}
}

# ============================================================
# HTTP SESSIONS
# ============================================================
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
HTTP.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0))
HTTP.mount("http://", HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0))

ADMIN_HTTP = requests.Session()
ADMIN_HTTP.headers.update({"Connection": "keep-alive"})
ADMIN_HTTP.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0))
ADMIN_HTTP.mount("http://", HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0))

TELEGRAM_CONNECT_TIMEOUT = 5
TELEGRAM_READ_TIMEOUT = 35
API_CONNECT_TIMEOUT = 3
API_READ_TIMEOUT = 15

USER_TELEGRAM_API = "https://api.telegram.org/bot" + USER_BOT_TOKEN
ADMIN_TELEGRAM_APIS = {1: "https://api.telegram.org/bot" + ADMIN_BOT_TOKEN_1}

# ============================================================
# STATE
# ============================================================
USER_STATE = {}
ACTIVATED_USERS = {}
USER_LANGS = {}
ADMIN_STATE = {}

# ============================================================
# DATABASE
# ============================================================
def load_activation_data():
    global ACTIVATED_USERS, USER_LANGS
    data = _safe_load(DB_FILE, {})
    ACTIVATED_USERS = {int(k): float(v) for k, v in data.get("activated_users", {}).items()}
    USER_LANGS = {int(k): str(v) for k, v in data.get("user_langs", {}).items()}

def save_activation_data():
    with db_lock:
        data = {"activated_users": ACTIVATED_USERS, "user_langs": USER_LANGS}
        _safe_save(DB_FILE, data)

def get_lang(chat_id):
    return USER_LANGS.get(chat_id, "en")

def set_lang(chat_id, lang):
    USER_LANGS[chat_id] = lang
    save_activation_data()

# ============================================================
# TELEGRAM API (USER BOT)
# ============================================================
def send_message(chat_id, text, keyboard=None, parse_mode="HTML"):
    url = USER_TELEGRAM_API + "/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if keyboard is not None:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        r = HTTP.post(url, data=data, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400 and "parse" in e.response.text.lower():
            data.pop("parse_mode", None)
            try:
                r = HTTP.post(url, data=data, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
                r.raise_for_status()
                return r.json()
            except Exception as inner:
                print("Plain retry fail:", inner)
        print("sendMessage err:", e)
        return None
    except Exception as e:
        print("sendMessage err:", e)
        return None

def send_photo(chat_id, photo, caption=None, keyboard=None, parse_mode="HTML"):
    url = USER_TELEGRAM_API + "/sendPhoto"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
    if keyboard is not None:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)

    files = None
    if isinstance(photo, str) and photo in IMAGE_CACHE:
        files = {"photo": (os.path.basename(photo).replace(".png", ".jpg"), IMAGE_CACHE[photo], "image/jpeg")}
    elif isinstance(photo, str) and os.path.exists(photo):
        try:
            with open(photo, "rb") as f:
                mime = "image/png" if photo.lower().endswith(".png") else "image/jpeg"
                files = {"photo": (os.path.basename(photo), f.read(), mime)}
        except Exception as e:
            print(f"read img err {photo}: {e}")
    elif isinstance(photo, str):
        data["photo"] = photo
    else:
        files = {"photo": ("qr.png", photo, "image/png")}

    if files is None and isinstance(photo, str) and (photo.endswith(".png") or photo.endswith(".jpg") or photo.endswith(".jpeg")):
        if caption:
            return send_message(chat_id, caption, keyboard, parse_mode)
        return None

    try:
        r = HTTP.post(url, data=data, files=files, timeout=(TELEGRAM_CONNECT_TIMEOUT, 60))
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None
    except requests.exceptions.HTTPError as e:
        print(f"sendPhoto HTTP {e.response.status_code}")
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None
    except Exception as e:
        print("sendPhoto err:", e)
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None

def get_updates(offset=None):
    """🔧 CHANGED: quieter 409 handling."""
    url = USER_TELEGRAM_API + "/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    try:
        r = HTTP.get(url, params=params, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
        if r.status_code == 409:
            # Conflict — another instance is polling. Sleep quietly.
            return {"ok": False, "conflict": True}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("getUpdates err:", e)
        return None

def answer_callback(callback_id, text=None):
    url = USER_TELEGRAM_API + "/answerCallbackQuery"
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text[:200]
    try:
        HTTP.post(url, data=data, timeout=(5, 10))
    except Exception as e:
        print("answerCB err:", e)

def delete_message(chat_id, message_id):
    url = USER_TELEGRAM_API + "/deleteMessage"
    try:
        HTTP.post(url, data={"chat_id": chat_id, "message_id": message_id}, timeout=(5, 10))
    except Exception as e:
        print("delMsg err:", e)

# ============================================================
# QR / HELPERS
# ============================================================
def generate_qr_bytes(data):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=3)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf.getvalue()

def copy_address_keyboard(address):
    return {"inline_keyboard": [[{"text": "📋 Copy Address", "copy_text": {"text": address}}]]}

def build_payment_uri(currency, address, amount=None):
    currency = (currency or "").lower()
    if currency == "btc":
        return f"bitcoin:{address}" + (f"?amount={amount}" if amount else "")
    if currency == "eth":  return f"ethereum:{address}"
    if currency == "ltc":
        return f"litecoin:{address}" + (f"?amount={amount}" if amount else "")
    if currency == "trx":  return f"tron:{address}"
    return address

def prettify_currency(raw):
    raw = (raw or "").upper()
    if raw == "USDTTRC20": return "USDT (TRC20)"
    if raw == "USDTERC20": return "USDT (ERC20)"
    return raw

# ============================================================
# CURRENCY LIST
# ============================================================
def fetch_all_currencies():
    now = time.time()
    if CURRENCY_CACHE["list"] and (now - CURRENCY_CACHE["ts"]) < CURRENCY_CACHE_TTL:
        return CURRENCY_CACHE["list"]
    merged = {code: {"code": code, "name": name} for code, name in FIAT_FALLBACK}
    try:
        r = HTTP.get(NOWPAYMENTS_API_URL + "/currencies",
                     headers={"x-api-key": NOWPAYMENTS_API_KEY},
                     timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
        if r.status_code == 200:
            for code in r.json().get("currencies", []):
                cl = code.lower()
                if cl not in merged:
                    merged[cl] = {"code": cl, "name": cl.upper()}
    except Exception as e:
        print("currencies err:", e)
    lst = sorted(merged.values(), key=lambda c: c["code"])
    CURRENCY_CACHE["list"] = lst
    CURRENCY_CACHE["ts"] = now
    return lst

def find_currencies(query, limit=10):
    q = normalize_text(query)
    if not q: return []
    lst = fetch_all_currencies()
    exact, starts, contains = [], [], []
    for c in lst:
        cl, nl = c["code"].lower(), c["name"].lower()
        if cl == q or nl == q: exact.append(c)
        elif cl.startswith(q) or nl.startswith(q): starts.append(c)
        elif q in cl or q in nl: contains.append(c)
    return (exact + starts + contains)[:limit]

# ============================================================
# NOWPAYMENTS MIN AMOUNT
# ============================================================
def get_min_amount(crypto_currency, fiat="usd"):
    try:
        r = HTTP.get(NOWPAYMENTS_API_URL + "/min-amount",
                     params={"currency_from": crypto_currency, "currency_to": fiat, "fiat_equivalent": fiat},
                     headers={"x-api-key": NOWPAYMENTS_API_KEY},
                     timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
        r.raise_for_status()
        d = r.json()
        return d.get("min_amount"), d.get("fiat_equivalent")
    except Exception as e:
        print(f"min-amount {crypto_currency}: {e}")
        return None, None

def get_min_amount_cached(crypto_currency, fiat="usd"):
    now = time.time()
    cached = MIN_AMOUNT_CACHE.get(crypto_currency)
    if cached and (now - cached[2]) < MIN_AMOUNT_CACHE_TTL:
        return cached[0], cached[1]
    mn, mf = get_min_amount(crypto_currency, fiat)
    if mn is not None and mf is not None:
        MIN_AMOUNT_CACHE[crypto_currency] = (mn, mf, now)
    return mn, mf

# ============================================================
# USER KEYBOARDS
# ============================================================
def payment_inline_keyboard(lang="en"):
    return {"inline_keyboard": [
        [{"text": "1 Month - $13.00", "callback_data": "select_plan:plan_1"},
         {"text": "3 Months - $18.00", "callback_data": "select_plan:plan_2"}],
        [{"text": "6 Months - $25.00", "callback_data": "select_plan:plan_3"},
         {"text": "1 Year - $35.00", "callback_data": "select_plan:plan_4"}],
        [{"text": t(lang, "check_status_btn"), "callback_data": "user:check_status"},
         {"text": t(lang, "cancel_btn"), "callback_data": "user:cancel"}],
        [{"text": t(lang, "lang_btn"), "callback_data": "user:lang"}],
    ]}

def main_keyboard(lang="en"):
    buttons = list(API_CONFIG.keys())
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    keyboard.append([t(lang, "deactivate_btn"), t(lang, "cancel_btn")])
    keyboard.append([t(lang, "lang_btn")])
    return {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": False}

def language_keyboard():
    items = list(LANGUAGES.items())
    rows = []
    for i in range(0, len(items), 2):
        row = [{"text": name, "callback_data": f"lang:{code}"} for code, name in items[i:i+2]]
        rows.append(row)
    return {"inline_keyboard": rows}

def currency_inline_keyboard(results):
    rows = [[{"text": f"{c['code'].upper()} — {c['name']}", "callback_data": f"cur:{c['code']}"}] for c in results]
    rows.append([{"text": "❌ Cancel", "callback_data": "cur:cancel"}])
    return {"inline_keyboard": rows}

def popular_currency_keyboard(plan_id, lang="en"):
    rows, row = [], []
    for code in POPULAR_CODES:
        row.append({"text": code.upper(), "callback_data": f"plan:{plan_id}:{code}"})
        if len(row) == 3:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([{"text": t(lang, "search_currency"), "callback_data": f"search:{plan_id}"},
                 {"text": t(lang, "back"), "callback_data": "back:plans"}])
    return {"inline_keyboard": rows}

# ============================================================
# ADMIN KEYBOARDS
# ============================================================
def admin_main_keyboard():
    return {"inline_keyboard": [
        [{"text": "👥 Users",       "callback_data": "admin:list"},
         {"text": "📊 Stats",       "callback_data": "admin:stats"}],
        [{"text": "🎁 Activate User", "callback_data": "admin:activate_help"},
         {"text": "❌ Revoke",       "callback_data": "admin:revoke_help"}],
        [{"text": "🚫 Banned",      "callback_data": "admin:banned"},
         {"text": "🟢 Online",      "callback_data": "admin:online"}],
        [{"text": "👑 Admins",      "callback_data": "admin:admins"},
         {"text": "📜 Logs",        "callback_data": "admin:logs"}],
        [{"text": "💰 Revenue",     "callback_data": "admin:revenue"},
         {"text": "📁 View DB",     "callback_data": "admin:db"}],
        [{"text": "📢 Broadcast",   "callback_data": "admin:broadcast"},
         {"text": "🧹 Remove All",  "callback_data": "admin:remove_all"}],
        [{"text": "🛠 Maintenance", "callback_data": "admin:maintenance"},
         {"text": "🆔 Who Am I",    "callback_data": "admin:whoami"}],
    ]}

def admin_admins_keyboard():
    return {"inline_keyboard": [
        [{"text": "➕ Add Admin",    "callback_data": "admin:add_admin"}],
        [{"text": "➖ Remove Admin", "callback_data": "admin:remove_admin"}],
        [{"text": "📋 List Admins",  "callback_data": "admin:list_admins"}],
        [{"text": "🔙 Back",         "callback_data": "admin:back"}],
    ]}

def admin_plan_picker_keyboard(target_uid, mode="set"):
    rows = []
    for pid, p in PLANS.items():
        label = f"{p['name']} · {p['days']}d · ${p['price_usd']:.0f}"
        rows.append([{"text": label, "callback_data": f"admin:do_activate:{target_uid}:{pid}:{mode}"}])
    rows.append([
        {"text": "✏️ Custom days", "callback_data": f"admin:custom_activate:{target_uid}:{mode}"},
        {"text": "❌ Cancel",      "callback_data": "admin:back"},
    ])
    return {"inline_keyboard": rows}

# ============================================================
# NOWPAYMENTS PAYMENT CREATION
# ============================================================
def create_nowpayments_payment(chat_id, plan_id, pay_currency, charge_usd=None):
    plan = PLANS.get(plan_id)
    if not plan: return {"error": "unknown_plan"}
    if charge_usd is None: charge_usd = float(plan["price_usd"])
    order_id = f"tg_{chat_id}_{plan['days']}_{int(time.time())}"
    payload = {
        "price_amount": charge_usd, "price_currency": "usd",
        "pay_currency": pay_currency, "order_id": order_id,
        "order_description": f"Bot Activation - {plan['name']} - {chat_id}",
    }
    if IPN_CALLBACK_URL and IPN_CALLBACK_URL.startswith("http") and "your-app" not in IPN_CALLBACK_URL:
        payload["ipn_callback_url"] = IPN_CALLBACK_URL
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
    try:
        r = HTTP.post(NOWPAYMENTS_API_URL + "/payment", json=payload, headers=headers,
                      timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
        try: body = r.json()
        except Exception: return {"error": "api_error", "status": r.status_code, "message": r.text[:500]}
        if r.status_code not in (200, 201):
            return {"error": "api_error", "status": r.status_code,
                    "message": body.get("message") or body.get("error") or str(body)}
        if not body.get("pay_address"):
            return {"error": "api_error", "status": r.status_code, "message": body.get("message") or "No pay_address"}
        return body
    except requests.exceptions.Timeout:
        return {"error": "timeout"}
    except requests.exceptions.RequestException as e:
        return {"error": "network", "message": str(e)}
    except Exception as e:
        return {"error": "unexpected", "message": str(e)}

# ============================================================
# IPN WEBHOOK
# ============================================================
def verify_nowpayments_ipn(request_body, received_signature):
    try:
        body = request_body if isinstance(request_body, dict) else json.loads(request_body)
        sorted_body = json.dumps(body, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(NOWPAYMENTS_IPN_SECRET.encode("utf-8"),
                            sorted_body.encode("utf-8"), hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, received_signature)
    except Exception as e:
        print("IPN verify err:", e)
        return False

@app.route("/nowpayments_webhook", methods=["POST"])
def nowpayments_webhook():
    raw_body = request.data.decode("utf-8")
    sig = request.headers.get("x-nowpayments-sig")
    if not sig or not verify_nowpayments_ipn(raw_body, sig):
        return jsonify({"status": "invalid signature"}), 400
    try:
        data = json.loads(raw_body)
        status = data.get("payment_status")
        order_id = data.get("order_id")
        if status in ("finished", "confirmed") and order_id:
            parts = order_id.split("_")
            if len(parts) >= 4 and parts[0] == "tg":
                user_id = int(parts[1]); days = int(parts[2])
                current = ACTIVATED_USERS.get(user_id, 0)
                if current < time.time(): current = time.time()
                new_expiry = current + (days * 86400)
                ACTIVATED_USERS[user_id] = new_expiry
                save_activation_data()
                lang = get_lang(user_id)
                expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(new_expiry))
                send_message(user_id,
                    f"{t(lang, 'payment_confirmed')}\n\n"
                    f"{t(lang, 'activated_days', days=days)}\n"
                    f"{t(lang, 'expiry')}: <code>{expiry_str}</code>\n\n"
                    f"{t(lang, 'select_feature')}",
                    main_keyboard(lang))
    except Exception as e:
        print("webhook err:", e)
    return jsonify({"status": "ok"}), 200

# ============================================================
# HELPERS
# ============================================================
def is_active(chat_id):
    exp = ACTIVATED_USERS.get(chat_id)
    return bool(exp and exp > time.time())

def grant_plan(target_uid, days, mode="set"):
    now = time.time()
    prev = ACTIVATED_USERS.get(target_uid, 0)
    if mode == "extend":
        base = prev if prev > now else now
        new_expiry = base + days * 86400
        added = days
    else:
        new_expiry = now + days * 86400
        added = days
    ACTIVATED_USERS[target_uid] = new_expiry
    save_activation_data()
    return new_expiry, added, prev

def notify_user_activated(target_uid, plan_label, days, new_expiry):
    lang = get_lang(target_uid)
    expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(new_expiry))
    try:
        send_message(target_uid,
            t(lang, "admin_granted", plan=plan_label, days=days, expiry=expiry_str),
            main_keyboard(lang))
        return True
    except Exception as e:
        print("notify_user_activated err:", e)
        return False

def create_payment_and_send(chat_id, plan_id, pay_currency):
    lang = get_lang(chat_id)
    plan = PLANS.get(plan_id)
    if not plan:
        send_message(chat_id, "Unknown plan.", payment_inline_keyboard(lang)); return
    send_message(chat_id, t(lang, "generating"))
    charge_usd = float(plan["price_usd"])
    mn, mf = get_min_amount_cached(pay_currency, "usd")
    if mf is not None and charge_usd < float(mf):
        charge_usd = round(float(mf) * 1.05, 2)
    payment = create_nowpayments_payment(chat_id, plan_id, pay_currency, charge_usd=charge_usd)
    if payment and payment.get("error"):
        err = payment.get("error"); msg_text = payment.get("message", "")
        if err == "timeout":
            send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "payment_timeout"),
                       keyboard=payment_inline_keyboard(lang))
        else:
            send_photo(chat_id, PAYMENT_IMG,
                caption=f"{t(lang, 'payment_api_error')}\n\n<code>{err}: {msg_text[:400]}</code>\n\n{t(lang, 'try_again')}",
                keyboard=payment_inline_keyboard(lang))
        return
    if not payment or not payment.get("pay_address"):
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "try_again"),
                   keyboard=payment_inline_keyboard(lang)); return
    pay_address = payment["pay_address"]
    pay_amount = payment.get("pay_amount")
    pay_curr = prettify_currency(payment.get("pay_currency") or pay_currency)
    try:
        qr_data = build_payment_uri(pay_currency, pay_address,
                                    amount=pay_amount if pay_currency in ("btc","ltc") else None)
        send_photo(chat_id, generate_qr_bytes(qr_data),
            caption=(f"🪙 <b>{pay_curr} Payment Invoice</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                     f"📷 <b>Scan the QR</b> or copy the address below."),
            keyboard=copy_address_keyboard(pay_address))
    except Exception as e:
        print("QR err:", e)
    send_message(chat_id,
        t(lang, "send_amount", amount=pay_amount, currency=pay_curr) +
        f"\n<code>{pay_address}</code>",
        copy_address_keyboard(pay_address))

# ============================================================
# USER CALLBACK HANDLER
# ============================================================
def process_callback(cb):
    data = cb.get("data", "") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    msg_id = msg.get("message_id")
    cb_id = cb.get("id")
    if chat_id is None: return
    lang = get_lang(chat_id)

    if is_banned(chat_id):
        answer_callback(cb_id, "🚫 Banned"); return
    if MAINTENANCE_MODE and get_role(chat_id) == "user":
        answer_callback(cb_id, "🛠 Maintenance"); return

    if data.startswith("lang:"):
        code = data.split(":", 1)[1]
        if code in LANGUAGES:
            set_lang(chat_id, code)
            answer_callback(cb_id, t(code, "language_set"))
            if msg_id: delete_message(chat_id, msg_id)
            if is_active(chat_id):
                caption = t(code, "already_active") + "\n\n" + t(code, "select_feature")
                send_photo(chat_id, OSINT_IMG, caption=caption, keyboard=main_keyboard(code))
            else:
                caption = t(code, "welcome") + "\n\n" + t(code, "select_plan")
                send_photo(chat_id, PAYMENT_IMG, caption=caption, keyboard=payment_inline_keyboard(code))
        return

    if data == "back:plans":
        answer_callback(cb_id)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "select_plan"),
                   keyboard=payment_inline_keyboard(lang)); return

    if data.startswith("select_plan:"):
        plan_id = data.split(":", 1)[1]
        USER_STATE[chat_id] = {"flow": "select_currency", "plan_id": plan_id}
        answer_callback(cb_id)
        if msg_id: delete_message(chat_id, msg_id)
        caption_text = t(lang, "select_currency", plan=t(lang, plan_id),
                         price=f"{PLANS[plan_id]['price_usd']:.2f}") + "\n\n" + t(lang, "popular")
        send_photo(chat_id, PAYMENT_IMG, caption=caption_text,
                   keyboard=popular_currency_keyboard(plan_id, lang)); return

    if data == "user:check_status":
        answer_callback(cb_id)
        if is_active(chat_id):
            expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ACTIVATED_USERS[chat_id]))
            send_message(chat_id,
                f"{t(lang, 'status_active')}\n━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{t(lang, 'expiry')}: <code>{expiry_str}</code>",
                main_keyboard(lang))
        else:
            send_photo(chat_id, PAYMENT_IMG,
                caption=f"{t(lang, 'status_inactive')}\n\n{t(lang, 'buy_plan')}",
                keyboard=payment_inline_keyboard(lang))
        return

    if data == "user:cancel":
        answer_callback(cb_id)
        USER_STATE.pop(chat_id, None)
        if msg_id: delete_message(chat_id, msg_id)
        send_photo(chat_id, PAYMENT_IMG,
                   caption=t(lang, "cancelled") + "\n\n" + t(lang, "select_plan"),
                   keyboard=payment_inline_keyboard(lang)); return

    if data == "user:lang":
        answer_callback(cb_id)
        send_message(chat_id, t(lang, "choose_language"), language_keyboard()); return

    if data.startswith("search:"):
        plan_id = data.split(":", 1)[1]
        USER_STATE[chat_id] = {"flow": "search_currency", "plan_id": plan_id}
        answer_callback(cb_id)
        send_message(chat_id, t(lang, "send_currency_code")); return

    if data == "cur:cancel":
        answer_callback(cb_id)
        USER_STATE.pop(chat_id, None)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "cancelled"),
                   keyboard=payment_inline_keyboard(lang)); return

    if data.startswith("cur:"):
        code = data.split(":", 1)[1]
        plan_id = USER_STATE.get(chat_id, {}).get("plan_id")
        if not plan_id:
            answer_callback(cb_id, "Please select a plan first."); return
        answer_callback(cb_id)
        create_payment_and_send(chat_id, plan_id, code)
        USER_STATE.pop(chat_id, None); return

    if data.startswith("plan:"):
        parts = data.split(":")
        if len(parts) != 3:
            answer_callback(cb_id); return
        _, plan_id, code = parts
        answer_callback(cb_id)
        create_payment_and_send(chat_id, plan_id, code)
        USER_STATE.pop(chat_id, None); return

# ============================================================
# USER UPDATE HANDLER
# ============================================================
def process_update(update):
    if "callback_query" in update:
        process_callback(update["callback_query"]); return
    if "message" not in update: return
    message = update["message"]
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None: return

    LAST_SEEN[chat_id] = time.time()

    text = message.get("text", "")
    if not isinstance(text, str): return
    text = text.strip()
    lang = get_lang(chat_id)

    if is_banned(chat_id):
        if text == "/start":
            send_message(chat_id, t(lang, "banned_msg"))
        return

    if MAINTENANCE_MODE and get_role(chat_id) == "user":
        if text == "/start":
            send_message(chat_id, t(lang, "maintenance"))
        return

    if text == "/start":
        USER_STATE.pop(chat_id, None)
        caption = t(lang, "welcome") + "\n\n━━━━━━━━━━━━━━━━━━━━━━━\n\n" + t(lang, "choose_language")
        send_photo(chat_id, WELCOME_IMG, caption=caption, keyboard=language_keyboard()); return

    if text in ("/lang", "/language") or is_button(text, "lang_btn", lang):
        send_message(chat_id, t(lang, "choose_language"), language_keyboard()); return

    if text == "/cancel" or is_button(text, "cancel_btn", lang):
        USER_STATE.pop(chat_id, None)
        if is_active(chat_id):
            send_message(chat_id, t(lang, "cancelled") + "\n\n" + t(lang, "select_feature"),
                         main_keyboard(lang))
        else:
            send_photo(chat_id, PAYMENT_IMG,
                       caption=t(lang, "cancelled") + "\n\n" + t(lang, "select_plan"),
                       keyboard=payment_inline_keyboard(lang))
        return

    if is_button(text, "check_status_btn", lang):
        if is_active(chat_id):
            expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ACTIVATED_USERS[chat_id]))
            send_message(chat_id,
                f"{t(lang, 'status_active')}\n━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{t(lang, 'expiry')}: <code>{expiry_str}</code>", main_keyboard(lang))
        else:
            send_photo(chat_id, PAYMENT_IMG,
                       caption=f"{t(lang, 'status_inactive')}\n\n{t(lang, 'buy_plan')}",
                       keyboard=payment_inline_keyboard(lang))
        return

    if is_button(text, "deactivate_btn", lang):
        if chat_id in ACTIVATED_USERS:
            del ACTIVATED_USERS[chat_id]; save_activation_data()
        USER_STATE.pop(chat_id, None)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "deactivated_msg"),
                   keyboard=payment_inline_keyboard(lang)); return

    state = USER_STATE.get(chat_id, {})
    if state.get("flow") == "search_currency":
        results = find_currencies(text, limit=12)
        if not results:
            send_message(chat_id, t(lang, "no_match")); return
        send_message(chat_id, t(lang, "found_currencies", n=len(results)),
                     currency_inline_keyboard(results)); return

    if state.get("flow") == "api_query":
        api_name = state.get("api_name")
        if not api_name:
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, t(lang, "select_option"), main_keyboard(lang)); return
        query = text.strip()
        if not query:
            send_message(chat_id, "❌ Query cannot be empty."); return
        config = API_CONFIG.get(api_name)
        send_message(chat_id, t(lang, "searching"))
        try:
            r = HTTP.get(config["url"] + quote_plus(query),
                         timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
            r.raise_for_status()
            api_result = r.json()
            formatted = json.dumps(api_result, indent=2, ensure_ascii=False)
            formatted = formatted.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            max_length = 3900
            if len(formatted) <= max_length:
                send_message(chat_id, f"<pre>{formatted}</pre>", main_keyboard(lang))
            else:
                for i in range(0, len(formatted), max_length):
                    send_message(chat_id, f"<pre>{formatted[i:i+max_length]}</pre>")
                send_message(chat_id, "✅ Finished.", main_keyboard(lang))
        except Exception as e:
            print("API err:", e)
            send_message(chat_id, t(lang, "no_result"), main_keyboard(lang))
        USER_STATE.pop(chat_id, None); return

    if not is_active(chat_id):
        send_photo(chat_id, PAYMENT_IMG,
                   caption=f"{t(lang, 'locked')}\n\n{t(lang, 'buy_plan')}",
                   keyboard=payment_inline_keyboard(lang))
        return

    api_name = next((name for name in API_CONFIG if name.strip() == text.strip()), None)
    if api_name is not None:
        config = API_CONFIG[api_name]
        USER_STATE[chat_id] = {"flow": "api_query", "api_name": api_name}
        send_message(chat_id, config["prompt"] + "\n\n" + t(lang, "send_cancel"),
                     main_keyboard(lang)); return

    send_message(chat_id, t(lang, "select_option"), main_keyboard(lang))

# ============================================================
# ADMIN BOT
# ============================================================
def admin_send_message(bot_number, chat_id, text, keyboard=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api: return None
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        r = ADMIN_HTTP.post(api + "/sendMessage", data=data, timeout=(5, 35))
        return r.json()
    except Exception as e:
        print(f"adminSend err: {e}")
        return None

def admin_get_updates(bot_number, offset=None):
    """🔧 CHANGED: quieter 409 handling."""
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api: return None
    params = {"timeout": 30}
    if offset: params["offset"] = offset
    try:
        r = ADMIN_HTTP.get(api + "/getUpdates", params=params, timeout=(5, 35))
        if r.status_code == 409:
            return {"ok": False, "conflict": True}
        if r.status_code != 200:
            print(f"admin getUpdates HTTP {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"admin getUpdates err: {e}")
        return None

def admin_answer_callback(bot_number, callback_id, text=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api or not callback_id or callback_id == "dummy": return
    data = {"callback_query_id": callback_id}
    if text: data["text"] = text[:200]
    try:
        ADMIN_HTTP.post(api + "/answerCallbackQuery", data=data, timeout=(5, 10))
    except Exception as e:
        print(f"answerCB err: {e}")

def fmt_user_line(uid):
    exp = ACTIVATED_USERS.get(uid)
    lang = USER_LANGS.get(uid, "en")
    if exp:
        status = "✅" if exp > time.time() else "⌛"
        exp_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
    else:
        status = "❌"
        exp_str = "—"
    ban = "🚫" if uid in BANNED_USERS else ""
    seen = LAST_SEEN.get(uid)
    seen_str = time.strftime("%m-%d %H:%M", time.localtime(seen)) if seen else "—"
    return f"{status}{ban} <code>{uid}</code> · {lang} · exp {exp_str} · seen {seen_str}"

def plans_summary_text():
    lines = ["📦 <b>Available plans</b>"]
    for pid, p in PLANS.items():
        lines.append(f"• <code>{pid}</code> — {p['name']} ({p['days']}d, ${p['price_usd']:.0f})")
    lines.append("\nUsage: <code>/activate USER_ID</code> or <code>/activate USER_ID plan_1</code>")
    lines.append("Extend instead of reset: add <code>extend</code> at the end.")
    lines.append("Custom days: <code>/activate USER_ID custom 45</code>")
    return "\n".join(lines)

# ---------- ADMIN CALLBACK ROUTER ----------
def process_admin_callback(bot_number, cb):
    global MAINTENANCE_MODE

    data = cb.get("data", "") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    cb_id = cb.get("id")
    if chat_id is None: return

    if not is_admin(chat_id):
        admin_answer_callback(bot_number, cb_id, "⛔ Unauthorized"); return

    if data == "admin:back":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            "🛠 <b>A D M I N   P A N E L</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 Choose an action below:",
            admin_main_keyboard()); return

    if data == "admin:list":
        admin_answer_callback(bot_number, cb_id)
        if not ACTIVATED_USERS:
            admin_send_message(bot_number, chat_id, "📭 No users.", admin_main_keyboard()); return
        lines = ["👥 <b>USERS</b> (recent first)\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        items = sorted(ACTIVATED_USERS.items(), key=lambda x: x[1], reverse=True)[:40]
        for uid, _ in items:
            lines.append(fmt_user_line(uid))
        if len(ACTIVATED_USERS) > 40:
            lines.append(f"\n…and {len(ACTIVATED_USERS)-40} more (use /export).")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard()); return

    if data == "admin:banned":
        admin_answer_callback(bot_number, cb_id)
        if not BANNED_USERS:
            admin_send_message(bot_number, chat_id, "✅ No banned users.", admin_main_keyboard()); return
        lines = ["🚫 <b>BANNED USERS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for uid, info in sorted(BANNED_USERS.items()):
            reason = info.get("reason", "—")
            lines.append(f"• <code>{uid}</code> — {reason}")
        lines.append("\nUnban: <code>/unban USER_ID</code>")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard()); return

    if data == "admin:online":
        admin_answer_callback(bot_number, cb_id)
        now = time.time()
        recent = [(uid, ts) for uid, ts in LAST_SEEN.items() if now - ts < 86400]
        recent.sort(key=lambda x: x[1], reverse=True)
        if not recent:
            admin_send_message(bot_number, chat_id, "💤 No activity in last 24h.", admin_main_keyboard()); return
        lines = ["🟢 <b>ACTIVE (last 24h)</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for uid, ts in recent[:40]:
            ago = int(now - ts)
            if ago < 3600: mins = ago // 60; rel = f"{mins}m ago"
            else: rel = f"{ago // 3600}h ago"
            lines.append(f"• <code>{uid}</code> — {rel}")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard()); return

    if data == "admin:logs":
        admin_answer_callback(bot_number, cb_id)
        if not ADMIN_LOG:
            admin_send_message(bot_number, chat_id, "📭 No admin logs yet.", admin_main_keyboard()); return
        lines = ["📜 <b>ADMIN LOG</b> (latest 40)\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for e in ADMIN_LOG[-40:][::-1]:
            ts = time.strftime("%m-%d %H:%M", time.localtime(e["ts"]))
            by = e["by"]; act = e["action"]; tgt = e.get("target", "")
            lines.append(f"<code>{ts}</code> · <code>{by}</code> → {act} <code>{tgt}</code>")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard()); return

    if data == "admin:revenue":
        admin_answer_callback(bot_number, cb_id)
        total_users = len(ACTIVATED_USERS)
        now = time.time()
        active = sum(1 for e in ACTIVATED_USERS.values() if e > now)
        expired = total_users - active
        avg_price = sum(p["price_usd"] for p in PLANS.values()) / len(PLANS)
        est = round(avg_price * total_users, 2)
        txt = (
            f"💰 <b>REVENUE ESTIMATE</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Paid users (all time): <b>{total_users}</b>\n"
            f"✅ Active: <b>{active}</b>\n"
            f"⌛ Expired: <b>{expired}</b>\n"
            f"💵 Avg plan price: <b>${avg_price:.2f}</b>\n"
            f"📊 Estimated revenue: <b>${est:.2f} USD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>(estimated — not from payment logs)</i>"
        )
        admin_send_message(bot_number, chat_id, txt, admin_main_keyboard()); return

    if data == "admin:stats":
        admin_answer_callback(bot_number, cb_id)
        total = len(ACTIVATED_USERS); now = time.time()
        active = sum(1 for e in ACTIVATED_USERS.values() if e > now)
        banned = len(BANNED_USERS)
        admins = len(DYNAMIC_ADMINS)
        seen24 = sum(1 for ts in LAST_SEEN.values() if now - ts < 86400)
        stats_text = (
            f"📊 <b>BOT STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total users: <b>{total}</b>\n"
            f"✅ Active: <b>{active}</b>\n"
            f"⌛ Expired: <b>{total - active}</b>\n"
            f"🟢 Seen (24h): <b>{seen24}</b>\n"
            f"🚫 Banned: <b>{banned}</b>\n"
            f"🛡 Admins: <b>{admins}</b>\n"
            f"🛠 Maintenance: <b>{'ON' if MAINTENANCE_MODE else 'OFF'}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )
        admin_send_message(bot_number, chat_id, stats_text, admin_main_keyboard()); return

    if data == "admin:db":
        admin_answer_callback(bot_number, cb_id)
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 3500: content = content[:3500] + "\n... [TRUNCATED]"
            content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            admin_send_message(bot_number, chat_id, f"📁 <b>RAW DATABASE</b>\n<pre>{content}</pre>",
                               admin_main_keyboard())
        except Exception as e:
            admin_send_message(bot_number, chat_id, f"❌ Error: {e}", admin_main_keyboard())
        return

    if data == "admin:admins":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            "👑 <b>A D M I N   M A N A G E M E N T</b>\n━━━━━━━━━━━━━━━━━━━━━━━",
            admin_admins_keyboard()); return

    if data == "admin:list_admins":
        admin_answer_callback(bot_number, cb_id)
        lines = ["👑 <b>ADMIN LIST</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for aid in sorted(DYNAMIC_ADMINS):
            lines.append(f"• <code>{aid}</code> — {role_badge(aid)}")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_admins_keyboard()); return

    if data == "admin:maintenance":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        admin_answer_callback(bot_number, cb_id)
        kb = {"inline_keyboard": [
            [{"text": "🟢 Turn ON",  "callback_data": "admin:maintenance_on"}],
            [{"text": "🔴 Turn OFF", "callback_data": "admin:maintenance_off"}],
            [{"text": "🔙 Back",     "callback_data": "admin:back"}],
        ]}
        admin_send_message(bot_number, chat_id,
            f"🛠 <b>MAINTENANCE MODE</b>\nCurrent: <b>{'ON' if MAINTENANCE_MODE else 'OFF'}</b>",
            kb); return

    if data == "admin:maintenance_on":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        MAINTENANCE_MODE = True
        log_admin(chat_id, "maintenance ON")
        admin_answer_callback(bot_number, cb_id, "🛠 ON")
        admin_send_message(bot_number, chat_id, "🛠 Maintenance mode <b>ON</b>.", admin_main_keyboard()); return

    if data == "admin:maintenance_off":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        MAINTENANCE_MODE = False
        log_admin(chat_id, "maintenance OFF")
        admin_answer_callback(bot_number, cb_id, "✅ OFF")
        admin_send_message(bot_number, chat_id, "✅ Maintenance mode <b>OFF</b>.", admin_main_keyboard()); return

    if data == "admin:whoami":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            f"🆔 <code>{chat_id}</code>\n"
            f"🏷 Role: <b>{role_badge(chat_id)}</b>\n"
            f"🛠 Maintenance: <b>{'ON' if MAINTENANCE_MODE else 'OFF'}</b>",
            admin_main_keyboard()); return

    if data == "admin:add_admin":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_add_admin"
        admin_send_message(bot_number, chat_id,
            "➕ <b>ADD ADMIN</b>\n\nSend the Telegram User ID to promote.\n\n/cancel to abort.",
            admin_admins_keyboard()); return

    if data == "admin:remove_admin":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_remove_admin"
        admin_send_message(bot_number, chat_id,
            "➖ <b>REMOVE ADMIN</b>\n\nSend the Telegram User ID to demote.\n\n/cancel to abort.",
            admin_admins_keyboard()); return

    if data == "admin:broadcast":
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_broadcast"
        admin_send_message(bot_number, chat_id,
            "📢 <b>BROADCAST</b>\n\nSend message to broadcast to all users. /cancel to abort.",
            admin_main_keyboard()); return

    if data == "admin:remove_all":
        if not is_owner(chat_id):
            admin_answer_callback(bot_number, cb_id, "⛔ Owner only"); return
        admin_answer_callback(bot_number, cb_id)
        ACTIVATED_USERS.clear(); save_activation_data()
        log_admin(chat_id, "remove_all users")
        admin_send_message(bot_number, chat_id, "🧹 All users removed.", admin_main_keyboard()); return

    if data == "admin:activate_help":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            "🎁 <b>ACTIVATE USER</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Pick a plan for the user. Then send their Telegram ID.\n\n"
            "<b>Quick commands:</b>\n"
            "<code>/activate USER_ID</code> — choose plan by buttons\n"
            "<code>/activate USER_ID plan_1</code> — direct\n"
            "<code>/activate USER_ID plan_1 extend</code> — extend, don't reset\n"
            "<code>/activate USER_ID custom 45</code> — custom days\n\n"
            f"{plans_summary_text()}")
        return

    if data == "admin:revoke_help":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            "❌ <b>REVOKE PLAN</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Usage: <code>/revoke USER_ID</code> — sets expiry to now.")
        return

    if data.startswith("admin:activate_for:"):
        target_str = data.split(":", 2)[2]
        try: target_uid = int(target_str)
        except ValueError:
            admin_answer_callback(bot_number, cb_id, "❌ Bad ID"); return
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(bot_number, chat_id,
            f"🎁 <b>Pick a plan for</b> <code>{target_uid}</code>:\n\n"
            f"(set mode = reset expiry to new total)",
            admin_plan_picker_keyboard(target_uid, mode="set"))
        return

    if data.startswith("admin:do_activate:"):
        try:
            _, _, uid_str, plan_id, mode = data.split(":", 4)
            target_uid = int(uid_str)
            plan = PLANS.get(plan_id)
            if not plan:
                admin_answer_callback(bot_number, cb_id, "❌ Unknown plan"); return
        except Exception:
            admin_answer_callback(bot_number, cb_id, "❌ Bad callback"); return

        new_expiry, added, prev = grant_plan(target_uid, plan["days"], mode=mode)
        log_admin(chat_id, f"activate:{mode}", f"{target_uid} {plan_id} +{plan['days']}d")
        admin_answer_callback(bot_number, cb_id, "✅ Activated")
        expiry_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_expiry))
        sent = notify_user_activated(target_uid, plan["name"], plan["days"], new_expiry)
        admin_send_message(bot_number, chat_id,
            f"✅ <b>Activated</b>\n"
            f"👤 User: <code>{target_uid}</code>\n"
            f"📦 Plan: <b>{plan['name']}</b> ({plan['days']}d)\n"
            f"🔁 Mode: <b>{mode}</b>\n"
            f"⏳ New expiry: <code>{expiry_str}</code>\n"
            f"📨 DM to user: {'✅' if sent else '❌ (blocked or unreachable)'}",
            admin_main_keyboard())
        return

    if data.startswith("admin:custom_activate:"):
        try:
            _, _, uid_str, mode = data.split(":", 3)
            target_uid = int(uid_str)
        except Exception:
            admin_answer_callback(bot_number, cb_id, "❌ Bad callback"); return
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = {"flow": "awaiting_custom_days",
                                "target": target_uid, "mode": mode}
        admin_send_message(bot_number, chat_id,
            f"✏️ Send number of <b>days</b> to add for <code>{target_uid}</code>.\n\n"
            f"Mode: <b>{mode}</b>\n/cancel to abort.")
        return

# ---------- ADMIN COMMANDS ----------
def process_admin_command(bot_number, chat_id, text, message):
    global CURRENT_PASSWORD, MAINTENANCE_MODE

    args = text.split()
    cmd = args[0].lower() if args else ""

    if cmd in ("/start", "/help"):
        admin_send_message(bot_number, chat_id,
            "🛠 <b>A D M I N   P A N E L</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🎁 Activation</b>\n"
            "/activate ID              — pick plan via buttons\n"
            "/activate ID plan_1       — direct assign\n"
            "/activate ID plan_1 extend — add, don't reset\n"
            "/activate ID custom 45    — custom days\n"
            "/activate_many ID1,ID2 plan_1\n"
            "/revoke ID                — cancel plan\n\n"
            "<b>User management</b>\n"
            "/add_user ID DAYS · /deactivate ID\n"
            "/extend ID DAYS · /reduce ID DAYS\n"
            "/check ID · /role ID\n\n"
            "<b>Moderation</b>\n"
            "/ban ID [reason] · /unban ID · /banned\n"
            "/msg ID TEXT\n\n"
            "<b>Notes</b>\n"
            "/note ID TEXT · /notes ID · /delnote ID N\n\n"
            "<b>Reports</b>\n"
            "/list · /stats · /revenue · /online · /logs · /export\n\n"
            "<b>Owner only</b>\n"
            "/add_admin ID · /remove_admin ID\n"
            "/setpassword NEW · /maintenance on|off · /remove_all\n\n"
            "/plans · /whoami · /logout",
            admin_main_keyboard()); return

    if cmd == "/whoami":
        admin_send_message(bot_number, chat_id,
            f"🆔 <code>{chat_id}</code>\n"
            f"🏷 Role: <b>{role_badge(chat_id)}</b>\n"
            f"🛠 Maintenance: <b>{'ON' if MAINTENANCE_MODE else 'OFF'}</b>",
            admin_main_keyboard()); return

    if cmd == "/plans":
        admin_send_message(bot_number, chat_id, plans_summary_text(), admin_main_keyboard()); return

    if cmd == "/logout":
        if is_owner(chat_id):
            admin_send_message(bot_number, chat_id,
                "❌ Owner can't logout (remove OWNER_ID env to disable).",
                admin_main_keyboard()); return
        DYNAMIC_ADMINS.discard(chat_id); save_admins()
        log_admin(chat_id, "logout")
        admin_send_message(bot_number, chat_id,
            "👋 Logged out. Send /login &lt;password&gt; to log back in."); return

    if cmd == "/setpassword":
        if not is_owner(chat_id):
            admin_send_message(bot_number, chat_id, "⛔ Owner only.", admin_main_keyboard()); return
        if len(args) < 2:
            admin_send_message(bot_number, chat_id,
                "Usage: <code>/setpassword NEW_PASSWORD</code>", admin_main_keyboard()); return
        CURRENT_PASSWORD = args[1]
        save_password()
        log_admin(chat_id, "setpassword")
        admin_send_message(bot_number, chat_id,
            "✅ <b>Password updated.</b>", admin_main_keyboard()); return

    if cmd == "/maintenance":
        if not is_owner(chat_id):
            admin_send_message(bot_number, chat_id, "⛔ Owner only.", admin_main_keyboard()); return
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            admin_send_message(bot_number, chat_id,
                "Usage: <code>/maintenance on|off</code>", admin_main_keyboard()); return
        MAINTENANCE_MODE = (args[1].lower() == "on")
        log_admin(chat_id, f"maintenance {args[1].lower()}")
        admin_send_message(bot_number, chat_id,
            f"🛠 Maintenance <b>{'ON' if MAINTENANCE_MODE else 'OFF'}</b>.",
            admin_main_keyboard()); return

    if cmd == "/add_admin":
        if not is_owner(chat_id):
            admin_send_message(bot_number, chat_id, "⛔ Owner only.", admin_main_keyboard()); return
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /add_admin ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
            DYNAMIC_ADMINS.add(target); save_admins()
            log_admin(chat_id, "add_admin", target)
            admin_send_message(bot_number, chat_id,
                f"✅ <code>{target}</code> is now Admin.", admin_main_keyboard())
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard())
        return

    if cmd == "/remove_admin":
        if not is_owner(chat_id):
            admin_send_message(bot_number, chat_id, "⛔ Owner only.", admin_main_keyboard()); return
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /remove_admin ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
            if is_owner(target):
                admin_send_message(bot_number, chat_id, "❌ Cannot remove owner.", admin_main_keyboard()); return
            DYNAMIC_ADMINS.discard(target); save_admins()
            log_admin(chat_id, "remove_admin", target)
            admin_send_message(bot_number, chat_id,
                f"✅ <code>{target}</code> removed.", admin_main_keyboard())
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard())
        return

    if cmd == "/activate":
        if len(args) < 2:
            admin_send_message(bot_number, chat_id,
                "🎁 <b>ACTIVATE USER</b>\n\n"
                "Usage:\n"
                "<code>/activate USER_ID</code> — choose plan by buttons\n"
                "<code>/activate USER_ID plan_1</code>\n"
                "<code>/activate USER_ID plan_1 extend</code>\n"
                "<code>/activate USER_ID custom 45</code>\n"
                "<code>/activate USER_ID custom 45 extend</code>\n\n"
                f"{plans_summary_text()}",
                admin_main_keyboard())
            return
        try:
            target_uid = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid USER_ID.", admin_main_keyboard()); return

        if len(args) == 2:
            admin_send_message(bot_number, chat_id,
                f"🎁 <b>Pick a plan for</b> <code>{target_uid}</code>:",
                admin_plan_picker_keyboard(target_uid, mode="set"))
            return

        plan_arg = args[2].lower()
        mode = "extend" if (len(args) >= 4 and args[-1].lower() == "extend") else "set"

        if plan_arg == "custom":
            if len(args) < 4:
                admin_send_message(bot_number, chat_id,
                    "Usage: /activate USER_ID custom DAYS [extend]",
                    admin_main_keyboard()); return
            try:
                days = int(args[3])
                if days < 1 or days > 3650:
                    raise ValueError
            except ValueError:
                admin_send_message(bot_number, chat_id, "❌ Days must be 1–3650.", admin_main_keyboard()); return
            new_expiry, added, prev = grant_plan(target_uid, days, mode=mode)
            log_admin(chat_id, f"activate:custom:{mode}", f"{target_uid} +{days}d")
            sent = notify_user_activated(target_uid, f"Custom {days}d", days, new_expiry)
            expiry_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_expiry))
            admin_send_message(bot_number, chat_id,
                f"✅ <b>Activated (custom)</b>\n"
                f"👤 <code>{target_uid}</code>\n"
                f"➕ +{days} days · mode <b>{mode}</b>\n"
                f"⏳ New expiry: <code>{expiry_str}</code>\n"
                f"📨 DM: {'✅' if sent else '❌'}",
                admin_main_keyboard())
            return

        plan = PLANS.get(plan_arg)
        if not plan:
            admin_send_message(bot_number, chat_id,
                f"❌ Unknown plan <code>{plan_arg}</code>.\n\n{plans_summary_text()}",
                admin_main_keyboard()); return

        new_expiry, added, prev = grant_plan(target_uid, plan["days"], mode=mode)
        log_admin(chat_id, f"activate:{mode}", f"{target_uid} {plan_arg} +{plan['days']}d")
        sent = notify_user_activated(target_uid, plan["name"], plan["days"], new_expiry)
        expiry_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_expiry))
        admin_send_message(bot_number, chat_id,
            f"✅ <b>Activated</b>\n"
            f"👤 User: <code>{target_uid}</code>\n"
            f"📦 Plan: <b>{plan['name']}</b> ({plan['days']}d)\n"
            f"🔁 Mode: <b>{mode}</b>\n"
            f"⏳ New expiry: <code>{expiry_str}</code>\n"
            f"📨 DM to user: {'✅' if sent else '❌ (blocked?)'}",
            admin_main_keyboard())
        return

    if cmd == "/activate_many":
        if len(args) < 3:
            admin_send_message(bot_number, chat_id,
                "Usage: /activate_many ID1,ID2,ID3 plan_1 [extend]",
                admin_main_keyboard()); return
        plan = PLANS.get(args[2].lower())
        if not plan:
            admin_send_message(bot_number, chat_id,
                f"❌ Unknown plan <code>{args[2]}</code>.", admin_main_keyboard()); return
        mode = "extend" if (len(args) >= 4 and args[-1].lower() == "extend") else "set"
        ids_raw = args[1].split(",")
        ok, fail = [], []
        for s in ids_raw:
            s = s.strip()
            if not s: continue
            try:
                uid = int(s)
                new_expiry, _, _ = grant_plan(uid, plan["days"], mode=mode)
                notify_user_activated(uid, plan["name"], plan["days"], new_expiry)
                ok.append(uid)
            except ValueError:
                fail.append(s)
        log_admin(chat_id, f"activate_many:{mode}", f"{len(ok)} ok / {len(fail)} fail")
        admin_send_message(bot_number, chat_id,
            f"✅ Bulk activation done.\n"
            f"Plan: <b>{plan['name']}</b> · mode <b>{mode}</b>\n"
            f"✔️ Success: <b>{len(ok)}</b>\n"
            f"❌ Failed: <b>{len(fail)}</b>"
            + (f"\n\nBad IDs: <code>{', '.join(fail)}</code>" if fail else ""),
            admin_main_keyboard())
        return

    if cmd == "/revoke":
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /revoke USER_ID", admin_main_keyboard()); return
        try:
            target_uid = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        if target_uid in ACTIVATED_USERS:
            del ACTIVATED_USERS[target_uid]; save_activation_data()
            log_admin(chat_id, "revoke", target_uid)
            lang = get_lang(target_uid)
            send_message(target_uid,
                f"{t(lang,'deactivated_msg')}", payment_inline_keyboard(lang))
            admin_send_message(bot_number, chat_id,
                f"❌ Plan revoked for <code>{target_uid}</code>.", admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id,
                "❌ User has no active plan.", admin_main_keyboard())
        return

    if cmd == "/list":
        process_admin_callback(bot_number, {"data": "admin:list", "message": message}); return
    if cmd == "/stats":
        process_admin_callback(bot_number, {"data": "admin:stats", "message": message}); return
    if cmd == "/revenue":
        process_admin_callback(bot_number, {"data": "admin:revenue", "message": message}); return
    if cmd == "/online":
        process_admin_callback(bot_number, {"data": "admin:online", "message": message}); return
    if cmd == "/logs":
        process_admin_callback(bot_number, {"data": "admin:logs", "message": message}); return
    if cmd == "/banned":
        process_admin_callback(bot_number, {"data": "admin:banned", "message": message}); return
    if cmd == "/db":
        process_admin_callback(bot_number, {"data": "admin:db", "message": message}); return
    if cmd == "/broadcast":
        process_admin_callback(bot_number, {"data": "admin:broadcast", "message": message}); return
    if cmd == "/remove_all":
        process_admin_callback(bot_number, {"data": "admin:remove_all", "message": message}); return

    if cmd == "/export":
        try:
            import csv, io as _io
            buf = _io.StringIO()
            w = csv.writer(buf)
            w.writerow(["user_id", "expiry_ts", "expiry_human", "lang", "banned", "last_seen", "notes"])
            for uid in sorted(ACTIVATED_USERS.keys()):
                exp = ACTIVATED_USERS.get(uid, 0)
                lang = USER_LANGS.get(uid, "en")
                banned = "yes" if uid in BANNED_USERS else "no"
                seen = LAST_SEEN.get(uid)
                seen_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(seen)) if seen else ""
                notes = " | ".join(n["text"] for n in USER_NOTES.get(uid, []))
                w.writerow([uid, int(exp),
                            time.strftime("%Y-%m-%d %H:%M", time.localtime(exp)) if exp else "",
                            lang, banned, seen_str, notes])
            content = buf.getvalue()
            tmp_path = "/tmp/export_users.csv"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            url = ADMIN_TELEGRAM_APIS[bot_number] + "/sendDocument"
            with open(tmp_path, "rb") as f:
                ADMIN_HTTP.post(url,
                    data={"chat_id": chat_id, "caption": f"📁 Export · {len(ACTIVATED_USERS)} users"},
                    files={"document": ("users.csv", f, "text/csv")},
                    timeout=(10, 60))
            log_admin(chat_id, "export")
        except Exception as e:
            admin_send_message(bot_number, chat_id, f"❌ Export failed: {e}", admin_main_keyboard())
        return

    if cmd == "/check" or cmd == "/role":
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, f"Usage: {cmd} USER_ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        exp = ACTIVATED_USERS.get(target)
        lang = USER_LANGS.get(target, "en")
        role = role_badge(target)
        ban_info = BANNED_USERS.get(target)
        seen = LAST_SEEN.get(target)
        if exp:
            remaining = exp - time.time()
            if remaining > 0:
                d = int(remaining // 86400); h = int((remaining % 86400) // 3600)
                status = f"✅ Active ({d}d {h}h)"
            else:
                status = "⌛ Expired"
            exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
        else:
            status = "❌ Not in DB"; exp_str = "—"
        ban_line = f"🚫 Banned — {ban_info.get('reason','—')}" if ban_info else "🟢 Not banned"
        seen_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(seen)) if seen else "—"
        notes = USER_NOTES.get(target, [])
        note_block = ""
        if notes:
            note_block = "\n\n📝 <b>NOTES</b>\n" + "\n".join(
                f"{i+1}. {n['text']}" for i, n in enumerate(notes[-5:]))
        msg = (f"👤 <b>USER INFO</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🆔 <code>{target}</code>\n"
               f"🏷 Role: <b>{role}</b>\n"
               f"🌐 Lang: {lang}\n"
               f"📅 Expiry: <code>{exp_str}</code>\n"
               f"📊 Status: {status}\n"
               f"{ban_line}\n"
               f"👀 Last seen: {seen_str}"
               f"{note_block}\n━━━━━━━━━━━━━━━━━━━━━━━")
        admin_send_message(bot_number, chat_id, msg, admin_main_keyboard()); return

    if cmd == "/add_user":
        if len(args) != 3:
            admin_send_message(bot_number, chat_id, "Usage: /add_user ID DAYS", admin_main_keyboard()); return
        try:
            target = int(args[1]); days = int(args[2])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid.", admin_main_keyboard()); return
        cur = ACTIVATED_USERS.get(target, 0)
        if cur < time.time(): cur = time.time()
        ACTIVATED_USERS[target] = cur + days * 86400
        save_activation_data()
        log_admin(chat_id, "add_user", f"{target} +{days}d")
        admin_send_message(bot_number, chat_id,
            f"✅ <code>{target}</code> + {days} days.", admin_main_keyboard()); return

    if cmd in ("/extend", "/reduce"):
        if len(args) != 3:
            admin_send_message(bot_number, chat_id, f"Usage: {cmd} ID DAYS", admin_main_keyboard()); return
        try:
            target = int(args[1]); days = int(args[2])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid.", admin_main_keyboard()); return
        cur = ACTIVATED_USERS.get(target, time.time())
        delta = days * 86400 if cmd == "/extend" else -days * 86400
        ACTIVATED_USERS[target] = max(cur + delta, 0)
        save_activation_data()
        log_admin(chat_id, cmd[1:], f"{target} {days}d")
        admin_send_message(bot_number, chat_id,
            f"✅ <code>{target}</code> adjusted by {days} days.", admin_main_keyboard()); return

    if cmd == "/deactivate":
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /deactivate ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        if target in ACTIVATED_USERS:
            del ACTIVATED_USERS[target]; save_activation_data()
            log_admin(chat_id, "deactivate", target)
            admin_send_message(bot_number, chat_id, f"🔒 <code>{target}</code> deactivated.",
                               admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ User not found.", admin_main_keyboard())
        return

    if cmd == "/ban":
        if len(args) < 2:
            admin_send_message(bot_number, chat_id, "Usage: /ban ID [reason]", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        if is_admin(target):
            admin_send_message(bot_number, chat_id, "❌ Cannot ban an admin.", admin_main_keyboard()); return
        reason = " ".join(args[2:]) or "—"
        BANNED_USERS[target] = {"reason": reason, "ts": int(time.time()), "by": chat_id}
        save_banned()
        log_admin(chat_id, "ban", f"{target} ({reason})")
        send_message(target, t(get_lang(target), "banned_msg"))
        admin_send_message(bot_number, chat_id,
            f"🚫 <code>{target}</code> banned. Reason: {reason}",
            admin_main_keyboard()); return

    if cmd == "/unban":
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /unban ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        if target in BANNED_USERS:
            del BANNED_USERS[target]; save_banned()
            log_admin(chat_id, "unban", target)
            admin_send_message(bot_number, chat_id, f"✅ <code>{target}</code> unbanned.",
                               admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ Not banned.", admin_main_keyboard())
        return

    if cmd == "/msg":
        if len(args) < 3:
            admin_send_message(bot_number, chat_id, "Usage: /msg ID TEXT", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        body = " ".join(args[2:])
        res = send_message(target, f"📩 <b>Message from admin</b>\n\n{body}")
        if res and res.get("ok"):
            log_admin(chat_id, "msg", target)
            admin_send_message(bot_number, chat_id, "✅ Sent.", admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ Failed (user may have blocked bot).",
                               admin_main_keyboard())
        return

    if cmd == "/note":
        if len(args) < 3:
            admin_send_message(bot_number, chat_id, "Usage: /note ID TEXT", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        body = " ".join(args[2:])
        USER_NOTES.setdefault(target, []).append({"text": body, "ts": int(time.time()), "by": chat_id})
        save_notes()
        log_admin(chat_id, "note", target)
        admin_send_message(bot_number, chat_id, "📝 Note added.", admin_main_keyboard()); return

    if cmd == "/notes":
        if len(args) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /notes ID", admin_main_keyboard()); return
        try:
            target = int(args[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard()); return
        notes = USER_NOTES.get(target, [])
        if not notes:
            admin_send_message(bot_number, chat_id, "📭 No notes.", admin_main_keyboard()); return
        lines = [f"📝 <b>NOTES — <code>{target}</code></b>\n━━━━━━━━━━━━━━━━━━━━━━━"]
        for i, n in enumerate(notes):
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(n["ts"]))
            lines.append(f"{i+1}. {n['text']}\n   <i>{ts} · by {n['by']}</i>")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard()); return

    if cmd == "/delnote":
        if len(args) != 3:
            admin_send_message(bot_number, chat_id, "Usage: /delnote ID N", admin_main_keyboard()); return
        try:
            target = int(args[1]); idx = int(args[2]) - 1
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid.", admin_main_keyboard()); return
        notes = USER_NOTES.get(target, [])
        if 0 <= idx < len(notes):
            notes.pop(idx); save_notes()
            log_admin(chat_id, "delnote", f"{target} #{idx+1}")
            admin_send_message(bot_number, chat_id, "🗑 Deleted.", admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ Note index out of range.", admin_main_keyboard())
        return

    admin_send_message(bot_number, chat_id,
        "❓ Unknown command. Use /help.", admin_main_keyboard())

# ---------- ADMIN UPDATE ROUTER ----------
def process_admin_update(bot_number, update):
    if "callback_query" in update:
        process_admin_callback(bot_number, update["callback_query"]); return
    if "message" not in update: return
    message = update["message"]
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None: return

    text_raw = message.get("text", "")
    text = text_raw.strip() if isinstance(text_raw, str) else ""

    if not is_admin(chat_id):
        if text in ("/start", "/help", "/whoami", "/id"):
            admin_send_message(bot_number, chat_id,
                f"🔐 <b>Admin Bot</b>\n\n"
                f"🆔 Your Chat ID: <code>{chat_id}</code>\n\n"
                f"Send <code>/login YOUR_ADMIN_PASSWORD</code>\n\n"
                f"💡 Owner: set OWNER_ID=<code>{chat_id}</code> in env to auto-login.")
            return

        if text.startswith("/login"):
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                admin_send_message(bot_number, chat_id, "Usage: <code>/login YOUR_PASSWORD</code>"); return
            supplied = parts[1].strip()
            if (supplied == CURRENT_PASSWORD) or (supplied in (ADMIN_BOT_TOKEN_1, USER_BOT_TOKEN)):
                DYNAMIC_ADMINS.add(chat_id); save_admins()
                log_admin(chat_id, "login")
                admin_send_message(bot_number, chat_id,
                    f"✅ <b>Login OK.</b>\n🏷 Role: <b>{role_badge(chat_id)}</b>",
                    admin_main_keyboard())
            else:
                admin_send_message(bot_number, chat_id, "❌ Incorrect password.")
            return

        if text and text == CURRENT_PASSWORD:
            DYNAMIC_ADMINS.add(chat_id); save_admins()
            log_admin(chat_id, "login (bare)")
            admin_send_message(bot_number, chat_id,
                f"✅ <b>Login OK.</b>\n🏷 Role: <b>{role_badge(chat_id)}</b>",
                admin_main_keyboard())
            return

        admin_send_message(bot_number, chat_id,
            f"⛔ Not authorized.\n🆔 Your ID: <code>{chat_id}</code>\n\n"
            f"Send <code>/login YOUR_PASSWORD</code>.")
        return

    if ADMIN_STATE.get(chat_id) == "awaiting_add_admin":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_admins_keyboard()); return
        try:
            new_admin = int(text)
            DYNAMIC_ADMINS.add(new_admin); save_admins()
            ADMIN_STATE.pop(chat_id, None)
            log_admin(chat_id, "add_admin", new_admin)
            admin_send_message(bot_number, chat_id,
                f"✅ <code>{new_admin}</code> is now Admin.", admin_admins_keyboard())
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_admins_keyboard())
        return

    if ADMIN_STATE.get(chat_id) == "awaiting_remove_admin":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_admins_keyboard()); return
        try:
            target = int(text)
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_admins_keyboard()); return
        if is_owner(target):
            admin_send_message(bot_number, chat_id, "❌ Cannot remove owner.", admin_admins_keyboard()); return
        if target in DYNAMIC_ADMINS:
            DYNAMIC_ADMINS.discard(target); save_admins()
            ADMIN_STATE.pop(chat_id, None)
            log_admin(chat_id, "remove_admin", target)
            admin_send_message(bot_number, chat_id,
                f"✅ <code>{target}</code> removed.", admin_admins_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ Not an admin.", admin_admins_keyboard())
        return

    st = ADMIN_STATE.get(chat_id)
    if isinstance(st, dict) and st.get("flow") == "awaiting_custom_days":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_main_keyboard()); return
        try:
            days = int(text)
            if days < 1 or days > 3650: raise ValueError
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Send a number between 1 and 3650.")
            return
        target = st["target"]; mode = st.get("mode", "set")
        new_expiry, _, _ = grant_plan(target, days, mode=mode)
        log_admin(chat_id, f"activate:custom:{mode}", f"{target} +{days}d")
        sent = notify_user_activated(target, f"Custom {days}d", days, new_expiry)
        ADMIN_STATE.pop(chat_id, None)
        expiry_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_expiry))
        admin_send_message(bot_number, chat_id,
            f"✅ <b>Activated (custom)</b>\n"
            f"👤 <code>{target}</code>\n"
            f"➕ +{days} days · mode <b>{mode}</b>\n"
            f"⏳ New expiry: <code>{expiry_str}</code>\n"
            f"📨 DM: {'✅' if sent else '❌'}",
            admin_main_keyboard())
        return

    if ADMIN_STATE.get(chat_id) == "awaiting_broadcast":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_main_keyboard()); return
        ADMIN_STATE.pop(chat_id, None)
        admin_send_message(bot_number, chat_id, "⏳ Broadcasting…")
        success = failed = 0
        for uid in list(ACTIVATED_USERS.keys()):
            if is_banned(uid): continue
            try:
                res = send_message(uid, f"📢 <b>ANNOUNCEMENT</b>\n\n{text}")
                success += 1 if (res and res.get("ok")) else 0
                failed  += 0 if (res and res.get("ok")) else 1
                time.sleep(0.05)
            except Exception:
                failed += 1
        log_admin(chat_id, "broadcast", f"ok={success} fail={failed}")
        admin_send_message(bot_number, chat_id,
            f"✅ Broadcast done.\nSent: {success} · Failed: {failed}",
            admin_main_keyboard()); return

    process_admin_command(bot_number, chat_id, text, message)

def admin_bot_loop(bot_number):
    print(f"🚀 Admin bot {bot_number} polling started → {ADMIN_TELEGRAM_APIS.get(bot_number)}")
    offset = None
    backoff = 1
    while True:
        try:
            result = admin_get_updates(bot_number, offset)
            if result and result.get("ok"):
                backoff = 1
                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    try:
                        process_admin_update(bot_number, update)
                    except Exception as ue:
                        print(f"admin update err: {ue}")
            elif result and result.get("conflict"):
                # 🔧 409 detected — sleep quietly, don't spam
                time.sleep(5)
            else:
                time.sleep(min(backoff, 10))
                backoff = min(backoff * 2, 30)
        except Exception as e:
            print(f"admin loop err: {e}")
            time.sleep(min(backoff, 10))
            backoff = min(backoff * 2, 30)

# ============================================================
# DELETE WEBHOOK (🔧 NEW — fixes stale webhook 409s)
# ============================================================
def clear_webhook(api_base, label):
    try:
        r = HTTP.get(api_base + "/deleteWebhook",
                     params={"drop_pending_updates": "true"},
                     timeout=(5, 10))
        j = r.json()
        if j.get("ok"):
            print(f"🧹 {label}: webhook cleared, pending updates dropped.")
        else:
            print(f"⚠️ {label}: deleteWebhook → {j}")
    except Exception as e:
        print(f"⚠️ {label}: deleteWebhook failed — {e}")

# ============================================================
# SELF-PING
# ============================================================
def self_ping_loop():
    if not SELF_URL or not SELF_URL.startswith("http"):
        print("ℹ️  SELF_URL not set — skipping.")
        return
    target = SELF_URL.rstrip("/") + "/health"
    print(f"🔁 Self-ping → {target} every {SELF_PING_INTERVAL}s")
    time.sleep(30)
    while True:
        try:
            r = HTTP.get(target, timeout=(5, 15))
            print(f"💓 {r.status_code} @ {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️  self-ping fail: {e}")
        time.sleep(SELF_PING_INTERVAL)

# ============================================================
# MAIN
# ============================================================
def main():
    load_activation_data()
    load_password()
    load_admins()
    load_banned()
    load_notes()
    load_log()
    load_lastseen()

    if not USER_BOT_TOKEN or USER_BOT_TOKEN == "YOUR_USER_BOT_TOKEN":
        print("ERROR: USER_BOT_TOKEN missing."); return

    # 🔧 NEW: clear webhooks before polling
    clear_webhook(USER_TELEGRAM_API, "USER bot")
    clear_webhook(ADMIN_TELEGRAM_APIS[1], "ADMIN bot")

    try:
        r = HTTP.get(USER_TELEGRAM_API + "/getMe", timeout=(5, 10))
        info = r.json()
        if not info.get("ok"):
            print("ERROR: Invalid USER token."); return
        print("✅ USER bot:", info["result"]["username"])
    except Exception as e:
        print("USER bot connect error:", e); return

    try:
        r = ADMIN_HTTP.get(ADMIN_TELEGRAM_APIS[1] + "/getMe", timeout=(5, 10))
        info = r.json()
        print(f"✅ ADMIN bot: {info['result']['username']}" if info.get("ok") else f"⚠️ {info}")
    except Exception as e:
        print("⚠️ ADMIN bot verify fail:", e)

    threading.Thread(target=admin_bot_loop, args=(1,), daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()

    print("=" * 60)
    print("Bot started · owner:", OWNER_ID or "(unset)")
    print("=" * 60)

    offset = None; backoff = 1
    while True:
        try:
            result = get_updates(offset)
            if result and result.get("ok"):
                backoff = 1
                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    try: process_update(update)
                    except Exception as ue: print("update err:", ue)
            elif result and result.get("conflict"):
                # 🔧 409 detected — sleep quietly, don't spam
                time.sleep(5)
            else:
                time.sleep(min(backoff, 10)); backoff = min(backoff * 2, 30)
        except KeyboardInterrupt:
            print("\nStopped."); break
        except Exception as e:
            print("main loop err:", e)
            time.sleep(min(backoff, 10)); backoff = min(backoff * 2, 30)

if __name__ == "__main__":
    main()
