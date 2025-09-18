# chinese_bot_advanced.py
import telebot
import schedule
import time
import json
import random
import threading
from datetime import datetime, timedelta
import os

# =========== НАСТРОЙКИ ===========
TOKEN = "7772224219:AAHf0FnFFIz4aVZQI8tqp7V9U09zjJ029g4"
CHAT_ID = -1003004150175  # замените на ваш group id
WORDS_FILE = "words.json"
ACTIVITY_FILE = "activity.json"
POLL_INTERVAL_MINUTES = 60    # опросы каждые 30 минут
GOODNIGHT_HOUR = 22         # 22:00 "пора спать"
CHECK_AWAKE_MIN_AFTER_22 = 30 # в 22:30 проверяем активность после 22:00 (30 минут)
LEADERBOARD_HOUR_MIN = "21:30" # формат "HH:MM" для leaderboard
# =================================

bot = telebot.TeleBot(TOKEN)

# Загружаем слова
if not os.path.exists(WORDS_FILE):
    raise SystemExit(f"Файл {WORDS_FILE} не найден. Создайте words.json рядом со скриптом.")
with open(WORDS_FILE, "r", encoding="utf-8") as f:
    words = json.load(f)
if not isinstance(words, list) or len(words) < 3:
    raise SystemExit("words.json должен быть списком объектов с полями chinese,pinyin,meaning (минимум 3 записи).")

# --- Утилиты для активности (persist в activity.json) ---
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

# возвращает отображаемое имя и mention HTML
def display_and_mention(uid, user_rec):
    username = user_rec.get("username")
    first = user_rec.get("first_name", "")
    last = user_rec.get("last_name", "")
    disp = username or (first + (" " + last if last else ""))
    # упоминание: если есть username — можно @username, иначе tg://user?id
    if username:
        mention = "@" + username
    else:
        mention = f'<a href="tg://user?id={uid}">{first}</a>'
    return disp, mention

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def handle_start(message):
    bot.reply_to(message, "👋 Бот работает! Я буду присылать слова и проводить опросы. Используй /leaderboard чтобы увидеть топ активных.")

@bot.message_handler(commands=["leaderboard", "top"])
def cmd_leaderboard(message):
    data = load_activity()
    users = data.get("users", {})
    if not users:
        bot.reply_to(message, "Пока нет данных о активности.")
        return
    # сортируем по count
    sorted_users = sorted(users.items(), key=lambda it: it[1].get("count", 0), reverse=True)
    lines = []
    for i, (uid, rec) in enumerate(sorted_users[:10], start=1):
        disp, _ = display_and_mention(uid, rec)
        cnt = rec.get("count", 0)
        lines.append(f"{i}. {disp} — {cnt} сообщений")
    text = "🏆 Топ активных пользователей:\n" + "\n".join(lines)
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=["send_now"])
def cmd_send_now(message):
    send_word_and_quiz()
    bot.reply_to(message, "Отправил слово и опрос (тест).")

@bot.message_handler(func=lambda m: True)
def track_activity(message):
    # фиксируем только сообщения из нужной группы
    if message.chat is None:
        return
    if message.chat.id != CHAT_ID:
        return
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
    # (не отвечаем — просто отслеживаем)

# --- Функции для опроса / слова ---
def get_random_word():
    return random.choice(words)

def send_word_and_quiz():
    word = get_random_word()
    try:
        text = f"🀄 Слово:\n{word['chinese']} — ({word.get('pinyin','')})\nЗначение: {word.get('meaning','')}"
        bot.send_message(CHAT_ID, text, parse_mode='HTML')
    except Exception as e:
        print("Ошибка отправки слова:", e)
    # отправляем опрос/quiz
    send_quiz(word)

def send_quiz(word):
    # тип вопроса: pinyin, meaning или chinese
    qtype = random.choice(["pinyin", "meaning", "chinese"])
    try:
        if qtype == "pinyin":
            question = f"Какой пиньин у слова {word['chinese']}?"
            correct = word.get("pinyin", "")
            pool = [w.get("pinyin","") for w in words if w.get("pinyin","") and w.get("pinyin","") != correct]
        elif qtype == "chinese":
            question = f"Какой иероглиф соответствует значению '{word.get('meaning','')}'?"
            correct = word.get("chinese", "")
            pool = [w.get("chinese","") for w in words if w.get("chinese","") and w.get("chinese","") != correct]
        else:
            question = f"Что означает слово {word['chinese']} ({word.get('pinyin','')})?"
            correct = word.get("meaning", "")
            pool = [w.get("meaning","") for w in words if w.get("meaning","") and w.get("meaning","") != correct]

        # набираем варианты (3 варианта-отвлекающие + 1 правильный)
        options = []
        # если не хватает элементов в pool, уменьшаем число отвлечений
        k = min(3, len(pool))
        if k > 0:
            distractors = random.sample(pool, k)
            options = distractors + [correct]
        else:
            # мало слов — делаем простую пару
            options = [correct]

        # ensure uniqueness
        options = list(dict.fromkeys(options))
        random.shuffle(options)
        correct_id = options.index(correct)

        # отправляем quiz (неанонимный)
        bot.send_poll(CHAT_ID, question, options, type='quiz', correct_option_id=correct_id, is_anonymous=False)
    except Exception as e:
        print("Ошибка при создании опроса:", e)
        # fallback: отправляем просто текст с ответом
        try:
            bot.send_message(CHAT_ID, f"Ошибка при создании опроса. Правильный ответ: {correct}")
        except:
            pass

# --- check_who_awake: в 22:30 отмечаем тех, кто писал после 22:00 ---
def check_who_awake():
    data = load_activity()
    users = data.get("users", {})
    if not users:
        bot.send_message(CHAT_ID, "Никто не писал сегодня.")
        return

    now = datetime.now()
    # начало сегодняшних 22:00
    today_22 = now.replace(hour=GOODNIGHT_HOUR, minute=0, second=0, microsecond=0)
    # если сейчас до 22:30, берем last 30 минут иначе — смотрим после 22:00
    # но по заданию: в 22:30 проверяем, кто писал после 22:00
    awake = []
    for uid, rec in users.items():
        last = rec.get("last_active")
        if not last:
            continue
        try:
            t = datetime.fromisoformat(last)
        except Exception:
            continue
        if t >= today_22:
            disp, mention = display_and_mention(uid, rec)
            awake.append((uid, disp, mention, t))

    if not awake:
        bot.send_message(CHAT_ID, "😴 Все спят — никто не писал после 22:00.")
        return

    # отправляем одному сообщением список упоминаний + текст
    mentions = " ".join(a[2] for a in awake)
    msg = f"😏 {mentions} — эх, кто не спит? Зачем не спим?"
    try:
        bot.send_message(CHAT_ID, msg, parse_mode='HTML')
    except Exception as e:
        print("Ошибка отправки check_who_awake:", e)

# --- leaderboard (топ активных) ---
def send_leaderboard():
    data = load_activity()
    users = data.get("users", {})
    if not users:
        bot.send_message(CHAT_ID, "Никто не писал пока, топ пуст.")
        return
    sorted_users = sorted(users.items(), key=lambda it: it[1].get("count", 0), reverse=True)
    lines = []
    for i, (uid, rec) in enumerate(sorted_users[:10], start=1):
        disp, mention = display_and_mention(uid, rec)
        cnt = rec.get("count", 0)
        lines.append(f"{i}. {mention} — {cnt} сообщений")
    text = "🏆 Ежедневный рейтинг активности:\n" + "\n".join(lines)
    try:
        bot.send_message(CHAT_ID, text, parse_mode='HTML')
    except Exception as e:
        print("Ошибка отправки leaderboard:", e)

# ========== Запуск polling в отдельном потоке & расписание ==========
def start_polling_thread():
    # запускаем polling в отдельном потоке, чтобы не блокировать schedule loop
    polling_thread = threading.Thread(target=bot.infinity_polling, kwargs={"timeout": 60})
    polling_thread.daemon = True
    polling_thread.start()

# Расписание
schedule.every(POLL_INTERVAL_MINUTES).minutes.do(send_word_and_quiz)
# "пора спать" в 22:00
schedule.every().day.at(f"{GOODNIGHT_HOUR:02d}:00").do(lambda: bot.send_message(CHAT_ID, "🌙 Уже 22:00 — пора отдыхать!"))
# в 22:30 — check who awake (те, кто писал после 22:00)
# вычисляем строку "22:30"
schedule.every().day.at(f"{GOODNIGHT_HOUR:02d}:30").do(check_who_awake)
# leaderboard в 21:30 (LEADERBOARD_HOUR_MIN может быть "21:30")
schedule.every().day.at(LEADERBOARD_HOUR_MIN).do(send_leaderboard)

if __name__ == "__main__":
    print("Стартую бота...")
    # стартуем polling
    start_polling_thread()
    # оповестим группу, что бот включился (попробуем, но может упасть если не настроен CHAT_ID)
    try:
        bot.send_message(CHAT_ID, "✅ Бот включён и слушает чат. Для проверки используйте /start и /leaderboard", parse_mode='HTML')
    except Exception as e:
        print("Не смог отправить стартовое сообщение в чат — проверьте CHAT_ID и права бота:", e)

    # основной цикл расписания
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print("Ошибка в schedule:", e)
        time.sleep(1)
