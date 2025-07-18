import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
import sqlite3
from datetime import datetime


# Настройки бота
with open('token.txt') as file:
    TOKEN = file.readline()
    
GROUP_CHAT_ID = -4802024453  # Замените на ID вашей группы (должен начинаться с -)

ADMIN_IDS = [1007591028]  # ID администраторовм

# Состояния для ConversationHandler
REGISTER_NAME, MODERATION = range(2)

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                      (user_id INTEGER PRIMARY KEY,
                       username TEXT,
                       full_name TEXT,
                       registration_date TEXT,
                       is_approved INTEGER DEFAULT 0,
                       points INTEGER DEFAULT 0)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS photos
                      (photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       file_id TEXT,
                       sent_date TEXT,
                       status TEXT DEFAULT 'pending',
                       moderator_id INTEGER,
                       decision_date TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
                      (transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       amount INTEGER,
                       admin_id INTEGER,
                       date TEXT,
                       reason TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Функции работы с БД
def add_user(user_id, username, full_name):
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, registration_date) VALUES (?, ?, ?, ?)",
                   (user_id, username, full_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def approve_user(user_id, admin_id):
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_approved = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return f"Пользователь {user_id} одобрен администратором {admin_id}"

def add_points(user_id, amount, admin_id=None, reason=""):
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    
    # Добавляем баллы
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    
    # Записываем транзакцию
    if admin_id:
        cursor.execute("INSERT INTO transactions (user_id, amount, admin_id, date, reason) VALUES (?, ?, ?, ?, ?)",
                      (user_id, amount, admin_id, datetime.now().isoformat(), reason))
    
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, full_name, is_approved, points FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_user_transactions(user_id, limit=5):
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('''SELECT t.date, t.amount, t.reason, u.username 
                      FROM transactions t
                      LEFT JOIN users u ON t.admin_id = u.user_id
                      WHERE t.user_id = ?
                      ORDER BY t.date DESC
                      LIMIT ?''', (user_id, limit))
    result = cursor.fetchall()
    conn.close()
    return result

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_info = get_user_info(user.id)
    
    if user_info is None:
        await update.message.reply_text(
            "Добро пожаловать! Для использования бота необходимо зарегистрироваться.\n"
            "Пожалуйста, отправьте ваше ФИО (полное имя) для регистрации."
        )
        return REGISTER_NAME
    elif user_info[3] == 0:
        await update.message.reply_text(
            "Ваша регистрация еще не одобрена администратором. Пожалуйста, подождите."
        )
    else:
        await show_profile(update, context)
    return ConversationHandler.END

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_info = get_user_info(user.id)
    transactions = get_user_transactions(user.id)
    
    if not user_info:
        await update.message.reply_text("Вы не зарегистрированы. Используйте /start")
        return
    
    message = (
        f"👤 Ваш профиль:\n"
        f"🆔 ID: {user_info[0]}\n"
        f"📛 ФИО: {user_info[2]}\n"
        f"⭐ Баллы: {user_info[4]}\n\n"
        f"📊 Последние операции:\n"
    )
    
    for trans in transactions:
        admin = f"@{trans[3]}" if trans[3] else "система"
        message += f"{trans[0][:10]}: {'+' if trans[1] > 0 else ''}{trans[1]} баллов ({admin})"
        if trans[2]:
            message += f" - {trans[2]}\n"
        else:
            message += "\n"
    
    await update.message.reply_text(message)

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    full_name = update.message.text
    
    conn = sqlite3.connect('data/bot_db.sqlite')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, full_name, registration_date, is_approved) VALUES (?, ?, ?, ?, 0)",
                  (user.id, user.username, full_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_user_{user.id}"),
         InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_user_{user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id= -4802024453,
        text=f"Новый пользователь хочет зарегистрироваться:\n"
             f"ID: {user.id}\n"
             f"Username: @{user.username}\n"
             f"ФИО: {full_name}",
        reply_markup=reply_markup
    )
    
    await update.message.reply_text("Ваша регистрация отправлена на модерацию. Вы получите уведомление, когда администратор ее рассмотрит.")
    return ConversationHandler.END

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_info = get_user_info(user.id)
    
    if not user_info or user_info[3] == 0:
        await update.message.reply_text("Вы не можете отправлять фото. Зарегистрируйтесь и дождитесь одобрения.")
        return
    
    try:
        photo = update.message.photo[-1]
        
        conn = sqlite3.connect('data/bot_db.sqlite')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO photos (user_id, file_id, sent_date) VALUES (?, ?, ?)",
                      (user.id, photo.file_id, datetime.now().isoformat()))
        photo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("✅ Одобрить (+1 балл)", callback_data=f"approve_photo_{photo_id}"),
             InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_photo_{photo_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_photo(
            chat_id= -4802024453,
            photo=photo.file_id,
            caption=f"Фото от пользователя: @{user.username}\n"
                   f"ID: {user.id}\n"
                   f"ФИО: {user_info[2]}\n"
                   f"Текущие баллы: {user_info[4]}",
            reply_markup=reply_markup
        )
        
        await update.message.reply_text("Ваше фото отправлено на модерацию. При одобрении вы получите 1 балл.")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке вашего фото.")

async def remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для этой команды.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /remove_points <user_id> <amount> [reason]")
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else "Списание администратором"
        
        if amount <= 0:
            await update.message.reply_text("Сумма должна быть положительной.")
            return
        
        # Списываем баллы (передаем отрицательное значение)
        add_points(target_user_id, -amount, update.effective_user.id, reason)
        
        # Получаем информацию о пользователе
        user_info = get_user_info(target_user_id)
        
        await update.message.reply_text(
            f"Списано {amount} баллов у пользователя @{user_info[1]} (ID: {target_user_id})\n"
            f"Новый баланс: {user_info[4]}\n"
            f"Причина: {reason}"
        )
        
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Администратор списал у вас {amount} баллов.\n"
                 f"Причина: {reason}\n"
                 f"Новый баланс: {user_info[4]}"
        )
        
    except ValueError:
        await update.message.reply_text("Некорректные аргументы. user_id и amount должны быть числами.")
    except Exception as e:
        logger.error(f"Ошибка при списании баллов: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    admin_id = query.from_user.id
    
    if admin_id not in ADMIN_IDS:
        await query.answer("У вас нет прав для этого действия.")
        return
    
    try:
        if data.startswith("approve_user_"):
            target_user_id = int(data.split("_")[2])
            approve_user(target_user_id, admin_id)
            await query.answer("Пользователь одобрен")
            await context.bot.send_message(
                chat_id=target_user_id,
                text="✅ Ваша регистрация одобрена! Теперь вы можете отправлять фото и зарабатывать баллы."
            )
            await query.edit_message_text(
                text=f"{query.message.text}\n\nОдобрено администратором @{query.from_user.username}"
            )
        
        elif data.startswith("reject_user_"):
            target_user_id = int(data.split("_")[2])
            await query.answer("Пользователь отклонен")
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ Ваша регистрация отклонена администратором."
            )
            await query.edit_message_text(
                text=f"{query.message.text}\n\nОтклонено администратором @{query.from_user.username}"
            )
        
        elif data.startswith("approve_photo_"):
            photo_id = int(data.split("_")[2])
            
            # Получаем информацию о фото
            conn = sqlite3.connect('data/bot_db.sqlite')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM photos WHERE photo_id = ?", (photo_id,))
            user_id = cursor.fetchone()[0]
            conn.close()
            
            # Начисляем баллы
            add_points(user_id, 1, admin_id, "Одобрение фото")
            
            # Обновляем статус фото
            conn = sqlite3.connect('data/bot_db.sqlite')
            cursor = conn.cursor()
            cursor.execute("UPDATE photos SET status = 'approved', moderator_id = ?, decision_date = ? WHERE photo_id = ?",
                          (admin_id, datetime.now().isoformat(), photo_id))
            conn.commit()
            conn.close()
            
            await query.answer("Фото одобрено (+1 балл)")
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Ваше фото одобрено! Вам начислен 1 балл.\nНапишите /profile, чтобы узнать больше о баллах."
            )
            await query.edit_message_caption(
                caption=f"{query.message.caption}\n\nОдобрено администратором @{query.from_user.username}\n+1 балл пользователю"
            )
        
        elif data.startswith("reject_photo_"):
            photo_id = int(data.split("_")[2])
            
            conn = sqlite3.connect('data/bot_db.sqlite')
            cursor = conn.cursor()
            cursor.execute("UPDATE photos SET status = 'rejected', moderator_id = ?, decision_date = ? WHERE photo_id = ?",
                          (admin_id, datetime.now().isoformat(), photo_id))
            cursor.execute("SELECT user_id FROM photos WHERE photo_id = ?", (photo_id,))
            user_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            await query.answer("Фото отклонено")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ваше фото отклонено администратором."
            )
            await query.edit_message_caption(
                caption=f"{query.message.caption}\n\nОтклонено администратором @{query.from_user.username}"
            )
    
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")
        await query.answer("Произошла ошибка")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Обработчик регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('profile', show_profile))
    application.add_handler(CommandHandler('remove_points', remove_points))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

if __name__ == "__main__":
    main()