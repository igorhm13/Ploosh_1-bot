import sqlite3
import datetime
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TOKEN")

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

def get_user(user_id):
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

def update_user(user_id, field, value):
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()

def detect_rudeness(text):
    rude_words = ["глуп", "туп", "бесполез"]
    return any(word in text.lower() for word in rude_words)

def detect_name(text):
    if "меня зовут" in text.lower():
        return text.split()[-1]
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    user = get_user(user_id)
    name, honey, hurt, msg_count = user[1], user[2], user[3], user[4]

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

    if "привет" in text.lower():
        if name:
            await update.message.reply_text(f"Привет, {name}. Я здесь.")
        else:
            await update.message.reply_text("Привет. Я Плюш 🧸")
        return

    if "кто ты" in text.lower():
        await update.message.reply_text("Я плюшевый медвежонок. Немного цифровой.")
        return

    await update.message.reply_text("Это звучит серьёзно для плюшевого существа.")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Плюш запущен 🧸")
app.run_polling()