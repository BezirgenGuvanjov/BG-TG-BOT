import telebot
import schedule
import time
import json
import random
import threading
from datetime import datetime
import os
from flask import Flask

# =========== НАСТРОЙКИ ===========
TOKEN = "7772224219:AAHf0FnFFIz4aVZQI8tqp7V9U09zjJ029g4"
CHAT_ID = -1003004150175  # замените на ваш group id
WORDS_FILE = "words.json"
ACTIVITY_FILE = "activity.json"
POLL_INTERVAL_MINUTES = 30    # опросы каждые 30 минут
GOODNIGHT_HOUR = 22           # 22:00 "пора спать"
LEADERBOARD_HOUR_MIN = "21:30"
# =================================

bot = telebot.TeleBot(TOKEN)

# ------------------- Flask сервер -------------------
app = Flask(name)

@app.route("/")
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ------------------- Работа с файлами -------------------
def load_activity():
    if not os.path.exists(ACTIVITY_FILE):
        return {"users": {}}
    try:
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}

def save_activity(data):
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ------------------- Утилита для отображения -------------------
def display_and_mention(uid, user_rec):
    username = user_rec.get("username")
    first = user_rec.get("first_name", "")
    last = user_rec.get("last_name", "")
    if username:
        mention = "@" + username
        disp = username
    else:
        mention = f'<a href="tg://user?id={uid}">{first}</a>'
        disp = first + (" " + last if last else "")
    return disp, mention

# ------------------- Хэндлеры -------------------
@bot.message_handler(commands=["start"])
def handle_start(message):
    bot.reply_to(message, "👋 Бот работает!")

@bot.message_handler(func=lambda m: True)
def track_activity(message):
    if message.chat and message.chat.id == CHAT_ID:
        uid = str(message.from_user.id)
        data = load_activity()
        users = data.setdefault("users", {})
        rec = users.get(uid, {})
        rec["username"] = getattr(message.from_user, "username", None)
        rec["first_name"] = getattr(message.from_user, "first_name", "")
        rec["last_name"] = getattr(message.from_user, "last_name", "")
        rec["last_active"] = datetime.now().isoformat()
        rec["count"] = rec.get("count", 0) + 1
        users[uid] = rec
        save_activity(data)

# ------------------- Слова и опросы -------------------
if not os.path.exists(WORDS_FILE):
    raise SystemExit(f"Файл {WORDS_FILE} не найден.")
with open(WORDS_FILE, "r", encoding="utf-8") as f:
    words = json.load(f)

def get_random_word():
    return random.choice(words)

def send_word_and_quiz():
    word = get_random_word()
    text = f"🀄 Слово:\n{word['chinese']} — ({word['pinyin']})\nЗначение: {word['meaning']}"
    bot.send_message(CHAT_ID, text)
    send_quiz(word)

def send_quiz(word):
    question = f"Что означает {word['chinese']} ({word['pinyin']})?"
    correct = word["meaning"]
    options = [correct] + [w["meaning"] for w in random.sample(words, 3)]
    random.shuffle(options)
    correct_id = options.index(correct)
    bot.send_poll(CHAT_ID, question, options, type="quiz", correct_option_id=correct_id, is_anonymous=False)

# ------------------- Расписание -------------------
def check_who_awake():
    data = load_activity()
    users = data.get("users", {})
    now = datetime.now()
    today_22 = now.replace(hour=GOODNIGHT_HOUR, minute=0, second=0, microsecond=0)
    awake = []
    for uid, rec in users.items():
        last = rec.get("last_active")
        if last:
            t = datetime.fromisoformat(last)
            if t >= today_22:
                _, mention = display_and_mention(uid, rec)
                awake.append(mention)
    if awake:
        bot.send_message(CHAT_ID, f"😏 {' '.join(awake)} — зачем не спим?", parse_mode="HTML")
    else:
        bot.send_message(CHAT_ID, "😴 Все спят — никто не писал после 22:00.")

def send_leaderboard():
    data = load_activity()
    users = data.get("users", {})
    if not users:
        bot.send_message(CHAT_ID, "Сегодня никто не писал.")
        return
    sorted_users = sorted(users.items(), key=lambda it: it[1].get("count", 0), reverse=True)
    text = "🏆 Топ пользователей:\n" + "\n".join(
        [f"{i+1}. {display_and_mention(uid, rec)[0]} — {rec.get('count',0)} сообщений"
         for i, (uid, rec) in enumerate(sorted_users[:10])]
    )
    bot.send_message(CHAT_ID, text, parse_mode="HTML")

schedule.every(POLL_INTERVAL_MINUTES).minutes.do(send_word_and_quiz)
schedule.every().day.at("22:00").do(lambda: bot.send_message(CHAT_ID, "🌙 Уже 22:00 — пора отдыхать!"))
schedule.every().day.at("22:30").do(check_who_awake)
schedule.every().day.at(LEADERBOARD_HOUR_MIN).do(send_leaderboard)

# ------------------- Запуск -------------------
def start_polling():
    bot.infinity_polling(timeout=60)

if name == "main":
    print("Запуск бота и Flask...")

    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()

    # Запускаем polling в отдельном потоке
    threading.Thread(target=start_polling, daemon=True).start()

    # Основной цикл расписания
    while True:
        schedule.run_pending()
        time.sleep(1)
