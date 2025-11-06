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

# Настройки AI провайдера
# Если USE_OPENROUTER=true, будет использован OpenRouter
USE_OPENROUTER = os.getenv('USE_OPENROUTER', 'false').lower() == 'true'
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', OPENAI_API_KEY)

# Настройки модели
if USE_OPENROUTER:
    # OpenRouter модели (можно выбрать любую)
    # Примеры: openai/gpt-3.5-turbo, anthropic/claude-3-haiku, meta-llama/llama-3-70b
    OPENAI_MODEL = os.getenv('OPENROUTER_MODEL', 'openai/gpt-3.5-turbo')
    OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
    # Опционально: настройки для OpenRouter
    OPENROUTER_APP_NAME = os.getenv('OPENROUTER_APP_NAME', 'AI Content Generator')
    OPENROUTER_SITE_URL = os.getenv('OPENROUTER_SITE_URL', '')
else:
    # Обычный OpenAI
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    OPENAI_BASE_URL = None

OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.8'))
OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '2000'))

# Пути
DATA_DIR = "data"
HISTORY_FILE = f"{DATA_DIR}/user_history.json"

# Проверка наличия ключей
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен! Проверьте файл .env")

if USE_OPENROUTER:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY не установлен! Проверьте файл .env")
else:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY не установлен! Проверьте файл .env")
