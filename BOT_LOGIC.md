# Документация логики Telegram-бота "Каролина"

## 📋 Оглавление
1. [Архитектура](#архитектура)
2. [Состояния ConversationHandler](#состояния-conversationhandler)
3. [Поток работы бота](#поток-работы-бота)
4. [Обработчики и их зависимости](#обработчики-и-их-зависимости)
5. [AI-интенты](#ai-интенты)
6. [Валидация ответов](#валидация-ответов)
7. [Система хранения данных](#система-хранения-данных)
8. [Typing indicators](#typing-indicators)
9. [Пагинация истории](#пагинация-истории)

---

## Архитектура

### Основные файлы:
```
bot.py           - Основная логика бота, все обработчики
prompts.py       - AI промпты (SYSTEM_PROMPT, IDEAS_GENERATION_PROMPT, POST_GENERATION_PROMPT)
storage.py       - Работа с JSON-хранилищем пользовательских данных
config.py        - Конфигурация (токены, API ключи)
.env             - Переменные окружения
```

### Технологический стек:
- **Python 3.x**
- **python-telegram-bot v20.7** - основной фреймворк
- **OpenRouter API** - для AI генерации (через OpenAI SDK)
- **asyncio** - асинхронная обработка
- **JSON** - хранение данных пользователей

---

## Состояния ConversationHandler

```python
ASKING_NAME = 0           # Спрашиваем имя пользователя
ASKING_NICHE = 1          # Спрашиваем нишу/тематику
ASKING_GOAL = 2           # Спрашиваем цель контента
ASKING_FORMAT = 3         # Спрашиваем платформу/формат
ASKING_REUSE_PARAMS = 4   # Подтверждение переиспользования параметров
```

### Переходы между состояниями:

```
START/NEW ──> ASKING_NAME (если имя не сохранено)
          └─> ASKING_NICHE (если имя уже есть)

ASKING_NAME ──(валидация)──> ASKING_NICHE
ASKING_NICHE ──(валидация)──> ASKING_GOAL
ASKING_GOAL ──(валидация)──> ASKING_FORMAT
ASKING_FORMAT ──> [Генерация идей] ──> END

"еще идеи" + есть параметры ──> ASKING_REUSE_PARAMS
ASKING_REUSE_PARAMS ──(да)──> [Генерация идей] ──> END
                     └─(нет)─> ASKING_NICHE
```

---

## Поток работы бота

### 1. Начало работы

**Entry Points (точки входа в ConversationHandler):**
```python
/start                    → start_command()
/new                      → start_command()
🆕 Новый запрос (кнопка)  → handle_menu_buttons() → start_command()
Любой текст               → handle_free_text() [AI анализ интента]
```

**Логика start_command():**
```python
1. Проверяет имя пользователя:
   - Есть в context.user_data['user_name'] ИЛИ в storage.get_user_name()
   - Если НЕТ → переход в ASKING_NAME
   - Если ЕСТЬ → переход в ASKING_NICHE

2. Показывает приветствие (если skip_greeting=False)

3. Сохраняет имя в context для текущей сессии
```

### 2. Сбор параметров

#### ASKING_NAME → get_name()
```python
1. Получает имя от пользователя
2. Сохраняет в:
   - context.user_data['user_name']
   - storage.save_user_name(user_id, name)  # Постоянное хранилище
3. Переход → ASKING_NICHE
```

#### ASKING_NICHE → get_niche()
```python
1. Получает ответ пользователя
2. ВАЛИДАЦИЯ через validate_user_answer():
   - VALID → сохраняет в context.user_data['niche'], переход → ASKING_GOAL
   - QUESTION → отвечает на вопрос, остается в ASKING_NICHE
   - UNCLEAR → объясняет, остается в ASKING_NICHE
   - OFF_TOPIC → отменяет сессию, переход → END
3. Если VALID: переход → ASKING_GOAL
```

#### ASKING_GOAL → get_goal()
```python
1. Получает ответ пользователя
2. ВАЛИДАЦИЯ через validate_user_answer()
3. Если VALID: сохраняет в context.user_data['goal'], переход → ASKING_FORMAT
```

#### ASKING_FORMAT → get_format_and_generate()
```python
1. Получает ответ пользователя
2. ВАЛИДАЦИЯ через validate_user_answer()
3. Если VALID:
   - Сохраняет в context.user_data['format']
   - Формирует user_request = f"{niche}, {goal}, {format}"
   - Сохраняет в context.user_data['user_request']
   - Вызывает AI генерацию идей
   - Парсит ответ, создает кнопки
   - Переход → END
```

### 3. Генерация идей

**Процесс генерации в get_format_and_generate():**

```python
1. Формирование промпта:
   system_prompt = SYSTEM_PROMPT + IDEAS_GENERATION_PROMPT
   user_prompt = get_ideas_user_prompt(user_request)

2. AI запрос с typing:
   ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)

3. Парсинг ответа:
   ideas = parse_ideas_response(ideas_text)
   # Ожидается формат:
   # 1. Заголовок - Описание
   # 2. Заголовок - Описание
   # ...

4. Сохранение в context:
   context.user_data['ideas'] = ideas          # Список идей
   context.user_data['ideas_text'] = ideas_text

5. Создание кнопок:
   InlineKeyboardButton("💡 1. Заголовок", callback_data="idea_1")
   InlineKeyboardButton("💡 2. Заголовок", callback_data="idea_2")
   ...

6. Отправка с typing animation
```

### 4. Выбор идеи и генерация поста

**handle_idea_selection()** - обрабатывает callback "idea_{number}":

```python
1. Получает номер идеи из callback_data
2. Находит идею в context.user_data['ideas']
3. Сохраняет в context.user_data['selected_idea']
4. Формирует промпт для генерации поста:
   system_prompt = SYSTEM_PROMPT + POST_GENERATION_PROMPT
   user_prompt = get_post_user_prompt(user_request, selected_idea_text)
5. Генерирует пост с typing:
   post_text = await call_openai_with_typing(update, system_prompt, user_prompt)
6. Сохраняет в context.user_data['generated_post']
7. Показывает пост в код-блоке + кнопки:
   - 💾 Сохранить в избранное
   - 🔄 Другая идея
   - 🆕 Новый запрос
```

### 5. Действия после генерации

**handle_post_actions()** - обрабатывает callback после генерации поста:

```python
callback_data = "save_favorite" | "another_idea" | "new_request"

1. save_favorite:
   - Берет generated_post, selected_idea, user_request из context
   - storage.save_favorite(user_id, {...})
   - Сообщение "Сохранила!"

2. another_idea:
   - Проверяет есть ли ideas в context
   - Если есть → показывает кнопки с идеями снова
   - Если нет → сообщение об ошибке

3. new_request:
   - Очищает context.user_data.clear()
   - Запускает start_command() заново
```

---

## Обработчики и их зависимости

### Основной ConversationHandler

```python
conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start_command),
        CommandHandler("new", start_command),
        MessageHandler(menu_filter, handle_menu_buttons),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text)  # ⚠️ ВАЖНО!
    ],
    states={
        ASKING_NAME: [
            MessageHandler(menu_filter, handle_menu_buttons),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
        ],
        ASKING_NICHE: [
            MessageHandler(menu_filter, handle_menu_buttons),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_niche)
        ],
        ASKING_GOAL: [
            MessageHandler(menu_filter, handle_menu_buttons),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_goal)
        ],
        ASKING_FORMAT: [
            MessageHandler(menu_filter, handle_menu_buttons),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_and_generate)
        ],
        ASKING_REUSE_PARAMS: [
            MessageHandler(menu_filter, handle_menu_buttons),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reuse_confirmation)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
```

**⚠️ КРИТИЧЕСКИ ВАЖНО:** `handle_free_text` находится в `entry_points`, а не как отдельный handler! Это позволяет ему возвращать состояния и инициировать conversation.

### Callback Handlers (вне ConversationHandler)

```python
CallbackQueryHandler(handle_idea_selection, pattern="^idea_")
CallbackQueryHandler(handle_post_actions, pattern="^(save_favorite|another_idea|new_request)$")
CallbackQueryHandler(handle_history_pagination, pattern="^history_page_")
CallbackQueryHandler(view_saved_post, pattern="^view_post_")
```

### Standalone Handlers

```python
CommandHandler("history", history_command)
CommandHandler("help", help_command)
```

---

## AI-интенты

### handle_free_text() - AI-powered анализ намерений

**Когда вызывается:**
- Пользователь пишет текст ВНЕ conversation (не в процессе ответов на вопросы)
- Entry point в ConversationHandler

**Процесс:**

```python
1. Получает текст от пользователя
2. Формирует промпт с описанием всех интентов
3. Вызывает AI через call_openai_with_typing()
4. Парсит ответ в формате:
   INTENT: [название интента]
   RESPONSE: [ответ Каролины]
5. Выполняет соответствующее действие
```

### Список интентов:

#### 1. ANOTHER_IDEA
**Фразы:** "другую", "плохая идея", "не нравится", "покажи другие", "есть еще?"

**Логика:**
```python
if ideas в context:
    Показать все 5 идей с кнопками снова
else:
    Начать новую генерацию (start_command с skip_greeting=True)
```

#### 2. GENERATE_IDEAS
**Фразы:** "еще идеи", "еще", "дай еще", "другие идеи", "повтори", "еще раз"

**Логика:**
```python
if есть сохраненные niche, goal, format:
    Показать подтверждение:
    "Использовать те же параметры?
     Ниша: X
     Цель: Y
     Платформа: Z"
    → Переход в ASKING_REUSE_PARAMS
else:
    Начать новую сессию (start_command с skip_greeting=True)
```

#### 3. NEW_REQUEST
**Фразы:** "новый запрос", "начать заново", "с нуля"

**Логика:**
```python
Очистить context (опционально)
start_command(skip_greeting=False)  # С приветствием
```

#### 4. SHOW_HISTORY
**Фразы:** "покажи посты", "мои посты", "история", "что сохранял"

**Логика:**
```python
history_command(update, context)
→ Показывает первую страницу сохраненных постов
```

#### 5. HELP
**Фразы:** "помощь", "что умеешь", "команды"

**Логика:**
```python
help_command(update, context)
```

#### 6. GREETING
**Фразы:** "привет", "здравствуй", "хай"

**Логика:**
```python
Отвечает дружеским приветствием
Предлагает начать работу
```

#### 7. THANKS
**Фразы:** "спасибо", "благодарю", "круто", "супер"

**Логика:**
```python
Отвечает "Всегда рада помочь!" и подобными фразами
```

#### 8. OTHER
**Все остальное** (вопросы не по теме)

**Логика:**
```python
"Я много в чем сильна, но моя задача - помогать с контентом"
Предлагает создать новые идеи
```

---

## Валидация ответов

### validate_user_answer() - AI-powered валидация

**Используется в:**
- `get_niche()`
- `get_goal()`
- `get_format_and_generate()`

**Процесс:**

```python
1. Получает:
   - user_answer: ответ пользователя
   - question_context: контекст вопроса ("нишу", "цель", "платформу")
   - user_name: имя для персонализации

2. Формирует промпт для AI:
   "Я спросила про {question_context}
    Пользователь ответил: {user_answer}
    Классифицируй ответ..."

3. AI возвращает одну из категорий:
   - VALID: нормальный ответ
   - QUESTION: пользователь задал вопрос ("что такое ниша?")
   - UNCLEAR: неопределенный ответ ("другое", "не знаю", "хз")
   - OFF_TOPIC: совсем не по теме ("как погода?")

4. Для каждой категории AI генерирует подходящий ответ Каролины
```

**Применение результата:**

```python
validation = await validate_user_answer(update, niche, "нишу", user_name)

if validation['status'] == 'OFF_TOPIC':
    # Совсем не по теме - прерываем разговор
    await send_message_with_typing(update, validation['response'])
    context.user_data.clear()
    return ConversationHandler.END

elif validation['status'] in ['QUESTION', 'UNCLEAR']:
    # Вопрос или неясность - объясняем и повторяем
    await send_message_with_typing(update, validation['response'])
    return ASKING_NICHE  # Остаемся в том же состоянии

# VALID - принимаем ответ
context.user_data['niche'] = niche
# Продолжаем дальше...
```

---

## Система хранения данных

### storage.py - PostStorage класс

**Структура JSON файла:**

```json
{
  "123456789": [  // user_id
    {
      "type": "user_name",
      "name": "Алексей",
      "timestamp": "2025-01-06T12:34:56"
    },
    {
      "type": "favorite",
      "request": "фитнес, привлечь подписчиков, Instagram Reels",
      "idea": "Заголовок идеи - Описание",
      "post": "Текст поста...",
      "timestamp": "2025-01-06T13:45:00"
    },
    {
      "type": "favorite",
      "request": "...",
      "idea": "...",
      "post": "...",
      "timestamp": "..."
    }
  ],
  "987654321": [...]
}
```

### Методы storage:

```python
save_user_name(user_id, name)
# Сохраняет имя, удаляет старое если было

get_user_name(user_id) -> str
# Возвращает сохраненное имя или ""

save_favorite(user_id, request, idea, post)
# Добавляет пост в избранное с timestamp

get_favorites(user_id) -> list
# Возвращает все избранные посты пользователя
# Сортировка: новые сверху

get_user_history(user_id) -> list
# Возвращает ВСЮ историю пользователя (имя + посты)
```

### context.user_data (временное хранилище сессии)

```python
context.user_data = {
    'user_name': str,           # Имя пользователя
    'niche': str,               # Ниша/тематика
    'goal': str,                # Цель контента
    'format': str,              # Платформа/формат
    'user_request': str,        # Полный запрос "ниша, цель, формат"
    'ideas': list,              # Список сгенерированных идей
    'ideas_text': str,          # Сырой текст от AI
    'selected_idea': dict,      # Выбранная идея
    'generated_post': str,      # Сгенерированный пост
}
```

---

## Typing indicators

### Два режима typing animation:

#### 1. send_message_with_typing() - для простых сообщений
```python
# Фиксированная задержка 1 секунда
await update.effective_chat.send_action(ChatAction.TYPING)
await asyncio.sleep(1.0)
await update.message.reply_text(text)
```

**Используется для:**
- Простых ответов Каролины
- Подтверждений
- Коротких сообщений

#### 2. call_openai_with_typing() - для AI запросов
```python
# Показывает typing ВО ВРЕМЯ реального ожидания AI

1. Запускает фоновую задачу typing (повторяется каждые 4 сек)
2. Делает AI запрос через asyncio.to_thread()
3. Гарантирует минимум 1 секунду typing
4. Останавливает фоновую задачу когда получен ответ
```

**Используется для:**
- Валидация ответов (`validate_user_answer`)
- Анализ интентов (`handle_free_text`)
- Генерация идей (`get_format_and_generate`)
- Генерация постов (`handle_idea_selection`)

**Код:**
```python
async def call_openai_with_typing(update, system_prompt, user_prompt,
                                   temperature=0.7, max_tokens=2000):
    start_time = time.time()

    # Фоновая задача typing
    async def keep_typing():
        while True:
            await update.effective_chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(keep_typing())

    try:
        # Реальный AI запрос
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model=OPENAI_MODEL,
            messages=[...],
            temperature=temperature,
            max_tokens=max_tokens
        )

        result = response.choices[0].message.content.strip()

        # Минимум 1 секунда
        elapsed = time.time() - start_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        return result
    finally:
        typing_task.cancel()
```

---

## Пагинация истории

### Структура пагинации:

```
history_command()
  → show_history_page(page=0)
      → Показывает 5 постов с кнопками:
        [#1 • Первые 50 символов идеи...]
        [#2 • Другая идея...]
        ...
        [⬅️ Назад] [Дальше ➡️]

Клик на кнопку поста:
  callback_data = "view_post_{index}_{from_page}"
  → view_saved_post()
      → Показывает полный пост + кнопку:
        [⬅️ Назад к списку] → callback_data = "history_page_{from_page}"

Клик "Назад к списку":
  → handle_history_pagination()
      → show_history_page(page=from_page)  # Возврат на ту же страницу!
```

### show_history_page() - главная функция пагинации

```python
async def show_history_page(update, context, page=0):
    POSTS_PER_PAGE = 5

    # 1. Получаем посты
    favorites = storage.get_favorites(user_id)
    total_posts = len(favorites)
    total_pages = (total_posts + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE

    # 2. Вырезаем нужную страницу
    start_idx = page * POSTS_PER_PAGE
    end_idx = min(start_idx + POSTS_PER_PAGE, total_posts)
    page_posts = favorites[start_idx:end_idx]

    # 3. Создаем кнопки для каждого поста
    keyboard = []
    for i, fav in enumerate(page_posts):
        actual_idx = start_idx + i
        idea = fav.get('idea', 'Без описания')
        preview = idea[:50] + "..." if len(idea) > 50 else idea
        button_text = f"#{actual_idx + 1} • {preview}"

        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"view_post_{actual_idx}_{page}"
        )])

    # 4. Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"history_page_{page - 1}"
        ))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            "Дальше ➡️",
            callback_data=f"history_page_{page + 1}"
        ))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # 5. Отправка
    text = f"📚 Твои сохранённые посты, {user_name}\n"
    text += f"Страница {page + 1} из {total_pages} (всего {total_posts})\n\n"
    text += "Выбери пост чтобы открыть:"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
```

### view_saved_post() - просмотр конкретного поста

```python
async def view_saved_post(update, context):
    query = update.callback_query

    # Парсим callback_data: "view_post_{index}_{page}"
    parts = query.data.split('_')
    post_idx = int(parts[2])
    from_page = int(parts[3])  # ⚠️ Запоминаем страницу!

    # Получаем пост
    favorites = storage.get_favorites(user_id)
    fav = favorites[post_idx]

    # Форматируем
    text = f"📝 Пост #{post_idx + 1}\n"
    text += f"📅 {timestamp[:10]}\n\n"
    text += f"📋 Запрос: {request}\n\n"
    text += f"💡 Идея: {idea}\n\n"
    text += f"```\n{post}\n```\n\n"
    text += "💡 _Нажми на текст поста чтобы скопировать_"

    # Кнопка "Назад" с указанием страницы
    keyboard = [[InlineKeyboardButton(
        "⬅️ Назад к списку",
        callback_data=f"history_page_{from_page}"  # ⚠️ Возврат на ту же страницу!
    )]]

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
```

---

## Зависимости между компонентами

### Граф зависимостей:

```
ConversationHandler
├─ entry_points
│  ├─ start_command()
│  │  └─ storage.get_user_name()
│  ├─ handle_menu_buttons()
│  └─ handle_free_text()
│     ├─ call_openai_with_typing()  [AI интент]
│     ├─ start_command()
│     ├─ history_command()
│     └─ help_command()
│
├─ states
│  ├─ ASKING_NAME → get_name()
│  │  └─ storage.save_user_name()
│  │
│  ├─ ASKING_NICHE → get_niche()
│  │  └─ validate_user_answer()
│  │     └─ call_openai_with_typing()  [AI валидация]
│  │
│  ├─ ASKING_GOAL → get_goal()
│  │  └─ validate_user_answer()
│  │     └─ call_openai_with_typing()  [AI валидация]
│  │
│  ├─ ASKING_FORMAT → get_format_and_generate()
│  │  ├─ validate_user_answer()
│  │  │  └─ call_openai_with_typing()  [AI валидация]
│  │  ├─ call_openai_with_typing()  [Генерация идей]
│  │  └─ parse_ideas_response()
│  │
│  └─ ASKING_REUSE_PARAMS → handle_reuse_confirmation()
│     └─ [Повторяет логику генерации идей]
│
└─ fallbacks
   └─ cancel()

Callback Handlers (вне ConversationHandler):
├─ handle_idea_selection()
│  ├─ call_openai_with_typing()  [Генерация поста]
│  └─ get_post_user_prompt()
│
├─ handle_post_actions()
│  ├─ save_favorite → storage.save_favorite()
│  ├─ another_idea → [показывает кнопки с идеями]
│  └─ new_request → start_command()
│
├─ handle_history_pagination()
│  └─ show_history_page()
│
└─ view_saved_post()
   └─ storage.get_favorites()

Standalone Commands:
├─ history_command()
│  ├─ storage.get_favorites()
│  └─ show_history_page()
│
└─ help_command()
```

### Критические зависимости:

1. **handle_free_text ДОЛЖЕН быть в entry_points**, иначе не может возвращать состояния
2. **context.user_data очищается при новой сессии**, поэтому параметры нужно проверять
3. **storage - единственный источник постоянных данных** (имя, посты)
4. **Все AI вызовы идут через call_openai_with_typing()** для показа typing
5. **Пагинация хранит from_page в callback_data** для возврата на ту же страницу

---

## Константы и конфигурация

### config.py:
```python
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'meta-llama/llama-3.1-8b-instruct:free')
OPENAI_TEMPERATURE = 0.7
```

### prompts.py:
```python
SYSTEM_PROMPT - базовая личность Каролины (женщина, контент-маркетолог)
IDEAS_GENERATION_PROMPT - промпт для генерации 5 идей
POST_GENERATION_PROMPT - промпт для генерации поста по идее
```

### Функции из prompts.py:
```python
get_ideas_user_prompt(user_request) -> str
# Форматирует запрос пользователя для генерации идей

get_post_user_prompt(user_request, selected_idea) -> str
# Форматирует запрос для генерации поста

parse_ideas_response(ideas_text) -> list[dict]
# Парсит ответ AI в структурированный список идей
# Формат: [{number: 1, title: "...", description: "..."}, ...]
```

---

## Меню-кнопки

### get_main_menu_keyboard():
```python
ReplyKeyboardMarkup([
    ["🆕 Новый запрос", "📚 Мои посты"],
    ["❌ Отмена"]
], resize_keyboard=True)
```

**Обработка в handle_menu_buttons():**
```python
"🆕 Новый запрос" → start_command()
"📚 Мои посты" → history_command()
"❌ Отмена" → cancel() (очистка + приветственное сообщение)
```

---

## Логи и отладка

### Важные логи:

```python
logger.info(f"👤 Новый пользователь: {user_name}")
logger.info(f"🎯 Попытка ввода ниши: {niche}")
logger.info(f"✅ Ниша принята: {niche}")
logger.info(f"💬 Свободное сообщение от {user_name}: {user_text}")
logger.info(f"🤖 AI ответ: {ai_response}")
logger.info(f"🔄 Подтверждение переиспользования параметров: {user_text}")
logger.info(f"💾 Сохраняем пост в избранное")
```

---

## Возможные проблемы и решения

### 1. "Бот не понимает команды после генерации поста"
**Причина:** handle_free_text не в entry_points
**Решение:** Убедиться что handle_free_text в entry_points ConversationHandler

### 2. "Состояние теряется после запуска start_command из handle_free_text"
**Причина:** handle_free_text был standalone handler
**Решение:** Переместить в entry_points

### 3. "Typing показывается слишком быстро"
**Причина:** Использовался send_message_with_typing вместо call_openai_with_typing
**Решение:** Для AI запросов всегда использовать call_openai_with_typing

### 4. "Валидация не работает"
**Причина:** AI возвращает неожиданный формат
**Решение:** Проверить парсинг INTENT: и RESPONSE: в коде

### 5. "Пагинация возвращает на первую страницу"
**Причина:** Не передается from_page в callback_data
**Решение:** Проверить callback_data = f"view_post_{idx}_{page}"

### 6. "Кнопки-миниатюры показывают запрос вместо идеи"
**Причина:** Использовалось fav.get('request') вместо fav.get('idea')
**Решение:** В show_history_page использовать idea для preview

---

## Итоговая схема работы бота

```
ПОЛЬЗОВАТЕЛЬ
    ↓
[Отправляет сообщение]
    ↓
┌─────────────────────────────────┐
│ Определение точки входа:        │
│ • /start, /new → start_command  │
│ • Кнопка → handle_menu_buttons  │
│ • Текст → handle_free_text      │
└─────────────────────────────────┘
    ↓
[ConversationHandler определяет состояние]
    ↓
┌──────────────────────────────────────┐
│ ASKING_NAME → get_name               │
│ ASKING_NICHE → get_niche (валидация) │
│ ASKING_GOAL → get_goal (валидация)   │
│ ASKING_FORMAT → get_format (+ gen)   │
│ ASKING_REUSE_PARAMS → confirmation   │
└──────────────────────────────────────┘
    ↓
[Генерация идей через AI]
    ↓
[Показ 5 идей с кнопками]
    ↓
[Пользователь выбирает идею]
    ↓
[Генерация поста через AI]
    ↓
[Показ поста + кнопки действий]
    ↓
┌────────────────────────────────┐
│ 💾 Сохранить → storage         │
│ 🔄 Другая идея → показать идеи │
│ 🆕 Новый запрос → start заново │
└────────────────────────────────┘
```

---

## Версия бота: 2025-01-06

**Основные возможности:**
✅ Персонализация (запоминает имя)
✅ AI-валидация ответов с аварийными сценариями
✅ AI-распознавание интентов для свободного текста
✅ Генерация 5 идей на основе ниши/цели/платформы
✅ Генерация поста по выбранной идее
✅ Сохранение постов в избранное
✅ Пагинированная история с кнопками-миниатюрами
✅ Умное переиспользование параметров ("еще идеи")
✅ Реальные typing indicators во время AI обработки
✅ Постоянное меню-кнопки для навигации
✅ Копирование постов одним тапом (код-блоки)

**AI Модель:** OpenRouter (бесплатные модели)
**Язык:** Русский
**Персонаж:** Каролина (женщина, контент-маркетолог)
