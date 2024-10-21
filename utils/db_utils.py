import sqlite3
import logging as logger
from collections import defaultdict

def is_admin(user_id):
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM admins WHERE tg_id = ?", (user_id,))
    admin_entry = c.fetchone()
    conn.close()
    return admin_entry is not None

def is_subscriber(user_id):
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM subscribers WHERE user_id = ?", (user_id,))
    subscriber_entry = c.fetchone()
    conn.close()
    return subscriber_entry is not None

def split_message_in_half(message):
    half_index = len(message) // 2
    split_index = message.rfind('\n', 0, half_index)
    if split_index == -1:
        split_index = half_index

    part1 = message[:split_index].strip()
    part2 = message[split_index:].strip()
    return [part1, part2]


def get_chapters(chapters_file, grade_number):
    chapters = {}
    current_grade = None
    try:
        with open(chapters_file, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith("Grade"):
                    current_grade = line.strip()
                    logger.debug(f"Current grade set to: {current_grade}")

                if current_grade == f"Grade {grade_number}" and ': ' in line:
                    chapter_number, chapter_name = line.strip().split(': ', 1)
                    chapters[chapter_number] = chapter_name
                    logger.debug(f"Added chapter {chapter_number}: {chapter_name}")
    except FileNotFoundError:
        logger.error(f"{chapters_file} не найден.")
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {chapters_file}: {e}")

    logger.info(f"Chapters for Grade {grade_number}: {chapters}")
    return chapters


def get_lessons(lessons_file):
    lessons = {}
    try:
        with open(lessons_file, 'r', encoding='utf-8') as file:
            current_chapter = None
            for line in file:
                if line.startswith('l'):
                    current_chapter = line.strip()[:-1]
                elif current_chapter and line.strip():
                    lesson_number, lesson_info = line.strip().split(': ', 1)
                    if ' (' in lesson_info and lesson_info.endswith(')'):
                        lesson_name, lesson_url = lesson_info.split(' (', 1)
                        lesson_key = f"{current_chapter}_{lesson_number}"
                        lessons[lesson_key] = {
                            'name': lesson_name.strip(),
                            'url': lesson_url[:-1].strip()
                        }
    except FileNotFoundError:
        logger.error(f"{lessons_file} не найден.")
    return lessons


def save_chapters(chapters_file, grade_number, chapters):
    try:
        with open(chapters_file, 'r+', encoding='utf-8') as file:
            lines = file.readlines()
            file.seek(0)
            file.truncate()

            grade_found = False
            for line in lines:
                if line.startswith(f"Grade {grade_number}"):
                    grade_found = True
                    file.write(line)
                    for chapter_number, chapter_name in chapters.items():
                        safe_chapter_name = chapter_name.replace('_', ' ')
                        file.write(f"{chapter_number}: {safe_chapter_name}\n")
                    continue

                if line.startswith("Grade") and grade_found:
                    grade_found = False

                if not grade_found:
                    file.write(line)
    except Exception as e:
        logger.error(f"Ошибка при сохранении разделов в {chapters_file}: {e}")


def save_lessons(lessons_file, lessons):
    try:
        lessons_by_chapter = defaultdict(list)
        for lesson_key, lesson_data in lessons.items():
            chapter, lesson_num = lesson_key.split('_')
            lessons_by_chapter[chapter].append((lesson_num, lesson_data))

        with open(lessons_file, 'w', encoding='utf-8') as file:
            for chapter in sorted(lessons_by_chapter.keys(), key=lambda x: int(x[1:])):
                file.write(f"{chapter}:\n")
                sorted_lessons = sorted(lessons_by_chapter[chapter], key=lambda x: int(x[0]))
                for lesson_num, lesson_data in sorted_lessons:
                    safe_lesson_name = lesson_data['name'].replace('_', ' ')
                    safe_lesson_url = lesson_data['url']
                    file.write(f"    {lesson_num}: {safe_lesson_name} ({safe_lesson_url})\n")
    except Exception as e:
        logger.error(f"Ошибка при сохранении уроков в {lessons_file}: {e}")


def init_db():
    conn = sqlite3.connect('utils/databases/users.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS admins (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 nickname TEXT, 
                 tg_id INTEGER UNIQUE)''')

    c.execute('''CREATE TABLE IF NOT EXISTS subscribers (
                 user_id INTEGER PRIMARY KEY, 
                 phone_number TEXT,
                 expiry_date TEXT,
                 subscription_date TEXT)''')

    # Create the expired table for users with expired subscriptions
    c.execute('''CREATE TABLE IF NOT EXISTS expired (
                 user_id INTEGER PRIMARY KEY, 
                 phone_number TEXT,
                 expiry_date TEXT,
                 subscription_date TEXT)''')  # Track when the user expired

    conn.commit()
    conn.close()

    # Create the old_expired table in the expired.db database
    conn_expired = sqlite3.connect('utils/databases/expired.db')
    c_expired = conn_expired.cursor()
    c_expired.execute('''CREATE TABLE IF NOT EXISTS old_expired (
                         user_id INTEGER PRIMARY KEY, 
                         phone_number TEXT,
                         expiry_date TEXT,
                         subscription_date TEXT)''')
    conn_expired.commit()
    conn_expired.close()