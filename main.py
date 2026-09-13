import os
import json
import time
import hmac
import hashlib
import threading
import requests
import qrcode
from io import BytesIO
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
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_server, daemon=True).start()

# ==========================================
# CONFIGURATION
# ==========================================
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN", "8771414496:AAEZYXZa3TXHPcJoEYxHmI105c60F8VSYxo")
ADMIN_BOT_TOKEN_1 = os.getenv("ADMIN_BOT_TOKEN_1", "8766550714:AAE2rUWxhf9jSIPCMIddkiNd7yz-3wKDxvM")
ADMIN_USER_IDS_1 = {8613123407}

NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "ZQRJG4Z-5PQ48ZM-M5C8PVH-V01CXT0")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "Gsx0umqAvAcrfOGfEOguqrL9UjhmoHoH")

IPN_CALLBACK_URL = os.getenv("IPN_CALLBACK_URL", "https://osint.onrender.com/nowpayments_webhook")

NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1"

PLANS = {
    "plan_1": {"name": "1 Month",  "price_usd": 13.00, "days": 30},
    "plan_2": {"name": "3 Months", "price_usd": 18.00, "days": 90},
    "plan_3": {"name": "6 Months", "price_usd": 25.00, "days": 180},
    "plan_4": {"name": "1 Year",   "price_usd": 35.00, "days": 365},
}

DB_FILE = "activation_data.json"
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
    "en": "🇬🇧 English",
    "hi": "🇮🇳 हिन्दी",
    "bn": "🇧🇩 বাংলা",
    "ur": "🇵🇰 اردو",
    "ar": "🇸🇦 العربية",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "de": "🇩🇪 Deutsch",
    "pt": "🇧🇷 Português",
    "ru": "🇷🇺 Русский",
    "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "id": "🇮🇩 Indonesia",
    "tr": "🇹🇷 Türkçe",
    "fa": "🇮🇷 فارسی",
    "it": "🇮🇹 Italiano",
    "vi": "🇻🇳 Tiếng Việt",
    "th": "🇹🇭 ไทย",
    "ta": "🇮🇳 தமிழ்",
    "te": "🇮🇳 తెలుగు",
    "mr": "🇮🇳 मराठी",
    "gu": "🇮🇳 ગુજરાતી",
    "pa": "🇮🇳 ਪੰਜਾਬੀ",
    "ml": "🇮🇳 മലയാളം",
    "nl": "🇳🇱 Nederlands",
    "pl": "🇵🇱 Polski",
    "uk": "🇺🇦 Українська",
    "ro": "🇷🇴 Română",
    "sw": "🇰🇪 Kiswahili",
    "ms": "🇲🇾 Bahasa Melayu",
    "fil": "🇵🇭 Filipino",
}

LANG_BY_NAME = {v: k for k, v in LANGUAGES.items()}

TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome!</b>",
        "locked": "🔒 This bot is locked.",
        "buy_plan": "Please purchase a plan to activate.",
        "select_feature": "Select a feature:",
        "already_active": "✅ You are already activated.",
        "status_active": "✅ Status: <b>Active</b>",
        "status_inactive": "❌ Status: <b>Inactive / Expired</b>",
        "expiry": "Expiry",
        "cancelled": "❌ Cancelled.",
        "deactivated": "🔒 Bot deactivated.",
        "deactivated_msg": "🔒 Bot deactivated. Purchase a plan to reactivate.",
        "select_plan": "Select a plan:",
        "checking": "🔎 Checking available currencies...",
        "no_crypto": "❌ No currencies available right now.",
        "generating": "⏳ Generating payment invoice...",
        "payment_confirmed": "✅ <b>Payment Confirmed!</b>",
        "activated_days": "Your bot has been activated for <b>{days} days</b>.",
        "payment_api_error": "❌ <b>Payment API error</b>",
        "try_again": "Please try again or contact admin.",
        "select_currency": "Choose a payment currency for <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Please choose your language:</b>",
        "language_set": "✅ Language updated.",
        "send_cancel": "Send /cancel to cancel.",
        "searching": "⏳ Searching...",
        "no_result": "❌ No result or API error.",
        "select_option": "❓ Please select an option from the menu.",
        "search_currency": "🔍 Search",
        "all_currencies": "📋 All Currencies",
        "back": "🔙 Back",
        "cancel_btn": "❌ Cancel",
        "deactivate_btn": "🔒 Deactivate",
        "check_status_btn": "🔄 Check Status",
        "lang_btn": "🌐 Language",
        "not_available": "❌ That currency is not available.",
        "payment_timeout": "⏱ Payment API timed out. Please try again.",
        "send_currency_code": "🔍 Type a currency code or name (e.g. BTC, ETH, USDT, Euro, INR):",
        "found_currencies": "Found {n} matching currencies:",
        "no_match": "❌ No matching currency found. Try another code.",
        "send_amount": "💰 Send <b>{amount} {currency}</b> to:",
        "popular": "⭐ Popular currencies:",
        "plan_1": "1 Month",
        "plan_2": "3 Months",
        "plan_3": "6 Months",
        "plan_4": "1 Year",
        "bumped_note": "ℹ️ Amount adjusted to meet the network minimum.",
        "currency_unsupported": "⚠️ This currency may not be supported for payments. Please try another.",
    },
    "hi": {
        "welcome": "👋 <b>स्वागत है!</b>",
        "locked": "🔒 यह बॉट लॉक है।",
        "buy_plan": "सक्रिय करने के लिए कृपया एक प्लान खरीदें।",
        "select_feature": "एक सुविधा चुनें:",
        "already_active": "✅ आप पहले से सक्रिय हैं।",
        "status_active": "✅ स्थिति: <b>सक्रिय</b>",
        "status_inactive": "❌ स्थिति: <b>निष्क्रिय / समाप्त</b>",
        "expiry": "समाप्ति",
        "cancelled": "❌ रद्द किया गया।",
        "deactivated": "🔒 बॉट निष्क्रिय कर दिया गया।",
        "deactivated_msg": "🔒 बॉट निष्क्रिय। दोबारा सक्रिय करने के लिए प्लान खरीदें।",
        "select_plan": "एक प्लान चुनें:",
        "checking": "🔎 उपलब्ध मुद्राएँ जाँच रहे हैं...",
        "no_crypto": "❌ अभी कोई मुद्रा उपलब्ध नहीं है।",
        "generating": "⏳ भुगतान इनवॉइस बना रहे हैं...",
        "payment_confirmed": "✅ <b>भुगतान की पुष्टि हो गई!</b>",
        "activated_days": "आपका बॉट <b>{days} दिनों</b> के लिए सक्रिय कर दिया गया है।",
        "payment_api_error": "❌ <b>भुगतान API त्रुटि</b>",
        "try_again": "कृपया पुनः प्रयास करें या एडमिन से संपर्क करें।",
        "select_currency": "<b>{plan}</b> (${price}) के लिए भुगतान मुद्रा चुनें:",
        "choose_language": "🌐 <b>कृपया अपनी भाषा चुनें:</b>",
        "language_set": "✅ भाषा अपडेट हो गई।",
        "send_cancel": "रद्द करने के लिए /cancel भेजें।",
        "searching": "⏳ खोज रहे हैं...",
        "no_result": "❌ कोई परिणाम नहीं या API त्रुटि।",
        "select_option": "❓ कृपया मेनू से एक विकल्प चुनें।",
        "search_currency": "🔍 खोजें",
        "all_currencies": "📋 सभी मुद्राएँ",
        "back": "🔙 वापस",
        "cancel_btn": "❌ रद्द करें",
        "deactivate_btn": "🔒 निष्क्रिय करें",
        "check_status_btn": "🔄 स्थिति देखें",
        "lang_btn": "🌐 भाषा",
        "not_available": "❌ वह मुद्रा उपलब्ध नहीं है।",
        "payment_timeout": "⏱ भुगतान API का समय समाप्त। पुनः प्रयास करें।",
        "send_currency_code": "🔍 मुद्रा कोड या नाम लिखें (जैसे BTC, ETH, USDT, Euro, INR):",
        "found_currencies": "{n} मिलती-जुलती मुद्राएँ मिलीं:",
        "no_match": "❌ कोई मेल खाती मुद्रा नहीं मिली।",
        "send_amount": "💰 <b>{amount} {currency}</b> भेजें:",
        "popular": "⭐ लोकप्रिय मुद्राएँ:",
        "plan_1": "1 महीना", "plan_2": "3 महीने", "plan_3": "6 महीने", "plan_4": "1 वर्ष",
        "bumped_note": "ℹ️ नेटवर्क न्यूनतम के अनुसार राशि समायोजित की गई।",
        "currency_unsupported": "⚠️ यह मुद्रा भुगतान के लिए समर्थित नहीं हो सकती। कृपया दूसरी चुनें।",
    },
    "bn": {
        "welcome": "👋 <b>স্বাগতম!</b>",
        "locked": "🔒 এই বটটি লক করা আছে।",
        "buy_plan": "সক্রিয় করতে অনুগ্রহ করে একটি প্ল্যান কিনুন।",
        "select_feature": "একটি বৈশিষ্ট্য নির্বাচন করুন:",
        "already_active": "✅ আপনি ইতিমধ্যে সক্রিয় আছেন।",
        "status_active": "✅ অবস্থা: <b>সক্রিয়</b>",
        "status_inactive": "❌ অবস্থা: <b>নিষ্ক্রিয় / মেয়াদোত্তীর্ণ</b>",
        "expiry": "মেয়াদ",
        "cancelled": "❌ বাতিল করা হয়েছে।",
        "deactivated": "🔒 বট নিষ্ক্রিয় করা হয়েছে।",
        "deactivated_msg": "🔒 বট নিষ্ক্রিয়। পুনরায় সক্রিয় করতে একটি প্ল্যান কিনুন।",
        "select_plan": "একটি প্ল্যান নির্বাচন করুন:",
        "checking": "🔎 উপলব্ধ মুদ্রা পরীক্ষা করা হচ্ছে...",
        "no_crypto": "❌ এখন কোনো মুদ্রা উপলব্ধ নেই।",
        "generating": "⏳ পেমেন্ট ইনভয়েস তৈরি হচ্ছে...",
        "payment_confirmed": "✅ <b>পেমেন্ট নিশ্চিত হয়েছে!</b>",
        "activated_days": "আপনার বট <b>{days} দিনের</b> জন্য সক্রিয় করা হয়েছে।",
        "payment_api_error": "❌ <b>পেমেন্ট API ত্রুটি</b>",
        "try_again": "আবার চেষ্টা করুন বা অ্যাডমিনের সাথে যোগাযোগ করুন।",
        "select_currency": "<b>{plan}</b> (${price}) এর জন্য পেমেন্ট মুদ্রা চুনুন:",
        "choose_language": "🌐 <b>অনুগ্রহ করে আপনার ভাষা চুনুন:</b>",
        "language_set": "✅ ভাষা আপডেট হয়েছে।",
        "send_cancel": "বাতিল করতে /cancel পাঠান।",
        "searching": "⏳ খোঁজা হচ্ছে...",
        "no_result": "❌ কোনো ফলাফল নেই বা API ত্রুটি।",
        "select_option": "❓ মেনু থেকে একটি বিকল্প চুনুন।",
        "search_currency": "🔍 খুঁজুন",
        "all_currencies": "📋 সব মুদ্রা",
        "back": "🔙 পিছনে",
        "cancel_btn": "❌ বাতিল",
        "deactivate_btn": "🔒 নিষ্ক্রিয় করুন",
        "check_status_btn": "🔄 অবস্থা দেখুন",
        "lang_btn": "🌐 ভাষা",
        "not_available": "❌ সেই মুদ্রা উপলব্ধ নয়।",
        "payment_timeout": "⏱ পেমেন্ট API সময় শেষ। আবার চেষ্টা করুন।",
        "send_currency_code": "🔍 একটি মুদ্রা কোড বা নাম লিখুন (যেমন BTC, ETH, USDT, Euro, INR):",
        "found_currencies": "{n}টি মিলে যাওয়া মুদ্রা পাওয়া গেছে:",
        "no_match": "❌ কোনো মিলে যাওয়া মুদ্রা পাওয়া যায়নি।",
        "send_amount": "💰 <b>{amount} {currency}</b> পাঠান:",
        "popular": "⭐ জনপ্রিয় মুদ্রা:",
        "plan_1": "1 মাস", "plan_2": "3 মাস", "plan_3": "6 মাস", "plan_4": "1 বছর",
        "bumped_note": "ℹ️ নেটওয়ার্ক ন্যূনতম অনুযায়ী পরিমাণ সমন্বয় করা হয়েছে।",
        "currency_unsupported": "⚠️ এই মুদ্রা পেমেন্টের জন্য সমর্থিত নাও হতে পারে। অন্যটি চেষ্টা করুন।",
    },
    "ur": {
        "welcome": "👋 <b>خوش آمدید!</b>",
        "locked": "🔒 یہ بوٹ لاک ہے۔",
        "buy_plan": "فعال کرنے کے لیے براہ کرم ایک پلان خریدیں۔",
        "select_feature": "ایک خصوصیت منتخب کریں:",
        "already_active": "✅ آپ پہلے سے فعال ہیں۔",
        "status_active": "✅ حیثیت: <b>فعال</b>",
        "status_inactive": "❌ حیثیت: <b>غیر فعال / ختم شدہ</b>",
        "expiry": "میعاد",
        "cancelled": "❌ منسوخ کر دیا گیا۔",
        "deactivated": "🔒 بوٹ غیر فعال کر دیا گیا۔",
        "deactivated_msg": "🔒 بوٹ غیر فعال۔ دوبارہ فعال کرنے کے لیے پلان خریدیں۔",
        "select_plan": "ایک پلان منتخب کریں:",
        "checking": "🔎 دستیاب کرنسیاں چیک کر رہے ہیں...",
        "no_crypto": "❌ ابھی کوئی کرنسی دستیاب نہیں۔",
        "generating": "⏳ ادائیگی انوائس بنائی جا رہی ہے...",
        "payment_confirmed": "✅ <b>ادائیگی کی تصدیق ہو گئی!</b>",
        "activated_days": "آپ کا بوٹ <b>{days} دنوں</b> کے لیے فعال کر دیا گیا ہے۔",
        "payment_api_error": "❌ <b>ادائیگی API خرابی</b>",
        "try_again": "دوبارہ کوشش کریں یا ایڈمن سے رابطہ کریں۔",
        "select_currency": "<b>{plan}</b> (${price}) کے لیے ادائیگی کرنسی منتخب کریں:",
        "choose_language": "🌐 <b>براہ کرم اپنی زبان منتخب کریں:</b>",
        "language_set": "✅ زبان اپ ڈیٹ ہو گئی۔",
        "send_cancel": "منسوخ کرنے کے لیے /cancel بھیجیں۔",
        "searching": "⏳ تلاش کر رہے ہیں...",
        "no_result": "❌ کوئی نتیجہ نہیں یا API خرابی۔",
        "select_option": "❓ براہ کرم مینو سے ایک آپشن منتخب کریں۔",
        "search_currency": "🔍 تلاش",
        "all_currencies": "📋 تمام کرنسیاں",
        "back": "🔙 واپس",
        "cancel_btn": "❌ منسوخ",
        "deactivate_btn": "🔒 غیر فعال کریں",
        "check_status_btn": "🔄 حیثیت دیکھیں",
        "lang_btn": "🌐 زبان",
        "not_available": "❌ وہ کرنسی دستیاب نہیں۔",
        "payment_timeout": "⏱ ادائیگی API کا وقت ختم۔ دوبارہ کوشش کریں۔",
        "send_currency_code": "🔍 کرنسی کوڈ یا نام لکھیں (مثلاً BTC, ETH, USDT, Euro, INR):",
        "found_currencies": "{n} ملتی جلتی کرنسیاں ملیں:",
        "no_match": "❌ کوئی ملتی کرنسی نہیں ملی۔",
        "send_amount": "💰 <b>{amount} {currency}</b> بھیجیں:",
        "popular": "⭐ مقبول کرنسیاں:",
        "plan_1": "1 ماہ", "plan_2": "3 ماہ", "plan_3": "6 ماہ", "plan_4": "1 سال",
        "bumped_note": "ℹ️ نیٹ ورک کم از کم کے مطابق رقم ایڈجسٹ کی گئی۔",
        "currency_unsupported": "⚠️ یہ کرنسی ادائیگی کے لیے معاون نہ ہو سکے۔ دوسری آزمائیں۔",
    },
    "ar": {
        "welcome": "👋 <b>مرحباً!</b>",
        "locked": "🔒 هذا البوت مقفل.",
        "buy_plan": "يرجى شراء خطة للتنشيط.",
        "select_feature": "اختر ميزة:",
        "already_active": "✅ أنت مفعّل بالفعل.",
        "status_active": "✅ الحالة: <b>نشط</b>",
        "status_inactive": "❌ الحالة: <b>غير نشط / منتهي</b>",
        "expiry": "الانتهاء",
        "cancelled": "❌ تم الإلغاء.",
        "deactivated": "🔒 تم إلغاء تنشيط البوت.",
        "deactivated_msg": "🔒 البوت معطّل. اشترِ خطة لإعادة التنشيط.",
        "select_plan": "اختر خطة:",
        "checking": "🔎 جارٍ التحقق من العملات المتاحة...",
        "no_crypto": "❌ لا توجد عملات متاحة الآن.",
        "generating": "⏳ جارٍ إنشاء فاتورة الدفع...",
        "payment_confirmed": "✅ <b>تم تأكيد الدفع!</b>",
        "activated_days": "تم تنشيط البوت لمدة <b>{days} يومًا</b>.",
        "payment_api_error": "❌ <b>خطأ في واجهة الدفع</b>",
        "try_again": "يرجى المحاولة مرة أخرى أو الاتصال بالمسؤول.",
        "select_currency": "اختر عملة الدفع لـ <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>يرجى اختيار لغتك:</b>",
        "language_set": "✅ تم تحديث اللغة.",
        "send_cancel": "أرسل /cancel للإلغاء.",
        "searching": "⏳ جارٍ البحث...",
        "no_result": "❌ لا نتيجة أو خطأ في الواجهة.",
        "select_option": "❓ يرجى اختيار خيار من القائمة.",
        "search_currency": "🔍 بحث",
        "all_currencies": "📋 كل العملات",
        "back": "🔙 رجوع",
        "cancel_btn": "❌ إلغاء",
        "deactivate_btn": "🔒 إلغاء التنشيط",
        "check_status_btn": "🔄 التحقق من الحالة",
        "lang_btn": "🌐 اللغة",
        "not_available": "❌ هذه العملة غير متاحة.",
        "payment_timeout": "⏱ انتهت مهلة الدفع. حاول مرة أخرى.",
        "send_currency_code": "🔍 اكتب رمز أو اسم العملة (مثل BTC, ETH, USDT, Euro, INR):",
        "found_currencies": "تم العثور على {n} عملة مطابقة:",
        "no_match": "❌ لم يتم العثور على عملة مطابقة.",
        "send_amount": "💰 أرسل <b>{amount} {currency}</b> إلى:",
        "popular": "⭐ العملات الشائعة:",
        "plan_1": "شهر واحد", "plan_2": "3 أشهر", "plan_3": "6 أشهر", "plan_4": "سنة واحدة",
        "bumped_note": "ℹ️ تم تعديل المبلغ لتلبية الحد الأدنى للشبكة.",
        "currency_unsupported": "⚠️ قد لا تكون هذه العملة مدعومة للدفع. جرّب أخرى.",
    },
    "es": {
        "welcome": "👋 <b>¡Bienvenido!</b>",
        "locked": "🔒 Este bot está bloqueado.",
        "buy_plan": "Compra un plan para activarlo.",
        "select_feature": "Selecciona una función:",
        "already_active": "✅ Ya estás activado.",
        "status_active": "✅ Estado: <b>Activo</b>",
        "status_inactive": "❌ Estado: <b>Inactivo / Expirado</b>",
        "expiry": "Expiración",
        "cancelled": "❌ Cancelado.",
        "deactivated": "🔒 Bot desactivado.",
        "deactivated_msg": "🔒 Bot desactivado. Compra un plan para reactivar.",
        "select_plan": "Selecciona un plan:",
        "checking": "🔎 Comprobando monedas disponibles...",
        "no_crypto": "❌ No hay monedas disponibles ahora mismo.",
        "generating": "⏳ Generando factura de pago...",
        "payment_confirmed": "✅ <b>¡Pago confirmado!</b>",
        "activated_days": "Tu bot ha sido activado por <b>{days} días</b>.",
        "payment_api_error": "❌ <b>Error de la API de pago</b>",
        "try_again": "Inténtalo de nuevo o contacta al administrador.",
        "select_currency": "Elige una moneda de pago para <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Elige tu idioma:</b>",
        "language_set": "✅ Idioma actualizado.",
        "send_cancel": "Envía /cancel para cancelar.",
        "searching": "⏳ Buscando...",
        "no_result": "❌ Sin resultados o error de API.",
        "select_option": "❓ Selecciona una opción del menú.",
        "search_currency": "🔍 Buscar",
        "all_currencies": "📋 Todas las monedas",
        "back": "🔙 Atrás",
        "cancel_btn": "❌ Cancelar",
        "deactivate_btn": "🔒 Desactivar",
        "check_status_btn": "🔄 Ver estado",
        "lang_btn": "🌐 Idioma",
        "not_available": "❌ Esa moneda no está disponible.",
        "payment_timeout": "⏱ La API de pago agotó el tiempo. Inténtalo de nuevo.",
        "send_currency_code": "🔍 Escribe un código o nombre de moneda (p. ej. BTC, ETH, USDT, Euro):",
        "found_currencies": "Se encontraron {n} monedas coincidentes:",
        "no_match": "❌ No se encontró ninguna moneda coincidente.",
        "send_amount": "💰 Envía <b>{amount} {currency}</b> a:",
        "popular": "⭐ Monedas populares:",
        "plan_1": "1 Mes", "plan_2": "3 Meses", "plan_3": "6 Meses", "plan_4": "1 Año",
        "bumped_note": "ℹ️ Importe ajustado para cumplir el mínimo de la red.",
        "currency_unsupported": "⚠️ Es posible que esta moneda no sea compatible. Prueba otra.",
    },
    "fr": {
        "welcome": "👋 <b>Bienvenue !</b>",
        "locked": "🔒 Ce bot est verrouillé.",
        "buy_plan": "Veuillez acheter un forfait pour l'activer.",
        "select_feature": "Sélectionnez une fonction :",
        "already_active": "✅ Vous êtes déjà activé.",
        "status_active": "✅ Statut : <b>Actif</b>",
        "status_inactive": "❌ Statut : <b>Inactif / Expiré</b>",
        "expiry": "Expiration",
        "cancelled": "❌ Annulé.",
        "deactivated": "🔒 Bot désactivé.",
        "deactivated_msg": "🔒 Bot désactivé. Achetez un forfait pour réactiver.",
        "select_plan": "Sélectionnez un forfait :",
        "checking": "🔎 Vérification des devises disponibles...",
        "no_crypto": "❌ Aucune devise disponible pour le moment.",
        "generating": "⏳ Génération de la facture...",
        "payment_confirmed": "✅ <b>Paiement confirmé !</b>",
        "activated_days": "Votre bot a été activé pour <b>{days} jours</b>.",
        "payment_api_error": "❌ <b>Erreur de l'API de paiement</b>",
        "try_again": "Réessayez ou contactez l'administrateur.",
        "select_currency": "Choisissez une devise de paiement pour <b>{plan}</b> (${price}) :",
        "choose_language": "🌐 <b>Choisissez votre langue :</b>",
        "language_set": "✅ Langue mise à jour.",
        "send_cancel": "Envoyez /cancel pour annuler.",
        "searching": "⏳ Recherche...",
        "no_result": "❌ Aucun résultat ou erreur API.",
        "select_option": "❓ Veuillez choisir une option du menu.",
        "search_currency": "🔍 Rechercher",
        "all_currencies": "📋 Toutes les devises",
        "back": "🔙 Retour",
        "cancel_btn": "❌ Annuler",
        "deactivate_btn": "🔒 Désactiver",
        "check_status_btn": "🔄 Vérifier le statut",
        "lang_btn": "🌐 Langue",
        "not_available": "❌ Cette devise n'est pas disponible.",
        "payment_timeout": "⏱ Délai de l'API de paiement dépassé. Réessayez.",
        "send_currency_code": "🔍 Saisissez un code ou nom de devise (ex. BTC, ETH, USDT, Euro) :",
        "found_currencies": "{n} devises correspondantes trouvées :",
        "no_match": "❌ Aucune devise correspondante trouvée.",
        "send_amount": "💰 Envoyez <b>{amount} {currency}</b> à :",
        "popular": "⭐ Devises populaires :",
        "plan_1": "1 Mois", "plan_2": "3 Mois", "plan_3": "6 Mois", "plan_4": "1 An",
        "bumped_note": "ℹ️ Montant ajusté pour respecter le minimum du réseau.",
        "currency_unsupported": "⚠️ Cette devise n'est peut-être pas prise en charge. Essayez-en une autre.",
    },
    "de": {
        "welcome": "👋 <b>Willkommen!</b>",
        "locked": "🔒 Dieser Bot ist gesperrt.",
        "buy_plan": "Bitte kaufe einen Plan zur Aktivierung.",
        "select_feature": "Wähle eine Funktion:",
        "already_active": "✅ Du bist bereits aktiviert.",
        "status_active": "✅ Status: <b>Aktiv</b>",
        "status_inactive": "❌ Status: <b>Inaktiv / Abgelaufen</b>",
        "expiry": "Ablauf",
        "cancelled": "❌ Abgebrochen.",
        "deactivated": "🔒 Bot deaktiviert.",
        "deactivated_msg": "🔒 Bot deaktiviert. Kaufe einen Plan zur Reaktivierung.",
        "select_plan": "Wähle einen Plan:",
        "checking": "🔎 Verfügbare Währungen werden geprüft...",
        "no_crypto": "❌ Derzeit keine Währungen verfügbar.",
        "generating": "⏳ Zahlungsrechnung wird erstellt...",
        "payment_confirmed": "✅ <b>Zahlung bestätigt!</b>",
        "activated_days": "Dein Bot wurde für <b>{days} Tage</b> aktiviert.",
        "payment_api_error": "❌ <b>Zahlungs-API-Fehler</b>",
        "try_again": "Bitte erneut versuchen oder Admin kontaktieren.",
        "select_currency": "Wähle eine Zahlungswährung für <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Bitte wähle deine Sprache:</b>",
        "language_set": "✅ Sprache aktualisiert.",
        "send_cancel": "Sende /cancel zum Abbrechen.",
        "searching": "⏳ Suche läuft...",
        "no_result": "❌ Kein Ergebnis oder API-Fehler.",
        "select_option": "❓ Bitte wähle eine Option aus dem Menü.",
        "search_currency": "🔍 Suchen",
        "all_currencies": "📋 Alle Währungen",
        "back": "🔙 Zurück",
        "cancel_btn": "❌ Abbrechen",
        "deactivate_btn": "🔒 Deaktivieren",
        "check_status_btn": "🔄 Status prüfen",
        "lang_btn": "🌐 Sprache",
        "not_available": "❌ Diese Währung ist nicht verfügbar.",
        "payment_timeout": "⏱ Zahlungs-API-Timeout. Bitte erneut versuchen.",
        "send_currency_code": "🔍 Gib einen Währungscode oder Namen ein (z. B. BTC, ETH, USDT, Euro):",
        "found_currencies": "{n} passende Währungen gefunden:",
        "no_match": "❌ Keine passende Währung gefunden.",
        "send_amount": "💰 Sende <b>{amount} {currency}</b> an:",
        "popular": "⭐ Beliebte Währungen:",
        "plan_1": "1 Monat", "plan_2": "3 Monate", "plan_3": "6 Monate", "plan_4": "1 Jahr",
        "bumped_note": "ℹ️ Betrag an das Netzwerkminimum angepasst.",
        "currency_unsupported": "⚠️ Diese Währung wird möglicherweise nicht unterstützt. Versuche eine andere.",
    },
    "pt": {
        "welcome": "👋 <b>Bem-vindo!</b>",
        "locked": "🔒 Este bot está bloqueado.",
        "buy_plan": "Compre um plano para ativar.",
        "select_feature": "Selecione um recurso:",
        "already_active": "✅ Você já está ativado.",
        "status_active": "✅ Status: <b>Ativo</b>",
        "status_inactive": "❌ Status: <b>Inativo / Expirado</b>",
        "expiry": "Expiração",
        "cancelled": "❌ Cancelado.",
        "deactivated": "🔒 Bot desativado.",
        "deactivated_msg": "🔒 Bot desativado. Compre um plano para reativar.",
        "select_plan": "Selecione um plano:",
        "checking": "🔎 Verificando moedas disponíveis...",
        "no_crypto": "❌ Nenhuma moeda disponível agora.",
        "generating": "⏳ Gerando fatura de pagamento...",
        "payment_confirmed": "✅ <b>Pagamento confirmado!</b>",
        "activated_days": "Seu bot foi ativado por <b>{days} dias</b>.",
        "payment_api_error": "❌ <b>Erro na API de pagamento</b>",
        "try_again": "Tente novamente ou contate o administrador.",
        "select_currency": "Escolha uma moeda de pagamento para <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Escolha seu idioma:</b>",
        "language_set": "✅ Idioma atualizado.",
        "send_cancel": "Envie /cancel para cancelar.",
        "searching": "⏳ Pesquisando...",
        "no_result": "❌ Sem resultado ou erro de API.",
        "select_option": "❓ Selecione uma opção do menu.",
        "search_currency": "🔍 Pesquisar",
        "all_currencies": "📋 Todas as moedas",
        "back": "🔙 Voltar",
        "cancel_btn": "❌ Cancelar",
        "deactivate_btn": "🔒 Desativar",
        "check_status_btn": "🔄 Ver status",
        "lang_btn": "🌐 Idioma",
        "not_available": "❌ Essa moeda não está disponível.",
        "payment_timeout": "⏱ Tempo esgotado na API de pagamento. Tente novamente.",
        "send_currency_code": "🔍 Digite um código ou nome de moeda (ex. BTC, ETH, USDT, Euro):",
        "found_currencies": "{n} moedas correspondentes encontradas:",
        "no_match": "❌ Nenhuma moeda correspondente encontrada.",
        "send_amount": "💰 Envie <b>{amount} {currency}</b> para:",
        "popular": "⭐ Moedas populares:",
        "plan_1": "1 Mês", "plan_2": "3 Meses", "plan_3": "6 Meses", "plan_4": "1 Ano",
        "bumped_note": "ℹ️ Valor ajustado para atender ao mínimo da rede.",
        "currency_unsupported": "⚠️ Esta moeda pode não ser suportada. Tente outra.",
    },
    "ru": {
        "welcome": "👋 <b>Добро пожаловать!</b>",
        "locked": "🔒 Этот бот заблокирован.",
        "buy_plan": "Купите план для активации.",
        "select_feature": "Выберите функцию:",
        "already_active": "✅ Вы уже активированы.",
        "status_active": "✅ Статус: <b>Активен</b>",
        "status_inactive": "❌ Статус: <b>Неактивен / Истёк</b>",
        "expiry": "Истекает",
        "cancelled": "❌ Отменено.",
        "deactivated": "🔒 Бот деактивирован.",
        "deactivated_msg": "🔒 Бот деактивирован. Купите план для повторной активации.",
        "select_plan": "Выберите план:",
        "checking": "🔎 Проверка доступных валют...",
        "no_crypto": "❌ Сейчас нет доступных валют.",
        "generating": "⏳ Создание платёжного счёта...",
        "payment_confirmed": "✅ <b>Платёж подтверждён!</b>",
        "activated_days": "Ваш бот активирован на <b>{days} дней</b>.",
        "payment_api_error": "❌ <b>Ошибка платёжного API</b>",
        "try_again": "Попробуйте снова или свяжитесь с админом.",
        "select_currency": "Выберите валюту оплаты для <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Выберите язык:</b>",
        "language_set": "✅ Язык обновлён.",
        "send_cancel": "Отправьте /cancel для отмены.",
        "searching": "⏳ Поиск...",
        "no_result": "❌ Нет результата или ошибка API.",
        "select_option": "❓ Выберите пункт меню.",
        "search_currency": "🔍 Поиск",
        "all_currencies": "📋 Все валюты",
        "back": "🔙 Назад",
        "cancel_btn": "❌ Отмена",
        "deactivate_btn": "🔒 Деактивировать",
        "check_status_btn": "🔄 Проверить статус",
        "lang_btn": "🌐 Язык",
        "not_available": "❌ Эта валюта недоступна.",
        "payment_timeout": "⏱ Тайм-аут платёжного API. Попробуйте снова.",
        "send_currency_code": "🔍 Введите код или название валюты (напр. BTC, ETH, USDT, Euro):",
        "found_currencies": "Найдено {n} подходящих валют:",
        "no_match": "❌ Подходящая валюта не найдена.",
        "send_amount": "💰 Отправьте <b>{amount} {currency}</b> на:",
        "popular": "⭐ Популярные валюты:",
        "plan_1": "1 месяц", "plan_2": "3 месяца", "plan_3": "6 месяцев", "plan_4": "1 год",
        "bumped_note": "ℹ️ Сумма скорректирована под минимум сети.",
        "currency_unsupported": "⚠️ Эта валюта может не поддерживаться. Попробуйте другую.",
    },
    "zh": {
        "welcome": "👋 <b>欢迎！</b>",
        "locked": "🔒 此机器人已锁定。",
        "buy_plan": "请购买套餐以激活。",
        "select_feature": "请选择功能：",
        "already_active": "✅ 您已激活。",
        "status_active": "✅ 状态：<b>已激活</b>",
        "status_inactive": "❌ 状态：<b>未激活 / 已过期</b>",
        "expiry": "到期时间",
        "cancelled": "❌ 已取消。",
        "deactivated": "🔒 机器人已停用。",
        "deactivated_msg": "🔒 机器人已停用。请购买套餐重新激活。",
        "select_plan": "请选择套餐：",
        "checking": "🔎 正在检查可用货币...",
        "no_crypto": "❌ 当前没有可用货币。",
        "generating": "⏳ 正在生成支付账单...",
        "payment_confirmed": "✅ <b>支付已确认！</b>",
        "activated_days": "您的机器人已激活 <b>{days} 天</b>。",
        "payment_api_error": "❌ <b>支付 API 错误</b>",
        "try_again": "请重试或联系管理员。",
        "select_currency": "为 <b>{plan}</b> (${price}) 选择支付货币：",
        "choose_language": "🌐 <b>请选择您的语言：</b>",
        "language_set": "✅ 语言已更新。",
        "send_cancel": "发送 /cancel 取消。",
        "searching": "⏳ 搜索中...",
        "no_result": "❌ 无结果或 API 错误。",
        "select_option": "❓ 请从菜单中选择一个选项。",
        "search_currency": "🔍 搜索",
        "all_currencies": "📋 所有货币",
        "back": "🔙 返回",
        "cancel_btn": "❌ 取消",
        "deactivate_btn": "🔒 停用",
        "check_status_btn": "🔄 检查状态",
        "lang_btn": "🌐 语言",
        "not_available": "❌ 该货币不可用。",
        "payment_timeout": "⏱ 支付 API 超时。请重试。",
        "send_currency_code": "🔍 输入货币代码或名称（如 BTC、ETH、USDT、Euro）：",
        "found_currencies": "找到 {n} 个匹配的货币：",
        "no_match": "❌ 未找到匹配的货币。",
        "send_amount": "💰 发送 <b>{amount} {currency}</b> 至：",
        "popular": "⭐ 热门货币：",
        "plan_1": "1 个月", "plan_2": "3 个月", "plan_3": "6 个月", "plan_4": "1 年",
        "bumped_note": "ℹ️ 金额已调整以满足网络最低要求。",
        "currency_unsupported": "⚠️ 该货币可能不支持支付，请尝试其他货币。",
    },
    "id": {
        "welcome": "👋 <b>Selamat datang!</b>",
        "locked": "🔒 Bot ini terkunci.",
        "buy_plan": "Silakan beli paket untuk mengaktifkan.",
        "select_feature": "Pilih fitur:",
        "already_active": "✅ Anda sudah aktif.",
        "status_active": "✅ Status: <b>Aktif</b>",
        "status_inactive": "❌ Status: <b>Tidak aktif / Kedaluwarsa</b>",
        "expiry": "Kedaluwarsa",
        "cancelled": "❌ Dibatalkan.",
        "deactivated": "🔒 Bot dinonaktifkan.",
        "deactivated_msg": "🔒 Bot dinonaktifkan. Beli paket untuk mengaktifkan kembali.",
        "select_plan": "Pilih paket:",
        "checking": "🔎 Memeriksa mata uang yang tersedia...",
        "no_crypto": "❌ Tidak ada mata uang yang tersedia saat ini.",
        "generating": "⏳ Membuat invoice pembayaran...",
        "payment_confirmed": "✅ <b>Pembayaran dikonfirmasi!</b>",
        "activated_days": "Bot Anda telah diaktifkan selama <b>{days} hari</b>.",
        "payment_api_error": "❌ <b>Kesalahan API pembayaran</b>",
        "try_again": "Coba lagi atau hubungi admin.",
        "select_currency": "Pilih mata uang pembayaran untuk <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Silakan pilih bahasa Anda:</b>",
        "language_set": "✅ Bahasa diperbarui.",
        "send_cancel": "Kirim /cancel untuk membatalkan.",
        "searching": "⏳ Mencari...",
        "no_result": "❌ Tidak ada hasil atau kesalahan API.",
        "select_option": "❓ Silakan pilih opsi dari menu.",
        "search_currency": "🔍 Cari",
        "all_currencies": "📋 Semua Mata Uang",
        "back": "🔙 Kembali",
        "cancel_btn": "❌ Batal",
        "deactivate_btn": "🔒 Nonaktifkan",
        "check_status_btn": "🔄 Cek Status",
        "lang_btn": "🌐 Bahasa",
        "not_available": "❌ Mata uang itu tidak tersedia.",
        "payment_timeout": "⏱ API pembayaran habis waktu. Coba lagi.",
        "send_currency_code": "🔍 Ketik kode atau nama mata uang (mis. BTC, ETH, USDT, Euro):",
        "found_currencies": "Ditemukan {n} mata uang yang cocok:",
        "no_match": "❌ Tidak ada mata uang yang cocok.",
        "send_amount": "💰 Kirim <b>{amount} {currency}</b> ke:",
        "popular": "⭐ Mata uang populer:",
        "plan_1": "1 Bulan", "plan_2": "3 Bulan", "plan_3": "6 Bulan", "plan_4": "1 Tahun",
        "bumped_note": "ℹ️ Jumlah disesuaikan dengan minimum jaringan.",
        "currency_unsupported": "⚠️ Mata uang ini mungkin tidak didukung. Coba yang lain.",
    },
    "tr": {
        "welcome": "👋 <b>Hoş geldiniz!</b>",
        "locked": "🔒 Bu bot kilitli.",
        "buy_plan": "Etkinleştirmek için lütfen bir plan satın alın.",
        "select_feature": "Bir özellik seçin:",
        "already_active": "✅ Zaten etkinsiniz.",
        "status_active": "✅ Durum: <b>Etkin</b>",
        "status_inactive": "❌ Durum: <b>Etkin değil / Süresi doldu</b>",
        "expiry": "Bitiş",
        "cancelled": "❌ İptal edildi.",
        "deactivated": "🔒 Bot devre dışı bırakıldı.",
        "deactivated_msg": "🔒 Bot devre dışı. Yeniden etkinleştirmek için plan satın alın.",
        "select_plan": "Bir plan seçin:",
        "checking": "🔎 Kullanılabilir para birimleri kontrol ediliyor...",
        "no_crypto": "❌ Şu anda kullanılabilir para birimi yok.",
        "generating": "⏳ Ödeme faturası oluşturuluyor...",
        "payment_confirmed": "✅ <b>Ödeme onaylandı!</b>",
        "activated_days": "Botunuz <b>{days} gün</b> için etkinleştirildi.",
        "payment_api_error": "❌ <b>Ödeme API hatası</b>",
        "try_again": "Tekrar deneyin veya yöneticiye başvurun.",
        "select_currency": "<b>{plan}</b> (${price}) için ödeme para birimi seçin:",
        "choose_language": "🌐 <b>Lütfen dilinizi seçin:</b>",
        "language_set": "✅ Dil güncellendi.",
        "send_cancel": "İptal için /cancel gönderin.",
        "searching": "⏳ Aranıyor...",
        "no_result": "❌ Sonuç yok veya API hatası.",
        "select_option": "❓ Lütfen menüden bir seçenek seçin.",
        "search_currency": "🔍 Ara",
        "all_currencies": "📋 Tüm Para Birimleri",
        "back": "🔙 Geri",
        "cancel_btn": "❌ İptal",
        "deactivate_btn": "🔒 Devre dışı bırak",
        "check_status_btn": "🔄 Durumu Kontrol Et",
        "lang_btn": "🌐 Dil",
        "not_available": "❌ Bu para birimi kullanılamıyor.",
        "payment_timeout": "⏱ Ödeme API zaman aşımı. Tekrar deneyin.",
        "send_currency_code": "🔍 Bir para birimi kodu veya adı yazın (örn. BTC, ETH, USDT, Euro):",
        "found_currencies": "{n} eşleşen para birimi bulundu:",
        "no_match": "❌ Eşleşen para birimi bulunamadı.",
        "send_amount": "💰 <b>{amount} {currency}</b> gönderin:",
        "popular": "⭐ Popüler para birimleri:",
        "plan_1": "1 Ay", "plan_2": "3 Ay", "plan_3": "6 Ay", "plan_4": "1 Yıl",
        "bumped_note": "ℹ️ Tutar ağ minimumuna göre ayarlandı.",
        "currency_unsupported": "⚠️ Bu para birimi desteklenmiyor olabilir. Başka bir tane deneyin.",
    },
    "fa": {
        "welcome": "👋 <b>خوش آمدید!</b>",
        "locked": "🔒 این ربات قفل است.",
        "buy_plan": "لطفاً برای فعال‌سازی یک طرح بخرید.",
        "select_feature": "یک ویژگی انتخاب کنید:",
        "already_active": "✅ شما قبلاً فعال هستید.",
        "status_active": "✅ وضعیت: <b>فعال</b>",
        "status_inactive": "❌ وضعیت: <b>غیرفعال / منقضی</b>",
        "expiry": "انقضا",
        "cancelled": "❌ لغو شد.",
        "deactivated": "🔒 ربات غیرفعال شد.",
        "deactivated_msg": "🔒 ربات غیرفعال شد. برای فعال‌سازی مجدد طرح بخرید.",
        "select_plan": "یک طرح انتخاب کنید:",
        "checking": "🔎 بررسی ارزهای موجود...",
        "no_crypto": "❌ در حال حاضر ارزی موجود نیست.",
        "generating": "⏳ در حال ایجاد فاکتور پرداخت...",
        "payment_confirmed": "✅ <b>پرداخت تأیید شد!</b>",
        "activated_days": "ربات شما برای <b>{days} روز</b> فعال شد.",
        "payment_api_error": "❌ <b>خطای API پرداخت</b>",
        "try_again": "دوباره تلاش کنید یا با مدیر تماس بگیرید.",
        "select_currency": "ارز پرداخت را برای <b>{plan}</b> (${price}) انتخاب کنید:",
        "choose_language": "🌐 <b>لطفاً زبان خود را انتخاب کنید:</b>",
        "language_set": "✅ زبان به‌روزرسانی شد.",
        "send_cancel": "برای لغو /cancel را بفرستید.",
        "searching": "⏳ در حال جستجو...",
        "no_result": "❌ نتیجه‌ای نیست یا خطای API.",
        "select_option": "❓ لطفاً یک گزینه از منو انتخاب کنید.",
        "search_currency": "🔍 جستجو",
        "all_currencies": "📋 همه ارزها",
        "back": "🔙 بازگشت",
        "cancel_btn": "❌ لغو",
        "deactivate_btn": "🔒 غیرفعال کردن",
        "check_status_btn": "🔄 بررسی وضعیت",
        "lang_btn": "🌐 زبان",
        "not_available": "❌ آن ارز موجود نیست.",
        "payment_timeout": "⏱ زمان API پرداخت تمام شد. دوباره تلاش کنید.",
        "send_currency_code": "🔍 کد یا نام ارز را وارد کنید (مثلاً BTC, ETH, USDT, Euro):",
        "found_currencies": "{n} ارز مطابق پیدا شد:",
        "no_match": "❌ ارز مطابقی پیدا نشد.",
        "send_amount": "💰 <b>{amount} {currency}</b> را بفرستید به:",
        "popular": "⭐ ارزهای محبوب:",
        "plan_1": "1 ماه", "plan_2": "3 ماه", "plan_3": "6 ماه", "plan_4": "1 سال",
        "bumped_note": "ℹ️ مبلغ برای رسیدن به حداقل شبکه تنظیم شد.",
        "currency_unsupported": "⚠️ این ارز ممکن است پشتیبانی نشود. ارز دیگری امتحان کنید.",
    },
    "it": {
        "welcome": "👋 <b>Benvenuto!</b>",
        "locked": "🔒 Questo bot è bloccato.",
        "buy_plan": "Acquista un piano per attivarlo.",
        "select_feature": "Seleziona una funzione:",
        "already_active": "✅ Sei già attivato.",
        "status_active": "✅ Stato: <b>Attivo</b>",
        "status_inactive": "❌ Stato: <b>Inattivo / Scaduto</b>",
        "expiry": "Scadenza",
        "cancelled": "❌ Annullato.",
        "deactivated": "🔒 Bot disattivato.",
        "deactivated_msg": "🔒 Bot disattivato. Acquista un piano per riattivare.",
        "select_plan": "Seleziona un piano:",
        "checking": "🔎 Controllo delle valute disponibili...",
        "no_crypto": "❌ Nessuna valuta disponibile al momento.",
        "generating": "⏳ Generazione della fattura...",
        "payment_confirmed": "✅ <b>Pagamento confermato!</b>",
        "activated_days": "Il tuo bot è stato attivato per <b>{days} giorni</b>.",
        "payment_api_error": "❌ <b>Errore API di pagamento</b>",
        "try_again": "Riprova o contatta l'amministratore.",
        "select_currency": "Scegli una valuta di pagamento per <b>{plan}</b> (${price}):",
        "choose_language": "🌐 <b>Scegli la tua lingua:</b>",
        "language_set": "✅ Lingua aggiornata.",
        "send_cancel": "Invia /cancel per annullare.",
        "searching": "⏳ Ricerca...",
        "no_result": "❌ Nessun risultato o errore API.",
        "select_option": "❓ Seleziona un'opzione dal menu.",
        "search_currency": "🔍 Cerca",
        "all_currencies": "📋 Tutte le valute",
        "back": "🔙 Indietro",
        "cancel_btn": "❌ Annulla",
        "deactivate_btn": "🔒 Disattiva",
        "check_status_btn": "🔄 Controlla stato",
        "lang_btn": "🌐 Lingua",
        "not_available": "❌ Questa valuta non è disponibile.",
        "payment_timeout": "⏱ Timeout API di pagamento. Riprova.",
        "send_currency_code": "🔍 Digita un codice o nome di valuta (es. BTC, ETH, USDT, Euro):",
        "found_currencies": "Trovate {n} valute corrispondenti:",
        "no_match": "❌ Nessuna valuta corrispondente trovata.",
        "send_amount": "💰 Invia <b>{amount} {currency}</b> a:",
        "popular": "⭐ Valute popolari:",
        "plan_1": "1 Mese", "plan_2": "3 Mesi", "plan_3": "6 Mesi", "plan_4": "1 Anno",
        "bumped_note": "ℹ️ Importo adeguato al minimo della rete.",
        "currency_unsupported": "⚠️ Questa valuta potrebbe non essere supportata. Provane un'altra.",
    },
    "ta": {
        "welcome": "👋 <b>வரவேற்கிறோம்!</b>",
        "locked": "🔒 இந்த பாட் பூட்டப்பட்டுள்ளது.",
        "buy_plan": "செயல்படுத்த ஒரு திட்டத்தை வாங்கவும்.",
        "select_feature": "ஒரு அம்சத்தைத் தேர்ந்தெடுக்கவும்:",
        "already_active": "✅ நீங்கள் ஏற்கனவே செயலில் உள்ளீர்கள்.",
        "status_active": "✅ நிலை: <b>செயலில்</b>",
        "status_inactive": "❌ நிலை: <b>செயலில் இல்லை / காலாவதி</b>",
        "expiry": "காலாவதி",
        "cancelled": "❌ ரத்து செய்யப்பட்டது.",
        "deactivated": "🔒 பாட் செயலிழக்கப்பட்டது.",
        "deactivated_msg": "🔒 பாட் செயலிழக்கப்பட்டது. மீண்டும் செயல்படுத்த ஒரு திட்டத்தை வாங்கவும்.",
        "select_plan": "ஒரு திட்டத்தைத் தேர்ந்தெடுக்கவும்:",
        "checking": "🔎 கிடைக்கும் நாணயங்களை சரிபார்க்கிறது...",
        "no_crypto": "❌ இப்போது நாணயங்கள் எதுவும் கிடைக்கவில்லை.",
        "generating": "⏳ கட்டண விலைப்பட்டியல் உருவாக்கப்படுகிறது...",
        "payment_confirmed": "✅ <b>கட்டணம் உறுதிப்படுத்தப்பட்டது!</b>",
        "activated_days": "உங்கள் பாட் <b>{days} நாட்களுக்கு</b> செயல்படுத்தப்பட்டது.",
        "payment_api_error": "❌ <b>கட்டண API பிழை</b>",
        "try_again": "மீண்டும் முயற்சிக்கவும் அல்லது நிர்வாகியைத் தொடர்பு கொள்ளவும்.",
        "select_currency": "<b>{plan}</b> (${price}) க்கான கட்டண நாணயத்தைத் தேர்ந்தெடுக்கவும்:",
        "choose_language": "🌐 <b>உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்:</b>",
        "language_set": "✅ மொழி புதுப்பிக்கப்பட்டது.",
        "send_cancel": "ரத்து செய்ய /cancel அனுப்பவும்.",
        "searching": "⏳ தேடுகிறது...",
        "no_result": "❌ முடிவு இல்லை அல்லது API பிழை.",
        "select_option": "❓ மெனுவிலிருந்து ஒரு விருப்பத்தைத் தேர்ந்தெடுக்கவும்.",
        "search_currency": "🔍 தேடு",
        "all_currencies": "📋 அனைத்து நாணயங்கள்",
        "back": "🔙 பின்செல்",
        "cancel_btn": "❌ ரத்து",
        "deactivate_btn": "🔒 செயலிழக்க",
        "check_status_btn": "🔄 நிலையைப் பார்",
        "lang_btn": "🌐 மொழி",
        "not_available": "❌ அந்த நாணயம் கிடைக்கவில்லை.",
        "payment_timeout": "⏱ கட்டண API நேரம் முடிந்தது. மீண்டும் முயற்சிக்கவும்.",
        "send_currency_code": "🔍 நாணய குறியீடு அல்லது பெயரை உள்ளிடவும் (எ.கா. BTC, ETH, USDT, Euro):",
        "found_currencies": "{n} பொருந்தும் நாணயங்கள் கிடைத்தன:",
        "no_match": "❌ பொருந்தும் நாணயம் இல்லை.",
        "send_amount": "💰 <b>{amount} {currency}</b> அனுப்பவும்:",
        "popular": "⭐ பிரபல நாணயங்கள்:",
        "plan_1": "1 மாதம்", "plan_2": "3 மாதங்கள்", "plan_3": "6 மாதங்கள்", "plan_4": "1 வருடம்",
        "bumped_note": "ℹ️ நெட்வொர்க் குறைந்தபட்சத்திற்கு ஏற்ப தொகை சரிசெய்யப்பட்டது.",
        "currency_unsupported": "⚠️ இந்த நாணயம் ஆதரிக்கப்படாமல் இருக்கலாம். வேறொன்றை முயற்சிக்கவும்.",
    },
}

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
    "🪪 Aadhaar Info ": {
        "url": "https://travelers-creature-sarah-rogers.trycloudflare.com/search?q=",
        "prompt": "🪪 Send a 12 Digit Aadhaar Number to Get🪪 information 💀"
    },
    "📞 Number Info ": {
        "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
        "prompt": "📞Send a 10 Digit Indian Number (Without +91) to Get🪪 information 💀     Example (9712073901)"
    },
    "📍PIN Code Lookup": {
        "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
        "prompt": "📍 Send PIN code to get information 💀 (number)"
    },
    "🚘 Vehicle Info": {
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
        "url": "https://upi-id-to-info-by-abhigyan.onrender.com/upi/",
        "prompt": "🏦 Send the authorized UPI ID:"
    },
    "📧 Advanced Email Info ": {
        "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
        "prompt": "📧 Send the authorized email:"
    },
    "🌐 IP Address Info": {
        "url": "https://talks-chain-restrictions-statistics.trycloudflare.com/search?query=",
        "prompt": "🌐 Send the IP address:"
    }
}

# ============================================================
# HTTP SESSION
# ============================================================
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
HTTP.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0))
HTTP.mount("http://", HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0))

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
# TELEGRAM API
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

def send_photo(chat_id, photo_bytes, caption=None, keyboard=None, parse_mode="HTML"):
    url = USER_TELEGRAM_API + "/sendPhoto"
    files = {"photo": ("qr.png", photo_bytes, "image/png")}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
    if keyboard is not None:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        response = HTTP.post(
            url, data=data, files=files,
            timeout=(TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_READ_TIMEOUT)
        )
        response.raise_for_status()
        return response.json()
    except Exception as error:
        print("Telegram sendPhoto error:", error)
        return None

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

def edit_inline_keyboard(chat_id, message_id, keyboard):
    url = USER_TELEGRAM_API + "/editMessageReplyMarkup"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": json.dumps(keyboard, ensure_ascii=False),
    }
    try:
        HTTP.post(url, data=data, timeout=(5, 15))
    except Exception as e:
        print("editMessageReplyMarkup error:", e)

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
# CURRENCY LIST (dynamic — all NOWPayments currencies)
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
def crypto_plan_keyboard(lang="en"):
    return {
        "keyboard": [
            ["1 Month - $13.00",  "3 Months - $18.00"],
            ["6 Months - $25.00", "1 Year - $35.00"],
            [t(lang, "check_status_btn"), t(lang, "cancel_btn")],
            [t(lang, "lang_btn")],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
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
        send_message(chat_id, "Unknown plan.", crypto_plan_keyboard(lang))
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
            send_message(chat_id, t(lang, "payment_timeout"), crypto_plan_keyboard(lang))
        else:
            send_message(
                chat_id,
                f"{t(lang, 'payment_api_error')}\n\n"
                f"<code>{err}: {msg_text[:400]}</code>\n\n"
                f"{t(lang, 'try_again')}",
                crypto_plan_keyboard(lang),
            )
        return

    if not payment or not payment.get("pay_address"):
        send_message(chat_id, t(lang, "try_again"), crypto_plan_keyboard(lang))
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
            caption=f"🪙 <b>{pay_curr} Payment</b>",
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
# CALLBACK HANDLER
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

    # === Language chosen → delete picker, then show plan/feature menu ===
    if data.startswith("lang:"):
        code = data.split(":", 1)[1]
        if code in LANGUAGES:
            set_lang(chat_id, code)
            answer_callback(cb_id, t(code, "language_set"))

            # 1) Remove the inline language picker message
            if msg_id:
                delete_message(chat_id, msg_id)

            # 2) Show the correct keyboard in the newly-chosen language
            if is_active(chat_id):
                send_message(
                    chat_id,
                    t(code, "already_active") + "\n\n" + t(code, "select_feature"),
                    main_keyboard(code),
                )
            else:
                send_message(
                    chat_id,
                    t(code, "welcome") + "\n\n" + t(code, "select_plan"),
                    crypto_plan_keyboard(code),
                )
        return

    if data == "back:plans":
        answer_callback(cb_id)
        send_message(chat_id, t(lang, "select_plan"), crypto_plan_keyboard(lang))
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
        send_message(chat_id, t(lang, "cancelled"), crypto_plan_keyboard(lang))
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
# USER BOT
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

    # === /start: ONLY show the language picker (step 1) ===
    if text == "/start":
        USER_STATE.pop(chat_id, None)
        send_message(chat_id, t(lang, "choose_language"), language_keyboard())
        return

    # /lang and 🌐 Language button → reopen picker
    if text in ("/lang", "/language") or is_button(text, "lang_btn", lang):
        send_message(chat_id, t(lang, "choose_language"), language_keyboard())
        return

    if text == "/cancel" or is_button(text, "cancel_btn", lang):
        USER_STATE.pop(chat_id, None)
        kb = main_keyboard(lang) if is_active(chat_id) else crypto_plan_keyboard(lang)
        send_message(chat_id, t(lang, "cancelled") + "\n\n" + t(lang, "select_feature"), kb)
        return

    if is_button(text, "check_status_btn", lang):
        if is_active(chat_id):
            expiry_str = time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(ACTIVATED_USERS[chat_id]))
            send_message(chat_id,
                         f"{t(lang, 'status_active')}\n{t(lang, 'expiry')}: <code>{expiry_str}</code>",
                         main_keyboard(lang))
        else:
            send_message(chat_id,
                         f"{t(lang, 'status_inactive')}\n\n{t(lang, 'buy_plan')}",
                         crypto_plan_keyboard(lang))
        return

    if is_button(text, "deactivate_btn", lang):
        if chat_id in ACTIVATED_USERS:
            del ACTIVATED_USERS[chat_id]
            save_activation_data()
        USER_STATE.pop(chat_id, None)
        send_message(chat_id, t(lang, "deactivated_msg"), crypto_plan_keyboard(lang))
        return

    plan_map = {
        normalize_text("1 Month - $13.00"):  "plan_1",
        normalize_text("3 Months - $18.00"): "plan_2",
        normalize_text("6 Months - $25.00"): "plan_3",
        normalize_text("1 Year - $35.00"):   "plan_4",
    }
    ntext = normalize_text(text)
    if ntext in plan_map:
        plan_id = plan_map[ntext]
        USER_STATE[chat_id] = {"flow": "select_currency", "plan_id": plan_id}
        send_message(chat_id,
                     t(lang, "select_currency",
                       plan=t(lang, plan_id),
                       price=f"{PLANS[plan_id]['price_usd']:.2f}"))
        send_message(chat_id, t(lang, "popular"), popular_currency_keyboard(plan_id, lang))
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
        send_message(chat_id,
                     f"{t(lang, 'locked')}\n\n{t(lang, 'buy_plan')}",
                     crypto_plan_keyboard(lang))
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
def admin_send_message(bot_number, chat_id, text):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    if not api:
        return
    try:
        HTTP.post(api + "/sendMessage",
                  data={"chat_id": chat_id, "text": text},
                  timeout=(5, 35))
    except Exception as e:
        print(f"Admin bot {bot_number} error:", e)

def admin_get_updates(bot_number, offset=None):
    api = ADMIN_TELEGRAM_APIS.get(bot_number)
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        r = HTTP.get(api + "/getUpdates", params=params, timeout=(5, 35))
        return r.json()
    except Exception:
        return None

def process_admin_update(bot_number, update):
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if chat_id not in ADMIN_USER_IDS_1:
        admin_send_message(bot_number, chat_id, "⛔ You are not authorized.")
        return

    if text in ("/start", "/help"):
        admin_send_message(bot_number, chat_id,
            "🛠 ADMIN PANEL\n\n"
            "/add_user USER_ID DAYS\n"
            "/list\n"
            "/deactivate USER_ID"
        )
        return

    if text == "/list":
        if not ACTIVATED_USERS:
            admin_send_message(bot_number, chat_id, "📭 No active users.")
            return
        lines = ["👥 ACTIVE USERS\n"]
        for uid, expiry in ACTIVATED_USERS.items():
            exp_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(expiry))
            status = "✅" if expiry > time.time() else "❌"
            lines.append(f"{status} {uid} — {exp_str}")
        admin_send_message(bot_number, chat_id, "\n".join(lines))
        return

    if text.startswith("/add_user"):
        parts = text.split()
        if len(parts) != 3:
            admin_send_message(bot_number, chat_id, "Usage: /add_user USER_ID DAYS")
            return
        try:
            target_id = int(parts[1]); days = int(parts[2])
            current = ACTIVATED_USERS.get(target_id, 0)
            if current < time.time():
                current = time.time()
            ACTIVATED_USERS[target_id] = current + (days * 86400)
            save_activation_data()
            admin_send_message(bot_number, chat_id, f"✅ User {target_id} activated for {days} days.")
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid format.")
        return

    if text.startswith("/deactivate"):
        parts = text.split()
        if len(parts) != 2:
            admin_send_message(bot_number, chat_id, "Usage: /deactivate USER_ID")
            return
        try:
            target_id = int(parts[1])
            if target_id in ACTIVATED_USERS:
                del ACTIVATED_USERS[target_id]
                save_activation_data()
                admin_send_message(bot_number, chat_id, f"🔒 User {target_id} deactivated.")
            else:
                admin_send_message(bot_number, chat_id, "❌ User not found.")
        except ValueError:
            admin_send_message(bot_number, chat_id, "❌ Invalid ID.")
        return

def admin_bot_loop(bot_number):
    print(f"Admin bot {bot_number} polling active.")
    offset = None
    while True:
        try:
            result = admin_get_updates(bot_number, offset)
            if result and result.get("ok"):
                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    process_admin_update(bot_number, update)
            time.sleep(1)
        except Exception as e:
            print(f"Admin bot {bot_number} loop error:", e)
            time.sleep(3)

# ============================================================
# MAIN
# ============================================================
def main():
    load_activation_data()

    if not USER_BOT_TOKEN or USER_BOT_TOKEN == "YOUR_USER_BOT_TOKEN":
        print("ERROR: Set USER_BOT_TOKEN environment variable.")
        return

    try:
        r = HTTP.get(USER_TELEGRAM_API + "/getMe", timeout=(5, 10))
        info = r.json()
        if not info.get("ok"):
            print("ERROR: Invalid Telegram token.")
            return
        print("Connected to Telegram bot:", info["result"]["username"])
    except Exception as e:
        print("Could not connect to Telegram:", e)
        return

    if not IPN_CALLBACK_URL:
        print("=" * 60)
        print("⚠️  IPN_CALLBACK_URL not set — users won't auto-activate.")
        print("=" * 60)

    threading.Thread(target=admin_bot_loop, args=(1,), daemon=True).start()

    print("=" * 60)
    print("Telegram Bot Started (language-first flow, all currencies)")
    print("=" * 60)

    offset = None
    while True:
        try:
            result = get_updates(offset)
            if result and result.get("ok"):
                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    process_update(update)
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print("Main loop error:", e)
            time.sleep(3)

if __name__ == "__main__":
    main()
