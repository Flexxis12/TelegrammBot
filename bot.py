import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from datetime import datetime, time
import pytz

# --- Настройки ---
TOKEN = '7585936393:AAEt6iXD9zUIYfu_sjLVPcanFBR7SF47PpY'
GOOGLE_SHEET_NAME = 'Обработка'

# Часовой пояс
TIMEZONE = pytz.timezone('Europe/Moscow')

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Доступ к Google Sheets ---
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(credentials)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# --- Этапы разговора ---
WAITING_FOR_PHONE, WAITING_FOR_ADDRESS, WAITING_FOR_PRICE = range(3)
WAITING_FOR_DAY_END_INPUT = range(1)

# --- Старт команды с меню ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Добавить нового клиента", callback_data='add_client')],
        [InlineKeyboardButton("Завершить рабочий день", callback_data='finish_day')],
        [InlineKeyboardButton("Подвести итог дня", callback_data='itog')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text('Привет! Выберите действие:', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text('Привет! Выберите действие:', reply_markup=reply_markup)

# --- Обработка кнопок меню ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'add_client':
        await query.edit_message_text('Введите номер клиента:')
        return WAITING_FOR_PHONE
    elif query.data == 'finish_day':
        await ask_day_end_from_query(update, context)
        return WAITING_FOR_DAY_END_INPUT
    elif query.data == 'itog':
        await ask_day_end_from_query(update, context)
        return WAITING_FOR_DAY_END_INPUT

# --- Обработка пошагового ввода клиента ---
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text('Введите адрес клиента:')
    return WAITING_FOR_ADDRESS

async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['address'] = update.message.text
    await update.message.reply_text('Введите стоимость работ у клиента (₽):')
    return WAITING_FOR_PRICE

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['price'] = update.message.text
    date_today = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
    row = [
        date_today,
        context.user_data['phone'],
        context.user_data['address'],
        context.user_data['price'],
        '', '', '', '', ''
    ]
    try:
        sheet.append_row(row)
        await update.message.reply_text('✅ Данные успешно записаны! Чтобы добавить следующего клиента, напишите снова /start')
    except Exception as e:
        logging.error(f"Ошибка записи в таблицу: {e}")
        await update.message.reply_text('⚠️ Ошибка при записи в таблицу.')
    return ConversationHandler.END

# --- Итог в конце дня ---
async def ask_day_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Рабочий день окончен.\nВведите три значения через запятую:\n\n"
        "Сумма Илье за день, Расходы за день, Моя зарплата за день\n\n"
        "Пример: 3000, 500, 2500"
    )
    return WAITING_FOR_DAY_END_INPUT

async def ask_day_end_from_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text(
        "Рабочий день окончен.\nВведите три значения через запятую:\n\n"
        "Сумма Илье за день, Расходы за день, Моя зарплата за день\n\n"
        "Пример: 3000, 500, 2500"
    )
    return WAITING_FOR_DAY_END_INPUT

async def receive_day_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        values = [v.strip() for v in text.split(',')]

        if len(values) != 3:
            await update.message.reply_text('Ошибка! Нужно ввести ровно 3 значения через запятую.')
            return WAITING_FOR_DAY_END_INPUT

        ilya_sum = values[0]
        expenses = values[1]
        salary = values[2]

        # Считаем сумму стоимости всех работ за сегодня
        date_today = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
        records = sheet.get_all_records()
        today_prices = [int(r['Стоимость работ у клиента']) for r in records if r['Дата'] == date_today and r['Стоимость работ у клиента']]
        total_earned = sum(today_prices)

        # Сумма за выход фиксированная
        exit_sum = 2000

        # Добавляем итоговую строку
        new_row = [
            date_today, '', '', '',
            str(total_earned),
            ilya_sum,
            expenses,
            salary,
            str(exit_sum)
        ]

        sheet.append_row(new_row)

        await update.message.reply_text('✅ Итог дня записан!\n\nХорошего отдыха!')
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"Ошибка при подсчёте итога дня: {e}")
        await update.message.reply_text('⚠️ Произошла ошибка при записи итога дня.')
        return ConversationHandler.END

# --- Автоматическое напоминание в 23:55 ---
async def daily_auto_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = 650178077  # <-- Твой Telegram ID
    await context.bot.send_message(
        chat_id=chat_id,
        text="Время подвести итоги!\nВведите команду /finish_day чтобы внести данные за день."
    )

# --- Основной код запуска ---
app = ApplicationBuilder().token(TOKEN).build()

# Разговорник для ввода клиентов
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('start', start),
        CallbackQueryHandler(button)  # сюда добавили обработку кнопок
    ],
    states={
        WAITING_FOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
        WAITING_FOR_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)],
        WAITING_FOR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
        WAITING_FOR_DAY_END_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_day_end_input)],
    },
    fallbacks=[]
)

app.add_handler(conv_handler)

# Ежедневное напоминание
job_queue = app.job_queue
job_queue.run_daily(daily_auto_reminder, time=time(hour=23, minute=55, tzinfo=TIMEZONE))

print("Бот запущен...")
app.run_polling()
