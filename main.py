import sqlite3
import datetime
import os
from telegram.ext import CommandHandler

import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

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

    if "morning_enabled" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN morning_enabled INTEGER DEFAULT 0")

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
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "auto"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def location_keyboard():
    kb = [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

def main_menu_keyboard():
    kb = [
        ["🌡 Погода сейчас", "📅 Погода завтра"],
        ["☔ Будет ли дождь?"],
        ["☀️ Утренние сообщения ВКЛ", "🌙 Утренние сообщения ВЫКЛ"],
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
        ["ℹ️ Помощь"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)
    
# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Здравствуйте! 🧸\n\n"
        "Меня зовут Плюш.\n"
        "Я умею:\n"
        "• показать погоду сейчас\n"
        "• сказать прогноз на завтра\n"
        "• подсказать, будет ли дождь ☔\n\n"
        "Меня нужно только спросить — или нажать кнопку ниже.\n"
        "Пока что других вещей я не умею делать."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ Как спросить Плюша:\n\n"
        "Напиши или нажми кнопку:\n"
        "• погода / погода сейчас\n"
        "• погода завтра\n"
        "• будет ли дождь / нужен ли зонт\n\n"
        "Чтобы я ответил точно, мне нужна геолокация.\n"
        "Нажми «📍 Отправить геолокацию»."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())
    
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    get_user(user_id)

    lat = update.message.location.latitude
    lon = update.message.location.longitude
    update_location(user_id, lat, lon)

    await update.message.reply_text(
        "Запомнил твою геолокацию 🧸 Теперь могу говорить о погоде.",
        reply_markup=main_menu_keyboard()
        )


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

    if "помощь" in text_l:
        await help_cmd(update, context)
        return

        # кнопки управления утренними сообщениями
    if "утренние сообщения" in text_l and "вкл" in text_l:
        await morning_on(update, context)
        return

    if "утренние сообщения" in text_l and "выкл" in text_l:
        await morning_off(update, context)
        return
        
    if ("погода" in text_l) or ("сколько градусов" in text_l) or ("завтра" in text_l) or ("дожд" in text_l) or ("зонт" in text_l):
        if lat is None or lon is None:
            await update.message.reply_text(
                "Мне нужна твоя геолокация 🧸",
                reply_markup=location_keyboard()
            )
            return

        data = await fetch_weather(lat, lon)

        # 👉 БЫСТРЫЙ ОТВЕТ: БУДЕТ ЛИ ДОЖДЬ
        if ("дожд" in text_l) or ("зонт" in text_l):
            d = data["daily"]

            # если спрашивают про завтра — берём индекс 1, иначе сегодня — индекс 0
            day_idx = 1 if "завтра" in text_l else 0
            p_rain = d["precipitation_probability_max"][day_idx]
            wcode = int(d["weather_code"][day_idx])
            desc_d = code_to_text(wcode)

            when = "завтра" if day_idx == 1 else "сегодня"

            if p_rain >= 60:
                msg = f"{when.capitalize()} вероятен дождь ☔ ({p_rain}%). {desc_d}. Зонт точно пригодится."
            elif p_rain >= 30:
                msg = f"{when.capitalize()} возможен дождь 🌦 ({p_rain}%). {desc_d}. На всякий случай возьми зонт."
            else:
                msg = f"{when.capitalize()} дождя почти не будет 🌤 ({p_rain}%). {desc_d}."

            await update.message.reply_text(msg)
            return
            
        # 👉 ЕСЛИ ЗАВТРА
        if "завтра" in text_l:
            d = data["daily"]
            tmax = d["temperature_2m_max"][1]
            tmin = d["temperature_2m_min"][1]
            p = d["precipitation_probability_max"][1]
            wcode = int(d["weather_code"][1])
            desc_d = code_to_text(wcode)

            await update.message.reply_text(
                f"Завтра {desc_d}: {tmin:.0f}…{tmax:.0f}°C, шанс осадков {p}%.\n"
                f"Я бы взял зонт… но я мишка 🧸"
            )
            return

        # 👉 ИНАЧЕ — СЕЙЧАС
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


        await update.message.reply_text(
        "Я пока не понял запрос 🧸\n\n"
        "Попробуй так:\n"
        "• погода\n"
        "• погода завтра\n"
        "• будет ли дождь\n\n"
        "Или нажми кнопку внизу.",
        reply_markup=main_menu_keyboard()
    )
async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши 'погода' или 'погода завтра' 🧸")
    return


async def cmd_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ок, отправь геолокацию заново 🧸", reply_markup=location_keyboard())

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = get_user(user_id)
    name = user[1]
    honey = user[2]
    hurt = user[3]
    lat = user[6] if len(user) > 6 else None
    lon = user[7] if len(user) > 7 else None

    loc = "есть ✅" if (lat is not None and lon is not None) else "нет ❌"
    
    morning_enabled = user[8] if len(user) > 8 and user[8] is not None else 0
    morning_text = "включены ☀️" if int(morning_enabled) == 1 else "выключены 🌙"

    await update.message.reply_text(
        f"Статус Плюша 🧸\n"
        f"Имя: {name or 'не знаю'}\n"
        f"Геолокация: {loc}\n"
        f"Утренние сообщения: {morning_text}\n"
        f"🍯 Уровень мёда: {honey}\n"
        f"🙃 Обида: {hurt}"
    )

async def morning_weather(context: ContextTypes.DEFAULT_TYPE):
    with db_lock:
        cursor.execute("""
            SELECT user_id, lat, lon
            FROM users
            WHERE lat IS NOT NULL
              AND lon IS NOT NULL
              AND morning_enabled = 1
        """)
    users = cursor.fetchall()

    for user_id, lat, lon in users:
        try:
            data = await fetch_weather(lat, lon, need="daily")

            d = data["daily"]
            tmax = d["temperature_2m_max"][0]
            tmin = d["temperature_2m_min"][0]
            rain = d["precipitation_probability_max"][0]
            desc = code_to_text(int(d["weather_code"][0]))

            if rain >= 60:
                rain_text = "☔ вероятен дождь"
            elif rain >= 30:
                rain_text = "🌦 возможен дождь"
            else:
                rain_text = "🌤 дождя почти не будет"

            msg = (
                f"Доброе утро 🧸\n\n"
                f"Сегодня {desc}\n"
                f"{tmin:.0f}…{tmax:.0f}°C\n"
                f"{rain_text} ({rain}%)"
            )

            await context.bot.send_message(chat_id=user_id, text=msg)

        except Exception as e:
            print("Ошибка утреннего прогноза:", e)

async def morning_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    with db_lock:
        cursor.execute(
            "UPDATE users SET morning_enabled = 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

    await update.message.reply_text(
        "Теперь я буду писать тебе каждое утро 🧸☀️\n"
        "Если захочешь отключить — напиши /morning_off"
    )


async def morning_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    with db_lock:
        cursor.execute(
            "UPDATE users SET morning_enabled = 0 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

    await update.message.reply_text(
        "Хорошо 🧸 Больше не буду писать по утрам."
    )
    
# ---------- RUN ----------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(MessageHandler(filters.LOCATION, handle_location))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("weather", cmd_weather))
app.add_handler(CommandHandler("location", cmd_location))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("morning_on", morning_on))
app.add_handler(CommandHandler("morning_off", morning_off))

job_queue = app.job_queue
job_queue.run_daily(morning_weather, time=datetime.time(hour=8, minute=0))

print("Плюш запущен 🧸")
app.run_polling()








