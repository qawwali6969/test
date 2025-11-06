"""
Telegram-бот для генерации контент-идей с помощью AI
"""
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

from config import (
    TELEGRAM_BOT_TOKEN,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_BASE_URL,
    USE_OPENROUTER,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_SITE_URL
)
from prompts import (
    SYSTEM_PROMPT,
    IDEAS_GENERATION_PROMPT,
    POST_GENERATION_PROMPT,
    get_ideas_user_prompt,
    get_post_user_prompt
)
from storage import storage

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
ASKING_NAME, ASKING_NICHE, ASKING_GOAL, ASKING_FORMAT = range(4)

# Инициализация AI клиента
if USE_OPENROUTER:
    # Используем OpenRouter
    openai_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENAI_BASE_URL,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        } if OPENROUTER_SITE_URL else {}
    )
    logger.info(f"🔄 Используется OpenRouter с моделью: {OPENAI_MODEL}")
else:
    # Используем обычный OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info(f"🤖 Используется OpenAI с моделью: {OPENAI_MODEL}")


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def parse_ideas(text: str) -> list[dict]:
    """Парсит текст с идеями в список словарей"""
    ideas = []
    # Паттерн для поиска идей: "1. Название\nОписание"
    pattern = r'(\d+)\.\s*(.+?)\n(.+?)(?=\n\d+\.|$)'
    matches = re.findall(pattern, text, re.DOTALL)

    for match in matches:
        idea_num, title, description = match
        ideas.append({
            'number': int(idea_num),
            'title': title.strip(),
            'description': description.strip()
        })

    return ideas


async def call_openai(system_prompt: str, user_prompt: str, temperature: float = OPENAI_TEMPERATURE) -> str:
    """Вызывает OpenAI API"""
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка вызова OpenAI API: {e}")
        return f"Ошибка при генерации: {str(e)}"


# ========== КОМАНДЫ БОТА ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - начало диалога с Каролиной"""
    logger.info(f"📥 Новый пользователь: {update.effective_user.id}")

    welcome_text = """👋 Привет! Меня зовут Каролина.

Я твой личный креативный ассистент по написанию постов и генерации идей для контента.

Буду рада познакомиться!

Как тебя зовут?"""

    await update.message.reply_text(welcome_text)
    return ASKING_NAME


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


# Функция new_command не нужна, так как /new теперь запускает start_command


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history"""
    user_id = update.effective_user.id
    favorites = storage.get_favorites(user_id)

    if not favorites:
        await update.message.reply_text("У тебя пока нет сохраненных постов.")
        return

    await update.message.reply_text(f"📚 Твои сохраненные посты ({len(favorites)}):\n")

    for idx, fav in enumerate(favorites, 1):
        timestamp = fav.get('timestamp', 'Неизвестно')
        idea = fav.get('idea', 'Без описания')
        post = fav.get('post', '')

        text = f"#{idx} | {timestamp[:10]}\n\n"
        text += f"💡 Идея: {idea}\n\n"
        text += f"📝 Пост:\n{post}\n"
        text += "—" * 30

        await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """❓ Как пользоваться:

👋 Меня зовут Каролина - я твой личный креативный ассистент!

**Как мы работаем:**
1️⃣ Знакомимся - ты называешь своё имя
2️⃣ Я узнаю твою нишу (фитнес, бизнес, образование...)
3️⃣ Спрашиваю цель контента (привлечь, обучить, продать...)
4️⃣ Уточняю формат (пост, статья, видео...)
5️⃣ Генерирую 5 идей специально для тебя!
6️⃣ Ты выбираешь идею - я пишу готовый пост
7️⃣ Можешь сохранить в избранное 💾

**Команды:**
/start - начать диалог со мной
/new - новый запрос (начинаем заново)
/cancel - отменить текущий диалог
/history - твои сохраненные посты
/help - эта справка

Просто напиши /start и начнем! 😊"""

    await update.message.reply_text(help_text)


# ========== ВЫБОР ИДЕИ И ГЕНЕРАЦИЯ ПОСТА ==========


# ========== ГЕНЕРАЦИЯ ПОСТА ==========

async def handle_idea_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора идеи через кнопки"""
    query = update.callback_query
    await query.answer()

    # Извлекаем номер идеи
    idea_number = int(query.data.split('_')[1])

    # Получаем данные из контекста
    ideas = context.user_data.get('ideas', [])
    user_request = context.user_data.get('user_request', '')

    if not ideas:
        await query.edit_message_text("Ошибка: идеи не найдены. Начни заново с /new")
        return

    # Находим выбранную идею
    selected_idea = None
    for idea in ideas:
        if idea['number'] == idea_number:
            selected_idea = idea
            break

    if not selected_idea:
        await query.edit_message_text("Ошибка: идея не найдена.")
        return

    # Сохраняем выбранную идею
    context.user_data['selected_idea'] = selected_idea

    # Сообщение "генерация"
    await query.edit_message_text(f"⚙️ Генерирую пост на основе идеи #{idea_number}...")

    # Формируем промпт для генерации поста
    selected_idea_text = f"{selected_idea['title']}\n{selected_idea['description']}"

    system_prompt = SYSTEM_PROMPT + "\n\n" + POST_GENERATION_PROMPT
    user_prompt = get_post_user_prompt(user_request, selected_idea_text)

    # Генерируем пост
    post_text = await call_openai(system_prompt, user_prompt)

    # Сохраняем пост в контексте
    context.user_data['generated_post'] = post_text

    # Кнопки после генерации поста
    keyboard = [
        [InlineKeyboardButton("💾 Сохранить в избранное", callback_data="save_favorite")],
        [InlineKeyboardButton("🔄 Другая идея", callback_data="another_idea")],
        [InlineKeyboardButton("🆕 Новый запрос", callback_data="new_request")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем готовый пост
    response_text = f"📝 Готовый пост:\n\n{post_text}"

    await query.message.reply_text(response_text, reply_markup=reply_markup)


# ========== ДЕЙСТВИЯ ПОСЛЕ ГЕНЕРАЦИИ ==========

async def handle_post_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик действий с готовым постом"""
    query = update.callback_query
    await query.answer()

    action = query.data

    if action == "save_favorite":
        # Сохранение в избранное
        user_id = update.effective_user.id
        user_request = context.user_data.get('user_request', '')
        selected_idea = context.user_data.get('selected_idea', {})
        generated_post = context.user_data.get('generated_post', '')

        idea_text = f"{selected_idea.get('title', '')} - {selected_idea.get('description', '')}"

        storage.save_favorite(user_id, user_request, idea_text, generated_post)

        await query.message.reply_text(
            "✅ Пост сохранен в избранное!\n\n"
            "Посмотреть все сохраненные посты: /history"
        )

    elif action == "another_idea":
        # Вернуться к выбору другой идеи
        ideas = context.user_data.get('ideas', [])

        if not ideas:
            await query.message.reply_text("Начни заново с /new")
            return

        # Формируем кнопки заново
        keyboard = []
        for idea in ideas:
            button_text = f"💡 {idea['number']}. {idea['title']}"
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"idea_{idea['number']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            "Выбери другую идею 👇",
            reply_markup=reply_markup
        )

    elif action == "new_request":
        # Новый запрос
        context.user_data.clear()
        user_name = context.user_data.get('user_name', '')

        if user_name:
            await query.message.reply_text(
                f"Отлично, {user_name}! Начнем заново?\n\n"
                "Напиши /start или /new чтобы начать новый диалог 😊"
            )
        else:
            await query.message.reply_text(
                "Отлично! Начнем заново?\n\n"
                "Напиши /start или /new чтобы начать новый диалог 😊"
            )


# ========== ГЛАВНАЯ ФУНКЦИЯ ==========

def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation Handler для диалога с Каролиной
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("new", start_command)  # /new тоже запускает диалог
        ],
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
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчики callback кнопок
    application.add_handler(CallbackQueryHandler(
        handle_idea_selection,
        pattern="^idea_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_post_actions,
        pattern="^(save_favorite|another_idea|new_request)$"
    ))

    # Запускаем бота
    logger.info("🤖 Бот запущен!")
    logger.info("📡 Начинаю получать обновления от Telegram...")
    logger.info(f"🔗 Бот доступен: https://t.me/{application.bot.username if hasattr(application, 'bot') else 'bot'}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("⛔ Бот остановлен")


if __name__ == '__main__':
    main()
