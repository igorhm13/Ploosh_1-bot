import sqlite3
import datetime
import os

import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN не найден. Добавь переменную окружения TOKEN в Railway.")

# ---------- DATABASE ----------
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  name TEXT,
  honey_level INTEGER DEFAULT 1,
  hurt_level INTEGER DEFAULT 0,
  msg_count INTEGER DEFAULT 0,
  last_seen TEXT
)
""")
conn.commit()


def ensure_columns():
    cursor.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cursor.fetchall()}

    if "lat" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN lat REAL")
    if "lon" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN lon REAL")

    conn.commit()


ensure_columns()


def get_user(user_id: str):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, last_seen) VALUES (?, ?)",
            (user_id, datetime.datetime.now().isoformat())
        )
        conn.commit()
        return get_user(user_id)
    return user


def update_user(user_id: str, field: str, value):
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()


def update_location(user_id: str, lat: float, lon: float):
    cursor.execute(
        "UPDATE users SET lat=?, lon=?, last_seen=? WHERE user_id=?",
        (lat, lon, datetime.datetime.now().isoformat(), user_id)
    )
    conn.commit()


# ---------- PLUSH LOGIC ----------
def detect_rudeness(text: str) -> bool:
    rude_words = ["глуп", "туп", "бесполез"]
    t = text.lower()
    return any(word in t for word in rude_words)


def detect_name(text: str):
    t = text.lower()
    if "меня зовут" in t:
        return text.split()[-1]
    return None


# ---------- WEATHER ----------
WEATHER_CODES = {
    0: "ясно",
    1: "в основном ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "туман",
    51: "морось",
    61: "дождь",
    63: "дождь",
    65: "сильный дождь",
    71: "снег",
    80: "ливни",
    95: "гроза"
}


def code_to_text(code: int) -> str:
    return WEATHER_CODES.get(code, "какая-то сложная погода")


async def fetch_weather(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def location_keyboard():
    kb = [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)


# ---------- HANDLERS ----------
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    get_user(user_id)

    lat = update.message.location.latitude
    lon = update.message.location.longitude
    update_location(user_id, lat, lon)

    await update.message.reply_text("Запомнил твою геолокацию 🧸 Теперь могу говорить о погоде.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text or ""
    text_l = text.lower()

    user = get_user(user_id)

    # user tuple: user_id(0), name(1), honey(2), hurt(3), msg_count(4), last_seen(5), lat(6), lon(7)
    name = user[1]
    honey = user[2]
    hurt = user[3]
    msg_count = user[4]
    lat = user[6] if len(user) > 6 else None
    lon = user[7] if len(user) > 7 else None

    msg_count += 1
    update_user(user_id, "msg_count", msg_count)

    detected_name = detect_name(text)
    if detected_name:
        update_user(user_id, "name", detected_name)
        await update.message.reply_text(f"{detected_name}? Хорошее имя. Я запомню.")
        return

    if detect_rudeness(text):
        hurt = min(hurt + 1, 3)
        update_user(user_id, "hurt_level", hurt)
        await update.message.reply_text("Эй… Я всё-таки плюшевый. Полегче.")
        return

    if "привет" in text_l:
        if name:
            await update.message.reply_text(f"Привет, {name}. Я здесь.")
        else:
            await update.message.reply_text("Привет. Я Плюш 🧸")
        return

    if "кто ты" in text_l:
        await update.message.reply_text("Я плюшевый медвежонок. Немного цифровой.")
        return

    if "погода" in text_l or "сколько градусов" in text_l:
        if lat is None or lon is None:
            await update.message.reply_text(
                "Мне нужна твоя геолокация 🧸",
                reply_markup=location_keyboard()
            )
            return

        data = await fetch_weather(lat, lon)
        cur = data["current"]

        temp = cur["temperature_2m"]
        feels = cur["apparent_temperature"]
        wind = cur["wind_speed_10m"]
        desc = code_to_text(int(cur["weather_code"]))

        await update.message.reply_text(
            f"Сейчас {temp:.0f}°C (ощущается как {feels:.0f}°C), {desc}, ветер {wind:.0f} м/с.\n"
            f"Погода нормальная… если ты не сахар 🍯"
        )
        return

    await update.message.reply_text("Это звучит серьёзно для плюшевого существа.")


# ---------- RUN ----------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.LOCATION, handle_location))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Плюш запущен 🧸")
app.run_polling()
