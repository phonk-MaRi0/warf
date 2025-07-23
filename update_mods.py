import requests
import re  # Import regular expressions
from item_translations import ITEM_TRANSLATIONS

def update_item_translations_from_txt(github_url):
    """
    Обновляет ITEM_TRANSLATIONS, добавляя моды из TXT файла с GitHub.

    Args:
        github_url (str): URL TXT-файла в репозитории GitHub.
    """
    try:
        response = requests.get(github_url)
        response.raise_for_status()  # Проверяем, что запрос выполнен успешно (код 200)
        text_data = response.text  # Получаем текст из ответа
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении данных с GitHub: {e}")
        return

    lines = text_data.splitlines()  # Разделяем текст на строки
    new_mods = []
    for line in lines:
        line = line.strip()  # Remove leading/trailing spaces

        # Skip lines that start with "##" (headers)
        if line.startswith("##"):
            continue

        # Use regular expression to split the line
        parts = re.split(r'\s{3,}|\t', line)  # Split by 3+ spaces or tab

        if len(parts) == 2:
            russian_name, english_name = parts[0].strip(), parts[1].strip() # Remove leading/trailing spaces

            # Removing Square brackets
            english_name = english_name.replace('[','').replace(']','')
            russian_name = russian_name.replace('[','').replace(']','')

            english_name = english_name.lower().replace(" ", "_").replace("-", "_") # Replace spaces with underscores and convert to lowercase
            english_name = re.sub(r'[^a-zA-Z0-9_]', '', english_name)  # Remove all characters except letters, numbers, and underscores

            new_mods.append((russian_name, english_name))

    # Adding non-duplicate mods
    for russian_name, english_name in new_mods:
        if not any(rus_name == russian_name for rus_name, _ in ITEM_TRANSLATIONS):
            ITEM_TRANSLATIONS.append((russian_name, english_name))
            print(f"Добавлен мод: {russian_name} ({english_name})")  # Log when add new item
        else:
            print(f"Мод уже существует: {russian_name}") # Log duplicate items

    print("Обновление ITEM_TRANSLATIONS завершено.")


# Example use
github_url = "https://raw.githubusercontent.com/phonk-MaRi0/warf/main/%D0%9A%D0%BD%D0%B8%D0%B3%D0%B01.txt"
update_item_translations_from_txt(github_url)

# В конце скрипта после update_item_translations_from_txt(github_url)
with open("item_translations.py", "w", encoding="utf-8") as f:
    f.write("ITEM_TRANSLATIONS = [\n")
    for russian_name, english_name in ITEM_TRANSLATIONS:
        f.write(f'    ("{russian_name}", "{english_name}"),\n')
    f.write("]\n")

print(ITEM_TRANSLATIONS)
