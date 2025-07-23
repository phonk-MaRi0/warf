import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QListWidget,
                             QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCompleter, QProgressBar)  # Import QProgressBar
from PyQt5.QtCore import QStringListModel, Qt, QThread, pyqtSignal, QCoreApplication
import requests
import json
import unicodedata
import time
import re  # Import regular expressions
from item_translations import ITEM_TRANSLATIONS  # Убедитесь, что этот файл доступен

# --- Функции для работы с Warframe.Market API ---

def normalize_string(s):
    """Нормализует строку, приводя ее к нижнему регистру и удаляя диакритические знаки."""
    s = s.lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', s)
                   if unicodedata.category(c) != 'Mn')

def get_item_stats(item_name):
    """
    Получает статистику по предмету с Warframe.Market.

    Args:
        item_name (str): Название предмета (как оно указано на Warframe.Market).

    Returns:
        dict: Словарь со статистикой (средняя цена, количество проданных за 24 часа, за 48 часов)
              или None, если предмет не найден или произошла ошибка.
    """
    url = f"https://api.warframe.market/v1/items/{item_name}/statistics"
    headers = {
        "Content-Type": "application/json",
        "Platform": "pc"  # Укажите платформу (pc, ps4, xb1, switch)
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if "payload" not in data or "statistics_closed" not in data["payload"]:
            return None  # Предмет не найден или структура JSON изменилась

        statistics_closed = data["payload"]["statistics_closed"]

        # Ищем данные за "48hours"
        stats_48h = statistics_closed.get("48hours")

        # Если есть данные за 48 часов, используем их для приблизительной оценки
        if stats_48h and len(stats_48h) > 0:
            total_volume_48h = 0
            total_price_volume_48h = 0

            # Суммируем данные из всех элементов списка stats_48h
            for entry in stats_48h:
                total_volume_48h += entry["volume"]
                total_price_volume_48h += entry["volume"] * entry["avg_price"]

            # Рассчитываем среднюю цену за 48 часов (если общий объем > 0)
            if total_volume_48h > 0:
                avg_price_48h = total_price_volume_48h / total_volume_48h
            else:
                avg_price_48h = 0

            volume_24h_approx = total_volume_48h / 2
            volume_24h_approx = round(volume_24h_approx)
            avg_price_24h_approx = avg_price_48h

            return {
                "average_price_24h": round(avg_price_24h_approx, 2),
                "volume_24h": volume_24h_approx,
                "volume_48h": total_volume_48h # Added volume_48h
            }
        else:
             return {
                "average_price_24h": 0,
                "volume_24h": 0,
                "volume_48h": 0 # If no data set 0
            }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Ошибка при разборе JSON: {e}")
        return None
    except Exception as e:
        print(f"Неизвестная ошибка: {e}")
        return None

def get_all_item_stats(progress_callback):
    """
    Получает статистику по всем предметам из ITEM_TRANSLATIONS.
    """
    all_stats = {}
    total_items = len(ITEM_TRANSLATIONS)
    for i, (name, english_name) in enumerate(ITEM_TRANSLATIONS):
        normalized_english_name = normalize_string(english_name)
        stats = get_item_stats(normalized_english_name)
        time.sleep(0.5)  # Add a delay of 0.5 seconds between requests
        all_stats[name] = stats
        progress = int((i + 1) / total_items * 100)
        progress_callback.emit(progress) # Send progress to main thread
    return all_stats

def get_recommendation(all_stats):
    """
    Анализирует статистику и выдает рекомендации по продаже.
    """
    # Убираем предметы, для которых не удалось получить статистику
    valid_items = {k: v for k, v in all_stats.items() if v is not None}

    if not valid_items:
        return None, []  # Если нет доступной статистики

    # Сортируем предметы по volume_48h в убывающем порядке
    sorted_items = sorted(valid_items.items(), key=lambda item: item[1]['volume_48h'], reverse=True)

    # Рекомендованный предмет - первый в списке
    recommended_item = sorted_items[0][0]

    # Все предметы
    all_items = [item[0] for item in sorted_items]

    return recommended_item, all_items

# --- Thread для получения статистики по всем предметам ---
class AllStatsThread(QThread):
    all_stats_ready = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    progress_update = pyqtSignal(int) # Signal to update progress bar

    def __init__(self):
        super().__init__()

    def run(self):
        all_stats = get_all_item_stats(self.progress_update)
        if all_stats:
            self.all_stats_ready.emit(all_stats)
        else:
            self.error_signal.emit("Не удалось получить статистику для всех предметов")

# --- Thread для получения статистики для одного предмета ---
class StatsThread(QThread):
    stats_ready = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, item_name):
        super().__init__()
        self.item_name = item_name

    def run(self):
        stats = get_item_stats(self.item_name)
        if stats:
            self.stats_ready.emit(stats)
        else:
            self.error_signal.emit(f"Не удалось получить статистику для {self.item_name}")

# --- Главное окно приложения ---

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warframe Market Analyzer")
        self.setGeometry(100, 100, 800, 600)  # Увеличил размер окна

        # --- Список русских названий для автозаполнения ---
        self.russian_names = [name for name, _ in ITEM_TRANSLATIONS]
        self.completer_model = QStringListModel(self.russian_names)  # Модель для QCompleter

        # --- GUI Elements ---
        self.search_label = QLabel("Поиск:")
        self.search_bar = QLineEdit()
        self.completer = QCompleter()
        self.completer.setModel(self.completer_model)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.search_bar.setCompleter(self.completer)
        self.search_bar.textChanged.connect(self.update_completer) # Keep autocomplete

        self.search_bar.returnPressed.connect(self.perform_search) # <--- ADDED

        self.item_details_table = QTableWidget()
        self.item_details_table.setColumnCount(2)
        self.item_details_table.setHorizontalHeaderLabels(["Показатель", "Значение"])
        self.item_details_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.top_items_button = QPushButton("Посмотреть топ продаваемых")
        self.top_items_button.clicked.connect(self.show_top_items)

        self.top_items_table = QTableWidget()
        self.top_items_table.setColumnCount(2)
        self.top_items_table.setHorizontalHeaderLabels(["Предмет", "Продано за 48ч"])
        self.top_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # --- Layout ---
        main_layout = QVBoxLayout()

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_label)
        search_layout.addWidget(self.search_bar)
        main_layout.addLayout(search_layout)

        main_layout.addWidget(self.item_details_table)
        main_layout.addWidget(self.top_items_button)
        main_layout.addWidget(self.top_items_table)

        self.setLayout(main_layout)

    def update_completer(self, text):
        """Обновляет список вариантов автозаполнения."""
        filtered_names = [name for name in self.russian_names if normalize_string(name).startswith(normalize_string(text))]
        self.completer_model.setStringList(filtered_names)


    def perform_search(self):
        """Выполняет поиск предмета."""
        item_name = self.search_bar.text()
        if item_name:
            self.search_item(item_name)

    def search_item(self, item_name):
        """Ищет предмет и отображает его детали."""
        english_name = next((eng_name for rus_name, eng_name in ITEM_TRANSLATIONS if rus_name == item_name), None)

        if not english_name:
            self.show_error("Не удалось найти английское название предмета.")
            return

        normalized_english_name = normalize_string(english_name)

        # ----- THREAD START ----
        self.stats_thread = StatsThread(normalized_english_name)
        self.stats_thread.stats_ready.connect(self.display_item_stats)
        self.stats_thread.error_signal.connect(self.show_error)
        self.stats_thread.start()


    def display_item_stats(self, stats):
        """Отображает статистику предмета в таблице."""
        self.item_details_table.setRowCount(0)  # Clear the table

        if not stats:
            self.show_error("Статистика для данного предмета не найдена.")
            return

        # Set the number of rows
        self.item_details_table.setRowCount(3)

        # Fill the table
        self.item_details_table.setItem(0, 0, QTableWidgetItem("Средняя цена за 24ч"))
        self.item_details_table.setItem(0, 1, QTableWidgetItem(str(stats.get("average_price_24h", "N/A"))))

        self.item_details_table.setItem(1, 0, QTableWidgetItem("Продано за 24ч"))
        self.item_details_table.setItem(1, 1, QTableWidgetItem(str(stats.get("volume_24h", "N/A"))))

        self.item_details_table.setItem(2, 0, QTableWidgetItem("Продано за 48ч"))
        self.item_details_table.setItem(2, 1, QTableWidgetItem(str(stats.get("volume_48h", "N/A")))) # volume_48h


    def show_top_items(self):
        """Показывает топ продаваемых предметов."""
        self.top_items_button.setEnabled(False)  # Disable the button
        self.top_items_button.setText("Загрузка... 0%") # Set initail text
        QCoreApplication.processEvents()

        self.all_stats_thread = AllStatsThread()
        self.all_stats_thread.progress_update.connect(self.update_button_progress)
        self.all_stats_thread.all_stats_ready.connect(self.display_all_items)
        self.all_stats_thread.error_signal.connect(self.show_error)
        self.all_stats_thread.finished.connect(self.enable_button)
        self.all_stats_thread.start()


    def display_all_items(self, all_stats):
        """Отображает все предметы в таблице."""
        recommended_item, all_items = get_recommendation(all_stats)

        self.top_items_table.setRowCount(0)  # Clear table before populating
        self.top_items_table.setRowCount(len(all_items))  # Set row count to all items

        for i, item_name in enumerate(all_items):
            english_name = next((eng_name for rus_name, eng_name in ITEM_TRANSLATIONS if rus_name == item_name), None)
            if not english_name:
                volume_48h = "N/A"
            else:
                normalized_english_name = normalize_string(english_name)
                stats = get_item_stats(normalized_english_name) # Direct call to get_item_stats
                volume_48h = str(stats.get("volume_48h", "N/A")) if stats else "N/A"  # Volume_48h

            self.top_items_table.setItem(i, 0, QTableWidgetItem(item_name)) # Column 0 = Item name
            self.top_items_table.setItem(i, 1, QTableWidgetItem(volume_48h))    # Column 1 = Volume

    def show_error(self, message):
        """Отображает сообщение об ошибке."""
        QMessageBox.critical(self, "Ошибка", message)

    def update_button_progress(self, value):
        """Обновляет прогресс на кнопке."""
        self.top_items_button.setText(f"Загрузка... {value}%")
        QCoreApplication.processEvents() # Force UI update

    def enable_button(self):
        """Enables the button and resets the text."""
        self.top_items_button.setEnabled(True)
        self.top_items_button.setText("Посмотреть топ продаваемых")
        QCoreApplication.processEvents() # Force UI update

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())