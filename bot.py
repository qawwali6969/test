"""
Telegram-бот для генерации контент-идей с помощью AI
"""
import logging
import re
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction
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
from nlp_utils import smart_parse_user_request, looks_like_content_request, extract_missing_fields

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
ASKING_NAME, ASKING_NICHE, ASKING_GOAL, ASKING_FORMAT, ASKING_REUSE_PARAMS = range(5)


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_typing_action(update: Update, duration: float = 1.0):
    """Отправляет действие 'печатает...' на указанное время"""
    await update.effective_chat.send_action(ChatAction.TYPING)
    await asyncio.sleep(duration)


async def send_message_with_typing(update: Update, text: str, **kwargs):
    """Отправляет сообщение с имитацией печатания (минимум 1 секунда)"""
    # Минимум 1 секунда печатания для обычных сообщений
    await send_typing_action(update, 1.0)

    # Отправляем сообщение
    return await update.message.reply_text(text, **kwargs)


async def call_openai_with_typing(update: Update, system_prompt: str, user_prompt: str, temperature: float = OPENAI_TEMPERATURE, max_tokens: int = 2000):
    """Вызывает OpenAI API с отображением typing action во время ожидания

    Показывает "печатает..." пока ждём ответ от сервера (минимум 1 секунда)
    """
    import time

    start_time = time.time()

    # Запускаем typing action (повторяем каждые 4 секунды пока ждём)
    async def keep_typing():
        while True:
            await update.effective_chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(4)  # Telegram typing действует ~5 сек

    # Запускаем typing в фоне
    typing_task = asyncio.create_task(keep_typing())

    try:
        # Делаем запрос к AI
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        result = response.choices[0].message.content.strip()

        # Гарантируем минимум 1 секунду typing
        elapsed = time.time() - start_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        return result

    finally:
        # Останавливаем typing
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


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


def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню"""
    keyboard = [
        [KeyboardButton("🆕 Новый запрос"), KeyboardButton("📚 Мои посты")],
        [KeyboardButton("❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_random_thinking_phrase():
    """Возвращает случайную фразу Каролины при обдумывании идей"""
    phrases = [
        "Сейчас придумаю для тебя идеи... 🤔",
        "Щас что-нибудь интересное накидаю! 💡",
        "Минутку, уже думаю над идеями! 🧠",
        "Сейчас придумаю что-то крутое! ✨",
        "Дай мне секунду, придумываю варианты! 💭"
    ]
    return random.choice(phrases)


def get_random_writing_phrase(idea_number):
    """Возвращает случайную фразу Каролины при написании поста"""
    phrases = [
        f"Щас напишу пост по идее #{idea_number}! ✍️",
        f"Минутку, пишу для тебя пост! 📝",
        f"Сейчас сделаю пост из идеи #{idea_number}! 💫",
        f"Щас придумаю что-нибудь крутое! 🎨",
        f"Уже пишу, будет огонь! 🔥"
    ]
    return random.choice(phrases)


async def validate_user_answer(update: Update, user_answer: str, question_context: str, user_name: str) -> dict:
    """Валидирует ответ пользователя с помощью AI

    Returns:
        dict: {
            'status': 'VALID' | 'QUESTION' | 'UNCLEAR' | 'OFF_TOPIC',
            'response': 'Ответ Каролины если нужно'
        }
    """
    validation_prompt = f"""Ты - Каролина, анализируешь ответ пользователя.

КОНТЕКСТ: Я спросила про {question_context}
ОТВЕТ ПОЛЬЗОВАТЕЛЯ: "{user_answer}"

Проанализируй ответ и классифицируй:

1. VALID - Нормальный, логичный ответ на вопрос
   Примеры для ниши: "фитнес", "бизнес и маркетинг", "психология", "кулинария"
   Примеры для цели: "привлечь аудиторию", "продать", "обучить"
   Примеры для формата: "пост", "статья", "видео"

2. QUESTION - Пользователь задал ВОПРОС о процессе/боте
   Примеры: "что такое ниша?", "как выбрать?", "а какие примеры?", "не понял", "что писать?"

3. UNCLEAR - Нелогичный/слишком короткий/неопределённый ответ
   Примеры: "другое", "не знаю", "хз", "любая", "разное", "всякое", "да"

4. OFF_TOPIC - Совсем не по теме генерации контента
   Примеры: "как погода?", "расскажи анекдот", "ты кто?"

Ответь в формате:

STATUS: [одна из категорий выше]
RESPONSE: [твой ответ Каролины если нужно (для QUESTION, UNCLEAR, OFF_TOPIC)]

Для QUESTION:
- Коротко ответь на вопрос (1-2 предложения)
- Объясни что нужно ввести
- Пример: "Ниша - это твоя тематика! Например: фитнес, бизнес, психология, кулинария. Просто напиши чем занимаешься 😊"

Для UNCLEAR:
- Мягко скажи что ответ не очень понятен
- Объясни что можно написать
- Дай примеры
- Пример: "Хм, '{user_answer}' - это слишком общее 😅 Напиши конкретную тему! Например: фитнес, бизнес, психология, путешествия, кулинария, IT..."

Для OFF_TOPIC:
- Скажи что это не по теме
- Напомни свою задачу
- Предложи начать заново
- Пример: "Я больше про контент и идеи для постов! 😊 Давай лучше сгенерируем крутые идеи? Начнём заново?"

Для VALID:
- Не нужен ответ (оставь пустым)

Будь дружелюбной, используй эмодзи, пиши естественно."""

    try:
        # Используем typing во время валидации
        ai_response = await call_openai_with_typing(
            update,
            "",  # Без системного промпта
            validation_prompt,
            temperature=0.7,
            max_tokens=150
        )

        # Парсим ответ
        status = "VALID"
        carolina_response = ""

        for line in ai_response.split('\n'):
            if line.startswith('STATUS:'):
                status = line.replace('STATUS:', '').strip()
            elif line.startswith('RESPONSE:'):
                carolina_response = line.replace('RESPONSE:', '').strip()

        # Если не удалось распарсить - берём весь текст как ответ
        if not status or status not in ['VALID', 'QUESTION', 'UNCLEAR', 'OFF_TOPIC']:
            # Фоллбэк логика
            if any(word in user_answer.lower() for word in ['?', 'как', 'что', 'почему', 'зачем']):
                status = 'QUESTION'
                carolina_response = ai_response
            elif len(user_answer.strip()) < 3 or user_answer.lower() in ['другое', 'не знаю', 'хз', 'любая']:
                status = 'UNCLEAR'
                carolina_response = ai_response
            else:
                status = 'VALID'

        return {
            'status': status,
            'response': carolina_response
        }

    except Exception as e:
        logger.error(f"Ошибка валидации ответа: {e}")
        # В случае ошибки - принимаем ответ
        return {'status': 'VALID', 'response': ''}


# ========== КОМАНДЫ БОТА ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, skip_greeting: bool = False):
    """Обработчик команды /start - начало диалога с Каролиной

    Args:
        skip_greeting: Если True - пропускает приветствие (продолжение сессии)
    """
    logger.info(f"📥 Пользователь: {update.effective_user.id}, skip_greeting={skip_greeting}")

    user_id = update.effective_user.id
    saved_name = storage.get_user_name(user_id)

    # Если имя уже сохранено
    if saved_name:
        context.user_data['user_name'] = saved_name
        logger.info(f"👤 Возвращается пользователь: {saved_name}")

        if skip_greeting:
            # Продолжение сессии - сразу к делу без приветствия
            niche_text = f"""**Ниша**

В какой области ты создаёшь контент? Это может быть что угодно:
• Фитнес и здоровье
• Бизнес и предпринимательство
• Образование и обучение
• Технологии и IT
• Психология и саморазвитие
• Кулинария
• Или что-то другое?

Просто напиши своими словами - какая у тебя ниша."""
            await send_message_with_typing(update, niche_text, reply_markup=get_main_menu_keyboard())
        else:
            # Новая сессия через кнопку - показываем приветствие
            welcome_text = f"""👋 Привет, {saved_name}! Рада тебя снова видеть!

Давай создадим что-то крутое?

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
            await send_message_with_typing(update, welcome_text, reply_markup=get_main_menu_keyboard())

        return ASKING_NICHE

    # Если имя не сохранено - спрашиваем
    welcome_text = """👋 Привет! Меня зовут Каролина.

Я твой личный креативный ассистент по написанию постов и генерации идей для контента.

Буду рада познакомиться!

Как тебя зовут?"""

    await send_message_with_typing(update, welcome_text, reply_markup=get_main_menu_keyboard())
    return ASKING_NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем имя пользователя"""
    user_name = update.message.text.strip()
    user_id = update.effective_user.id

    context.user_data['user_name'] = user_name

    # Сохраняем имя в storage
    storage.save_user_name(user_id, user_name)

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

    await send_message_with_typing(update, response, reply_markup=get_main_menu_keyboard())
    return ASKING_NICHE


async def get_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем нишу с валидацией"""
    niche = update.message.text.strip()
    user_name = context.user_data.get('user_name', 'дружище')

    logger.info(f"🎯 Попытка ввода ниши: {niche}")

    # Валидируем ответ
    validation = await validate_user_answer(update, niche, "нишу (тематику контента)", user_name)

    if validation['status'] == 'OFF_TOPIC':
        # Совсем не по теме - restart
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    elif validation['status'] in ['QUESTION', 'UNCLEAR']:
        # Вопрос или неясный ответ - объясняем и повторяем
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        # Возвращаем тот же state - будем ждать ответ снова
        return ASKING_NICHE

    # VALID - пробуем извлечь дополнительные параметры из текста
    parsed = smart_parse_user_request(niche)
    missing = extract_missing_fields(parsed)

    if len(missing) == 0:
        # ВСЕ параметры есть в одном ответе - пропускаем остальные вопросы!
        logger.info(f"✨ Умный парсер нашел все параметры в ответе на нишу: {parsed}")

        context.user_data['niche'] = parsed['niche']
        context.user_data['goal'] = parsed['goal']
        context.user_data['format'] = parsed['format']

        # Сразу переходим к генерации
        await send_message_with_typing(
            update,
            f"Супер, {user_name}! Все понятно - {parsed['niche']}, цель: {parsed['goal']}, формат: {parsed['format']} 🎯\n\nГенерирую идеи!",
            reply_markup=get_main_menu_keyboard()
        )

        # Переходим сразу к генерации (вызываем логику из get_format_and_generate)
        user_request = f"{parsed['niche']}, {parsed['goal']}, {parsed['format']}"
        context.user_data['user_request'] = user_request

        try:
            system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
            user_prompt = get_ideas_user_prompt(user_request)
            ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)
            ideas = parse_ideas(ideas_text)
        except Exception as e:
            logger.error(f"Ошибка при генерации идей (smart niche): {e}")
            error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"
            if "429" in str(e) or "rate limit" in str(e).lower():
                error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
            else:
                error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
            await update.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END

        if not ideas or len(ideas) < 5:
            fallback_text = f"Вот идеи для тебя, {user_name}:\n\n{ideas_text}\n\n"
            fallback_text += "Напиши номер идеи (1-5) для генерации поста"
            await update.message.reply_text(fallback_text)
            context.user_data['ideas_text'] = ideas_text
            context.user_data['ideas_raw'] = True
            return ConversationHandler.END

        context.user_data['ideas'] = ideas
        context.user_data['ideas_text'] = ideas_text

        keyboard = []
        for idea in ideas:
            button_text = f"💡 {idea['number']}. {idea['title']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"idea_{idea['number']}")])

        keyboard.append([
            InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
            InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        response_text = f"Готово, {user_name}! Вот 5 идей:\n\n"
        for idea in ideas:
            response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"
        response_text += "Выбирай какая нравится! 👇"

        await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        return ConversationHandler.END

    # Только ниша найдена - продолжаем обычный flow
    context.user_data['niche'] = parsed.get('niche') or niche
    logger.info(f"✅ Ниша принята: {context.user_data['niche']}")

    response = f"""Отлично, {user_name}! {context.user_data['niche']} - это интересная тема!

**Второй вопрос: Цель контента**

Что ты хочешь достичь своим контентом? Например:
• Привлечь новую аудиторию
• Обучить подписчиков чему-то конкретному
• Продать свой продукт или услугу
• Повысить вовлечённость
• Просто развлечь людей

Какая у тебя главная цель для этого контента?"""

    await send_message_with_typing(update, response)
    return ASKING_GOAL


async def get_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем цель с валидацией"""
    goal = update.message.text.strip()
    user_name = context.user_data.get('user_name', 'дружище')

    logger.info(f"🎯 Попытка ввода цели: {goal}")

    # Валидируем ответ
    validation = await validate_user_answer(update, goal, "цель контента (что хочешь достичь)", user_name)

    if validation['status'] == 'OFF_TOPIC':
        # Совсем не по теме - restart
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    elif validation['status'] in ['QUESTION', 'UNCLEAR']:
        # Вопрос или неясный ответ - объясняем и повторяем
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        return ASKING_GOAL

    # VALID - принимаем ответ
    context.user_data['goal'] = goal
    logger.info(f"✅ Цель принята: {goal}")

    response = f"""Поняла, {user_name}! {goal.capitalize()} - важная задача.

**Третий вопрос: Формат**

В каком формате тебе нужен контент?
• Пост для ВКонтакте
• Пост для Instagram
• Пост для Telegram-канала
• Статья для блога
• Видео-скрипт для YouTube/TikTok
• Карточки для соцсетей

Что тебе нужно?"""

    await send_message_with_typing(update, response)
    return ASKING_FORMAT


async def get_format_and_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем формат с валидацией и генерируем идеи"""
    format_type = update.message.text.strip()
    user_name = context.user_data.get('user_name', 'дружище')
    niche = context.user_data.get('niche')
    goal = context.user_data.get('goal')

    logger.info(f"📝 Попытка ввода формата: {format_type}")

    # Валидируем ответ
    validation = await validate_user_answer(update, format_type, "формат контента (пост, статья, видео и т.д.)", user_name)

    if validation['status'] == 'OFF_TOPIC':
        # Совсем не по теме - restart
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    elif validation['status'] in ['QUESTION', 'UNCLEAR']:
        # Вопрос или неясный ответ - объясняем и повторяем
        await send_message_with_typing(update, validation['response'], reply_markup=get_main_menu_keyboard())
        return ASKING_FORMAT

    # VALID - принимаем ответ
    context.user_data['format'] = format_type
    logger.info(f"✅ Формат принят: {format_type}")
    logger.info(f"🚀 Генерация для: ниша={niche}, цель={goal}, формат={format_type}")

    # Показываем "печатает..." и отправляем сообщение
    summary_text = f"Супер, {user_name}! Все данные собраны 📋\n\n" \
                   f"Ниша: {niche}\n" \
                   f"Цель: {goal}\n" \
                   f"Формат: {format_type}\n\n" \
                   f"{get_random_thinking_phrase()}"

    await send_message_with_typing(update, summary_text)

    # Формируем запрос для AI
    user_request = f"Ниша: {niche}. Цель: {goal}. Формат: {format_type}"
    context.user_data['user_request'] = user_request

    try:
        # Генерируем идеи с typing action (показываем "печатает..." пока AI думает)
        system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
        user_prompt = get_ideas_user_prompt(user_request)

        ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)

        # Парсим идеи
        ideas = parse_ideas(ideas_text)
    except Exception as e:
        logger.error(f"Ошибка при генерации идей: {e}")

        # Формируем сообщение об ошибке
        error_msg = f"Ой, {user_name}, кажется возникла проблема с генерацией 😔\n\n"

        error_str = str(e)
        if "429" in error_str or "rate limit" in error_str.lower():
            error_msg += "Похоже что исчерпан лимит бесплатных запросов к AI на сегодня.\n\n"
            error_msg += "Попробуй чуть позже или используй платную модель API 💡"
        else:
            error_msg += "Что-то пошло не так с AI сервисом. Попробуй ещё раз через минутку 🔄"

        await send_message_with_typing(update, error_msg, reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    if not ideas or len(ideas) < 5:
        # Если парсинг не удался
        fallback_text = f"Вот идеи для тебя, {user_name}:\n\n{ideas_text}\n\n" \
                       "Напиши номер идеи (1-5), чтобы я написала готовый пост."

        # Показываем typing перед отправкой
        await send_typing_action(update, 2.0)
        await update.message.reply_text(fallback_text)

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

    # Дополнительные кнопки
    keyboard.append([
        InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
        InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем идеи с имитацией печатания
    response_text = f"Готово, {user_name}! Вот 5 идей для тебя:\n\n"
    for idea in ideas:
        response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"

    response_text += "Выбирай какая нравится - напишу готовый пост! 👇\n\n"
    response_text += "💡 _Совет: Нажми на текст идеи чтобы скопировать его_"

    # Показываем typing перед отправкой идей
    await send_typing_action(update, 3.0)  # 3 секунды - идеи большие
    await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')

    return ConversationHandler.END


async def handle_reuse_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения повторного использования параметров"""
    user_text = update.message.text.strip().lower()
    user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"

    logger.info(f"🔄 Подтверждение переиспользования параметров: {user_text}")

    # Определяем утвердительные и отрицательные ответы
    yes_words = ['да', 'yes', 'д', 'y', 'ага', 'угу', 'конечно', 'давай', 'го', 'ок', 'окей', 'ok', 'okay', '+', '✓']
    no_words = ['нет', 'no', 'н', 'n', 'не', 'неа', 'нету', 'не надо', '-']

    if any(word in user_text for word in yes_words):
        # Пользователь согласен - повторяем генерацию с теми же параметрами
        await send_message_with_typing(
            update,
            f"Отлично, {user_name}! Генерирую новые идеи с теми же параметрами 🚀",
            reply_markup=get_main_menu_keyboard()
        )

        # Используем сохраненные параметры
        niche = context.user_data.get('niche')
        goal = context.user_data.get('goal')
        format_name = context.user_data.get('format')
        user_request = f"{niche}, {goal}, {format_name}"

        # Сохраняем запрос
        context.user_data['user_request'] = user_request

        try:
            # Генерируем идеи напрямую (копируем логику из get_format_and_generate)
            system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
            user_prompt = get_ideas_user_prompt(user_request)

            ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)

            # Парсим идеи
            ideas = parse_ideas_response(ideas_text)
        except Exception as e:
            logger.error(f"Ошибка при генерации идей (reuse): {e}")

            # Формируем сообщение об ошибке
            error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"

            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower():
                error_msg += "Похоже что исчерпан лимит бесплатных запросов к AI на сегодня.\n\n"
                error_msg += "Попробуй чуть позже или используй платную модель API 💡"
            else:
                error_msg += "Что-то пошло не так с AI сервисом. Попробуй ещё раз через минутку 🔄"

            await send_message_with_typing(update, error_msg, reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END

        if not ideas:
            # Если не удалось распарсить идеи
            fallback_text = f"Вот идеи для тебя, {user_name}! 💡\n\n{ideas_text}\n\n"
            fallback_text += "Выбери номер идеи (1-5) и я напишу полный пост! 😊"

            await send_typing_action(update, 2.0)
            await update.message.reply_text(fallback_text)

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

        # Дополнительные кнопки
        keyboard.append([
            InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
            InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем идеи
        response_text = f"Готово, {user_name}! Вот 5 новых идей:\n\n"
        for idea in ideas:
            response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"

        response_text += "Выбирай какая нравится - напишу готовый пост! 👇"

        await send_typing_action(update, 3.0)
        await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')

        return ConversationHandler.END

    elif any(word in user_text for word in no_words):
        # Пользователь не согласен - начинаем новую сессию
        await send_message_with_typing(
            update,
            f"Понятно, {user_name}! Давай введём новые параметры 💡",
            reply_markup=get_main_menu_keyboard()
        )
        return await start_command(update, context, skip_greeting=True)

    else:
        # Непонятный ответ - повторяем вопрос
        await send_message_with_typing(
            update,
            f"Не совсем поняла, {user_name} 😅 Напиши 'да' или 'нет'",
            reply_markup=get_main_menu_keyboard()
        )
        return ASKING_REUSE_PARAMS


async def handle_reuse_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Да, оставить' - генерирует с теми же параметрами"""
    query = update.callback_query
    await query.answer()

    user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"

    await query.edit_message_text(f"Отлично, {user_name}! Генерирую новые идеи 🚀")

    # Используем сохраненные параметры
    niche = context.user_data.get('niche')
    goal = context.user_data.get('goal')
    format_name = context.user_data.get('format')
    user_request = f"{niche}, {goal}, {format_name}"

    # Сохраняем запрос
    context.user_data['user_request'] = user_request

    try:
        # Генерируем идеи
        system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
        user_prompt = get_ideas_user_prompt(user_request)

        ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)
        ideas = parse_ideas_response(ideas_text)
    except Exception as e:
        logger.error(f"Ошибка при генерации идей (reuse yes): {e}")
        error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"
        if "429" in str(e) or "rate limit" in str(e).lower():
            error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
        else:
            error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
        await query.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    if not ideas:
        # Fallback если парсинг не удался
        fallback_text = f"Вот идеи для тебя, {user_name}! 💡\n\n{ideas_text}\n\n"
        fallback_text += "Выбери номер идеи (1-5) и я напишу полный пост!"
        await query.message.reply_text(fallback_text)
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

    # Дополнительные кнопки
    keyboard.append([
        InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
        InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем идеи
    response_text = f"Готово, {user_name}! Вот 5 новых идей:\n\n"
    for idea in ideas:
        response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"
    response_text += "Выбирай какая нравится! 👇"

    await query.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
    return ConversationHandler.END


async def handle_reuse_edit_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить нишу'"""
    query = update.callback_query
    await query.answer()

    user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"

    await query.edit_message_text(f"Окей, {user_name}! Какая ниша теперь? (тематика контента)")
    return ASKING_NICHE


async def handle_reuse_edit_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить цель'"""
    query = update.callback_query
    await query.answer()

    user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"

    await query.edit_message_text(f"Окей, {user_name}! Какая цель? (привлечь, обучить, продать или развлечь)")
    return ASKING_GOAL


async def handle_reuse_edit_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить платформу'"""
    query = update.callback_query
    await query.answer()

    user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"

    await query.edit_message_text(f"Окей, {user_name}! Какая платформа/формат? (Instagram, TikTok, пост, видео и т.д.)")
    return ASKING_FORMAT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена разговора"""
    user_name = context.user_data.get('user_name', 'дружище')
    cancel_text = f"Хорошо, {user_name}! Если захочешь начать заново - просто напиши /start 😊"
    await send_message_with_typing(update, cancel_text)
    return ConversationHandler.END


# Функция new_command не нужна, так как /new теперь запускает start_command


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history - показывает первую страницу"""
    user_id = update.effective_user.id
    user_name = storage.get_user_name(user_id) or "дружище"
    favorites = storage.get_favorites(user_id)

    if not favorites:
        await update.message.reply_text(
            f"У тебя пока нет сохранённых постов, {user_name} 🤷‍♀️\n\n"
            "Когда сгенерируешь пост - нажми кнопку '💾 Сохранить в избранное' чтобы он появился здесь!",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Показываем первую страницу
    await show_history_page(update, context, page=0)


async def show_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показывает страницу с сохраненными постами (по 5 штук)"""
    user_id = update.effective_user.id
    user_name = storage.get_user_name(user_id) or "дружище"
    favorites = storage.get_favorites(user_id)

    POSTS_PER_PAGE = 5
    total_posts = len(favorites)
    total_pages = (total_posts + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE  # Округление вверх

    # Проверка валидности страницы
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start_idx = page * POSTS_PER_PAGE
    end_idx = min(start_idx + POSTS_PER_PAGE, total_posts)
    page_posts = favorites[start_idx:end_idx]

    # Формируем текст заголовка
    text = f"📚 Твои сохранённые посты, {user_name}\n"
    text += f"Страница {page + 1} из {total_pages} (всего {total_posts})\n\n"
    text += "Выбери пост чтобы открыть:"

    # Создаём кнопки для каждого поста
    keyboard = []
    for i, fav in enumerate(page_posts):
        actual_idx = start_idx + i  # Реальный индекс в полном списке
        idea = fav.get('idea', 'Без описания')
        timestamp = fav.get('timestamp', '')[:10]  # Только дата

        # Миниатюра: первые 50 символов идеи
        preview = idea[:50] + "..." if len(idea) > 50 else idea
        button_text = f"#{actual_idx + 1} • {preview}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_post_{actual_idx}_{page}")])

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"history_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Дальше ➡️", callback_data=f"history_page_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем или редактируем сообщение
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_history_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик пагинации истории постов"""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "history_page_{page}"
    page = int(query.data.split('_')[2])

    await show_history_page(update, context, page=page)


async def view_saved_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает конкретный сохраненный пост"""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "view_post_{index}_{page}"
    parts = query.data.split('_')
    post_idx = int(parts[2])
    from_page = int(parts[3])

    user_id = update.effective_user.id
    favorites = storage.get_favorites(user_id)

    if post_idx >= len(favorites):
        await query.edit_message_text("Ошибка: пост не найден")
        return

    fav = favorites[post_idx]
    timestamp = fav.get('timestamp', 'Неизвестно')
    idea = fav.get('idea', 'Без описания')
    post = fav.get('post', '')
    request = fav.get('request', '')

    # Формируем текст с постом
    text = f"📝 Пост #{post_idx + 1}\n"
    text += f"📅 {timestamp[:10]}\n\n"
    if request:
        text += f"📋 Запрос: {request}\n\n"
    text += f"💡 Идея: {idea}\n\n"
    text += f"```\n{post}\n```\n\n"
    text += "💡 _Нажми на текст поста чтобы скопировать_"

    # Кнопки: "Назад" и "Удалить"
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"history_page_{from_page}")],
        [InlineKeyboardButton("🗑 Удалить этот пост", callback_data=f"delete_post_{post_idx}_{from_page}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def delete_saved_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет сохраненный пост"""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "delete_post_{index}_{page}"
    parts = query.data.split('_')
    post_idx = int(parts[2])
    from_page = int(parts[3])

    user_id = update.effective_user.id

    # Удаляем пост
    success = storage.delete_favorite(user_id, post_idx)

    if success:
        await query.answer("✅ Пост удален", show_alert=True)

        # Проверяем сколько постов осталось
        favorites = storage.get_favorites(user_id)

        if not favorites:
            # Постов не осталось - показываем сообщение
            user_name = storage.get_user_name(user_id) or "дружище"
            await query.edit_message_text(
                f"У тебя пока нет сохранённых постов, {user_name} 🤷‍♀️\n\n"
                "Когда сгенерируешь пост - нажми кнопку '💾 Сохранить в избранное' чтобы он появился здесь!",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            # Есть еще посты - возвращаемся к списку
            # Проверяем что страница еще валидна
            POSTS_PER_PAGE = 5
            total_pages = (len(favorites) + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE

            if from_page >= total_pages:
                from_page = total_pages - 1

            await show_history_page(update, context, page=from_page)
    else:
        await query.answer("❌ Не удалось удалить пост", show_alert=True)


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки меню"""
    text = update.message.text

    if text == "🆕 Новый запрос":
        # Запускаем start_command
        return await start_command(update, context)
    elif text == "📚 Мои посты":
        # Показываем историю
        return await history_command(update, context)
    elif text == "❌ Отмена":
        # Отменяем текущее действие
        user_name = context.user_data.get('user_name') or storage.get_user_name(update.effective_user.id) or "дружище"
        await send_message_with_typing(
            update,
            f"Хорошо, {user_name}! Если захочешь начать заново - нажми '🆕 Новый запрос' 😊",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END


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


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик свободных текстовых сообщений вне conversation"""
    user_id = update.effective_user.id
    user_name = storage.get_user_name(user_id) or "дружище"
    user_text = update.message.text.strip()

    logger.info(f"💬 Свободное сообщение от {user_name}: {user_text}")

    # АВТОСТАРТ: Если текст похож на запрос контента, пробуем сразу распарсить
    if looks_like_content_request(user_text):
        logger.info(f"🎯 Автостарт: текст похож на запрос контента")
        parsed = smart_parse_user_request(user_text)
        missing = extract_missing_fields(parsed)

        if len(missing) == 0:
            # ВСЕ параметры есть - сразу генерируем без вопросов!
            logger.info(f"✨ Умный парсер (автостарт) извлек все параметры: {parsed}")

            context.user_data['niche'] = parsed['niche']
            context.user_data['goal'] = parsed['goal']
            context.user_data['format'] = parsed['format']
            context.user_data['user_name'] = user_name

            user_request = f"{parsed['niche']}, {parsed['goal']}, {parsed['format']}"
            context.user_data['user_request'] = user_request

            await send_message_with_typing(update, f"Понятно! Генерирую идеи для {parsed['niche']} 🚀", reply_markup=get_main_menu_keyboard())

            try:
                system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
                user_prompt = get_ideas_user_prompt(user_request)
                ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)
                ideas = parse_ideas(ideas_text)
            except Exception as e:
                logger.error(f"Ошибка при генерации идей (автостарт): {e}")
                error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"
                if "429" in str(e) or "rate limit" in str(e).lower():
                    error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
                else:
                    error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
                await update.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
                return ConversationHandler.END

            if not ideas or len(ideas) < 5:
                fallback_text = f"Вот идеи для тебя, {user_name}:\n\n{ideas_text}\n\n"
                fallback_text += "Напиши номер идеи (1-5) для генерации поста"
                await update.message.reply_text(fallback_text)
                context.user_data['ideas_text'] = ideas_text
                context.user_data['ideas_raw'] = True
                return ConversationHandler.END

            context.user_data['ideas'] = ideas
            context.user_data['ideas_text'] = ideas_text

            keyboard = []
            for idea in ideas:
                button_text = f"💡 {idea['number']}. {idea['title']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"idea_{idea['number']}")])

            keyboard.append([
                InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
                InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = f"Готово, {user_name}! Вот 5 идей:\n\n"
            for idea in ideas:
                response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"
            response_text += "Выбирай какая нравится! 👇"

            await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
            return ConversationHandler.END

    # Используем AI для понимания намерений
    intent_prompt = f"""Ты - Каролина, личный креативный ассистент по генерации контент-идей. Ты женщина, используй женский род.

Пользователь {user_name} написал: "{user_text}"

Твои возможности:
1. ANOTHER_IDEA - Хочет другую идею из уже показанных или новые идеи
   Примеры: "другую", "давай другую", "плохая идея", "не нравится", "не то", "не подходит", "покажи другие", "есть еще?", "что еще есть?", "другие варианты", "не зашло", "мимо", "слабовато"

2. GENERATE_IDEAS - Сразу начать генерацию НОВЫХ идей (или повторить с теми же параметрами)
   Примеры: "давай еще идеи", "придумай еще", "есть ли еще идеи", "еще 5 идей", "новые идеи", "создай идеи", "сгенерируй идеи", "придумай новые", "хочу больше идей", "еще", "дай еще", "другие идеи", "еще варианты", "еще раз", "повтори", "сгенерируй еще"

3. NEW_REQUEST - Начать новую сессию с приветствием
   Примеры: "новый запрос", "начать заново", "с нуля", "начать сначала", "заново"

4. SHOW_HISTORY - Показать сохранённые посты
   Примеры: "покажи посты", "мои посты", "история", "что сохранял", "какие нравились", "мои любимые", "сохранённые", "избранное"

5. HELP - Дать помощь/справку
   Примеры: "помощь", "что умеешь", "команды", "справка", "как работать", "help"

6. GREETING - Приветствие
   Примеры: "привет", "здравствуй", "хай", "hello", "приветик", "ку", "хелло"

7. THANKS - Благодарность
   Примеры: "спасибо", "благодарю", "thanks", "от души", "классно", "круто", "супер", "отлично", "огонь"

8. OTHER - Всё остальное (вопросы не по теме)

ВАЖНЫЕ ПРАВИЛА РАСПОЗНАВАНИЯ:
- "другую", "другая", "плохая идея", "не нравится" → ANOTHER_IDEA
- "еще идеи", "придумай еще", "новые идеи", "еще", "дай еще" → GENERATE_IDEAS
- "что сохранял", "какие нравились" → SHOW_HISTORY
- "новый запрос", "заново" → NEW_REQUEST

Проанализируй сообщение и определи намерение. Ответь в формате:

INTENT: [одна из команд выше]
RESPONSE: [твой естественный ответ Каролины]

ТРЕБОВАНИЯ К ОТВЕТУ:
1. РАЗНООБРАЗИЕ - каждый ответ должен быть УНИКАЛЬНЫМ
2. Используй разные стили:
   - Иногда короткий и энергичный: "Окей, поехали! 🚀"
   - Иногда более развёрнутый: "Отличная идея, {user_name}! Сейчас придумаем ещё крутых вариантов 💡"
   - Иногда игривый: "Ооо, ещё порцию идей? Легко! ✨"
3. Варьируй эмодзи: 💡🚀✨🔥💫🎨✍️🎯💪🤔👀
4. Разные конструкции предложений
5. Разная длина (от 1 до 3 предложений)

Для ANOTHER_IDEA:
- "Окей, давай другой вариант! 🔄"
- "Понятно, щас покажу другие варианты! 👀"
- "Не зашла? Смотри другие идеи! ✨"

Если намерение OTHER (вопросы не связанные с генерацией контента):
- Мягко скажи что твоя задача - помогать с генерацией идей для контента
- Предложи создать новые идеи
- Используй разговорный стиль: "я много в чем сильна, но моя задача - помогать с контентом"
- Закончи призывом к действию
- Будь дружелюбной, не формальной
- ОБЯЗАТЕЛЬНО варьируй ответы! Никогда не повторяйся!

Пиши естественно, с эмодзи."""

    try:
        # Получаем ответ от AI с typing action
        ai_response = await call_openai_with_typing(
            update,
            "",  # Без системного промпта
            intent_prompt,
            temperature=0.8,
            max_tokens=200
        )
        logger.info(f"🤖 AI ответ: {ai_response}")

        # Парсим ответ
        intent_line = ""
        response_line = ""

        for line in ai_response.split('\n'):
            if line.startswith('INTENT:'):
                intent_line = line.replace('INTENT:', '').strip()
            elif line.startswith('RESPONSE:'):
                response_line = line.replace('RESPONSE:', '').strip()

        # Если не удалось распарсить - используем весь ответ
        if not response_line:
            response_line = ai_response
            intent_line = "OTHER"

        # Выполняем соответствующее действие
        if 'ANOTHER_IDEA' in intent_line.upper():
            # Хочет другую идею - проверяем есть ли уже сгенерированные
            ideas = context.user_data.get('ideas', [])

            if ideas:
                # Есть идеи - показываем их снова
                await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())

                # Формируем кнопки с идеями
                keyboard = []
                for idea in ideas:
                    button_text = f"💡 {idea['number']}. {idea['title']}"
                    keyboard.append([InlineKeyboardButton(
                        button_text,
                        callback_data=f"idea_{idea['number']}"
                    )])

                # Дополнительные кнопки
                keyboard.append([
                    InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
                    InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
                ])

                reply_markup = InlineKeyboardMarkup(keyboard)

                choice_text = f"Вот все 5 идей, {user_name}! Выбирай какая нравится 👇"
                await update.message.reply_text(choice_text, reply_markup=reply_markup)
            else:
                # Нет идей - начинаем новую генерацию
                await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())
                return await start_command(update, context, skip_greeting=True)

        elif 'GENERATE_IDEAS' in intent_line.upper():
            # Фразы типа "давай еще идеи" - пробуем распарсить из текста
            await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())

            # Сначала пробуем извлечь параметры из самого текста
            parsed = smart_parse_user_request(user_text)
            missing = extract_missing_fields(parsed)

            if len(missing) == 0:
                # ВСЕ параметры извлечены из текста - сразу генерируем!
                logger.info(f"✨ Умный парсер извлек все параметры: {parsed}")

                context.user_data['niche'] = parsed['niche']
                context.user_data['goal'] = parsed['goal']
                context.user_data['format'] = parsed['format']

                # Сразу переходим к генерации (пропускаем все вопросы!)
                user_request = f"{parsed['niche']}, {parsed['goal']}, {parsed['format']}"
                context.user_data['user_request'] = user_request

                # Генерируем идеи
                await send_message_with_typing(update, f"Понятно! Генерирую идеи для {parsed['niche']} 🚀", reply_markup=get_main_menu_keyboard())

                try:
                    system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
                    user_prompt = get_ideas_user_prompt(user_request)
                    ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)
                    ideas = parse_ideas(ideas_text)
                except Exception as e:
                    logger.error(f"Ошибка при генерации идей (smart parse): {e}")
                    error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"
                    if "429" in str(e) or "rate limit" in str(e).lower():
                        error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
                    else:
                        error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
                    await update.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
                    return ConversationHandler.END

                if not ideas or len(ideas) < 5:
                    # Fallback
                    fallback_text = f"Вот идеи для тебя, {user_name}:\n\n{ideas_text}\n\n"
                    fallback_text += "Напиши номер идеи (1-5) для генерации поста"
                    await update.message.reply_text(fallback_text)
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
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"idea_{idea['number']}")])

                keyboard.append([
                    InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
                    InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
                ])

                reply_markup = InlineKeyboardMarkup(keyboard)

                response_text = f"Готово, {user_name}! Вот 5 идей:\n\n"
                for idea in ideas:
                    response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"
                response_text += "Выбирай какая нравится! 👇"

                await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
                return ConversationHandler.END

            # Проверяем есть ли сохраненные параметры
            has_previous = (
                context.user_data.get('niche') and
                context.user_data.get('goal') and
                context.user_data.get('format')
            )

            if has_previous:
                # Есть предыдущие параметры - спрашиваем подтверждение с кнопками
                niche = context.user_data.get('niche')
                goal = context.user_data.get('goal')
                format_name = context.user_data.get('format')

                confirm_text = f"Оставим те же настройки?\n\n"
                confirm_text += f"📋 Ниша: {niche}\n"
                confirm_text += f"🎯 Цель: {goal}\n"
                confirm_text += f"📱 Платформа: {format_name}"

                # Кнопки для изменения параметров
                keyboard = [
                    [InlineKeyboardButton("✅ Да, оставить", callback_data="reuse_yes")],
                    [InlineKeyboardButton("✏️ Изменить нишу", callback_data="reuse_edit_niche")],
                    [InlineKeyboardButton("✏️ Изменить цель", callback_data="reuse_edit_goal")],
                    [InlineKeyboardButton("✏️ Изменить платформу", callback_data="reuse_edit_format")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await send_message_with_typing(update, confirm_text)
                await update.message.reply_text(
                    "Выбери действие:",
                    reply_markup=reply_markup
                )
                return ASKING_REUSE_PARAMS
            else:
                # Нет параметров - начинаем новую сессию
                return await start_command(update, context, skip_greeting=True)

        elif 'NEW_REQUEST' in intent_line.upper():
            # "Новый запрос" - с приветствием
            await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())
            return await start_command(update, context, skip_greeting=False)

        elif 'SHOW_HISTORY' in intent_line.upper():
            await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())
            return await history_command(update, context)

        elif 'HELP' in intent_line.upper():
            return await help_command(update, context)

        else:
            # Любой другой случай - отправляем ответ AI
            await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())

    except Exception as e:
        logger.error(f"Ошибка в handle_free_text: {e}")

        # Если AI недоступен - просто начинаем новую сессию
        # (предполагаем что пользователь хочет создать контент)
        error_msg = f"Извини, {user_name}, у меня небольшие технические трудности 😅"

        # Проверяем тип ошибки
        error_str = str(e)
        if "429" in error_str or "rate limit" in error_str.lower():
            error_msg += "\n\nПохоже что я исчерпала лимит бесплатных запросов на сегодня 😔"
            error_msg += "\n\nНо не переживай! Я всё равно могу помочь - просто без AI-помощника буду работать чуть проще."
            error_msg += "\n\nДавай попробуем создать контент? Нажми '🆕 Новый запрос' 💪"
        else:
            error_msg += "\n\nДавай попробуем ещё раз? Нажми '🆕 Новый запрос' 😊"

        await send_message_with_typing(update, error_msg, reply_markup=get_main_menu_keyboard())


# ========== ВЫБОР ИДЕИ И ГЕНЕРАЦИЯ ПОСТА ==========


async def handle_random_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Случайная идея'"""
    query = update.callback_query
    await query.answer()

    ideas = context.user_data.get('ideas', [])
    if not ideas:
        await query.answer("Идей пока нет. Начни заново с /new", show_alert=True)
        return

    # Выбираем случайную идею
    selected_idea = random.choice(ideas)
    context.user_data['selected_idea'] = selected_idea

    user_name = context.user_data.get('user_name', 'дружище')

    # Сообщение о выборе
    await query.edit_message_text(f"🎲 Выбрала случайную идею #{selected_idea['number']}!\n\nСейчас напишу пост...")

    # Формируем промпт для генерации поста
    user_request = context.user_data.get('user_request', '')
    selected_idea_text = f"{selected_idea['title']}\n{selected_idea['description']}"

    system_prompt = SYSTEM_PROMPT + "\n\n" + POST_GENERATION_PROMPT
    user_prompt = get_post_user_prompt(user_request, selected_idea_text)

    try:
        # Генерируем пост
        post_text = await call_openai_with_typing(update, system_prompt, user_prompt)
        context.user_data['generated_post'] = post_text
    except Exception as e:
        logger.error(f"Ошибка при генерации поста (random): {e}")
        error_msg = "Ой, кажется возникла проблема 😔\n\n"
        if "429" in str(e) or "rate limit" in str(e).lower():
            error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
        else:
            error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
        await query.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
        return

    # Кнопки после генерации
    keyboard = [
        [InlineKeyboardButton("💾 Сохранить в избранное", callback_data="save_favorite")],
        [InlineKeyboardButton("🔄 Другая идея", callback_data="another_idea")],
        [InlineKeyboardButton("🆕 Новый запрос", callback_data="new_request")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    response_text = f"📝 Готовый пост:\n\n```\n{post_text}\n```\n\n"
    response_text += "💡 _Нажми на текст поста чтобы скопировать его_"

    await query.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_regenerate_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Еще 5 идей' - регенерирует с теми же параметрами"""
    query = update.callback_query
    await query.answer()

    # Проверяем что есть параметры
    user_request = context.user_data.get('user_request')
    user_name = context.user_data.get('user_name', 'дружище')

    if not user_request:
        await query.answer("Параметры не найдены. Начни заново с /new", show_alert=True)
        return

    await query.edit_message_text(f"Окей, {user_name}! Генерирую еще 5 идей с теми же параметрами 🔄")

    try:
        # Генерируем новые идеи
        system_prompt = SYSTEM_PROMPT + "\n\n" + IDEAS_GENERATION_PROMPT
        user_prompt = get_ideas_user_prompt(user_request)

        ideas_text = await call_openai_with_typing(update, system_prompt, user_prompt)
        ideas = parse_ideas(ideas_text)
    except Exception as e:
        logger.error(f"Ошибка при регенерации идей: {e}")
        error_msg = f"Ой, {user_name}, кажется возникла проблема 😔\n\n"
        if "429" in str(e) or "rate limit" in str(e).lower():
            error_msg += "Исчерпан лимит бесплатных запросов. Попробуй позже 💡"
        else:
            error_msg += "Что-то пошло не так. Попробуй ещё раз 🔄"
        await query.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
        return

    if not ideas or len(ideas) < 5:
        # Fallback если парсинг не удался
        fallback_text = f"Вот новые идеи, {user_name}:\n\n{ideas_text}\n\n"
        fallback_text += "Напиши номер идеи (1-5) для генерации поста"
        await query.message.reply_text(fallback_text)
        return

    # Сохраняем новые идеи
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

    # Дополнительные кнопки
    keyboard.append([
        InlineKeyboardButton("🎲 Случайная идея", callback_data="idea_random"),
        InlineKeyboardButton("🔄 Еще 5 идей", callback_data="ideas_regenerate")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем новые идеи
    response_text = f"Готово, {user_name}! Вот 5 новых идей:\n\n"
    for idea in ideas:
        response_text += f"{idea['number']}. **{idea['title']}**\n{idea['description']}\n\n"
    response_text += "Выбирай какая нравится! 👇"

    await query.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')


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
    await query.edit_message_text(get_random_writing_phrase(idea_number))

    # Формируем промпт для генерации поста
    selected_idea_text = f"{selected_idea['title']}\n{selected_idea['description']}"

    system_prompt = SYSTEM_PROMPT + "\n\n" + POST_GENERATION_PROMPT
    user_prompt = get_post_user_prompt(user_request, selected_idea_text)

    try:
        # Генерируем пост с typing action (показываем "печатает..." пока AI думает)
        post_text = await call_openai_with_typing(update, system_prompt, user_prompt)

        # Сохраняем пост в контексте
        context.user_data['generated_post'] = post_text
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}")

        # Формируем сообщение об ошибке
        error_msg = "Ой, кажется возникла проблема при генерации поста 😔\n\n"

        error_str = str(e)
        if "429" in error_str or "rate limit" in error_str.lower():
            error_msg += "Похоже что исчерпан лимит бесплатных запросов к AI на сегодня.\n\n"
            error_msg += "Попробуй чуть позже или используй платную модель API 💡"
        else:
            error_msg += "Что-то пошло не так с AI сервисом. Попробуй ещё раз через минутку 🔄"

        await query.message.reply_text(error_msg, reply_markup=get_main_menu_keyboard())
        return

    # Кнопки после генерации поста
    keyboard = [
        [InlineKeyboardButton("💾 Сохранить в избранное", callback_data="save_favorite")],
        [InlineKeyboardButton("🔄 Другая идея", callback_data="another_idea")],
        [InlineKeyboardButton("🆕 Новый запрос", callback_data="new_request")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем готовый пост в код-блоке для удобного копирования
    response_text = f"📝 Готовый пост:\n\n```\n{post_text}\n```\n\n"
    response_text += "💡 _Нажми на текст поста чтобы скопировать его_"

    await query.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')


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

    # Создаём фильтр для кнопок меню
    menu_filter = filters.Regex("^(🆕 Новый запрос|📚 Мои посты|❌ Отмена)$")

    # Conversation Handler для диалога с Каролиной
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("new", start_command),  # /new тоже запускает диалог
            MessageHandler(menu_filter, handle_menu_buttons),  # Кнопки меню
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text)  # Свободный текст → entry point
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
                CallbackQueryHandler(handle_reuse_yes, pattern="^reuse_yes$"),
                CallbackQueryHandler(handle_reuse_edit_niche, pattern="^reuse_edit_niche$"),
                CallbackQueryHandler(handle_reuse_edit_goal, pattern="^reuse_edit_goal$"),
                CallbackQueryHandler(handle_reuse_edit_format, pattern="^reuse_edit_format$"),
                MessageHandler(menu_filter, handle_menu_buttons),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reuse_confirmation)
            ],
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
        pattern="^idea_\d+$"  # Только idea_1, idea_2 и т.д.
    ))
    application.add_handler(CallbackQueryHandler(
        handle_random_idea,
        pattern="^idea_random$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_regenerate_ideas,
        pattern="^ideas_regenerate$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_post_actions,
        pattern="^(save_favorite|another_idea|new_request)$"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_history_pagination,
        pattern="^history_page_"
    ))
    application.add_handler(CallbackQueryHandler(
        view_saved_post,
        pattern="^view_post_"
    ))
    application.add_handler(CallbackQueryHandler(
        delete_saved_post,
        pattern="^delete_post_"
    ))

    # Запускаем бота
    logger.info("🤖 Бот запущен!")
    logger.info("📡 Начинаю получать обновления от Telegram...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("⛔ Бот остановлен")


if __name__ == '__main__':
    main()
