import os
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Sozlamalar ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Joylashuv: Namangan viloyati, Kosonsoy tumani, Go'rmiron
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
WEATHER_TODAY = "🌤️ Bugun"
WEATHER_TOMORROW = "📅 Ertaga"
WEATHER_WEEK = "📊 1 Hafta"
WEATHER_HELP = "ℹ️ Yordam"


def get_main_keyboard():
    keyboard = [
        [KeyboardButton(WEATHER_TODAY)],
        [KeyboardButton(WEATHER_TOMORROW), KeyboardButton(WEATHER_WEEK)],
        [KeyboardButton(WEATHER_HELP)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# --- Ob-havo ma'lumotlarini olish ---
def get_weather_for_date(target_date: str):
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone={TIMEZONE}"
        f"&start_date={target_date}&end_date={target_date}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]
        idx = daily["time"].index(target_date)
        return {
            "date": target_date,
            "temp_max": daily["temperature_2m_max"][idx],
            "temp_min": daily["temperature_2m_min"][idx],
            "precip_prob": daily["precipitation_probability_max"][idx],
            "weather_desc": weather_code_to_text(daily["weathercode"][idx]),
        }
    except Exception as e:
        logger.error(f"Ob-havo olishda xatolik ({target_date}): {e}")
        return None


def get_forecast_week():
    today = datetime.now(ZoneInfo(TIMEZONE))
    end_date = (today + timedelta(days=6)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone={TIMEZONE}"
        f"&start_date={today_str}&end_date={end_date}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]
        forecast = []
        for i in range(len(daily["time"])):
            forecast.append({
                "date": daily["time"][i],
                "temp_max": daily["temperature_2m_max"][i],
                "temp_min": daily["temperature_2m_min"][i],
                "precip_prob": daily["precipitation_probability_max"][i],
                "weather_desc": weather_code_to_text(daily["weathercode"][i]),
            })
        return forecast
    except Exception as e:
        logger.error(f"Haftalik bashorat xatosi: {e}")
        return None


def weather_code_to_text(code: int) -> str:
    mapping = {
        0: "ochiq havo", 1: "anaqa ochiq", 2: "qisman bulutli", 3: "to'liq bulutli",
        45: "tuman", 48: "muruviy tuman", 51: "yengil yomg'ir", 53: "o'rtacha yomg'ir",
        55: "kuvvatli yomg'ir", 56: "yengil muzli yomg'ir", 57: "kuvvatli muzli yomg'ir",
        61: "yengil yomg'ir", 63: "o'rtacha yomg'ir", 65: "kuvvatli yomg'ir",
        66: "yengil muzli yomg'ir", 67: "kuvvatli muzli yomg'ir", 71: "yengil qor",
        73: "o'rtacha qor", 75: "kuvvatli qor", 77: "qorin qirralari",
        80: "yengil yomg'ir suvchi", 81: "o'rtacha yomg'ir suvchi", 82: "kuvvatli yomg'ir suvchi",
        85: "yengil qor suvchi", 86: "kuvvatli qor suvchi", 95: "g'iroli",
        96: "g'iroli, kichik qor bilan", 99: "g'iroli, katta qor bilan",
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
def build_weather_message(weather: dict, label: str) -> str:
    date_str = weather["date"]
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday_uz = {
        "Monday": "Dushanba", "Tuesday": "Seshanba", "Wednesday": "Chorshanba",
        "Thursday": "Payshanba", "Friday": "Juma", "Saturday": "Shanba", "Sunday": "Yakshanba",
    }.get(dt.strftime("%A"), dt.strftime("%A"))
    date_formatted = f"{dt.day}.{dt.month}.{dt.year}, {weekday_uz}"
    temp_max = weather["temp_max"]
    temp_min = weather["temp_min"]
    precip = weather["precip_prob"]
    desc = weather["weather_desc"]
    msg = f"{label}\n\n"
    msg += f"Sana: {date_formatted}\n"
    msg += f"Joy: {LOCATION_NAME}\n"
    msg += f"Ob-havo: {desc}\n"
    msg += f"Harorat: +{temp_min} … +{temp_max} °C\n"
    msg += f"Yomg'ir ehtimoli: {precip}%\n\n"
    if precip >= 40:
        msg += "⚠️ Yomg'ir ehtimoli yuqori. Sotib chiqishingiz mumkin!"
    elif precip >= 20:
        msg += "☔ Yomg'ir ehtimoli bor."
    else:
        msg += "✅ Ob-havo qulay."
    return msg


def build_week_message(forecast: list) -> str:
    msg = f"📊 1 Haftalik bashorat — {LOCATION_NAME}\n\n"
    for w in forecast:
        dt = datetime.strptime(w["date"], "%Y-%m-%d")
        weekday_uz = {
            "Monday": "Dushanba", "Tuesday": "Seshanba", "Wednesday": "Chorshanba",
            "Thursday": "Payshanba", "Friday": "Juma", "Saturday": "Shanba", "Sunday": "Yakshanba",
        }.get(dt.strftime("%A"), dt.strftime("%A"))
        date_formatted = f"{dt.day}.{dt.month}, {weekday_uz}"
        msg += f"{date_formatted}: {w['weather_desc']}, +{w['temp_min']}…+{w['temp_max']} °C, yomg'ir {w['precip_prob']}%\n"
    msg += "\n⚠️ Yomg'ir ehtimoli 40% dan yuqori kunlarda sotib chiqing!"
    return msg


# --- Telegram handlerlar ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers = load_subscribers()
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers(subscribers)
    await update.message.reply_text(
        "Ob-havo botiga xush kelibsiz! Har kuni ertalab 07:00 da ob-havo xabari keladi.\n"
        "To'xtatish uchun /stop bosing.\n\nQuyidagi tugmalardan birini bosing:",
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
    weather = get_weather_for_date(datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d"))
    if weather:
        await update.message.reply_text(
            build_weather_message(weather, "🌤️ Bugungi ob-havo"), reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("Xatolik yuz berdi.", reply_markup=get_main_keyboard())


async def tomorrow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tomorrow = (datetime.now(ZoneInfo(TIMEZONE)) + timedelta(days=1)).strftime("%Y-%m-%d")
    weather = get_weather_for_date(tomorrow)
    if weather:
        await update.message.reply_text(
            build_weather_message(weather, "📅 Ertangi ob-havo"), reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("Xatolik yuz berdi.", reply_markup=get_main_keyboard())


async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    forecast = get_forecast_week()
    if forecast:
        await update.message.reply_text(
            build_week_message(forecast), reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("Xatolik yuz berdi.", reply_markup=get_main_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Yordam\n\n"
        "/start — Botni ishga tushirish\n"
        "/stop — Obunadan chiqish\n"
        "/obhavo — Bugungi ob-havo\n"
        "/ertga — Ertangi ob-havo\n"
        "/hafta — 1 haftalik bashorat\n\n"
        "Tugmalar orqali ham foydalanishingiz mumkin.",
        reply_markup=get_main_keyboard()
    )


# --- Tugma handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == WEATHER_TODAY:
        await weather_cmd(update, context)
    elif text == WEATHER_TOMORROW:
        await tomorrow_cmd(update, context)
    elif text == WEATHER_WEEK:
        await week_cmd(update, context)
    elif text == WEATHER_HELP:
        await help_cmd(update, context)


# --- Kunlik avtomatik yuborish ---
async def send_daily_weather(context: ContextTypes.DEFAULT_TYPE):
    subscribers = load_subscribers()
    weather = get_weather_for_date(datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d"))
    if not weather:
        logger.error("Ob-havo olinmadi.")
        return
    text = build_weather_message(weather, "🌤️ Bugungi ob-havo")
    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=get_main_keyboard())
        except Exception as e:
            logger.error(f"Chat {chat_id} ga xatolik: {e}")


# --- Asosiy funksiya ---
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("XATO: .env faylida BOT_TOKEN ni kiriting!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("obhavo", weather_cmd))
    app.add_handler(CommandHandler("ertga", tomorrow_cmd))
    app.add_handler(CommandHandler("hafta", week_cmd))
    app.add_handler(CommandHandler("yordam", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    job_queue = app.job_queue
    job_queue.run_daily(
        send_daily_weather,
        time=time(hour=7, minute=0, second=0, tzinfo=ZoneInfo(TIMEZONE)),
        name="daily_weather",
    )
    print("Bot ishga tushdi.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()