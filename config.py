"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API ключи
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Настройки OpenAI
OPENAI_MODEL = "gpt-3.5-turbo"
OPENAI_TEMPERATURE = 0.8  # Для более творческих ответов
OPENAI_MAX_TOKENS = 2000

# Пути
DATA_DIR = "data"
HISTORY_FILE = f"{DATA_DIR}/user_history.json"

# Проверка наличия ключей
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен! Проверьте файл .env")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не установлен! Проверьте файл .env")
