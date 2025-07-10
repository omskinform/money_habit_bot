import json, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

TOKEN = "7701942495:AAHVh5ON1pp5ttuAWMpnLap737elNQb-9iw"
TASKS_FILE = "tasks.json"
USERS_FILE = "users.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    if uid not in users:
        users[uid] = {"day": 0, "goal": None, "completed_days": []}
        save_json(USERS_FILE, users)
    await update.message.reply_text(
        "Привет! Я бот «Привычка копить». Каждый день я буду присылать тебе задание.\n"
        "Команды:\n"
        "/next — взять задание\n"
        "/progress — твой прогресс\n"
        "/goal <сумма> — установить цель\n"
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
        text = "🎉 Все задания пройдены!"
    save_json(USERS_FILE, users)
    await update.message.reply_text(text)

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    day = users[uid]["day"]
    done = len(users[uid]["completed_days"])
    total = len(load_json(TASKS_FILE))
    bar = "🟩"*done + "⬜"*(total-done)
    await update.message.reply_text(
        f"День {day} из {total}\nПрогресс: {bar} {done}/{total}"
    )

async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    args = context.args
    if not args or not args[0].isdigit():
        return await update.message.reply_text("Используйте: /goal 50000")
    users = load_json(USERS_FILE)
    users[uid]["goal"] = int(args[0])
    save_json(USERS_FILE, users)
    await update.message.reply_text(f"Цель установлена: {args[0]} ₽.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = load_json(USERS_FILE)
    users[uid] = {"day": 0, "goal": None, "completed_days": []}
    save_json(USERS_FILE, users)
    await update.message.reply_text("Прогресс сброшен.")

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
    await query.edit_message_text(
        f"{query.message.text}\n\nВы ответили: {'✅ Сделано' if data=='done' else '❌ Не сделано'}"
    )

async def send_daily(context: ContextTypes.DEFAULT_TYPE):
    users = load_json(USERS_FILE)
    tasks = load_json(TASKS_FILE)
    for uid, info in users.items():
        day = info["day"]
        if day < len(tasks):
            try:
                await context.bot.send_message(chat_id=int(uid), text=tasks[day])
                users[uid]["day"] += 1
            except Exception as e:
                logger.error(f"Error {uid}: {e}")
    save_json(USERS_FILE, users)
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    users = load_json(USERS_FILE)
    for uid, info in users.items():
        day = info["day"]
        if day < len(load_json(TASKS_FILE)):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Сделано", callback_data="done"),
                InlineKeyboardButton("❌ Не сделано", callback_data="skip")
            ]])
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"Напоминание: вы сделали задание дня {day}?",
                    reply_markup=kb
                )
            except:
                pass

async def send_progress_report(context: ContextTypes.DEFAULT_TYPE):
    users = load_json(USERS_FILE)
    total = len(load_json(TASKS_FILE))
    for uid, info in users.items():
        day = info["day"]
        if day in (7,14,21):
            done = len(info["completed_days"])
            bar = "🟩"*done + "⬜"*(total-done)
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"Итоги за {day} дней:\n{bar} {done}/{total}"
            )

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_task))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("goal", set_goal))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(answer_callback))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily, CronTrigger(hour=6, minute=0))        # 09:00 МСК
    scheduler.add_job(send_reminder, CronTrigger(hour=18, minute=0))    # 21:00 МСК
    scheduler.add_job(send_progress_report, CronTrigger(hour=6, minute=5))  
    scheduler.start()

    app.run_polling()
