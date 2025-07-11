import logging
import os
import json
import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Логгер
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(name)

# Загрузка токена
TOKEN = os.getenv("TOKEN")

# Загрузка заданий из tasks.json
with open("tasks.json", "r", encoding="utf-8") as f:
    daily_tasks = json.load(f)

# Файл хранения данных пользователей
USER_DATA_FILE = "user_data.json"

# Загрузка пользовательских данных
def load_user_data():
    if not os.path.exists(USER_DATA_FILE):
        return {}
    with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Сохранение пользовательских данных
def save_user_data(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

user_data = load_user_data()

# Прогресс-бар
def get_progress_bar(day):
    total = len(daily_tasks)
    bar = "🟩" * day + "⬜" * (total - day)
    return f"{bar} ({day}/{total})"

# Обработка /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_data:
        user_data[user_id] = {"day": 0, "completed": [], "goal": None}
        save_user_data(user_data)
    keyboard = [["/next", "/progress"], ["/reset", "/goal 50000"]]
    await update.message.reply_text(
        "Добро пожаловать в челлендж «Привычка копить»!\nНажимай /next, чтобы получить первое задание.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )

# Обработка /next
async def next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = user_data.get(user_id, {"day": 0, "completed": [], "goal": None})
    if data["day"] >= len(daily_tasks):
        await update.message.reply_text("🎉 Челлендж завершён! Ты прошёл все 21 день!")
        return
    task = daily_tasks[data["day"]]
    await update.message.reply_text(f"{task}")
    data["day"] += 1
    data["completed"].append(True)
    user_data[user_id] = data
    save_user_data(user_data)

# Обработка /progress
async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = user_data.get(user_id, {"day": 0, "completed": [], "goal": None})
    day = data["day"]
    bar = get_progress_bar(day)
    await update.message.reply_text(f"📊 Прогресс:\n{bar}")

# Обработка /goal
async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    try:
        goal = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Используйте: /goal 50000")
        return
    user_data[user_id]["goal"] = goal
    save_user_data(user_data)
    await update.message.reply_text(f"✅ Цель установлена: {goal} руб.")

# Обработка /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data[user_id] = {"day": 0, "completed": [], "goal": None}
    save_user_data(user_data)
    await update.message.reply_text("🔄 Прогресс сброшен. Начни заново с /next")

# Вечернее напоминание (Да/Нет)
async def evening_check(context: ContextTypes.DEFAULT_TYPE):
    for user_id in user_data:
        await context.bot.send_message(
            chat_id=int(user_id),
            text="🔔 Напоминание: ты выполнил задание дня?\nНажми /next, если ещё нет.",
        )

# Плановая отправка прогресса (на 7, 14, 21 дни)
async def scheduled_progress(context: ContextTypes.DEFAULT_TYPE):
    for user_id, data in user_data.items():
        day = data.get("day", 0)
        if day in [7, 14, 21]:
            bar = get_progress_bar(day)
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"📈 Ты уже прошёл {day} дней!\nВот твой прогресс:\n{bar}",
            )

# Запуск
if name == "main":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_task))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("goal", set_goal))
    app.add_handler(CommandHandler("reset", reset))

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: app.create_task(evening_check(app.bot)),
        CronTrigger(hour=17, minute=0),  # По UTC, 20:00 МСК
    )
    scheduler.add_job(
        lambda: app.create_task(scheduled_progress(app.bot)),
        CronTrigger(hour=6, minute=0),  # 09:00 МСК
    )
    scheduler.start()

    print("Бот запущен.")
    app.run_polling()
