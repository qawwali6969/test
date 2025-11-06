# 🎭 ИНСТРУКЦИЯ: Как добавить диалоговый режим с Каролиной

## Изменения которые нужно внести в bot.py:

### 1. УЖЕ СДЕЛАНО ✅:
- Добавлен import ConversationHandler
- Добавлены состояния: ASKING_NAME, ASKING_NICHE, ASKING_GOAL, ASKING_FORMAT

### 2. ЗАМЕНИТЬ функцию start_command (строка ~102):

```python
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - начало диалога с Каролиной"""
    logger.info(f"📥 Новый пользователь: {update.effective_user.id}")

    welcome_text = """👋 Привет! Меня зовут Каролина.

Я твой личный креативный ассистент по написанию постов и генерации идей для контента.

Буду рада познакомиться!

Как тебя зовут?"""

    await update.message.reply_text(welcome_text)
    return ASKING_NAME
```

### 3. ДОБАВИТЬ после start_command новые функции:

```python
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем имя пользователя"""
    user_name = update.message.text.strip()
    context.user_data['user_name'] = user_name

    logger.info(f"👤 Пользователь представился: {user_name}")

    response = f"""Очень приятно, {user_name}! 😊

Отлично, давай приступим к работе!

Для начала мне нужно понять несколько вещей о твоём контенте.

**Первый вопрос: Ниша**

В какой области ты создаёшь контент? Это может быть что угодно:
• Фитнес и здоровье
• Бизнес и предпринимательство
• Образование и обучение
• Технологии и IT
• Психология и саморазвитие
• Кулинария
• Или что-то другое?

Просто напиши своими словами - какая у тебя ниша."""

    await update.message.reply_text(response)
    return ASKING_NICHE


async def get_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем нишу"""
    niche = update.message.text.strip()
    context.user_data['niche'] = niche
    user_name = context.user_data.get('user_name', 'дружище')

    logger.info(f"🎯 Ниша: {niche}")

    response = f"""Отлично, {user_name}! {niche} - это интересная тема!

**Второй вопрос: Цель контента**

Что ты хочешь достичь своим контентом? Например:
• Привлечь новую аудиторию
• Обучить подписчиков чему-то конкретному
• Продать свой продукт или услугу
• Повысить вовлечённость
• Просто развлечь людей

Какая у тебя главная цель для этого контента?"""

    await update.message.reply_text(response)
    return ASKING_GOAL


async def get_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем цель"""
    goal = update.message.text.strip()
    context.user_data['goal'] = goal
    user_name = context.user_data.get('user_name', 'дружище')

    logger.info(f"🎯 Цель: {goal}")

    response = f"""Понял, {user_name}! {goal.capitalize()} - важная задача.

**Третий вопрос: Формат**

В каком формате тебе нужен контент?
• Пост для ВКонтакте
• Пост для Instagram
• Пост для Telegram-канала
• Статья для блога
• Видео-скрипт для YouTube/TikTok
• Карточки для соцсетей

Что тебе нужно?"""

    await update.message.reply_text(response)
    return ASKING_FORMAT


async def get_format_and_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем формат и генерируем идеи"""
    format_type = update.message.text.strip()
    context.user_data['format'] = format_type
    user_name = context.user_data.get('user_name', 'дружище')
    niche = context.user_data.get('niche')
    goal = context.user_data.get('goal')

    logger.info(f"📝 Формат: {format_type}")
    logger.info(f"🚀 Генерация для: ниша={niche}, цель={goal}, формат={format_type}")

    # Отправляем сообщение что думаем
    thinking_msg = await update.message.reply_text(
        f"Супер, {user_name}! Все данные собраны 📋\n\n"
        f"Ниша: {niche}\n"
        f"Цель: {goal}\n"
        f"Формат: {format_type}\n\n"
        f"Сейчас придумаю для тебя идеи... 🤔"
    )

    # Формируем запрос для AI
    user_request = f"Ниша: {niche}. Цель: {goal}. Формат: {format_type}"
    context.user_data['user_request'] = user_request

    # Генерируем идеи
    system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
    user_prompt = get_ideas_user_prompt(user_request)

    ideas_text = await call_openai(system_prompt, user_prompt)

    # Удаляем сообщение "думаю"
    await thinking_msg.delete()

    # Парсим идеи
    ideas = parse_ideas(ideas_text)

    if not ideas or len(ideas) < 5:
        # Если парсинг не удался
        await update.message.reply_text(
            f"Вот идеи для тебя, {user_name}:\n\n{ideas_text}\n\n"
            "Напиши номер идеи (1-5), чтобы я написала готовый пост."
        )
        context.user_data['ideas_text'] = ideas_text
        context.user_data['ideas_raw'] = True
        return ConversationHandler.END

    # Сохраняем идеи
    context.user_data['ideas'] = ideas
    context.user_data['ideas_text'] = ideas_text

    # Формируем кнопки
    keyboard = []
    for idea in ideas:
        button_text = f"💡 {idea['number']}. {idea['title']}"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"idea_{idea['number']}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем идеи
    response_text = f"Готово, {user_name}! Вот 5 идей для тебя:\n\n"
    for idea in ideas:
        response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"

    response_text += "Выбирай какая нравится - напишу готовый пост! 👇"

    await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена разговора"""
    user_name = context.user_data.get('user_name', 'дружище')
    await update.message.reply_text(
        f"Хорошо, {user_name}! Если захочешь начать заново - просто напиши /start 😊"
    )
    return ConversationHandler.END
```

### 4. В функции main() ЗАМЕНИТЬ регистрацию обработчиков:

НАЙТИ эти строки (около строки 372):
```python
# Регистрируем обработчики команд
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("new", new_command))
application.add_handler(CommandHandler("history", history_command))
application.add_handler(CommandHandler("help", help_command))
```

ЗАМЕНИТЬ на:
```python
# Conversation Handler для диалога с Каролиной
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        ASKING_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_niche)],
        ASKING_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_goal)],
        ASKING_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_format_and_generate)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

application.add_handler(conversation_handler)

# Остальные команды
application.add_handler(CommandHandler("new", new_command))
application.add_handler(CommandHandler("history", history_command))
application.add_handler(CommandHandler("help", help_command))
```

### 5. УДАЛИТЬ старый обработчик текстовых сообщений:

НАЙТИ и УДАЛИТЬ (около строки 378):
```python
# Обработчик текстовых сообщений
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    handle_message
))
```

---

## ✅ Итоговый флоу:

1. Пользователь: `/start`
2. Каролина: "Привет! Меня зовут Каролина... Как тебя зовут?"
3. Пользователь: "Иван"
4. Каролина: "Очень приятно, Иван! Какая у тебя ниша?"
5. Пользователь: "Фитнес"
6. Каролина: "Отлично! Какая цель?"
7. Пользователь: "Привлечь аудиторию"
8. Каролина: "Понял! Какой формат?"
9. Пользователь: "Пост в Instagram"
10. Каролина: "Супер! Все данные собраны... 🤔" → генерирует 5 идей
11. Пользователь выбирает идею → получает пост

---

## 📝 Команды:

- `/start` - начать диалог с Каролиной
- `/new` - начать новый запрос (запускает `/start` заново)
- `/cancel` - отменить текущий диалог
- `/history` - показать сохранённые посты
- `/help` - справка

---

Сохраните этот файл как инструкцию! Я сейчас внесу все изменения в код.
