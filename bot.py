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
    """Обработчик команды /start"""
    logger.info(f"📥 Получена команда /start от пользователя {update.effective_user.id}")
    welcome_text = """👋 Привет! Я AI-генератор контент-идей.

Просто опиши мне, что нужно:
• Для какой ниши (фитнес, бизнес, образование...)
• Какая цель (привлечь, обучить, продать...)
• В каком формате (пост ВК, Instagram, статья, видео...)

Например:
"Нужны идеи для фитнес-блога в Инстаграм, хочу привлечь новую аудиторию"

Я сгенерирую 5 идей, ты выберешь одну — и получишь готовый пост!

Команды:
/new - начать новый запрос
/history - показать сохраненные посты
/help - помощь"""

    await update.message.reply_text(welcome_text)
    logger.info(f"✅ Отправлен ответ на /start пользователю {update.effective_user.id}")


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /new"""
    # Очищаем контекст
    context.user_data.clear()

    await update.message.reply_text(
        "Отлично! Опиши, какой контент тебе нужен.\n\n"
        "Укажи нишу, цель и формат в свободной форме."
    )


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

1️⃣ Опиши свою задачу в свободной форме
2️⃣ Получи 5 идей и выбери понравившуюся
3️⃣ Получи готовый пост
4️⃣ Сохрани в избранное (если нужно)

Команды:
/start - приветствие
/new - новый запрос
/history - сохраненные посты
/help - эта справка

Примеры запросов:
• "Идеи для образовательного блога по психологии в ВК"
• "Нужен пост для продажи курса по SMM в Instagram"
• "Видео-скрипт для развлекательного ютуб-канала про технологии"
"""

    await update.message.reply_text(help_text)


# ========== ГЕНЕРАЦИЯ ИДЕЙ ==========

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для генерации идей"""
    user_request = update.message.text
    user_id = update.effective_user.id

    # Сохраняем запрос пользователя
    context.user_data['user_request'] = user_request

    # Отправляем "думающее" сообщение
    thinking_msg = await update.message.reply_text("🤔 Генерирую идеи...")

    # Формируем промпты
    system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
    user_prompt = get_ideas_user_prompt(user_request)

    # Вызываем OpenAI
    ideas_text = await call_openai(system_prompt, user_prompt)

    # Удаляем "думающее" сообщение
    await thinking_msg.delete()

    # Парсим идеи
    ideas = parse_ideas(ideas_text)

    if not ideas or len(ideas) < 5:
        # Если парсинг не удался, показываем текст как есть
        await update.message.reply_text(
            f"💡 Вот идеи для тебя:\n\n{ideas_text}\n\n"
            "Напиши номер идеи (1-5), чтобы получить готовый пост."
        )
        context.user_data['ideas_text'] = ideas_text
        context.user_data['ideas_raw'] = True
        return

    # Сохраняем идеи в контексте
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

    # Отправляем идеи с кнопками
    response_text = "✨ Вот 5 идей для тебя:\n\n"
    for idea in ideas:
        response_text += f"{idea['number']}. {idea['title']}\n{idea['description']}\n\n"

    response_text += "Выбери идею, чтобы получить готовый пост 👇"

    await update.message.reply_text(response_text, reply_markup=reply_markup)


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
        await query.message.reply_text(
            "🆕 Отлично! Опиши новую задачу.\n\n"
            "Укажи нишу, цель и формат."
        )


# ========== ГЛАВНАЯ ФУНКЦИЯ ==========

def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

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
