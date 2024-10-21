import logging
import os
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils import admin, reports, db_utils as utils, lessons_handler

wants_subscribe = False
extend = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()

admin.register_handlers(bot)
lessons_handler.register_handlers(bot)
reports.register_handlers(bot)
utils.init_db()

def check_expired_subscriptions():
    while True:
        conn = sqlite3.connect('utils/databases/users.db')
        c = conn.cursor()
        now = datetime.now()
        three_days_later = (now + timedelta(days=3)).date()
        one_day_later = (now + timedelta(days=1)).date()
        c.execute("SELECT user_id FROM subscribers WHERE DATE(expiry_date) = ?", (three_days_later,))
        three_day_users = c.fetchall()
        for user in three_day_users:
            bot.send_message(user[0],
                             'Дорогой пользователь КөмекБай! 📅 Срок вашей подписки истекает через 3 дня. ⏳ Если вы желаете продлить подписку, напишите боту: "Продлить подписку" ✉️')

        c.execute("SELECT user_id FROM subscribers WHERE DATE(expiry_date) = ?", (one_day_later,))
        one_day_users = c.fetchall()
        for user in one_day_users:
            bot.send_message(user[0],
                             'Дорогой пользователь КөмекБай! 📅 Срок вашей подписки истекает завтра! ⏳ Если вы желаете продлить подписку, напишите боту: "Продлить подписку" ✉️')

        c.execute("SELECT user_id FROM subscribers WHERE expiry_date < ?", (now.isoformat(),))
        expired_users = c.fetchall()

        if expired_users:
            for user in expired_users:
                logger.info(f"Expired subscription removed for user ID: {user[0]}")
                bot.send_message(user[0],
                                 'Дорогой пользователь КөмекБай! 📅 К сожалению, срок вашей подписки истек. 😔 Чтобы продолжить пользоваться нашими услугами, пожалуйста, продлите подписку')

            admin.move_expired_users()
        else:
            logger.info(f"No expired subscriptions were found")

        conn.close()
        admin.move_old_expired_users()
        time.sleep(600)

def create_grade_inline_keyboard(user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("1 Класс", callback_data="grade1"))
    keyboard.add(InlineKeyboardButton("2 Класс", callback_data="grade2"))
    keyboard.add(InlineKeyboardButton("3 Класс", callback_data="grade3"))
    keyboard.add(InlineKeyboardButton("4 Класс", callback_data="grade4"))
    return keyboard

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, f"Привет 👋")
    bot.send_message(message.chat.id, f"В каком ты классе?", reply_markup=create_grade_inline_keyboard(message.chat.id))


@bot.message_handler(func=lambda message: "почему" in message.text.lower())
def why(message):
    bot.send_message(message.chat.id, f"Потому")


@bot.message_handler(func=lambda message: "тупой" in message.text.lower())
def smartbot(message):
    bot.send_message(message.chat.id, f"Я умный ")


words = {
    "привет", "Здравствуйте", "помоги", "салем", "сәлем", "сәлеметсіз",
    "домашнее", "задание", "дз", "работа", "домашку", "сделать", "домашка",
    "меню", "старт", "назад", "начало", "класс", "выбрать"
}

@bot.message_handler(func=lambda message: any(word in message.text.lower() for word in words))
def hello(message):
    username = message.chat.first_name or message.chat.from_user.username or "друг"
    bot.send_message(message.chat.id, f"Привет {username}! 👋")
    bot.send_message(message.chat.id, f"В каком ты классе?", reply_markup=create_grade_inline_keyboard(message.chat.id))

@bot.message_handler(commands=['get_id'])
def get_user_id(message):
    user_id = message.chat.id
    bot.send_message(message.chat.id, f"Ваш ID: {user_id}")

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("grade") and "_chapter_" not in call.data and "_lesson_" not in call.data)
def handle_grade_selection(call):
    grade_number = ''.join(filter(str.isdigit, call.data))
    logger.info(f"Grade selected: {grade_number}")

    if grade_number in ['2', '3', '4']:
        if not (utils.is_subscriber(call.message.chat.id) or utils.is_admin(call.message.chat.id)):
            bot.send_message(call.message.chat.id,
                             f"Оформите подписку для разблокировки {grade_number} класса. Отправьте боту "
                             "слово 'Подписка' для оплаты ✉️")
            return

    try:
        lessons_handler.menu(call, bot, grade_number)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Произошла ошибка: {str(e)}")

@bot.message_handler(commands=['lessons'])
def settings(message):
    if utils.is_admin(message.chat.id):
        try:
            parts = message.text.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "Использование: /lessons <номер класса>")
                return
            grade_num = parts[1]
            if grade_num not in ['1', '2', '3', '4']:
                bot.send_message(message.chat.id, "Пожалуйста, укажите корректный номер класса от 1 до 4.")
                return
            admin.show_settings(bot, message, grade_num)
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Ошибка в /lessons: {e}")
    else:
        bot.send_message(message.chat.id, "У вас недостаточно прав.")


@bot.message_handler(func=lambda message: message.text.lower() == "подписка")
def handle_subscription_request(message):
    user_id = message.chat.id
    markup = InlineKeyboardMarkup()
    subscribe_button = InlineKeyboardButton("Оформить Подписку 📲", callback_data="subscribe")
    markup.add(subscribe_button)
    bot.send_message(user_id, "Для оформления 30-дневной подписки, оплатите *4990₸* через Kaspi.kz",
                     parse_mode='Markdown', reply_markup=markup)


@bot.message_handler(func=lambda message: message.text.lower() == "продлить подписку")
def handle_extension_request(message):
    user_id = message.chat.id
    markup = InlineKeyboardMarkup()
    subscribe_button = InlineKeyboardButton("Продлить Подписку 📲", callback_data="extend")
    markup.add(subscribe_button)
    bot.send_message(user_id,
                     "Мы рады, что вам понравился КөмекБай! 😊 Для продления 30-дневной подписки, оплатите *4990₸* через Kaspi.kz",
                     parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == 'subscribe')
def callback_subscription(call):
    global wants_subscribe
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Отправьте свой номер телефона в чат 📞", parse_mode='Markdown')
    wants_subscribe = True


@bot.callback_query_handler(func=lambda call: call.data == 'extend')
def callback_extension(call):
    global wants_subscribe
    markup = InlineKeyboardMarkup()
    month = InlineKeyboardButton("1 месяц 🗓️", callback_data="m1")
    three_months = InlineKeyboardButton("3 месяца 📆", callback_data="m3")
    half_a_year = InlineKeyboardButton("6 месяцев 🕑", callback_data="m6")
    markup.add(month, three_months, half_a_year)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "На какой период вы бы хотели продлить подписку? 🕒", reply_markup=markup,
                     parse_mode='Markdown')
    wants_subscribe = True


# Handler function to print the selected period
@bot.callback_query_handler(func=lambda call: call.data in ['m1', 'm3', 'm6'])
def handle_subscription_period(call):
    global extend
    periods = {
        'm1': 1,
        'm3': 3,
        'm6': 6
    }

    # Print the selected period
    selected_period = periods[call.data]
    bot.answer_callback_query(call.id)
    extend = True
    finalize_subscription(call.message.chat.id, period=selected_period)


@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    if wants_subscribe:
        if message.text.startswith('+') or message.text[0].isdigit():
            global extend
            phone_number = message.text
            extend = False
            finalize_subscription(message.chat.id, phone_number)
        else:
            bot.send_message(message.chat.id, "Введите корректный номер телефона.", parse_mode='Markdown')
    else:
        unknown_command_responses = {
            1: "Извините, я вас не понял.",
            2: "Ой, не понял тебя.",
            3: "Прошу прощения, не совсем понял, что вы имеете в виду.",
            4: "Не совсем понял ваш запрос.",
            5: "К сожалению, я не смог понять ваш запрос.",
            6: 'Введи "Меню" если хочешь открыть список классов',
            7: "Простите, не разобрал ваш вопрос.",
            8: "Прошу прощения, не понял, о чем вы говорите.",
            9: "Упс, не совсем понятно.",
            10: "Извините, не могу понять запрос."
        }
        bot.send_message(message.chat.id, unknown_command_responses[random.randint(1, 10)], parse_mode='Markdown')


def finalize_subscription(chat_id, phone_number=None, period=None):
    global wants_subscribe
    global extend
    if not extend:
        bot.send_message(chat_id, f"Оплатите *4990₸* по номеру:\n+7 701 234 5678", parse_mode='Markdown')
        bot.send_message(chat_id, f"Бот сообщит вам, когда подписка станет активна 😊")
    else:
        bot.send_message(chat_id, f"Оплатите *{4990 * period}₸* по номеру:\n+7 701 234 5678", parse_mode='Markdown')
        bot.send_message(chat_id, f"Бот сообщит вам, как только подписка будет продлена 😊")
    wants_subscribe = False
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()
    c.execute("SELECT tg_id FROM admins")
    admins = c.fetchall()
    print(admins)
    conn.close()
    for admin in admins:
        admin_id = admin[0]
        text = f"Пользователь с ID: <b>{chat_id}</b>, телефон: {phone_number} желает купить подписку." if not extend else f"Пользователь с ID: <b>{chat_id}</b>, желает продлить подписку на {period} месяц(ев).\nИспользуйте команду '<i>/extend_sub user_id</i>' для продления подписки"
        bot.send_message(admin_id, text,
                         parse_mode="HTML")

@bot.message_handler(commands=['subscribe'])
def subscribe_command(message):
    handle_subscription_request(message)

threading.Thread(target=check_expired_subscriptions, daemon=True).start()

if __name__ == '__main__':
    logger.info("Bot started")
    bot.infinity_polling()
