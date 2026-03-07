import sqlite3
import datetime
import os
import random

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.ext import CallbackQueryHandler

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN не найден. Добавь переменную окружения TOKEN в Railway.")

# ---------- DATABASE ----------
conn = sqlite3.connect("users.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
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
    if "place" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN place TEXT")
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

def update_location(user_id: str, lat: float, lon: float, place: str = None):
    cursor.execute(
        "UPDATE users SET lat=?, lon=?, place=?, last_seen=? WHERE user_id=?",
        (lat, lon, place, datetime.datetime.now().isoformat(), user_id)
    )
    conn.commit()
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
def random_reply(options):
    return random.choice(options)


def is_thanks(text: str) -> bool:
    t = text.lower()
    return ("спасибо" in t) or ("благодарю" in t)


def is_praise(text: str) -> bool:
    t = text.lower()
    praise_words = ["молодец", "умница", "ты классный", "хороший бот", "ты хороший", "супер"]
    return any(word in t for word in praise_words)


def is_morning(text: str) -> bool:
    t = text.lower()
    return "доброе утро" in t


def is_night(text: str) -> bool:
    t = text.lower()
    return ("спокойной ночи" in t) or ("доброй ночи" in t)


def is_sad(text: str) -> bool:
    t = text.lower()
    return ("мне грустно" in t) or ("грустно" in t)


def is_tired(text: str) -> bool:
    t = text.lower()
    return ("я устал" in t) or ("я устала" in t) or ("устал" in t) or ("устала" in t)


def is_cold(text: str) -> bool:
    t = text.lower()
    return ("мне холодно" in t) or ("холодно" in t)


def is_hot(text: str) -> bool:
    t = text.lower()
    return ("мне жарко" in t) or ("жарко" in t)


def is_walk_question(text: str) -> bool:
    t = text.lower()
    return ("идти гулять" in t) or ("можно гулять" in t) or ("гулять?" in t)


def is_nice_weather_question(text: str) -> bool:
    t = text.lower()
    return ("приятная погода" in t) or ("хорошая погода" in t)

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

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print("fetch_weather failed:", e)
        return None

async def fetch_city(lat: float, lon: float):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 10,
        "addressdetails": 1
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)

        data = r.json()
        address = data.get("address", {})

        return (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("state")
        )

    except Exception as e:
        print("fetch_city error:", e)
        return None

        return results[0].get("name")

    except Exception as e:
        print("fetch_city error:", e)
        return None

        data = r.json()
        results = data.get("results") or []
        if not results:
            return None

        # Можно вернуть более “местно”:
        # name (поселок/район) чаще всего лучше чем "город"
        return results[0].get("name")

    except Exception as e:
        print("fetch_city error:", e)
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    if "results" in data and len(data["results"]) > 0:
        return data["results"][0]["name"]

    return None
    
def location_keyboard():
    kb = [[KeyboardButton("📍 Отправить геолокацию", request_location=True)]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    
def dress_advice_keyboard(mode= "now"):
    if mode == "tomorrow":
        keyboard = [
            [InlineKeyboardButton("👕 Как одеться завтра?", callback_data="dress_advice_tomorrow")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👕 Как одеться?", callback_data="dress_advice_now")]
        ]
    return InlineKeyboardMarkup(keyboard) 
    
def back_to_weather_keyboard(mode="now"):
    if mode == "tomorrow":
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к погоде", callback_data="back_weather_tomorrow")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к погоде", callback_data="back_weather_now")]
        ]

    return InlineKeyboardMarkup(keyboard)
    
def main_menu_keyboard():
    kb = [
        ["🌡 Погода сейчас", "📅 Погода завтра"],
        ["☔ Будет ли дождь?"],
        ["☀️ Утренние сообщения ВКЛ", "🌙 Утренние сообщения ВЫКЛ"],
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
        ["ℹ️ Помощь"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def plush_reply(update: Update, text: str):
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard()
    )


async def plush_reply_inline(update: Update, text: str, keyboard):
    await update.message.reply_text(
        text,
        reply_markup=keyboard
    )
    
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
    await update.message.reply_text( text, reply_markup=main_menu_keyboard())

async def handle_dress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode = query.data
    user_id = str(query.from_user.id)

    cursor.execute(
        "SELECT lat, lon FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row or row["lat"] is None or row["lon"] is None:
        await query.message.reply_text(
            "Мне нужна твоя геолокация 🧸",
            reply_markup=location_keyboard()
        )
        return

    lat = row["lat"]
    lon = row["lon"]

    data = await fetch_weather(lat, lon)
        if data is None:
            await update.message.reply_text(
                "Я не смог сейчас достучаться до погоды 🧸 Попробуй ещё раз через минуту.",
                reply_markup=main_menu_keyboard()
            )
            return
    if mode == "dress_advice_tomorrow":
        temp_max = data["daily"]["temperature_2m_max"][1]
        rain = data["daily"]["precipitation_probability_max"][1]
        temp_for_clothes = temp_max
        when_text = "Завтра"
    else:
        cur = data["current"]
        temp_now = cur["temperature_2m"]
        feels = cur["apparent_temperature"]
        rain = data["daily"]["precipitation_probability_max"][0]
        temp_for_clothes = feels if feels is not None else temp_now
        when_text = "Сейчас"

    if temp_for_clothes >= 28:
        advice = "Будет жарко — лучше что-то лёгкое: футболка, платье или рубашка с коротким рукавом."
    elif temp_for_clothes >= 22:
        advice = "Довольно тепло — подойдёт лёгкая одежда. На вечер можно взять тонкую накидку."
    elif temp_for_clothes >= 16:
        advice = "Нормально прохладно — лучше надеть что-то с длинным рукавом или лёгкую кофту."
    elif temp_for_clothes >= 10:
        advice = "Прохладно — я бы советовал куртку или тёплую кофту."
    else:
        advice = "Холодно — лучше тёплая куртка и что-то плотное."

    if rain >= 50:
        advice += " И захвати зонт ☔"

    await query.edit_message_text(
        f"👕 {when_text} лучше одеться так:\n\n{advice}",
        reply_markup=back_to_weather_keyboard(
            "tomorrow" if mode == "dress_advice_tomorrow" else "now"
        )
    )

async def handle_back_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)

    cursor.execute(
        "SELECT lat, lon, place FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row or row["lat"] is None or row["lon"] is None:
        await query.edit_message_text("Мне нужна твоя геолокация 🧸")
        return

    lat = row[0]
    lon = row[1]
    place = row[2]
    place_text = f"в {place} " if place else ""

    data = await fetch_weather(lat, lon)

    if query.data == "back_weather_tomorrow":
        d = data["daily"]
        tmax = d["temperature_2m_max"][1]
        tmin = d["temperature_2m_min"][1]
        p = d["precipitation_probability_max"][1]
        wcode = int(d["weather_code"][1])
        desc = code_to_text(wcode)

        await query.edit_message_text(
            f"Завтра {place_text}{desc}: {tmin:.0f}…{tmax:.0f}°C, шанс осадков {p}%.\n"
            f"Я бы взял зонт… но я мишка 🧸",
            reply_markup=dress_advice_keyboard("tomorrow")
        )
    else:
        cur = data["current"]
        temp = cur["temperature_2m"]
        feels = cur["apparent_temperature"]
        wind = cur["wind_speed_10m"]
        desc = code_to_text(int(cur["weather_code"]))

        await query.edit_message_text(
            f"Сейчас {place_text}{temp:.0f}°C (ощущается как {feels:.0f}°C), {desc}, ветер {wind:.0f} м/с.\n"
            f"Погода нормальная… если ты не сахар 🍯",
            reply_markup=dress_advice_keyboard("now")
        )
        
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
    await update.message.reply_text( text, reply_markup=main_menu_keyboard())
    
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    try:
        get_user(user_id)

        lat = update.message.location.latitude
        lon = update.message.location.longitude

        # пробуем получить place, но не даём этому сломать сохранение координат
        place = None
        try:
            place = await fetch_city(lat, lon)
        except Exception as e:
            print("fetch_city failed:", e)

        # ВАЖНО: сохраняем lat/lon даже если place=None
        try:
            update_location(user_id, lat, lon, place)
        except TypeError:
            # если у тебя update_location ещё старой сигнатуры (без place)
            update_location(user_id, lat, lon)

        await update.message.reply_text(
            "Запомнил твою геолокацию 🧸 Теперь могу говорить о погоде.",
            reply_markup=main_menu_keyboard() if "main_menu_keyboard" in globals() else None
        )

    except Exception as e:
        print("handle_location failed:", e)
        await update.message.reply_text(
            "Ой… я споткнулся, но уже встаю 🧸\n"
            "Попробуй отправить геолокацию ещё раз."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text or ""
    text_l = text.lower()

    user = get_user(user_id)

    cursor.execute(
    "SELECT name, honey_level, hurt_level, msg_count, lat, lon, place, morning_enabled "
    "FROM users WHERE user_id = ?",
    (user_id,)
    )

    row = cursor.fetchone()

    name = row["name"]
    honey = row["honey_level"]
    hurt = row["hurt_level"]
    msg_count = row["msg_count"]
    lat = row["lat"]
    lon = row["lon"]
    place = row["place"]
    morning_enabled = row["morning_enabled"]

    place_text = f"в {place} " if place else ""
    morning_enabled = morning_enabled or 0

    # данные пользователя из БД
    # name, honey_level, hurt_level, msg_count, lat, lon, place, morning_enabled

    msg_count += 1
    update_user(user_id, "msg_count", msg_count)

    detected_name = detect_name(text)
    if detected_name:
        update_user(user_id, "name", detected_name)
        await update.message.reply_text( f"{detected_name}? Хорошее имя. Я запомню.")
        return

    if detect_rudeness(text):
        hurt = min(hurt + 1, 3)
        update_user(user_id, "hurt_level", hurt)
        await update.message.reply_text( "Эй… Я всё-таки плюшевый. Полегче.")
        return

    if "привет" in text_l:
        if name:
            await update.message.reply_text( f"Привет, {name}. Я здесь.")
        else:
            await update.message.reply_text( "Привет. Я Плюш 🧸")
        return

    if "кто ты" in text_l:
        await update.message.reply_text( "Я плюшевый медвежонок. Немного цифровой.")
        return
        if is_thanks(text):
            honey = min(honey + 1, 10)
            update_user(user_id, "honey_level", honey)

            await update.message.reply_text( 
                random_reply([
                    "Пожалуйста 🧸",
                    "Всегда рад помочь 🧸",
                    "Для этого я тут и сижу, плюшевый и полезный."
                ])
            )
            return

    if is_praise(text):
        honey = min(honey + 1, 10)
        update_user(user_id, "honey_level", honey)

        await update.message.reply_text(
            random_reply([
                "Ой, мне приятно 🧸",
                "Я стараюсь изо всех сил.",
                "Плюш немного смутился, но доволен 🧸"
            ])
        )
        return

    if is_morning(text):
        await update.message.reply_text(
            random_reply([
                "Доброе утро 🧸 Пусть день будет мягким.",
                "Доброе утро 🧸 Надеюсь, сегодня без неприятного дождя.",
                "Доброе утро 🧸 Я уже готов говорить о погоде."
            ])
        )
        return

    if is_night(text):
        await update.message.reply_text(
            random_reply([
                "Спокойной ночи 🧸 Пусть завтра будет хорошая погода.",
                "Доброй ночи 🧸 Отдыхай, а я пока послежу за небом.",
                "Спокойной ночи 🧸 Плюш тоже уже почти спит."
            ])
        )
        return

    if is_sad(text):
        await update.message.reply_text(
            random_reply([
                "Мне жаль, что тебе грустно 🧸",
                "Иногда даже у плюшевых бывают тяжёлые дни 🧸",
                "Хочется, чтобы тебе стало чуть легче 🧸"
            ])
        )
        return

    if is_tired(text):
        await update.message.reply_text(
            random_reply([
                "Тогда тебе точно нужен отдых 🧸",
                "Похоже, день был тяжёлый. Побереги себя 🧸",
                "Усталость — серьёзная штука. Лучше немного выдохнуть 🧸"
            ])
        )
        return

    if is_cold(text):
        await update.message.reply_text(
            random_reply([
                "Тогда лучше что-то тёплое 🧸",
                "Я бы советовал кофту или куртку 🧸",
                "Если холодно — не геройствуй, утеплись 🧸"
            ])
        )
        return

    if is_hot(text):
        await update.message.reply_text(
            random_reply([
                "Тогда лучше что-то лёгкое 🧸",
                "Похоже, стоит одеться попроще и полегче.",
                "Если жарко — вода и лёгкая одежда будут хорошей идеей 🧸"
            ])
        )
        return

    if is_walk_question(text):
        await update.message.reply_text(
            "Могу подсказать 🧸 Напиши просто «погода» или «погода завтра», и будет понятнее, стоит ли идти гулять."
        )
        return

    if is_nice_weather_question(text):
        await update.message.reply_text(
            "Скажу точнее, если посмотрю погоду 🧸 Напиши «погода»."
        )
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
    # 👉 СОВЕТ ПО ОДЕЖДЕ
    if ("холодно" in text_l) or ("жарко" in text_l) or ("куртк" in text_l) or ("как одеться" in text_l):

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

        if feels <= 5:
            advice = "Очень холодно 🧊 Нужна тёплая куртка."
        elif feels <= 12:
            advice = "Прохладно 🧥 Лёгкая куртка будет кстати."
        elif feels <= 20:
            advice = "Нормальная температура 🙂 Можно без куртки."
        elif feels <= 27:
            advice = "Тепло ☀️ Идеально для лёгкой одежды."
        else:
            advice = "Жарко 🔥 Лучше что-нибудь очень лёгкое."
    
        await update.message.reply_text(
            f"Сейчас {temp:.0f}°C (ощущается как {feels:.0f}°C), {desc}, ветер {wind:.0f} м/с.\n"
            f"Погода нормальная… если ты не сахар 🍯",
            reply_markup=dress_advice_keyboard("now")
        )
        return   
    if ("погода" in text_l) or ("сколько градусов" in text_l) or ("дожд" in text_l) or ("зонт" in text_l):
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
                msg = f"{when.capitalize()} {place_text} вероятен дождь ☔ ({p_rain}%). {desc_d}. Зонт точно пригодится."
            elif p_rain >= 30:
                msg = f"{when.capitalize()} {place_text} возможен дождь 🌦 ({p_rain}%). {desc_d}. На всякий случай возьми зонт."
            else:
                msg = f"{when.capitalize()} {place_text} дождя почти не будет 🌤 ({p_rain}%). {desc_d}."

            await update.message.reply_text(msg)
            return
            
        # 👉 ЕСЛИ ЗАВТРА
        elif "завтра" in text_l:
            d = data["daily"]
            tmax = d["temperature_2m_max"][1]
            tmin = d["temperature_2m_min"][1]
            p = d["precipitation_probability_max"][1]
            wcode = int(d["weather_code"][1])
            desc_d = code_to_text(wcode)
             
            await update.message.reply_text(
                f"Завтра {place_text}{desc_d}: {tmin:.0f}…{tmax:.0f}°C, шанс осадков {p}%.\n"
                f"Я бы взял зонт… но я мишка 🧸",
                reply_markup=dress_advice_keyboard("tomorrow")
            )
            return

        # 👉 ИНАЧЕ — СЕЙЧАС
        else: 
            cur = data["current"]
            temp = cur["temperature_2m"]
            feels = cur["apparent_temperature"]
            wind = cur["wind_speed_10m"]
            desc = code_to_text(int(cur["weather_code"]))
        
            await update.message.reply_text(
                f"Сейчас {place_text}{temp:.0f}°C (ощущается как {feels:.0f}°C), {desc}, ветер {wind:.0f} м/с.\n"
                f"Погода нормальная… если ты не сахар 🍯",
                reply_markup=dress_advice_keyboard()
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
    await update.message.reply_text( "Напиши 'погода' или 'погода завтра' 🧸")
    return

async def cmd_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text( "Ок, отправь геолокацию заново 🧸", reply_markup=location_keyboard())

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
    cursor.execute("UPDATE users SET morning_enabled = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    await update.message.reply_text(
        "Теперь я буду писать тебе каждое утро 🧸☀️\n"
        "Если захочешь отключить — напиши /morning_off",
        reply_markup=main_menu_keyboard()
    )

async def morning_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cursor.execute("UPDATE users SET morning_enabled = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

    await update.message.reply_text(
        "Хорошо 🧸 Больше не буду писать по утрам.",
        reply_markup=main_menu_keyboard()
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
app.add_handler(CallbackQueryHandler(handle_dress_callback, pattern="^dress_advice_(now|tomorrow)$"))
app.add_handler(CallbackQueryHandler(handle_back_weather, pattern="^back_weather_(now|tomorrow)$"))
job_queue = app.job_queue
job_queue.run_daily(morning_weather, time=datetime.time(hour=8, minute=0))

print("Плюш запущен 🧸")
app.run_polling()








































