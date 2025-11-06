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


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_typing_action(update: Update, duration: float = 1.0):
    """Отправляет действие 'печатает...' на указанное время"""
    await update.effective_chat.send_action(ChatAction.TYPING)
    await asyncio.sleep(duration)


async def send_message_with_typing(update: Update, text: str, **kwargs):
    """Отправляет сообщение с имитацией печатания"""
    # Рассчитываем время печатания (0.015 сек на символ, макс 2.5 сек, мин 0.3 сек)
    typing_duration = min(max(len(text) * 0.015, 0.3), 2.5)

    # Показываем "печатает..."
    await send_typing_action(update, typing_duration)

    # Отправляем сообщение
    return await update.message.reply_text(text, **kwargs)


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


async def validate_user_answer(user_answer: str, question_context: str, user_name: str) -> dict:
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
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": validation_prompt}],
            temperature=0.7,
            max_tokens=150
        )

        ai_response = response.choices[0].message.content.strip()

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
    validation = await validate_user_answer(niche, "нишу (тематику контента)", user_name)

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

    # VALID - принимаем ответ
    context.user_data['niche'] = niche
    logger.info(f"✅ Ниша принята: {niche}")

    response = f"""Отлично, {user_name}! {niche} - это интересная тема!

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
    validation = await validate_user_answer(goal, "цель контента (что хочешь достичь)", user_name)

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
    validation = await validate_user_answer(format_type, "формат контента (пост, статья, видео и т.д.)", user_name)

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

    thinking_msg = await send_message_with_typing(update, summary_text)

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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена разговора"""
    user_name = context.user_data.get('user_name', 'дружище')
    cancel_text = f"Хорошо, {user_name}! Если захочешь начать заново - просто напиши /start 😊"
    await send_message_with_typing(update, cancel_text)
    return ConversationHandler.END


# Функция new_command не нужна, так как /new теперь запускает start_command


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history"""
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

    await update.message.reply_text(
        f"📚 Твои сохранённые посты, {user_name} ({len(favorites)}):\n",
        reply_markup=get_main_menu_keyboard()
    )

    for idx, fav in enumerate(favorites, 1):
        timestamp = fav.get('timestamp', 'Неизвестно')
        idea = fav.get('idea', 'Без описания')
        post = fav.get('post', '')
        request = fav.get('request', '')

        text = f"#{idx} | {timestamp[:10]}\n\n"
        if request:
            text += f"📋 Запрос: {request}\n\n"
        text += f"💡 Идея: {idea}\n\n"
        text += f"📝 Пост:\n```\n{post}\n```\n"
        text += "💡 _Нажми на текст поста чтобы скопировать_\n"
        text += "—" * 30

        await update.message.reply_text(text, parse_mode='Markdown')


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

    # Используем AI для понимания намерений
    intent_prompt = f"""Ты - Каролина, личный креативный ассистент по генерации контент-идей. Ты женщина, используй женский род.

Пользователь {user_name} написал: "{user_text}"

Твои возможности:
1. ANOTHER_IDEA - Хочет другую идею из уже показанных или новые идеи
   Примеры: "другую", "давай другую", "плохая идея", "не нравится", "не то", "не подходит", "покажи другие", "есть еще?", "что еще есть?", "другие варианты", "не зашло", "мимо", "слабовато"

2. GENERATE_IDEAS - Сразу начать генерацию НОВЫХ идей
   Примеры: "давай еще идеи", "придумай еще", "есть ли еще идеи", "еще 5 идей", "новые идеи", "создай идеи", "сгенерируй идеи", "придумай новые", "хочу больше идей"

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
- "еще идеи", "придумай еще", "новые идеи" → GENERATE_IDEAS
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
        # Получаем ответ от AI
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": intent_prompt}],
            temperature=0.8,
            max_tokens=200
        )

        ai_response = response.choices[0].message.content.strip()
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

                reply_markup = InlineKeyboardMarkup(keyboard)

                choice_text = f"Вот все 5 идей, {user_name}! Выбирай какая нравится 👇"
                await update.message.reply_text(choice_text, reply_markup=reply_markup)
            else:
                # Нет идей - начинаем новую генерацию
                await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())
                return await start_command(update, context, skip_greeting=True)

        elif 'GENERATE_IDEAS' in intent_line.upper():
            # Фразы типа "давай еще идеи" - сразу к генерации БЕЗ приветствия
            await send_message_with_typing(update, response_line, reply_markup=get_main_menu_keyboard())
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
        # Fallback на простой ответ
        fallback_responses = [
            f"Я много в чем сильна, {user_name}, но моя задача - помогать генерировать идеи для контента! 💡 Давай придумаем ещё парочку? Нажимай '🆕 Новый запрос' 😊",
            f"{user_name}, моя специализация - контент и идеи! 🎨 Хочешь создадим что-то крутое? Жми '🆕 Новый запрос'!",
            f"Я тут больше по контенту и идеям! ✍️ Давай лучше сделаем классный пост? Нажимай '🆕 Новый запрос', {user_name}! 🚀"
        ]
        await send_message_with_typing(update, random.choice(fallback_responses), reply_markup=get_main_menu_keyboard())


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
    await query.edit_message_text(get_random_writing_phrase(idea_number))

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
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("⛔ Бот остановлен")


if __name__ == '__main__':
    main()
