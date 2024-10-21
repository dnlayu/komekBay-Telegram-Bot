import os
import logging

logger = logging.getLogger(__name__)


def get_chapters(grade_number):
    chapters = {}
    filepath = os.path.join("utils", "lessons", "chapters.txt")

    if not os.path.exists(filepath):
        logger.error(f"File {filepath} does not exist.")
        return chapters

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            current_grade = None
            for line in file:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Grade"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        current_grade = parts[1]
                    else:
                        logger.warning(f"Incorrect grade format: {line}")
                    continue
                if current_grade and current_grade == str(grade_number):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        chapter_no, chapter_info = parts[0].strip(), parts[1].strip()
                        chapter_name = chapter_info.split("{")[0].strip()
                        require_subscription = chapter_info.split("{")[1].split("}")[
                            0].strip() if "{" in chapter_info else ""
                        opening_date = chapter_info.split("[")[1].split("]")[0].strip() if "[" in chapter_info else None
                        chapters[chapter_no] = (chapter_name, require_subscription, opening_date)
                    else:
                        logger.warning(f"Incorrect chapter format: {line}")
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")

    return chapters


def get_lessons(grade_number, chapter_no):
    lessons = []
    lessons_filepath = os.path.join("utils", "lessons", f"grade_{grade_number}.txt")

    if not os.path.exists(lessons_filepath):
        logger.error(f"File {lessons_filepath} does not exist.")
        return lessons

    try:
        with open(lessons_filepath, 'r', encoding='utf-8') as file:
            current_chapter = None
            for line in file:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("l"):
                    parts = line.split(":")
                    if len(parts) >= 1 and parts[0][1:].isdigit():
                        current_chapter = parts[0][1:]
                    else:
                        logger.warning(f"Incorrect chapter identifier format: {line}")
                    continue
                if current_chapter == chapter_no:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        lesson_no = parts[0].strip()
                        name_and_url = parts[1].strip()
                        if "(" in name_and_url and name_and_url.endswith(")"):
                            name, url = name_and_url.rsplit("(", 1)
                            name = name.strip()
                            url = url[:-1].strip()
                        else:
                            name = name_and_url
                            url = None
                        lessons.append({
                            'number': lesson_no,
                            'name': name,
                            'url': url
                        })
                    else:
                        logger.warning(f"Incorrect lesson format: {line}")
    except Exception as e:
        logger.error(f"Error reading file {lessons_filepath}: {e}")

    return lessons
