import os
import json
import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Sozlamalar ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Joylashuv: Namangan viloyati, Kosonsoy tumani, Go'rmiron (Kosonsoy shahri koordinatalari)
LATITUDE = 41.2556
LONGITUDE = 71.5573
TIMEZONE = "Asia/Tashkent"
LOCATION_NAME = "Namangan viloyati, Kosonsoy tumani, Go'rmiron"

# Obunacholar fayli
SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribers.json")

# Log sozlash
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Tugma klaviaturasi ---
WEATHER_BUTTON = "🌤️ Ob-havo"

def get_main_keyboard():
    """Asosiy tugma klaviaturasini qaytaradi."""
    keyboard = [[KeyboardButton(WEATHER_BUTTON)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# --- Ob-havo ma'lumotlarini olish ---
def get_weather_for_today():
    """Bugungi sana uchun ob-havo ma'lumotlarini open-meteo API dan oladi."""
    today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone={TIMEZONE}"
        f"&start_date={today}&end_date={today}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]
        idx = daily["time"].index(today)

        temp_max = daily["temperature_2m_max"][idx]
        temp_min = daily["temperature_2m_min"][idx]
        precip_prob = daily["precipitation_probability_max"][idx]
        weather_code = daily["weathercode"][idx]

        # Weather code -> tavsif (WMO kodlar)
        weather_desc = weather_code_to_text(weather_code)

        return {
            "date": today,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "precip_prob": precip_prob,
            "weather_desc": weather_desc,
        }
    except Exception as e:
        logger.error(f"Ob-havo olishda xatolik: {e}")
        return None


def weather_code_to_text(code: int) -> str:
    """WMO weather kodini o'zbek tilidagi matnga aylantiradi."""
    mapping = {
        0: "ochiq havo",
        1: "anaqa ochiq",
        2: "qisman bulutli",
        3: "to'liq bulutli",
        45: "tuman",
        48: "muruviy tuman",
        51: "yengil yomg'ir",
        53: "o'rtacha yomg'ir",
        55: "kuvvatli yomg'ir",
        56: "yengil muzli yomg'ir",
        57: "kuvvatli muzli yomg'ir",
        61: "yengil yomg'ir",
        63: "o'rtacha yomg'ir",
        65: "kuvvatli yomg'ir",
        66: "yengil muzli yomg'ir",
        67: "kuvvatli muzli yomg'ir",
        71: "yengil qor",
        73: "o'rtacha qor",
        75: "kuvvatli qor",
        77: "qorin qirralari",
        80: "yengil yomg'ir suvchi",
        81: "o'rtacha yomg'ir suvchi",
        82: "kuvvatli yomg'ir suvchi",
        85: "yengil qor suvchi",
        86: "kuvvatli qor suvchi",
        95: "g'iroli",
        96: "g'iroli, kichik qor bilan",
        99: "g'iroli, katta qor bilan",
    }
    return mapping.get(code, "nomlum ob-havo")


# --- Obunacholarni boshqarish ---
def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscribers, f, ensure_ascii=False, indent=2)


# --- Xabarni yasash ---
def build_weather_message(weather: dict) -> str:
    """Ob-havo xabarini shakllantiradi."""
    date_str = weather["date"]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = dt.strftime("%A")
        weekday_uz = {
            "Monday": "Dushanba",
            "Tuesday": "Seshanba",
            "Wednesday": "Chorshanba",
            "Thursday": "Payshanba",
            "Friday": "Juma",
            "Saturday": "Shanba",
            "Sunday": "Yakshanba",
        }.get(weekday, weekday)
        date_formatted = f"{dt.day}.{dt.month}.{dt.year}, {weekday_uz}"
    except Exception:
        date_formatted = date_str

    temp_max = weather["temp_max"]
    temp_min = weather["temp_min"]
    precip = weather["precip_prob"]
    desc = weather["weather_desc"]

    msg = f"Bugun! 🌤️\n\n"
    msg += f"Sana: {date_formatted}\n"
    msg += f"Joy: {LOCATION_NAME}\n"
    msg += f"Ob-havo: {desc}\n"
    msg += f"Harorat: +{temp_min} … +{temp_max} °C\n"
    msg += f"Yomg'ir ehtimoli: {precip}%\n\n"

    if precip >= 40:
        msg += "⚠️ Bugun yomg'ir yomon bo'lishi mumkin. Sotib oling yoki sotib chiqing qulayligiga e'tibor bering!"
    elif precip >= 20:
        msg += "☔ Yomg'ir ehtimoli bor, sotib chiqishingiz mumkin."
    else:
        msg += "✅ Ob-havo qulay, yomg'ir ehtimoli past."

    return msg


# --- Telegram handlerlar ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers = load_subscribers()
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers(subscribers)
        await update.message.reply_text(
            "Ob-havo obunangiz qilindi! Har kuni ertalab 07:00 da ob-havo xabari keladi.\n"
            "To'xtatish uchun /stop bosing.\n\n"
            "Hozirgi ob-havoni ko'rish uchun quyidagi tugmani bosing:",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Siz allaqachon obunacholisiz.\n\n"
            "Hozirgi ob-havoni ko'rish uchun quyidagi tugmani bosing:",
            reply_markup=get_main_keyboard()
        )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers = load_subscribers()
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers(subscribers)
        await update.message.reply_text("Obunangiz to'xtatildi.")
    else:
        await update.message.reply_text("Siz obunachomagan edingiz.")


async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weather = get_weather_for_today()
    if weather:
        await update.message.reply_text(build_weather_message(weather), reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("Kechirasiz, ob-havo ma'lumotlarini olishda xatolik yuz berdi.", reply_markup=get_main_keyboard())


# --- Tugma bosilganda ishlovchi handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == WEATHER_BUTTON:
        await weather_cmd(update, context)


# --- Kunlik avtomatik yuborish ---
async def send_daily_weather(context: ContextTypes.DEFAULT_TYPE):
    subscribers = load_subscribers()
    weather = get_weather_for_today()
    if not weather:
        logger.error("Ob-havo olinmadi, xabar yuborilmadi.")
        return

    text = build_weather_message(weather)
    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.error(f"Chat {chat_id} ga yuborishda xatolik: {e}")


# --- Asosiy funksiya ---
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("XATO: .env faylida BOT_TOKEN ni to'g'ri kiriting!")
        print("1. @BotFather ga yozib yangi bot yarating va token oling.")
        print("2. .env faylida YOUR_BOT_TOKEN_HERE ga o'rniga tokenni yozing.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Komandalar
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("obhavo", weather_cmd))

    # Tugma bosilganda
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    # Kunlik avtomatik yuborish (ertga 07:00 da Toshkent vaqtida)
    job_queue = app.job_queue
    job_queue.run_daily(
        send_daily_weather,
        time=time(hour=7, minute=0, second=0, tzinfo=ZoneInfo(TIMEZONE)),
        name="daily_weather",
    )

    print("Bot ishga tushdi. To'xtatish uchun Ctrl+C bosing.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()