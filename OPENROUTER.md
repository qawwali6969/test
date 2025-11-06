# 🔄 Использование OpenRouter

## Что такое OpenRouter?

OpenRouter - это унифицированный API для доступа к множеству AI моделей через один интерфейс:
- 🤖 OpenAI (GPT-3.5, GPT-4)
- 🧠 Anthropic (Claude)
- 🦙 Meta (Llama)
- ✨ Google (Gemini)
- И многие другие

**Преимущества:**
- ✅ Один API ключ для всех моделей
- ✅ Часто дешевле чем прямой доступ
- ✅ Fallback между моделями
- ✅ Детальная статистика использования

---

## 🚀 Быстрый старт

### 1. Получите API ключ OpenRouter

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
2. Пополните баланс ($5 минимум)
3. Создайте API ключ в [Keys](https://openrouter.ai/keys)

### 2. Настройте .env файл

Откройте файл `.env` и настройте для OpenRouter:

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather

# Включить OpenRouter
USE_OPENROUTER=true
OPENROUTER_API_KEY=sk-or-v1-ваш_ключ_openrouter
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```

### 3. Запустите бота

```bash
python bot.py
```

Вы должны увидеть:
```
🔄 Используется OpenRouter с моделью: openai/gpt-3.5-turbo
🤖 Бот запущен!
```

---

## 🎯 Выбор модели

### Популярные модели для контент-генерации:

#### 💰 Бюджетные варианты:
```env
OPENROUTER_MODEL=openai/gpt-3.5-turbo          # ~$0.002 / 1K токенов
OPENROUTER_MODEL=anthropic/claude-3-haiku      # ~$0.0025 / 1K токенов
OPENROUTER_MODEL=mistralai/mistral-7b-instruct # ~$0.0006 / 1K токенов
```

#### 🚀 Качественные варианты:
```env
OPENROUTER_MODEL=openai/gpt-4-turbo            # ~$0.01 / 1K токенов
OPENROUTER_MODEL=anthropic/claude-3-sonnet     # ~$0.015 / 1K токенов
OPENROUTER_MODEL=meta-llama/llama-3-70b-instruct # ~$0.008 / 1K токенов
```

#### 🌟 Премиум варианты:
```env
OPENROUTER_MODEL=openai/gpt-4                  # ~$0.03 / 1K токенов
OPENROUTER_MODEL=anthropic/claude-3-opus       # ~$0.075 / 1K токенов
OPENROUTER_MODEL=google/gemini-pro-1.5         # ~$0.007 / 1K токенов
```

**Полный список моделей:** https://openrouter.ai/models

#### 🆓 БЕСПЛАТНЫЕ модели (актуально на 2025):
```env
# Рекомендуемые бесплатные модели:
OPENROUTER_MODEL=mistralai/mistral-small-3.1-24b-instruct:free  # 24B параметров, март 2025
OPENROUTER_MODEL=google/gemma-3-4b-it:free                       # Google Gemma 3, быстрая
OPENROUTER_MODEL=deepseek/deepseek-r1-distill-llama-70b:free   # 70B параметров, мощная
```

**⚠️ Важно для бесплатных моделей:**
- Лимит: 50 запросов/день (или 1000/день если пополнили баланс на $10+)
- Нужно включить "Privacy Settings" → "Allow training" на openrouter.ai
- Могут быть очереди в часы пик
- Если модель недоступна (404 ошибка) - попробуйте другую из списка

**Проблема "No endpoints found"?**
Модель временно недоступна. Смените на другую бесплатную модель из списка выше.

---

## ⚙️ Дополнительные настройки

### Настройка температуры и токенов:

```env
# Температура (0.0 - 1.0)
# Чем выше - тем креативнее, но менее предсказуемо
OPENAI_TEMPERATURE=0.8

# Максимальное количество токенов в ответе
OPENAI_MAX_TOKENS=2000
```

### Опциональные параметры OpenRouter:

```env
# Название вашего приложения (показывается в статистике)
OPENROUTER_APP_NAME=AI Content Generator

# URL вашего сайта (для аналитики)
OPENROUTER_SITE_URL=https://yoursite.com
```

---

## 🔄 Переключение между OpenAI и OpenRouter

### Использовать OpenRouter:
```env
USE_OPENROUTER=true
OPENROUTER_API_KEY=sk-or-v1-ваш_ключ
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```

### Использовать обычный OpenAI:
```env
USE_OPENROUTER=false
OPENAI_API_KEY=sk-ваш_ключ_openai
OPENAI_MODEL=gpt-3.5-turbo
```

---

## 📊 Мониторинг использования

OpenRouter предоставляет детальную статистику:
1. Перейдите на [openrouter.ai/activity](https://openrouter.ai/activity)
2. Смотрите:
   - Количество запросов
   - Использованные токены
   - Стоимость
   - Какие модели использовались

---

## 🐛 Решение проблем

### Ошибка: "Invalid API key"
- Проверьте правильность ключа
- Убедитесь, что ключ начинается с `sk-or-v1-`
- Проверьте баланс на openrouter.ai

### Ошибка: "Model not found"
- Проверьте правильность названия модели
- Список моделей: https://openrouter.ai/models
- Формат: `provider/model-name`

### Ошибка: "Insufficient balance"
- Пополните баланс на openrouter.ai
- Минимум: $5

### Медленная генерация
- Некоторые модели медленнее других
- Попробуйте более быструю модель (gpt-3.5-turbo, claude-3-haiku)
- Уменьшите `OPENAI_MAX_TOKENS`

---

## 💡 Рекомендации

### Для тестирования:
```env
OPENROUTER_MODEL=mistralai/mistral-7b-instruct
```
Очень дешево, хорошее качество для простых задач.

### Для продакшена (баланс цена/качество):
```env
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```
Проверенная модель, отличное качество контента.

### Для максимального качества:
```env
OPENROUTER_MODEL=anthropic/claude-3-sonnet
```
Лучше справляется с длинными текстами и креативностью.

---

## 📝 Пример полного .env для OpenRouter

```env
# Telegram
TELEGRAM_BOT_TOKEN=7123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# OpenRouter
USE_OPENROUTER=true
OPENROUTER_API_KEY=sk-or-v1-abc123def456ghi789jkl
OPENROUTER_MODEL=openai/gpt-3.5-turbo
OPENROUTER_APP_NAME=AI Content Generator

# Настройки генерации
OPENAI_TEMPERATURE=0.8
OPENAI_MAX_TOKENS=2000
```

---

## 🔗 Полезные ссылки

- OpenRouter сайт: https://openrouter.ai
- Список моделей: https://openrouter.ai/models
- Документация: https://openrouter.ai/docs
- Цены: https://openrouter.ai/models (столбец "Price")
- Статистика: https://openrouter.ai/activity

---

**Готово! Теперь вы можете использовать любую AI модель через OpenRouter 🎉**
