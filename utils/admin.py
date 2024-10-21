import re
import sqlite3
import threading
from datetime import datetime, timedelta

import telebot
import html
import logging
from utils import db_utils as utils

logger = logging.getLogger(__name__)
db_lock = threading.Lock()


def get_file_paths(grade_number):
    grade_dir = f"grade_{grade_number}"
    chapters_file = 'utils/lessons/chapters.txt'
    lessons_file = f'utils/lessons/{grade_dir}.txt'
    return chapters_file, lessons_file


def show_settings(bot, message, grade_number):
    chapters_file, lessons_file = get_file_paths(grade_number)
    if not chapters_file or not lessons_file:
        bot.send_message(message.chat.id, "❌ Неверный номер класса. Пожалуйста, укажите класс от 1 до 4.")
        return

    chapters = utils.get_chapters(chapters_file, grade_number)
    lessons = utils.get_lessons(lessons_file)

    logger.info(f"Showing settings for grade {grade_number}")
    response = f"📚 <b>Текущие разделы для {grade_number} класса:</b>\n"
    for chapter_number, chapter_name in chapters.items():
        safe_chapter_name = html.escape(chapter_name)
        response += f"{chapter_number}: {safe_chapter_name}\n"

    response += f"\n📖 <b>Текущие уроки для {grade_number} класса:</b>\n"
    for lesson_key, lesson_data in lessons.items():
        safe_lesson_name = html.escape(lesson_data['name'])
        safe_lesson_url = html.escape(lesson_data['url'])
        if safe_lesson_url:
            response += f"{lesson_key}: <i>{safe_lesson_name}</i> (<a href=\"{safe_lesson_url}\">Видео✅</a>)\n"
        else:
            response += f"{lesson_key}: <i>{safe_lesson_name}</i> (<b>‼️Нет видео‼️</b>)\n"

    try:
        bot.send_message(message.chat.id, response, parse_mode='HTML')
    except telebot.apihelper.ApiException as e:
        if "message is too long" in str(e):
            parts = utils.split_message_in_half(response)
            for part in parts:
                bot.send_message(message.chat.id, part, parse_mode='HTML')
        else:
            logger.error(f"Не удалось отправить настройки для класса {grade_number}: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка при отправке настроек.")

def move_expired_users():
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()
    now = datetime.now().isoformat()

    # Select users with expired subscriptions
    c.execute("SELECT user_id, phone_number, expiry_date, subscription_date FROM subscribers WHERE expiry_date < ?",
              (now,))
    expired_users = c.fetchall()

    if expired_users:
        for user in expired_users:
            user_id, phone_number, expiry_date, subscription_date = user
            # Insert into expired table
            c.execute('''INSERT OR REPLACE INTO expired 
                         (user_id, phone_number, expiry_date, subscription_date) 
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, phone_number, expiry_date, subscription_date, now))
            # Remove from subscribers table
            c.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))

        conn.commit()
        logger.info(f"Moved {len(expired_users)} users to the expired table.")
    else:
        logger.info("No users with expired subscriptions found.")

    conn.close()


def move_old_expired_users():
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()
    conn_expired = sqlite3.connect('utils/databases/expired.db')
    c_expired = conn_expired.cursor()

    one_month_ago = (datetime.now() - timedelta(days=30)).date()

    # Select users whose expired_date is older than one month, comparing only the date part
    c.execute(
        "SELECT user_id, phone_number, expiry_date, subscription_date "
        "FROM expired WHERE DATE(expiry_date) < ?",
        (one_month_ago,))
    old_expired_users = c.fetchall()

    if old_expired_users:
        for user in old_expired_users:
            user_id, phone_number, expiry_date, subscription_date = user
            # Insert into old_expired table in expired.db
            c_expired.execute('''INSERT OR REPLACE INTO old_expired 
                                 (user_id, phone_number, expiry_date, subscription_date) 
                                 VALUES (?, ?, ?, ?)''',
                              (user_id, phone_number, expiry_date, subscription_date))
            # Remove from expired table
            c.execute("DELETE FROM expired WHERE user_id = ?", (user_id,))

        conn.commit()
        conn_expired.commit()
        logger.info(f"Moved {len(old_expired_users)} users to the old_expired table in expired.db.")
    else:
        logger.info("No users with expired subscriptions older than a month found.")

    conn.close()
    conn_expired.close()


def register_handlers(bot):
    def edit_chapter_name_handler(message):
        logger.info(f"edit_chapter_name_handler triggered by user {message.chat.id}")
        try:
            parts = message.text.split(' ', 3)
            if len(parts) < 4:
                bot.send_message(
                    message.chat.id,
                    '❌ Формат команды: /edit_chapter_name <номер класса> <номер главы> <новое название>'
                )
                return
            grade_number, chapter_number, new_name = parts[1], parts[2], parts[3]
            chapters_file, _ = get_file_paths(grade_number)
            chapters = utils.get_chapters(chapters_file, grade_number)
            if chapter_number in chapters:
                chapters[chapter_number] = new_name
                utils.save_chapters(chapters_file, grade_number, chapters)
                bot.send_message(
                    message.chat.id,
                    f"✅ Раздел {chapter_number} в {grade_number} классе переименован в: <b>{html.escape(new_name)}</b>",
                    parse_mode='HTML'
                )
                logger.info(f"Раздел {chapter_number} в классе {grade_number} переименован в {new_name}")
            else:
                bot.send_message(message.chat.id, "❌ Раздел не найден.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось переименовать раздел: {e}")

    def edit_lesson_name_handler(message):
        logger.info(f"edit_lesson_name_handler triggered by user {message.chat.id}")
        try:
            parts = message.text.split(' ', 3)
            if len(parts) < 4:
                bot.send_message(
                    message.chat.id,
                    '❌ Формат команды: /edit_lesson_name <номер класса> <ключ урока> <новое название>'
                )
                return
            grade_number, lesson_key, new_name = parts[1], parts[2], parts[3]
            _, lessons_file = get_file_paths(grade_number)
            lessons = utils.get_lessons(lessons_file)
            if lesson_key in lessons:
                lessons[lesson_key]['name'] = new_name
                utils.save_lessons(lessons_file, lessons)
                bot.send_message(
                    message.chat.id,
                    f"✅ Урок {lesson_key} в {grade_number} классе переименован в: <b>{html.escape(new_name)}</b>",
                    parse_mode='HTML'
                )
                logger.info(f"Урок {lesson_key} в классе {grade_number} переименован в {new_name}")
            else:
                bot.send_message(message.chat.id, "❌ Урок не найден.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось переименовать урок: {e}")

    def edit_lesson_url_handler(message):
        logger.info(f"edit_lesson_url_handler triggered by user {message.chat.id}")
        try:
            # Expected format: /edit_lesson_url <grade_number> <lesson_key> <new_url>
            parts = message.text.split(' ', 3)
            if len(parts) < 4:
                bot.send_message(
                    message.chat.id,
                    "❌ Формат команды: /edit_lesson_url <номер класса> <ключ урока> <ccылка на видео>"
                )
                return
            grade_number, lesson_key, new_url = parts[1], parts[2], parts[3]
            if grade_number not in ["1", "2", "3", "4"]:
                bot.send_message(message.chat.id, "❌ Неверный номер класса. Пожалуйста, укажите класс от 1 до 4.")
                return
            _, lessons_file = get_file_paths(grade_number)
            lessons = utils.get_lessons(lessons_file)
            logger.debug(f"Current lessons: {lessons}")
            if lesson_key in lessons:
                lessons[lesson_key]['url'] = new_url
                print(lessons)
                utils.save_lessons(lessons_file, lessons)
                bot.send_message(
                    message.chat.id,
                    f"✅ URL урока {lesson_key} в {grade_number} классе обновлен: <a href=\"{html.escape(new_url)}\">{html.escape(new_url)}</a>",
                    parse_mode='HTML'
                )
                logger.info(
                    f"URL урока {lesson_key} в классе {grade_number} обновлен на {new_url} пользователем {message.chat.id}")
            else:
                bot.send_message(message.chat.id, "❌ Урок не найден.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось обновить URL урока: {e}")

    def settings_handler(message):
        logger.info(f"settings_handler triggered by user {message.chat.id}")
        try:
            # Expected format: /settings <grade_number>
            parts = message.text.split(' ', 1)
            if len(parts) < 2:
                bot.send_message(
                    message.chat.id,
                    "❌ Формат команды: /settings <номер класса>"
                )
                return
            grade_number = parts[1].strip()
            if grade_number not in ["1", "2", "3", "4"]:
                bot.send_message(message.chat.id, "❌ Неверный номер класса. Пожалуйста, укажите класс от 1 до 4.")
                return
            show_settings(bot, message, grade_number)
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось показать настройки: {e}")

    def update_opening_date(chapters_file, grade_number, chapter_number, new_date):
        try:
            with open(chapters_file, 'r+', encoding='utf-8') as file:
                lines = file.readlines()
                file.seek(0)
                file.truncate()  # Clear the file for rewriting

                grade_found = False
                for line in lines:
                    if line.startswith(f"Grade {grade_number}"):
                        grade_found = True

                    if grade_found and line.startswith(f"{chapter_number}:"):
                        # Use regex to replace the date inside the brackets
                        line = re.sub(r'\[\d{2}/\d{2}\]', f'[{new_date}]', line)

                    # Write the updated or unchanged line back to the file
                    file.write(line)

                    # Stop after finishing the current grade's chapters
                    if line.startswith("Grade") and not line.startswith(f"Grade {grade_number}"):
                        grade_found = False

        except Exception as e:
            logger.error(f"Ошибка при обновлении даты открытия в {chapters_file}: {e}")

    # Command handler for editing opening date
    def edit_opening_date_handler(message):
        logger.info(f"edit_opening_date_handler triggered by user {message.chat.id}")
        try:
            # Expected format: /edit_opening_date <grade_number> <chapter_number> <new_date>
            parts = message.text.split(' ', 4)
            if len(parts) < 4:
                bot.send_message(
                    message.chat.id,
                    '❌ Формат команды: /edit_chapter_date <номер класса> <номер главы> <дата в формате день/месяц>'
                )
                return
            grade_number, chapter_number, new_date = parts[1], parts[2], parts[3]

            if grade_number not in ["1", "2", "3", "4"]:
                bot.send_message(message.chat.id, "❌ Неверный номер класса. Пожалуйста, укажите класс от 1 до 4.")
                return

            # Validate new date format
            if not re.match(r'\d{2}/\d{2}', new_date):
                bot.send_message(message.chat.id, "❌ Неверный формат даты. Пожалуйста, используйте формат день/месяц.")
                return

            chapters_file, _ = get_file_paths(grade_number)
            update_opening_date(chapters_file, grade_number, chapter_number, new_date)

            bot.send_message(
                message.chat.id,
                f"✅ Дата открытия главы {chapter_number} в {grade_number} классе обновлена на: {new_date}"
            )
            logger.info(
                f"Дата открытия главы {chapter_number} в классе {grade_number} обновлена на {new_date} пользователем {message.chat.id}")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось обновить дату открытия: {e}")

    def add_lesson_handler(message):
        logger.info(f"add_lesson_handler triggered by user {message.chat.id}")
        try:
            parts = message.text.split(' ', 4)
            if len(parts) < 5:
                bot.send_message(
                    message.chat.id,
                    '❌ Формат команды: /add_lesson <номер класса> <номер главы> <название урока> <ссылка на '
                    'видео>\n‼️Используйте "_" вместо пробела‼️'
                )
                return

            grade_number, chapter_number, lesson_name, lesson_url = parts[1], parts[2], parts[3], parts[4]

            if grade_number not in ["1", "2", "3", "4"]:
                bot.send_message(message.chat.id, "❌ Неверный номер класса. Пожалуйста, укажите класс от 1 до 4.")
                return

            # Load current lessons
            _, lessons_file = get_file_paths(grade_number)
            lessons = utils.get_lessons(lessons_file)
            chapter_key = f"l{chapter_number}"
            lesson_number = str(
                len([k for k in lessons if k.startswith(chapter_key)]) + 1)
            lesson_key = f"{chapter_key}_{lesson_number}"

            # Add the new lesson to the dictionary
            lessons[lesson_key] = {
                'name': lesson_name.strip(),
                'url': lesson_url.strip()
            }
            utils.save_lessons(lessons_file, lessons)

            bot.send_message(
                message.chat.id,
                f"✅ Урок добавлен в {grade_number} класс, глава {chapter_number}: {lesson_name} (<a href=\"{html.escape(lesson_url)}\">Ссылка</a>)",
                parse_mode='HTML'
            )
            logger.info(f"Новый урок добавлен пользователем {message.chat.id}: {lesson_name} ({lesson_url})")

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")
            logger.error(f"Не удалось добавить урок: {e}")

    def admin_add(message):
        if utils.is_admin(message.chat.id):
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    bot.send_message(message.chat.id, "Использование: /admin_add <user_id>")
                    return
                user_id = int(parts[1])
                nickname = parts[2] if len(parts) > 2 else "Unknown"

                with db_lock:
                    conn = sqlite3.connect('utils/databases/users.db')
                    c = conn.cursor()
                    c.execute("INSERT INTO admins (nickname, tg_id) VALUES (?, ?)", (nickname, user_id))
                    conn.commit()
                    conn.close()
                bot.send_message(message.chat.id, f"Админ с ID {user_id} добавлен!")
                bot.send_message(user_id, "Вы были назначены админом ⚙")
            except IndexError:
                bot.send_message(message.chat.id, "Использование: /admin_add <user_id>")
            except ValueError:
                bot.send_message(message.chat.id, "Пожалуйста, введите корректный ID пользователя.")
            except sqlite3.IntegrityError:
                bot.send_message(message.chat.id, f"Админ с ID {user_id} уже существует.")
        else:
            bot.send_message(message.chat.id, "У вас недостаточно прав.")

    def admin_remove(message):
        if utils.is_admin(message.chat.id):
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    bot.send_message(message.chat.id, "Использование: /admin_remove <user_id>")
                    return
                identifier = parts[1]
                conn = sqlite3.connect('utils/databases/users.db')
                c = conn.cursor()
                if identifier.isdigit():
                    c.execute("DELETE FROM admins WHERE tg_id = ?", (int(identifier),))
                else:
                    c.execute("DELETE FROM admins WHERE nickname = ?", (identifier,))
                conn.commit()
                conn.close()
                bot.send_message(message.chat.id, f"Админ {identifier} удален")
            except IndexError:
                bot.send_message(message.chat.id, "Использование: /admin_remove <user_id>")
        else:
            bot.send_message(message.chat.id, "У вас недостаточно прав.")

    def add_subscriber(message):
        if utils.is_admin(message.chat.id):
            try:
                parts = message.text.split()
                if len(parts) < 3:
                    bot.send_message(message.chat.id, "Использование: /add_sub <user_id> <телефон>")
                    return
                user_id = int(parts[1])
                phone_number = parts[2]
                subscription_period = 30
                expiry_date = datetime.now() + timedelta(days=subscription_period)
                subscription_date = datetime.now().isoformat()

                with db_lock:
                    conn = sqlite3.connect('utils/databases/users.db')
                    c = conn.cursor()
                    # Add the user to the subscribers table
                    c.execute('''INSERT OR REPLACE INTO subscribers 
                                 (user_id, phone_number, expiry_date, subscription_date) 
                                 VALUES (?, ?, ?, ?)''',
                              (user_id, phone_number, expiry_date.isoformat(), subscription_date))

                    c.execute("DELETE FROM expired WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()

                conn_expired = sqlite3.connect('utils/databases/expired.db')
                c_expired = conn_expired.cursor()
                c_expired.execute("DELETE FROM old_expired WHERE user_id = ?", (user_id,))
                conn_expired.commit()
                conn_expired.close()

                bot.send_message(message.chat.id,
                                 f"Подписка для пользователя {user_id} добавлена до {expiry_date.strftime('%Y-%m-%d')}")
                bot.send_message(user_id,
                                 "Ваша Подписка была успешно активирована!\nПриятного пользования ботом КөмекБай!")

            except IndexError:
                bot.send_message(message.chat.id, "Использование: /add_sub <user_id> <телефон>")
            except ValueError:
                bot.send_message(message.chat.id, "Пожалуйста, введите корректные значения.")
        else:
            bot.send_message(message.chat.id, "У вас недостаточно прав.")

    def extend_subscription(message):
        if utils.is_admin(message.chat.id):
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    bot.send_message(message.chat.id, "Использование: /extend_sub <user_id>")
                    return
                user_id = int(parts[1])
                extension_days = 30

                with db_lock:
                    conn = sqlite3.connect('utils/databases/users.db')
                    c = conn.cursor()
                    c.execute("SELECT expiry_date FROM subscribers WHERE user_id = ?", (user_id,))
                    result = c.fetchone()

                    if result:
                        current_expiry = datetime.fromisoformat(result[0])
                        new_expiry = current_expiry + timedelta(days=extension_days)

                        c.execute("UPDATE subscribers SET expiry_date = ? WHERE user_id = ?",
                                  (new_expiry.isoformat(), user_id))
                        conn.commit()
                        conn.close()

                        bot.send_message(user_id,
                                         f"Ваша подписка продлена на {extension_days} дней. Новая дата окончания: {new_expiry.strftime('%Y-%m-%d')}")
                        bot.send_message(message.chat.id,
                                         f"Подписка для пользователя {user_id} продлена до {new_expiry.strftime('%Y-%m-%d')}")
                    else:
                        conn.close()
                        bot.send_message(message.chat.id, f"Пользователь {user_id} не найден среди подписчиков.")

            except IndexError:
                bot.send_message(message.chat.id, "Использование: /extend_sub <user_id>")
            except ValueError:
                bot.send_message(message.chat.id, "Пожалуйста, введите корректные значения.")
        else:
            bot.send_message(message.chat.id, "У вас недостаточно прав.")

    def remove_subscriber(message):
        if utils.is_admin(message.chat.id):
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    bot.send_message(message.chat.id, "Использование: /remove_sub <user_id>")
                    return
                user_id = int(parts[1])

                with db_lock:
                    conn = sqlite3.connect('utils/databases/users.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
                bot.send_message(message.chat.id, f"Подписка для пользователя {user_id} удалена")
            except IndexError:
                bot.send_message(message.chat.id, "Использование: /remove_sub <user_id>")
            except ValueError:
                bot.send_message(message.chat.id, "Пожалуйста, введите корректное значение.")
        else:
            bot.send_message(message.chat.id, "У вас недостаточно прав.")

    bot.register_message_handler(edit_chapter_name_handler, commands=['edit_chapter_name'])
    bot.register_message_handler(edit_lesson_name_handler, commands=['edit_lesson_name'])
    bot.register_message_handler(edit_lesson_url_handler, commands=['edit_lesson_url'])
    bot.register_message_handler(settings_handler, commands=['settings'])
    bot.register_message_handler(edit_opening_date_handler, commands=['edit_chapter_date'])
    bot.register_message_handler(add_lesson_handler, commands=['add_lesson'])
    bot.register_message_handler(add_subscriber, commands=['add_sub'])
    bot.register_message_handler(remove_subscriber, commands=['remove_sub'])
    bot.register_message_handler(extend_subscription, commands=['extend_sub'])
    bot.register_message_handler(admin_add, commands=['admin_add'])
    bot.register_message_handler(admin_remove, commands=['admin_remove'])
