"""
Модуль для работы с хранением данных
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Any
from config import HISTORY_FILE, DATA_DIR


class Storage:
    """Класс для работы с историей пользователей"""

    def __init__(self):
        self._ensure_data_dir()
        self._ensure_history_file()

    def _ensure_data_dir(self):
        """Создает директорию data если её нет"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def _ensure_history_file(self):
        """Создает файл истории если его нет"""
        if not os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load_history(self) -> Dict:
        """Загружает историю из файла"""
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки истории: {e}")
            return {}

    def _save_history(self, history: Dict):
        """Сохраняет историю в файл"""
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")

    def get_user_history(self, user_id: int) -> List[Dict]:
        """Получает историю конкретного пользователя"""
        history = self._load_history()
        user_id_str = str(user_id)
        return history.get(user_id_str, [])

    def add_to_history(self, user_id: int, item: Dict):
        """Добавляет запись в историю пользователя"""
        history = self._load_history()
        user_id_str = str(user_id)

        if user_id_str not in history:
            history[user_id_str] = []

        # Добавляем timestamp
        item['timestamp'] = datetime.now().isoformat()

        history[user_id_str].append(item)
        self._save_history(history)

    def save_favorite(self, user_id: int, request: str, idea: str, post: str):
        """Сохраняет избранный пост"""
        self.add_to_history(user_id, {
            'type': 'favorite',
            'request': request,
            'idea': idea,
            'post': post
        })

    def get_favorites(self, user_id: int) -> List[Dict]:
        """Получает все избранные посты пользователя"""
        user_history = self.get_user_history(user_id)
        return [item for item in user_history if item.get('type') == 'favorite']

    def delete_favorite(self, user_id: int, index: int) -> bool:
        """Удаляет избранный пост по индексу

        Args:
            user_id: ID пользователя
            index: Индекс поста в списке favorites (0-based)

        Returns:
            bool: True если удаление успешно, False если пост не найден
        """
        history = self._load_history()
        user_id_str = str(user_id)

        if user_id_str not in history:
            return False

        user_items = history[user_id_str]

        # Получаем только favorites
        favorites = [item for item in user_items if item.get('type') == 'favorite']

        if index < 0 or index >= len(favorites):
            return False

        # Находим целевой пост
        target_post = favorites[index]

        # Удаляем его из общего списка
        # Ищем по полному совпадению
        for i, item in enumerate(user_items):
            if (item.get('type') == 'favorite' and
                item.get('post') == target_post.get('post') and
                item.get('timestamp') == target_post.get('timestamp')):
                user_items.pop(i)
                break

        history[user_id_str] = user_items
        self._save_history(history)
        return True

    def clear_user_history(self, user_id: int):
        """Очищает историю пользователя"""
        history = self._load_history()
        user_id_str = str(user_id)

        if user_id_str in history:
            history[user_id_str] = []
            self._save_history(history)

    def save_user_name(self, user_id: int, name: str):
        """Сохраняет имя пользователя"""
        history = self._load_history()
        user_id_str = str(user_id)

        if user_id_str not in history:
            history[user_id_str] = []

        # Сохраняем имя как специальный тип записи
        # Сначала удаляем старое имя если есть
        history[user_id_str] = [item for item in history[user_id_str] if item.get('type') != 'user_name']

        # Добавляем новое имя
        history[user_id_str].insert(0, {
            'type': 'user_name',
            'name': name,
            'timestamp': datetime.now().isoformat()
        })

        self._save_history(history)

    def get_user_name(self, user_id: int) -> str:
        """Получает сохранённое имя пользователя"""
        user_history = self.get_user_history(user_id)
        for item in user_history:
            if item.get('type') == 'user_name':
                return item.get('name', '')
        return ''


# Создаем глобальный экземпляр
storage = Storage()
