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

IPN_CALLBACK_URL = os.getenv("IPN_CALLBACK_URL", "https://osint.onrender.com/nowpayments_webhook")

NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1"

# ==========================================
# ADMIN AUTH CONFIG
# ==========================================
# 🔐 Shared password — YOU and all other admins use the SAME password to /login
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "mahesh@321").strip()

# 👑 Owner — always admin, cannot be removed. Send /whoami to bot to learn your chat id.
OWNER_ID = os.getenv("OWNER_ID", "6326027750").strip()

# ==========================================
# 24/7 KEEP-ALIVE
# ==========================================
SELF_URL = os.getenv("SELF_URL", "https://osint.onrender.com")
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "600"))

# ==========================================
# ADMIN STORAGE
# ==========================================
ADMINS_FILE = os.getenv("ADMINS_FILE", "admins.json")
PASSWORD_FILE = os.getenv("PASSWORD_FILE", "admin_password.json")
DYNAMIC_ADMINS = set()
CURRENT_PASSWORD = ADMIN_PASSWORD  # runtime-changeable via /setpassword

def load_password():
    """Load persisted password (overrides env if present)."""
    global CURRENT_PASSWORD
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("password"):
                CURRENT_PASSWORD = str(data["password"])
                print("🔐 Loaded persisted admin password.")
    except FileNotFoundError:
        pass
    except Exception as e:
        print("Error loading password file:", e)

def save_password():
    try:
        with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
            json.dump({"password": CURRENT_PASSWORD}, f, indent=2)
        print("💾 Password saved.")
    except Exception as e:
        print("Could not save password:", e)

def load_admins():
    global DYNAMIC_ADMINS
    try:
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            DYNAMIC_ADMINS = set(int(x) for x in data)
            print(f"✅ Loaded {len(DYNAMIC_ADMINS)} dynamic admins.")
    except FileNotFoundError:
        DYNAMIC_ADMINS = set()
    except Exception as e:
        print("Error loading admins:", e)
        DYNAMIC_ADMINS = set()

    if OWNER_ID:
        try:
            DYNAMIC_ADMINS.add(int(OWNER_ID))
            print(f"👑 OWNER_ID {OWNER_ID} auto-added as admin.")
        except ValueError:
            print(f"⚠️ OWNER_ID is not numeric: {OWNER_ID}")

    save_admins()

def save_admins():
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(DYNAMIC_ADMINS)), f, indent=2)
    except Exception as e:
        print("Could not save admins:", e)

# ==========================================
# IMAGE CONFIGURATION
# ==========================================
WELCOME_IMG = os.getenv("WELCOME_IMG", r"images\welcome.png")
OSINT_IMG = os.getenv("OSINT_IMG", r"images\osint.png")
PAYMENT_IMG = os.getenv("PAYMENT_IMG", r"images\payment.png")

IMAGE_CACHE = {}

def cache_image(path):
    if not os.path.exists(path):
        print(f"⚠️ Warning: Image not found at {path}")
        return
    try:
        with Image.open(path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            IMAGE_CACHE[path] = buf.getvalue()
            size_kb = len(IMAGE_CACHE[path]) / 1024
            print(f"✅ Cached & compressed: {path} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"❌ Failed to compress image {path}: {e}")
        try:
            with open(path, "rb") as f:
                IMAGE_CACHE[path] = f.read()
            print(f"⚠️ Loaded raw image instead: {path}")
        except Exception as raw_e:
            print(f"❌ Failed to load raw image {path}: {raw_e}")

cache_image(WELCOME_IMG)
cache_image(OSINT_IMG)
cache_image(PAYMENT_IMG)

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
# API CONFIGURATION
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
ADMIN_TELEGRAM_APIS = {
    1: "https://api.telegram.org/bot" + ADMIN_BOT_TOKEN_1,
}

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
    try:
        with open(DB_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        raw_users = data.get("activated_users", {})
        ACTIVATED_USERS = {int(k): float(v) for k, v in raw_users.items()}
        raw_langs = data.get("user_langs", {})
        USER_LANGS = {int(k): str(v) for k, v in raw_langs.items()}
    except FileNotFoundError:
        ACTIVATED_USERS = {}
        USER_LANGS = {}
    except Exception as error:
        print("Could not load activation database:", error)

def save_activation_data():
    with db_lock:
        data = {
            "activated_users": ACTIVATED_USERS,
            "user_langs": USER_LANGS,
        }
        temp_file = DB_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
            os.replace(temp_file, DB_FILE)
        except Exception as error:
            print("Could not save activation database:", error)

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
        response = HTTP.post(url, data=data, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400 and "parse" in e.response.text.lower():
            print("HTML parse failed, retrying as plain text...")
            data.pop("parse_mode", None)
            try:
                response = HTTP.post(url, data=data, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
                response.raise_for_status()
                return response.json()
            except Exception as inner:
                print("Plain text retry failed:", inner)
                return None
        print("Telegram error:", e)
        return None
    except Exception as error:
        print("Telegram error:", error)
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
            print(f"Error reading local image {photo}: {e}")
    elif isinstance(photo, str):
        data["photo"] = photo
    else:
        files = {"photo": ("qr.png", photo, "image/png")}

    if files is None and isinstance(photo, str) and (photo.endswith(".png") or photo.endswith(".jpg") or photo.endswith(".jpeg")):
        print(f"⚠️ Cannot send image '{photo}'. Falling back to text message.")
        if caption:
            return send_message(chat_id, caption, keyboard, parse_mode)
        return None

    try:
        response = HTTP.post(url, data=data, files=files, timeout=(TELEGRAM_CONNECT_TIMEOUT, 60))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print("⚠️ Telegram sendPhoto timed out. Falling back to text.")
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Telegram sendPhoto HTTP Error: {e.response.status_code} - {e.response.text}")
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None
    except Exception as error:
        print("Telegram sendPhoto general error:", error)
        if caption:
            send_message(chat_id, caption, keyboard, parse_mode)
        return None

def edit_photo_caption(chat_id, message_id, caption, keyboard=None, parse_mode="HTML"):
    url = USER_TELEGRAM_API + "/editMessageCaption"
    data = {"chat_id": chat_id, "message_id": message_id, "caption": caption}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if keyboard is not None:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        HTTP.post(url, data=data, timeout=(5, 15))
    except Exception as e:
        print("editMessageCaption error:", e)

def get_updates(offset=None):
    url = USER_TELEGRAM_API + "/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    try:
        response = HTTP.get(url, params=params, timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT))
        response.raise_for_status()
        return response.json()
    except Exception as error:
        print("getUpdates error:", error)
        return None

def answer_callback(callback_id, text=None):
    url = USER_TELEGRAM_API + "/answerCallbackQuery"
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text[:200]
    try:
        HTTP.post(url, data=data, timeout=(5, 10))
    except Exception as e:
        print("answerCallbackQuery error:", e)

def delete_message(chat_id, message_id):
    url = USER_TELEGRAM_API + "/deleteMessage"
    try:
        HTTP.post(url, data={"chat_id": chat_id, "message_id": message_id}, timeout=(5, 10))
    except Exception as e:
        print("deleteMessage error:", e)

# ============================================================
# QR + HELPERS
# ============================================================
def generate_qr_bytes(data):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

def copy_address_keyboard(address):
    return {
        "inline_keyboard": [
            [{"text": "📋 Copy Address", "copy_text": {"text": address}}]
        ]
    }

def build_payment_uri(currency, address, amount=None):
    currency = (currency or "").lower()
    if currency == "btc":
        uri = f"bitcoin:{address}"
        if amount:
            uri += f"?amount={amount}"
        return uri
    if currency == "eth":
        return f"ethereum:{address}"
    if currency == "ltc":
        uri = f"litecoin:{address}"
        if amount:
            uri += f"?amount={amount}"
        return uri
    if currency == "trx":
        return f"tron:{address}"
    return address

def prettify_currency(raw):
    raw = (raw or "").upper()
    if raw == "USDTTRC20":
        return "USDT (TRC20)"
    if raw == "USDTERC20":
        return "USDT (ERC20)"
    return raw

# ============================================================
# CURRENCY LIST
# ============================================================
def fetch_all_currencies():
    now = time.time()
    if CURRENCY_CACHE["list"] and (now - CURRENCY_CACHE["ts"]) < CURRENCY_CACHE_TTL:
        return CURRENCY_CACHE["list"]

    merged = {}
    for code, name in FIAT_FALLBACK:
        merged[code] = {"code": code, "name": name}

    try:
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        r = HTTP.get(
            NOWPAYMENTS_API_URL + "/currencies",
            headers=headers,
            timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT)
        )
        if r.status_code == 200:
            data = r.json()
            for code in data.get("currencies", []):
                code_l = code.lower()
                if code_l not in merged:
                    merged[code_l] = {"code": code_l, "name": code_l.upper()}
    except Exception as e:
        print("fetch_all_currencies error:", e)

    lst = sorted(merged.values(), key=lambda c: c["code"])
    CURRENCY_CACHE["list"] = lst
    CURRENCY_CACHE["ts"] = now
    return lst

def find_currencies(query, limit=10):
    q = normalize_text(query)
    if not q:
        return []
    lst = fetch_all_currencies()
    exact, starts, contains = [], [], []
    for c in lst:
        code_l = c["code"].lower()
        name_l = c["name"].lower()
        if code_l == q or name_l == q:
            exact.append(c)
        elif code_l.startswith(q) or name_l.startswith(q):
            starts.append(c)
        elif q in code_l or q in name_l:
            contains.append(c)
    return (exact + starts + contains)[:limit]

# ============================================================
# NOWPAYMENTS MIN AMOUNT
# ============================================================
def get_min_amount(crypto_currency, fiat="usd"):
    try:
        params = {
            "currency_from": crypto_currency,
            "currency_to": fiat,
            "fiat_equivalent": fiat,
        }
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        response = HTTP.get(
            NOWPAYMENTS_API_URL + "/min-amount",
            params=params, headers=headers,
            timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT),
        )
        response.raise_for_status()
        data = response.json()
        return data.get("min_amount"), data.get("fiat_equivalent")
    except Exception as e:
        print(f"min-amount error for {crypto_currency}: {e}")
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
# KEYBOARDS
# ============================================================
def payment_inline_keyboard(lang="en"):
    return {
        "inline_keyboard": [
            [
                {"text": "1 Month - $13.00", "callback_data": "select_plan:plan_1"},
                {"text": "3 Months - $18.00", "callback_data": "select_plan:plan_2"}
            ],
            [
                {"text": "6 Months - $25.00", "callback_data": "select_plan:plan_3"},
                {"text": "1 Year - $35.00", "callback_data": "select_plan:plan_4"}
            ],
            [
                {"text": t(lang, "check_status_btn"), "callback_data": "user:check_status"},
                {"text": t(lang, "cancel_btn"), "callback_data": "user:cancel"}
            ],
            [
                {"text": t(lang, "lang_btn"), "callback_data": "user:lang"}
            ]
        ]
    }

def main_keyboard(lang="en"):
    buttons = list(API_CONFIG.keys())
    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i + 2])
    keyboard.append([t(lang, "deactivate_btn"), t(lang, "cancel_btn")])
    keyboard.append([t(lang, "lang_btn")])
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

def language_keyboard():
    items = list(LANGUAGES.items())
    rows = []
    for i in range(0, len(items), 2):
        row = []
        for code, name in items[i:i + 2]:
            row.append({"text": name, "callback_data": f"lang:{code}"})
        rows.append(row)
    return {"inline_keyboard": rows}

def currency_inline_keyboard(results):
    rows = []
    for c in results:
        label = f"{c['code'].upper()} — {c['name']}"
        rows.append([{"text": label, "callback_data": f"cur:{c['code']}"}])
    rows.append([{"text": "❌ Cancel", "callback_data": "cur:cancel"}])
    return {"inline_keyboard": rows}

def popular_currency_keyboard(plan_id, lang="en"):
    rows, row = [], []
    for code in POPULAR_CODES:
        row.append({"text": code.upper(), "callback_data": f"plan:{plan_id}:{code}"})
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        {"text": t(lang, "search_currency"), "callback_data": f"search:{plan_id}"},
        {"text": t(lang, "back"), "callback_data": "back:plans"},
    ])
    return {"inline_keyboard": rows}

# ============================================================
# ADMIN KEYBOARDS
# ============================================================
def admin_main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "👥 User List", "callback_data": "admin:list"}, {"text": "📊 Stats", "callback_data": "admin:stats"}],
            [{"text": "📁 View DB", "callback_data": "admin:db"}],
            [{"text": "👑 Admins", "callback_data": "admin:admins"}],
            [{"text": "📢 Broadcast", "callback_data": "admin:broadcast"}],
            [{"text": "🧹 Remove All", "callback_data": "admin:remove_all"}],
        ]
    }

def admin_admins_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "➕ Add Admin", "callback_data": "admin:add_admin"}],
            [{"text": "➖ Remove Admin", "callback_data": "admin:remove_admin"}],
            [{"text": "📋 List Admins", "callback_data": "admin:list_admins"}],
            [{"text": "🔙 Back to Panel", "callback_data": "admin:back"}],
        ]
    }

# ============================================================
# NOWPAYMENTS PAYMENT CREATION
# ============================================================
def create_nowpayments_payment(chat_id, plan_id, pay_currency, charge_usd=None):
    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": "unknown_plan"}

    if charge_usd is None:
        charge_usd = float(plan["price_usd"])

    order_id = f"tg_{chat_id}_{plan['days']}_{int(time.time())}"

    payload = {
        "price_amount": charge_usd,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": order_id,
        "order_description": f"Bot Activation - {plan['name']} - {chat_id}",
    }
    if IPN_CALLBACK_URL and IPN_CALLBACK_URL.startswith("http") and "your-app" not in IPN_CALLBACK_URL:
        payload["ipn_callback_url"] = IPN_CALLBACK_URL

    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}

    try:
        response = HTTP.post(
            NOWPAYMENTS_API_URL + "/payment",
            json=payload, headers=headers,
            timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT),
        )
        try:
            body = response.json()
        except Exception:
            return {"error": "api_error", "status": response.status_code,
                    "message": response.text[:500]}

        if response.status_code not in (200, 201):
            return {"error": "api_error", "status": response.status_code,
                    "message": body.get("message") or body.get("error") or str(body)}
        if not body.get("pay_address"):
            return {"error": "api_error", "status": response.status_code,
                    "message": body.get("message") or "No pay_address in response"}
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
        expected = hmac.new(
            NOWPAYMENTS_IPN_SECRET.encode("utf-8"),
            sorted_body.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, received_signature)
    except Exception as e:
        print("IPN Verification Error:", e)
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
                user_id = int(parts[1])
                days = int(parts[2])
                current = ACTIVATED_USERS.get(user_id, 0)
                if current < time.time():
                    current = time.time()
                new_expiry = current + (days * 86400)
                ACTIVATED_USERS[user_id] = new_expiry
                save_activation_data()
                lang = get_lang(user_id)
                expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(new_expiry))
                send_message(
                    user_id,
                    f"{t(lang, 'payment_confirmed')}\n\n"
                    f"{t(lang, 'activated_days', days=days)}\n"
                    f"{t(lang, 'expiry')}: <code>{expiry_str}</code>\n\n"
                    f"{t(lang, 'select_feature')}",
                    main_keyboard(lang),
                )
    except Exception as e:
        print("Error processing webhook:", e)

    return jsonify({"status": "ok"}), 200

# ============================================================
# HELPERS
# ============================================================
def is_active(chat_id):
    exp = ACTIVATED_USERS.get(chat_id)
    return bool(exp and exp > time.time())

def create_payment_and_send(chat_id, plan_id, pay_currency):
    lang = get_lang(chat_id)
    plan = PLANS.get(plan_id)
    if not plan:
        send_message(chat_id, "Unknown plan.", payment_inline_keyboard(lang))
        return

    send_message(chat_id, t(lang, "generating"))

    charge_usd = float(plan["price_usd"])
    mn, mf = get_min_amount_cached(pay_currency, "usd")
    if mf is not None and charge_usd < float(mf):
        charge_usd = round(float(mf) * 1.05, 2)

    payment = create_nowpayments_payment(chat_id, plan_id, pay_currency, charge_usd=charge_usd)

    if payment and payment.get("error"):
        err = payment.get("error")
        msg_text = payment.get("message", "")
        if err == "timeout":
            send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "payment_timeout"), keyboard=payment_inline_keyboard(lang))
        else:
            send_photo(
                chat_id, PAYMENT_IMG,
                caption=f"{t(lang, 'payment_api_error')}\n\n<code>{err}: {msg_text[:400]}</code>\n\n{t(lang, 'try_again')}",
                keyboard=payment_inline_keyboard(lang),
            )
        return

    if not payment or not payment.get("pay_address"):
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "try_again"), keyboard=payment_inline_keyboard(lang))
        return

    pay_address = payment["pay_address"]
    pay_amount = payment.get("pay_amount")
    pay_curr = prettify_currency(payment.get("pay_currency") or pay_currency)

    try:
        qr_data = build_payment_uri(
            pay_currency, pay_address,
            amount=pay_amount if pay_currency in ("btc", "ltc") else None,
        )
        qr_bytes = generate_qr_bytes(qr_data)
        send_photo(
            chat_id, qr_bytes,
            caption=(
                f"🪙 <b>{pay_curr} Payment Invoice</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📷 <b>Scan the QR</b> or copy the address below."
            ),
            keyboard=copy_address_keyboard(pay_address),
        )
    except Exception as e:
        print("QR error:", e)

    send_message(
        chat_id,
        t(lang, "send_amount", amount=pay_amount, currency=pay_curr)
        + f"\n<code>{pay_address}</code>",
        copy_address_keyboard(pay_address),
    )

# ============================================================
# CALLBACK HANDLER (USER BOT)
# ============================================================
def process_callback(cb):
    data = cb.get("data", "") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    msg_id = msg.get("message_id")
    cb_id = cb.get("id")
    if chat_id is None:
        return
    lang = get_lang(chat_id)

    if data.startswith("lang:"):
        code = data.split(":", 1)[1]
        if code in LANGUAGES:
            set_lang(chat_id, code)
            answer_callback(cb_id, t(code, "language_set"))
            if msg_id:
                delete_message(chat_id, msg_id)
            if is_active(chat_id):
                caption = t(code, "already_active") + "\n\n" + t(code, "select_feature")
                send_photo(chat_id, OSINT_IMG, caption=caption, keyboard=main_keyboard(code))
            else:
                caption = t(code, "welcome") + "\n\n" + t(code, "select_plan")
                send_photo(chat_id, PAYMENT_IMG, caption=caption, keyboard=payment_inline_keyboard(code))
        return

    if data == "back:plans":
        answer_callback(cb_id)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "select_plan"), keyboard=payment_inline_keyboard(lang))
        return

    if data.startswith("select_plan:"):
        plan_id = data.split(":", 1)[1]
        USER_STATE[chat_id] = {"flow": "select_currency", "plan_id": plan_id}
        answer_callback(cb_id)
        if msg_id:
            delete_message(chat_id, msg_id)
        caption_text = t(lang, "select_currency", plan=t(lang, plan_id), price=f"{PLANS[plan_id]['price_usd']:.2f}") + "\n\n" + t(lang, "popular")
        send_photo(chat_id, PAYMENT_IMG, caption=caption_text, keyboard=popular_currency_keyboard(plan_id, lang))
        return

    if data == "user:check_status":
        answer_callback(cb_id)
        if is_active(chat_id):
            expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ACTIVATED_USERS[chat_id]))
            send_message(
                chat_id,
                f"{t(lang, 'status_active')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{t(lang, 'expiry')}: <code>{expiry_str}</code>",
                main_keyboard(lang),
            )
        else:
            send_photo(chat_id, PAYMENT_IMG, caption=f"{t(lang, 'status_inactive')}\n\n{t(lang, 'buy_plan')}", keyboard=payment_inline_keyboard(lang))
        return

    if data == "user:cancel":
        answer_callback(cb_id)
        USER_STATE.pop(chat_id, None)
        if msg_id:
            delete_message(chat_id, msg_id)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "cancelled") + "\n\n" + t(lang, "select_plan"), keyboard=payment_inline_keyboard(lang))
        return

    if data == "user:lang":
        answer_callback(cb_id)
        send_message(chat_id, t(lang, "choose_language"), language_keyboard())
        return

    if data.startswith("search:"):
        plan_id = data.split(":", 1)[1]
        USER_STATE[chat_id] = {"flow": "search_currency", "plan_id": plan_id}
        answer_callback(cb_id)
        send_message(chat_id, t(lang, "send_currency_code"))
        return

    if data == "cur:cancel":
        answer_callback(cb_id)
        USER_STATE.pop(chat_id, None)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "cancelled"), keyboard=payment_inline_keyboard(lang))
        return

    if data.startswith("cur:"):
        code = data.split(":", 1)[1]
        state = USER_STATE.get(chat_id, {})
        plan_id = state.get("plan_id")
        if not plan_id:
            answer_callback(cb_id, "Please select a plan first.")
            return
        answer_callback(cb_id)
        create_payment_and_send(chat_id, plan_id, code)
        USER_STATE.pop(chat_id, None)
        return

    if data.startswith("plan:"):
        parts = data.split(":")
        if len(parts) != 3:
            answer_callback(cb_id)
            return
        _, plan_id, code = parts
        answer_callback(cb_id)
        create_payment_and_send(chat_id, plan_id, code)
        USER_STATE.pop(chat_id, None)
        return

# ============================================================
# USER BOT UPDATE HANDLER
# ============================================================
def process_update(update):
    if "callback_query" in update:
        process_callback(update["callback_query"])
        return

    if "message" not in update:
        return
    message = update["message"]
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return

    text = message.get("text", "")
    if not isinstance(text, str):
        return
    text = text.strip()
    lang = get_lang(chat_id)

    if text == "/start":
        USER_STATE.pop(chat_id, None)
        caption = (
            t(lang, "welcome")
            + "\n\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + t(lang, "choose_language")
        )
        send_photo(chat_id, WELCOME_IMG, caption=caption, keyboard=language_keyboard())
        return

    if text in ("/lang", "/language") or is_button(text, "lang_btn", lang):
        send_message(chat_id, t(lang, "choose_language"), language_keyboard())
        return

    if text == "/cancel" or is_button(text, "cancel_btn", lang):
        USER_STATE.pop(chat_id, None)
        if is_active(chat_id):
            send_message(chat_id, t(lang, "cancelled") + "\n\n" + t(lang, "select_feature"), main_keyboard(lang))
        else:
            send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "cancelled") + "\n\n" + t(lang, "select_plan"), keyboard=payment_inline_keyboard(lang))
        return

    if is_button(text, "check_status_btn", lang):
        if is_active(chat_id):
            expiry_str = time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(ACTIVATED_USERS[chat_id]))
            send_message(
                chat_id,
                f"{t(lang, 'status_active')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{t(lang, 'expiry')}: <code>{expiry_str}</code>",
                main_keyboard(lang),
            )
        else:
            send_photo(chat_id, PAYMENT_IMG, caption=f"{t(lang, 'status_inactive')}\n\n{t(lang, 'buy_plan')}", keyboard=payment_inline_keyboard(lang))
        return

    if is_button(text, "deactivate_btn", lang):
        if chat_id in ACTIVATED_USERS:
            del ACTIVATED_USERS[chat_id]
            save_activation_data()
        USER_STATE.pop(chat_id, None)
        send_photo(chat_id, PAYMENT_IMG, caption=t(lang, "deactivated_msg"), keyboard=payment_inline_keyboard(lang))
        return

    state = USER_STATE.get(chat_id, {})

    if state.get("flow") == "search_currency":
        results = find_currencies(text, limit=12)
        if not results:
            send_message(chat_id, t(lang, "no_match"))
            return
        send_message(chat_id, t(lang, "found_currencies", n=len(results)),
                     currency_inline_keyboard(results))
        return

    if state.get("flow") == "api_query":
        api_name = state.get("api_name")
        if not api_name:
            USER_STATE.pop(chat_id, None)
            send_message(chat_id, t(lang, "select_option"), main_keyboard(lang))
            return
        query = text.strip()
        if not query:
            send_message(chat_id, "❌ Query cannot be empty.")
            return
        config = API_CONFIG.get(api_name)
        send_message(chat_id, t(lang, "searching"))
        try:
            response = HTTP.get(
                config["url"] + quote_plus(query),
                timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT),
            )
            response.raise_for_status()
            api_result = response.json()
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
            print("API Error:", e)
            send_message(chat_id, t(lang, "no_result"), main_keyboard(lang))
        USER_STATE.pop(chat_id, None)
        return

    if not is_active(chat_id):
        send_photo(chat_id, PAYMENT_IMG, caption=f"{t(lang, 'locked')}\n\n{t(lang, 'buy_plan')}", keyboard=payment_inline_keyboard(lang))
        return

    api_name = next((name for name in API_CONFIG if name.strip() == text.strip()), None)
    if api_name is not None:
        config = API_CONFIG[api_name]
        USER_STATE[chat_id] = {"flow": "api_query", "api_name": api_name}
        send_message(chat_id, config["prompt"] + "\n\n" + t(lang, "send_cancel"),
                     main_keyboard(lang))
        return

    send_message(chat_id, t(lang, "select_option"), main_keyboard(lang))

# ============================================================
# ADMIN BOT
# ============================================================
def admin_send_message(bot_number, chat_id, text, keyboard=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api:
        return None
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        r = ADMIN_HTTP.post(api + "/sendMessage", data=data, timeout=(5, 35))
        return r.json()
    except Exception as e:
        print(f"Admin bot {bot_number} sendMessage error:", e)
        return None

def admin_get_updates(bot_number, offset=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api:
        print(f"❌ Admin bot {bot_number}: API URL missing.")
        return None
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        r = ADMIN_HTTP.get(api + "/getUpdates", params=params, timeout=(5, 35))
        if r.status_code != 200:
            print(f"⚠️ Admin bot {bot_number} getUpdates HTTP {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"⚠️ Admin bot {bot_number} getUpdates exception: {e}")
        return None

def admin_answer_callback(bot_number, callback_id, text=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api or not callback_id or callback_id == "dummy":
        return
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text[:200]
    try:
        ADMIN_HTTP.post(api + "/answerCallbackQuery", data=data, timeout=(5, 10))
    except Exception as e:
        print(f"Admin answerCallback error: {e}")

def process_admin_callback(bot_number, cb):
    data = cb.get("data", "") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    cb_id = cb.get("id")
    if chat_id is None:
        return

    if chat_id not in DYNAMIC_ADMINS:
        admin_answer_callback(bot_number, cb_id, "⛔ Unauthorized")
        return

    if data == "admin:back":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(
            bot_number, chat_id,
            "🛠 <b>A D M I N   P A N E L</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 Choose an action below:",
            admin_main_keyboard()
        )
        return

    if data == "admin:list":
        admin_answer_callback(bot_number, cb_id)
        if not ACTIVATED_USERS:
            admin_send_message(bot_number, chat_id, "📭 No active users.", admin_main_keyboard())
            return
        lines = ["👥 <b>ACTIVE USERS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for uid, expiry in sorted(ACTIVATED_USERS.items(), key=lambda x: x[1], reverse=True):
            exp_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(expiry))
            status = "✅" if expiry > time.time() else "❌"
            lines.append(f"{status} <code>{uid}</code> — {exp_str}")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_main_keyboard())
        return

    if data == "admin:stats":
        admin_answer_callback(bot_number, cb_id)
        total = len(ACTIVATED_USERS)
        now = time.time()
        active = sum(1 for exp in ACTIVATED_USERS.values() if exp > now)
        expired = total - active
        stats_text = (
            f"📊 <b>BOT STATISTICS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total Users: <b>{total}</b>\n"
            f"✅ Active Users: <b>{active}</b>\n"
            f"❌ Expired Users: <b>{expired}</b>\n"
            f"👑 Total Admins: <b>{len(DYNAMIC_ADMINS)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )
        admin_send_message(bot_number, chat_id, stats_text, admin_main_keyboard())
        return

    if data == "admin:db":
        admin_answer_callback(bot_number, cb_id)
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 3500:
                content = content[:3500] + "\n... [TRUNCATED]"
            content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            admin_send_message(bot_number, chat_id, f"📁 <b>RAW DATABASE</b>\n<pre>{content}</pre>", admin_main_keyboard())
        except Exception as e:
            admin_send_message(bot_number, chat_id, f"❌ Error reading DB: {e}", admin_main_keyboard())
        return

    if data == "admin:admins":
        admin_answer_callback(bot_number, cb_id)
        admin_send_message(
            bot_number, chat_id,
            "👑 <b>A D M I N   M A N A G E M E N T</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            admin_admins_keyboard()
        )
        return

    if data == "admin:list_admins":
        admin_answer_callback(bot_number, cb_id)
        lines = ["👑 <b>ADMIN LIST</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for admin_id in sorted(DYNAMIC_ADMINS):
            tag = " (owner)" if OWNER_ID and str(admin_id) == OWNER_ID else ""
            lines.append(f"• <code>{admin_id}</code>{tag}")
        admin_send_message(bot_number, chat_id, "\n".join(lines), admin_admins_keyboard())
        return

    if data == "admin:add_admin":
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_add_admin"
        admin_send_message(bot_number, chat_id, "➕ <b>ADD ADMIN</b>\n\nSend me the Telegram User ID you want to promote to Admin.\n\nSend /cancel to abort.", admin_admins_keyboard())
        return

    if data == "admin:remove_admin":
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_remove_admin"
        admin_send_message(bot_number, chat_id, "➖ <b>REMOVE ADMIN</b>\n\nSend me the Telegram User ID you want to demote.\n\nSend /cancel to abort.", admin_admins_keyboard())
        return

    if data == "admin:broadcast":
        admin_answer_callback(bot_number, cb_id)
        ADMIN_STATE[chat_id] = "awaiting_broadcast"
        admin_send_message(bot_number, chat_id, "📢 <b>BROADCAST MODE</b>\n\nSend me the message you want to send to all users. (Send /cancel to abort)", admin_main_keyboard())
        return

    if data == "admin:remove_all":
        admin_answer_callback(bot_number, cb_id)
        ACTIVATED_USERS.clear()
        save_activation_data()
        admin_send_message(bot_number, chat_id, "🧹 All users have been removed from the database.", admin_main_keyboard())
        return

def is_owner(chat_id):
    return bool(OWNER_ID) and str(chat_id) == OWNER_ID

def process_admin_command(bot_number, chat_id, text, message):
    if text in ("/start", "/help"):
        admin_send_message(bot_number, chat_id,
            "🛠 <b>A D M I N   P A N E L</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Use the buttons below to manage the bot.\n\n"
            "<b>Available commands:</b>\n"
            "/add_user USER_ID DAYS\n"
            "/check USER_ID\n"
            "/list\n"
            "/stats\n"
            "/db\n"
            "/broadcast\n"
            "/deactivate USER_ID\n"
            "/remove_all\n"
            "/whoami\n"
            "/logout\n"
            "/setpassword NEW_PASSWORD  (owner only)",
            admin_main_keyboard()
        )
        return

    if text == "/whoami":
        admin_send_message(bot_number, chat_id,
            f"🆔 Your Chat ID: <code>{chat_id}</code>\n"
            f"👑 Admin: <b>{'Yes' if chat_id in DYNAMIC_ADMINS else 'No'}</b>\n"
            f"🧑‍💼 Owner: <b>{'Yes' if is_owner(chat_id) else 'No'}</b>",
            admin_main_keyboard())
        return

    if text == "/logout":
        if is_owner(chat_id):
            admin_send_message(bot_number, chat_id,
                "❌ Owner cannot logout (remove OWNER_ID env var to disable owner mode).",
                admin_main_keyboard())
            return
        DYNAMIC_ADMINS.discard(chat_id)
        save_admins()
        admin_send_message(bot_number, chat_id,
            "👋 You have been logged out. Send /login &lt;password&gt; to log back in.")
        return

    if text.startswith("/setpassword"):
        if not is_owner(chat_id):
            admin_send_message(bot_number, chat_id, "⛔ Only the OWNER can change the password.", admin_main_keyboard())
            return
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            admin_send_message(bot_number, chat_id, "Usage: <code>/setpassword NEW_PASSWORD</code>", admin_main_keyboard())
            return
        global CURRENT_PASSWORD
        CURRENT_PASSWORD = parts[1].strip()
        save_password()
        admin_send_message(bot_number, chat_id,
            "✅ <b>Admin password updated.</b>\n\n"
            "All admins must now use the new password on next /login.",
            admin_main_keyboard())
        return

    if text == "/list":
        process_admin_callback(bot_number, {"data": "admin:list", "message": message})
        return

    if text == "/stats":
        process_admin_callback(bot_number, {"data": "admin:stats", "message": message})
        return

    if text == "/db":
        process_admin_callback(bot_number, {"data": "admin:db", "message": message})
        return

    if text == "/broadcast":
        process_admin_callback(bot_number, {"data": "admin:broadcast", "message": message})
        return

    if text == "/remove_all":
        process_admin_callback(bot_number, {"data": "admin:remove_all", "message": message})
        return

    if text.startswith("/check"):
        parts = text.split()
        if len(parts) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /check USER_ID", admin_main_keyboard())
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid User ID.", admin_main_keyboard())
            return
        if target_id in ACTIVATED_USERS:
            expiry = ACTIVATED_USERS[target_id]
            lang = USER_LANGS.get(target_id, "en")
            remaining = expiry - time.time()
            if remaining > 0:
                days_left = int(remaining // 86400)
                hours_left = int((remaining % 86400) // 3600)
                status = f"✅ Active ({days_left}d {hours_left}h remaining)"
            else:
                status = "❌ Expired"
            exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry))
            msg = (
                f"👤 <b>USER INFO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 ID: <code>{target_id}</code>\n"
                f"🌐 Lang: {lang}\n"
                f"📅 Expiry: <code>{exp_str}</code>\n"
                f"📊 Status: {status}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━"
            )
            admin_send_message(bot_number, chat_id, msg, admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, f"❌ User <code>{target_id}</code> not found in database.", admin_main_keyboard())
        return

    if text.startswith("/add_user"):
        parts = text.split()
        if len(parts) != 3:
            admin_send_message(bot_number, chat_id, "Usage: /add_user USER_ID DAYS", admin_main_keyboard())
            return
        try:
            target_id = int(parts[1]); days = int(parts[2])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid format.", admin_main_keyboard())
            return
        current = ACTIVATED_USERS.get(target_id, 0)
        if current < time.time():
            current = time.time()
        ACTIVATED_USERS[target_id] = current + (days * 86400)
        save_activation_data()
        admin_send_message(bot_number, chat_id, f"✅ User <code>{target_id}</code> activated for {days} days.", admin_main_keyboard())
        return

    if text.startswith("/deactivate"):
        parts = text.split()
        if len(parts) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /deactivate USER_ID", admin_main_keyboard())
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.", admin_main_keyboard())
            return
        if target_id in ACTIVATED_USERS:
            del ACTIVATED_USERS[target_id]
            save_activation_data()
            admin_send_message(bot_number, chat_id, f"🔒 User <code>{target_id}</code> deactivated.", admin_main_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ User not found.", admin_main_keyboard())
        return

    admin_send_message(bot_number, chat_id, "❓ Unknown command. Use /help to see available commands.", admin_main_keyboard())

def process_admin_update(bot_number, update):
    if "callback_query" in update:
        process_admin_callback(bot_number, update["callback_query"])
        return

    if "message" not in update:
        return
    message = update["message"]
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return

    text_raw = message.get("text", "")
    text = text_raw.strip() if isinstance(text_raw, str) else ""

    # ================= LOGIN (shared password) =================
    if chat_id not in DYNAMIC_ADMINS:
        if text in ("/start", "/help", "/whoami", "/id"):
            admin_send_message(
                bot_number, chat_id,
                f"🔐 <b>Admin Bot</b>\n\n"
                f"🆔 Your Chat ID: <code>{chat_id}</code>\n\n"
                f"To log in, send:\n"
                f"<code>/login YOUR_ADMIN_PASSWORD</code>\n\n"
                f"💡 Owner: set OWNER_ID=<code>{chat_id}</code> in env to auto-login."
            )
            return

        if text.startswith("/login"):
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                admin_send_message(bot_number, chat_id, "Usage: <code>/login YOUR_PASSWORD</code>")
                return
            supplied = parts[1].strip()

            # Accept: shared password OR either bot token (backup)
            if (supplied == CURRENT_PASSWORD) or (supplied in (ADMIN_BOT_TOKEN_1, USER_BOT_TOKEN)):
                DYNAMIC_ADMINS.add(chat_id)
                save_admins()
                admin_send_message(bot_number, chat_id,
                    "✅ <b>Login successful!</b>\nYou are now an Admin.",
                    admin_main_keyboard())
            else:
                admin_send_message(bot_number, chat_id, "❌ Incorrect password.")
            return

        # Bare-message login (only the shared password alone)
        if text == CURRENT_PASSWORD and text:
            DYNAMIC_ADMINS.add(chat_id)
            save_admins()
            admin_send_message(bot_number, chat_id,
                "✅ <b>Login successful!</b>\nYou are now an Admin.",
                admin_main_keyboard())
            return

        admin_send_message(bot_number, chat_id,
            f"⛔ You are not authorized.\n\n"
            f"🆔 Your Chat ID: <code>{chat_id}</code>\n\n"
            f"Send <code>/login YOUR_PASSWORD</code> to authenticate.")
        return

    # ============ ADMIN MANAGEMENT STATES ============
    if ADMIN_STATE.get(chat_id) == "awaiting_add_admin":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_admins_keyboard())
            return
        try:
            new_admin = int(text)
            DYNAMIC_ADMINS.add(new_admin)
            save_admins()
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, f"✅ User <code>{new_admin}</code> is now an Admin!", admin_admins_keyboard())
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID. Please send a numeric Telegram User ID.", admin_admins_keyboard())
        return

    if ADMIN_STATE.get(chat_id) == "awaiting_remove_admin":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Cancelled.", admin_admins_keyboard())
            return
        try:
            target = int(text)
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID. Please send a numeric Telegram User ID.", admin_admins_keyboard())
            return
        if is_owner(target):
            admin_send_message(bot_number, chat_id, "❌ Cannot remove the OWNER.", admin_admins_keyboard())
            return
        if target in DYNAMIC_ADMINS:
            DYNAMIC_ADMINS.discard(target)
            save_admins()
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, f"✅ User <code>{target}</code> has been removed from Admins.", admin_admins_keyboard())
        else:
            admin_send_message(bot_number, chat_id, "❌ User is not an Admin.", admin_admins_keyboard())
        return

    if ADMIN_STATE.get(chat_id) == "awaiting_broadcast":
        if text == "/cancel":
            ADMIN_STATE.pop(chat_id, None)
            admin_send_message(bot_number, chat_id, "❌ Broadcast cancelled.", admin_main_keyboard())
            return
        ADMIN_STATE.pop(chat_id, None)
        admin_send_message(bot_number, chat_id, "⏳ Broadcasting... Please wait.")
        success = failed = 0
        for user_id in list(ACTIVATED_USERS.keys()):
            try:
                res = send_message(user_id, f"📢 <b>ANNOUNCEMENT</b>\n\n{text}")
                if res and res.get("ok"):
                    success += 1
                else:
                    failed += 1
                time.sleep(0.05)
            except Exception:
                failed += 1
        admin_send_message(bot_number, chat_id, f"✅ Broadcast complete!\nSent: {success}\nFailed: {failed}", admin_main_keyboard())
        return

    # ============ COMMANDS ============
    process_admin_command(bot_number, chat_id, text, message)

def admin_bot_loop(bot_number):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    print(f"🚀 Admin bot {bot_number} polling started → {api}")
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
                        print(f"Admin update handler error: {ue}")
            else:
                time.sleep(min(backoff, 10))
                backoff = min(backoff * 2, 30)
        except Exception as e:
            print(f"Admin bot {bot_number} loop error:", e)
            time.sleep(min(backoff, 10))
            backoff = min(backoff * 2, 30)

# ============================================================
# SELF-PING
# ============================================================
def self_ping_loop():
    if not SELF_URL or not SELF_URL.startswith("http"):
        print("ℹ️  SELF_URL not set — skipping self-ping loop.")
        return
    target = SELF_URL.rstrip("/") + "/health"
    print(f"🔁 Self-ping loop started → {target} every {SELF_PING_INTERVAL}s")
    time.sleep(30)
    while True:
        try:
            r = HTTP.get(target, timeout=(5, 15))
            print(f"💓 self-ping {r.status_code} @ {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️  self-ping failed: {e}")
        time.sleep(SELF_PING_INTERVAL)

# ============================================================
# MAIN
# ============================================================
def main():
    load_activation_data()
    load_password()
    load_admins()

    if not USER_BOT_TOKEN or USER_BOT_TOKEN == "YOUR_USER_BOT_TOKEN":
        print("ERROR: Set USER_BOT_TOKEN environment variable.")
        return

    try:
        r = HTTP.get(USER_TELEGRAM_API + "/getMe", timeout=(5, 10))
        info = r.json()
        if not info.get("ok"):
            print("ERROR: Invalid USER bot token.")
            return
        print("✅ Connected to USER bot:", info["result"]["username"])
    except Exception as e:
        print("Could not connect to Telegram (user bot):", e)
        return

    try:
        r = ADMIN_HTTP.get(ADMIN_TELEGRAM_APIS[1] + "/getMe", timeout=(5, 10))
        info = r.json()
        if info.get("ok"):
            print("✅ Connected to ADMIN bot:", info["result"]["username"])
        else:
            print("⚠️ ADMIN bot token invalid:", info)
    except Exception as e:
        print("⚠️ Could not verify ADMIN bot:", e)

    if not IPN_CALLBACK_URL:
        print("=" * 60)
        print("⚠️  IPN_CALLBACK_URL not set — users won't auto-activate.")
        print("=" * 60)

    if not OWNER_ID:
        print("=" * 60)
        print("⚠️  OWNER_ID not set. Send /whoami to the admin bot to learn your ID,")
        print("    then set OWNER_ID=<id> and ADMIN_PASSWORD=<secret> in env.")
        print("=" * 60)

    threading.Thread(target=admin_bot_loop, args=(1,), daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()

    print("=" * 60)
    print("Telegram Bot Started (language-first flow, all currencies)")
    print("=" * 60)

    offset = None
    backoff = 1
    while True:
        try:
            result = get_updates(offset)
            if result and result.get("ok"):
                backoff = 1
                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    try:
                        process_update(update)
                    except Exception as ue:
                        print("Update handler error:", ue)
            else:
                time.sleep(min(backoff, 10))
                backoff = min(backoff * 2, 30)
        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print("Main loop error:", e)
            time.sleep(min(backoff, 10))
            backoff = min(backoff * 2, 30)

if __name__ == "__main__":
    main()
