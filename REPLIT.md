# 🚀 Деплой бота на Replit

Replit - отличная платформа для запуска бота 24/7 с бесплатным тарифом!

## ✅ Преимущества Replit:

- 🆓 **Бесплатный тариф** (с ограничениями)
- 🌐 **Работает 24/7** (на платном Always On)
- 🔧 **Простая настройка** (всё в браузере)
- 🔒 **Безопасное хранение ключей** (Secrets)
- 🐍 **Python из коробки**

---

## 📦 Пошаговая инструкция

### Шаг 1: Создайте Repl

1. Зайдите на [replit.com](https://replit.com)
2. Войдите или зарегистрируйтесь
3. Нажмите **+ Create Repl**
4. Выберите:
   - Template: **Python**
   - Title: `AI Content Generator Bot`
5. Нажмите **Create Repl**

---

### Шаг 2: Загрузите код

#### Вариант А: Через GitHub (рекомендуется)

1. В Replit нажмите на три точки (...) → **Import from GitHub**
2. Вставьте URL вашего репозитория
3. Нажмите **Import**

#### Вариант Б: Вручную

1. Удалите файл `main.py`
2. Загрузите все файлы проекта через **Upload file**:
   - `bot.py`
   - `config.py`
   - `prompts.py`
   - `storage.py`
   - `requirements.txt`
   - `.replit`

---

### Шаг 3: Установите зависимости

В терминале Replit (снизу) выполните:

```bash
pip install -r requirements.txt
```

Или просто нажмите **Run** - Replit автоматически установит зависимости.

---

### Шаг 4: Настройте Secrets (переменные окружения)

**ВАЖНО:** НЕ используйте .env файл на Replit! Используйте Secrets.

1. На левой панели найдите иконку 🔒 **Secrets** (замок)
2. Или откройте Tools → Secrets
3. Добавьте следующие секреты:

#### Обязательные секреты:

**Для Telegram:**
```
Key: TELEGRAM_BOT_TOKEN
Value: ваш_токен_от_BotFather
```

**Для OpenRouter (рекомендуется):**
```
Key: USE_OPENROUTER
Value: true

Key: OPENROUTER_API_KEY
Value: sk-or-v1-ваш_ключ_openrouter

Key: OPENROUTER_MODEL
Value: openai/gpt-3.5-turbo
```

**Для обычного OpenAI (альтернатива):**
```
Key: USE_OPENROUTER
Value: false

Key: OPENAI_API_KEY
Value: sk-ваш_ключ_openai

Key: OPENAI_MODEL
Value: gpt-3.5-turbo
```

#### Опциональные секреты:

```
Key: OPENAI_TEMPERATURE
Value: 0.8

Key: OPENAI_MAX_TOKENS
Value: 2000

Key: OPENROUTER_APP_NAME
Value: AI Content Generator

Key: OPENROUTER_SITE_URL
Value: https://ваш-сайт.com
```

---

### Шаг 5: Запустите бота

1. Нажмите большую зелёную кнопку **Run** (или F5)
2. В консоли должно появиться:
   ```
   🔄 Используется OpenRouter с моделью: openai/gpt-3.5-turbo
   🤖 Бот запущен!
   ```
3. Откройте Telegram и напишите вашему боту `/start`

**Готово! Бот работает! 🎉**

---

## 🔄 Как бот будет работать 24/7

### На бесплатном тарифе:

❌ **Проблема:** Replit выключает бесплатные проекты через некоторое время неактивности.

✅ **Решение 1:** Использовать UptimeRobot (бесплатно)
1. Зарегистрируйтесь на [uptimerobot.com](https://uptimerobot.com)
2. Добавьте новый монитор (HTTP)
3. URL: `https://ваш-repl.username.repl.co`
4. Интервал: 5 минут
5. UptimeRobot будет "будить" ваш Repl

✅ **Решение 2:** Replit Always On (платно)
- $7/месяц
- Гарантирует работу 24/7
- В настройках Repl → включите **Always On**

### На платном тарифе (Replit Core):

✅ Просто включите **Always On** в настройках Repl.

---

## 🐛 Возможные проблемы и решения

### Проблема: "Module not found"

**Решение:**
```bash
pip install -r requirements.txt
```

### Проблема: "TELEGRAM_BOT_TOKEN не установлен"

**Решение:**
- Проверьте что добавили секрет `TELEGRAM_BOT_TOKEN` (не забудьте сохранить!)
- Перезапустите Repl

### Проблема: "Error 429: Too Many Requests"

**Решение:**
- Слишком много запросов к OpenRouter/OpenAI
- Подождите несколько минут
- Проверьте лимиты вашего аккаунта

### Проблема: Бот не отвечает

**Решение:**
1. Проверьте логи в консоли Replit
2. Убедитесь что бот запущен (Run)
3. Проверьте правильность токена
4. Попробуйте `/start` в Telegram

### Проблема: "Out of memory"

**Решение:**
- Replit имеет лимит памяти на бесплатном тарифе
- Перезапустите Repl
- Рассмотрите платный тариф

---

## 💰 Стоимость

### Replit:
- **Бесплатно:** 0.5 GB RAM, останавливается при неактивности
- **Core ($20/мес):** 2 GB RAM, Always On, приоритетная поддержка

### OpenRouter/OpenAI:
- См. OPENROUTER.md для деталей
- Примерно $0.0014 за 1 полную генерацию (5 идей + пост)

**Итого для 100 пользователей/день:**
- Replit: $0 (бесплатный) или $20/мес (Always On)
- AI API: ~$14/мес (при 100 генерациях в день)

---

## 📊 Мониторинг

### Просмотр логов в Replit:

1. Откройте консоль (снизу в Replit)
2. Все события бота будут отображаться там
3. Ошибки будут выделены красным

### Просмотр использования AI:

**Для OpenRouter:**
- [openrouter.ai/activity](https://openrouter.ai/activity)

**Для OpenAI:**
- [platform.openai.com/usage](https://platform.openai.com/usage)

---

## 🔒 Безопасность

### ✅ Что делать:

- Всегда используйте Secrets для API ключей
- НЕ коммитьте .env в Git
- Регулярно проверяйте баланс AI провайдера
- Установите лимиты расходов в OpenRouter/OpenAI

### ❌ Что НЕ делать:

- Не публикуйте API ключи в коде
- Не делайте Repl публичным с открытыми Secrets
- Не давайте доступ к Repl посторонним

---

## 🚀 Оптимизация для Replit

### 1. Добавьте keepalive (для бесплатного тарифа)

Создайте файл `keep_alive.py`:

```python
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
```

В `bot.py` добавьте в начало:

```python
from keep_alive import keep_alive

# В функции main() перед application.run_polling():
keep_alive()
```

И добавьте в `requirements.txt`:
```
flask
```

### 2. Настройте .gitignore для Replit

Добавьте в `.gitignore`:
```
.replit
.upm/
venv/
```

---

## 📝 Чеклист запуска

- [ ] Создан Repl на replit.com
- [ ] Загружен код проекта
- [ ] Установлены зависимости (`pip install -r requirements.txt`)
- [ ] Добавлены все необходимые Secrets
- [ ] Бот запущен (кнопка Run)
- [ ] Протестирован в Telegram (`/start`)
- [ ] (Опционально) Настроен UptimeRobot для 24/7
- [ ] (Опционально) Включен Always On

---

## 🔗 Полезные ссылки

- Replit документация: https://docs.replit.com
- UptimeRobot (для keepalive): https://uptimerobot.com
- Replit Secrets: https://docs.replit.com/programming-ide/workspace-features/secrets

---

## 💡 Советы

1. **Для разработки:** используйте бесплатный Repl
2. **Для продакшена:** рассмотрите Replit Core ($20/мес) с Always On
3. **Альтернативы Replit:**
   - Railway.app (бесплатный tier)
   - Render.com (бесплатный tier)
   - PythonAnywhere (бесплатный tier)
   - Heroku (платный, от $5/мес)

---

**Готово! Ваш бот работает на Replit! 🎉**

Если возникнут проблемы - проверьте логи в консоли Replit или напишите в Issues на GitHub.
