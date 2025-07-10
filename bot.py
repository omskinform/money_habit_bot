import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# -------------------------------------------------------------------
# Конфиг
# -------------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")  # берётся из GitHub Secrets

TASKS_FILE = "tasks.json"
USERS_FILE = "users.json"

# -------------------------------------------------------------------
# Логирование
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Утилиты для работы с JSON
# -------------------------------------------------------------------
def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -------------------------------------------------------------------
# Хендлеры Telegram-команд
# -------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    if uid not in users:
        users[uid] = {"day": 0, "goal": None, "completed_days": []}
        save_json(USERS_FILE, users)
    await update.message.reply_text(
        "Привет! Я бот «Привычка копить». Каждый день в 9:00 МСК "
        "я пришлю тебе новое задание.\n\n"
        "Доступные команды:\n"
        "/next — получить текущее задание\n"
        "/progress — узнать прогресс\n"
        "/goal <сумма> — установить финансовую цель\n"
        "/reset — сбросить прогресс"
    )

async def next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    tasks = load_json(TASKS_FILE)
    day = users[uid]["day"]
    if day < len(tasks):
        text = tasks[day]
        users[uid]["day"] += 1
    else:
        text = "🎉 Вы успешно прошли все 21 задание!"
    save_json(USERS_FILE, users)
    await update.message.reply_text(text)

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    total = len(load_json(TASKS_FILE))
    day = users[uid]["day"]
    done = len(users[uid]["completed_days"])
    bar = "🟩" * done + "⬜" * (total - done)
    await update.message.reply_text(
        f"Вы на дне {day} из {total}\nПрогресс:\n{bar} {done}/{total}"
    )

async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    args = context.args
    if not args or not args[0].isdigit():
        return await update.message.reply_text("Используйте: /goal 50000")
    goal = int(args[0])
    users = load_json(USERS_FILE)
    users[uid]["goal"] = goal
    save_json(USERS_FILE, users)
    await update.message.reply_text(f"Цель установлена: {goal} ₽.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    users[uid] = {"day": 0, "goal": None, "completed_days": []}
    save_json(USERS_FILE, users)
    await update.message.reply_text("Прогресс сброшен.")

# -------------------------------------------------------------------
# Хендлер для кнопок «✅ Сделано» / «❌ Не сделано»
# -------------------------------------------------------------------
async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.message.chat.id)
    data = query.data  # 'done' или 'skip'
    users = load_json(USERS_FILE)
    day = users[uid]["day"]
    if data == "done" and day not in users[uid]["completed_days"]:
        users[uid]["completed_days"].append(day)
    save_json(USERS_FILE, users)
    result = "✅ Сделано" if data == "done" else "❌ Не сделано"
    await query.edit_message_text(f"{query.message.text}\n\nВы ответили: {result}")

# -------------------------------------------------------------------
# Авто‑задачи планировщика
# -------------------------------------------------------------------
async def send_daily():
    """Утренняя рассылка нового задания в 9:00 МСК (06:00 UTC)."""
    users = load_json(USERS_FILE)
    tasks = load_json(TASKS_FILE)
    global app
    for uid, info in users.items():
        day = info["day"]
        if day < len(tasks):
            try:
                await app.bot.send_message(chat_id=int(uid), text=tasks[day])
                users[uid]["day"] += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке задания {uid}: {e}")
    save_json(USERS_FILE, users)

async def send_reminder():
    """Вечернее напоминание в 21:00 МСК (18:00 UTC)."""
    users = load_json(USERS_FILE)
    global app
    for uid, info in users.items():
        day = info["day"]
        if day < len(load_json(TASKS_FILE)):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Сделано", callback_data="done"),
                InlineKeyboardButton("❌ Не сделано", callback_data="skip")
            ]])
            try:
                await app.bot.send_message(
                    chat_id=int(uid),
                    text=f"Напоминание: вы сделали задание дня {day}?",
                    reply_markup=kb
                )
            except Exception:
                pass

async def send_progress_report():
    """Отчёт прогресса в дни 7, 14 и 21 в 09:05 МСК (06:05 UTC)."""
    users = load_json(USERS_FILE)
    total = len(load_json(TASKS_FILE))
    global app
    for uid, info in users.items():
        day = info["day"]
        if day in (7, 14, 21):
            done = len(info["completed_days"])
            bar = "🟩" * done + "⬜" * (total - done)
            try:
                await app.bot.send_message(
                    chat_id=int(uid),
                    text=f"Итоги за {day} дней:\n{bar} {done}/{total}"
                )
            except Exception:
                pass

# -------------------------------------------------------------------
# Основная точка входа
# -------------------------------------------------------------------
if __name__ == "__main__":
    # создаём приложение
    app = ApplicationBuilder().token(TOKEN).build()

    # регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_task))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("goal", set_goal))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(answer_callback))

    # настраиваем планировщик
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily, CronTrigger(hour=6,  minute=0))  # 09:00 МСК
    scheduler.add_job(send_reminder, CronTrigger(hour=18, minute=0))  # 21:00 МСК
    scheduler.add_job(send_progress_report, CronTrigger(hour=6, minute=5))  # 09:05 МСК
    scheduler.start()

    # запускаем бот
    app.run_polling()
