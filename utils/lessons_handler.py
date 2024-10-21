import logging
import sqlite3
from datetime import datetime
from telebot import types
from utils import lessons_retriever, db_utils as utils

logger = logging.getLogger(__name__)

months_russian = {
    1: "Января",
    2: "Февраля",
    3: "Марта",
    4: "Апреля",
    5: "Мая",
    6: "Июня",
    7: "Июля",
    8: "Августа",
    9: "Сентября",
    10: "Октября",
    11: "Ноября",
    12: "Декабря"
}

def format_opening_date_message(opening_date):
    date_obj = datetime.strptime(opening_date, "%d/%m")
    return f"Этот раздел откроется {date_obj.day} {months_russian[date_obj.month]} 🗓️"

def menu(call, bot, grade_number):
    username = call.from_user.first_name or call.from_user.username or "друг"
    bot.send_message(
        call.message.chat.id,
        f"Привет, {username}! Я КөмекБай - твой помощник в выполнении домашних заданий за {grade_number} класс 😇"
    )

    chapters = lessons_retriever.get_chapters(grade_number)
    if not chapters:
        bot.send_message(call.message.chat.id, "Нет доступных глав.")
        return

    user_id = call.from_user.id
    current_date = datetime.now().strftime("%d/%m")
    markup = types.InlineKeyboardMarkup()

    for chapter_no, chapter_data in chapters.items():
        chapter_name, require_subscription, opening_date = chapter_data

        if opening_date and datetime.strptime(current_date, "%d/%m") < datetime.strptime(opening_date, "%d/%m"):
            button_text = "Заблокировано"
            callback_data = f"locked_due_date_{grade_number}_{chapter_no}"
        elif require_subscription == 'locked' and not utils.is_admin(user_id) and not utils.is_subscriber(user_id):
            button_text = "Заблокировано"
            callback_data = f"locked_chapter_{chapter_no}"
        else:
            button_text = chapter_name
            callback_data = f"grade{grade_number}_chapter_{chapter_no}"

        button = types.InlineKeyboardButton(text=button_text, callback_data=callback_data)
        markup.add(button)

    bot.send_message(call.message.chat.id, "На какой ты главе? 📖", reply_markup=markup)

def handle_chapter_selection(call, bot):
    data_parts = call.data.split("_")

    if data_parts[0] == "locked":
        grade_number = data_parts[1].replace("grade", "")
        chapter_no = data_parts[2]

        chapters = lessons_retriever.get_chapters(grade_number)
        chapter_data = chapters.get(chapter_no)

        if chapter_data:
            chapter_name, require_subscription, opening_date = chapter_data
            user_id = call.from_user.id
            if require_subscription == 'locked' and not utils.is_admin(user_id) and not utils.is_subscriber(user_id):
                bot.send_message(call.message.chat.id, 'Оформите подписку для разблокировки этого раздела. Отправьте боту слово "Подписка" для оплаты ✉️')
                return

            if opening_date and datetime.now() < datetime.strptime(opening_date, "%d/%m"):
                opening_date_message = format_opening_date_message(opening_date)
                bot.send_message(call.message.chat.id, opening_date_message)
                return

    if len(data_parts) == 3:
        grade_part, chapter_part, chapter_no = data_parts

        if not grade_part.startswith("grade") or chapter_part != "chapter":
            bot.send_message(call.message.chat.id, "Некорректный выбор главы.")
            return

        grade_number = grade_part.replace("grade", "")
        lessons = lessons_retriever.get_lessons(grade_number, chapter_no)

        if not lessons:
            bot.send_message(call.message.chat.id, "Нет доступных уроков.")
            return

        markup = types.InlineKeyboardMarkup()
        for lesson in lessons:
            lesson_no = lesson['number']
            lesson_name = lesson['name']
            callback_data = f"grade{grade_number}_chapter_{chapter_no}_lesson_{lesson_no}"
            markup.add(types.InlineKeyboardButton(text=lesson_name, callback_data=callback_data))

        bot.send_message(call.message.chat.id, "Выберите урок 📚", reply_markup=markup)

    elif len(data_parts) == 5:
        handle_lesson_selection(call, bot)
    else:
        bot.send_message(call.message.chat.id, "Некорректный выбор.")
        return

def handle_lesson_selection(call, bot):
    data_parts = call.data.split("_")

    if len(data_parts) != 5:
        bot.send_message(call.message.chat.id, "Некорректный выбор урока.")
        return

    grade_part, chapter_part, chapter_no, lesson_part, lesson_no = data_parts

    if not grade_part.startswith("grade") or chapter_part != "chapter" or lesson_part != "lesson":
        bot.send_message(call.message.chat.id, "Некорректный выбор урока.")
        return

    grade_number = grade_part.replace("grade", "")
    lessons = lessons_retriever.get_lessons(grade_number, chapter_no)
    lesson = next((lesson for lesson in lessons if lesson['number'] == lesson_no), None)

    if not lesson:
        bot.send_message(call.message.chat.id, "Урок не найден.")
        return

    lesson_name = lesson['name']
    lesson_url = lesson['url']

    if lesson_url:
        if "/" in lesson_url:
            bot.send_message(call.message.chat.id, f'(Подожди пока видео загрузится <a href="{lesson_url}">⌛</a>)\n<b>Урок - {lesson_name}</b>', parse_mode="HTML")
        else:
            bot.send_message(call.message.chat.id, "К сожалению, возникли проблемы с этим уроком. Попробуйте еще раз позже ⚙")
            conn = sqlite3.connect('utils/databases/users.db')
            c = conn.cursor()
            c.execute("SELECT tg_id FROM admins")
            admins = c.fetchall()
            conn.close()

            for admin in admins:
                admin_id = admin[0]
                bot.send_message(admin_id,
                                 f"Проблема с ссылкой на видео в уроке {lesson_name}, глава {chapter_no}, класс {grade_number}",
                                 parse_mode="Markdown")
    else:
        bot.send_message(call.message.chat.id, "К сожалению, этот урок еще не готов ☹")

def handle_locked_chapter(call, bot, locked_msg):
    bot.send_message(call.message.chat.id, locked_msg)

def register_handlers(bot):
    @bot.callback_query_handler(func=lambda call: call.data.startswith("grade") and "_chapter_" in call.data)
    def chapter_selection_handler(call):
        handle_chapter_selection(call, bot)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("locked_chapter"))
    def locked_chapter_handler(call):
        user_id = call.from_user.id
        if not utils.is_admin(user_id) and not utils.is_subscriber(user_id):
            locked_msg = 'Оформите подписку для разблокировки этого раздела. Отправьте боту слово "Подписка" для оплаты ✉️'
            handle_locked_chapter(call, bot, locked_msg)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("locked_due_date"))
    def locked_chapter_due_to_date(call):
        grade_number, chapter_no = call.data.split("_")[3], call.data.split("_")[4]

        chapter_data = lessons_retriever.get_chapters(grade_number).get(chapter_no)
        if chapter_data:
            opening_date = chapter_data[2]
            if opening_date:
                locked_msg = format_opening_date_message(opening_date)
                handle_locked_chapter(call, bot, locked_msg)
