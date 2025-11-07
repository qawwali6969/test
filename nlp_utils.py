"""
NLP утилиты для парсинга пользовательского ввода
"""
import re

# Списки ключевых слов для распознавания
GOALS = [
    "привлечь", "привлечение", "привлекать", "набрать", "получить", "привлеку",
    "обучить", "обучение", "обучать", "обуч", "научить",
    "продать", "продажа", "продавать", "продаж",
    "развлечь", "развлечение", "развлекать"
]

FORMATS = [
    "пост", "посты", "постов", "поста", "посте",
    "сторис", "stories", "story", "сториз",
    "видео", "ролик", "видос", "ролика", "видоса",
    "статья", "статью", "статьи", "статье",
    "reels", "рилс", "рилсы", "рилсов",
    "shorts", "шортс", "шорты", "шортов",
    "vk", "вк", "вконтакте",
    "instagram", "инстаграм", "инста", "инсты", "инсте", "инстаграма",
    "telegram", "телеграм", "тг", "телеги", "телеге",
    "youtube", "ютуб", "ютуба", "ютубе",
    "tiktok", "тикток", "тиктока", "тиктоке"
]

# Синонимы для нормализации
GOAL_SYNONYMS = {
    "привлечь": ["привлечь", "привлечение", "привлекать", "привлеку", "набрать", "получить"],
    "обучить": ["обучить", "обучение", "обучать", "обуч", "научить", "учить"],
    "продать": ["продать", "продажа", "продавать", "продаж", "продам"],
    "развлечь": ["развлечь", "развлечение", "развлекать"]
}

FORMAT_SYNONYMS = {
    "пост": ["пост", "посты", "постов", "постик", "поста", "посте"],
    "сторис": ["сторис", "stories", "story", "истории", "сториз"],
    "видео": ["видео", "ролик", "видос", "видосик", "ролика", "видоса"],
    "статья": ["статья", "статью", "статьи", "статье"],
    "reels": ["reels", "рилс", "рилсы", "рилсов"],
    "shorts": ["shorts", "шортс", "шорты", "шортов"],
    "telegram": ["telegram", "телеграм", "тг", "телега", "телеги", "телеге"],
    "instagram": ["instagram", "инстаграм", "инста", "ig", "инсты", "инсте", "инстаграма"],
    "vk": ["vk", "вк", "вконтакте"],
    "youtube": ["youtube", "ютуб", "ютьюб", "ютуба", "ютубе"],
    "tiktok": ["tiktok", "тикток", "тиктока", "тиктоке"]
}


def normalize_goal(goal_word: str) -> str:
    """Нормализует найденную цель к базовой форме"""
    goal_word = goal_word.lower()
    for base, variants in GOAL_SYNONYMS.items():
        if any(goal_word.startswith(v) for v in variants):
            return base
    return goal_word


def normalize_format(format_word: str) -> str:
    """Нормализует найденный формат к базовой форме"""
    format_word = format_word.lower()
    for base, variants in FORMAT_SYNONYMS.items():
        if format_word in variants:
            return base
    return format_word


def is_format_word(word: str) -> bool:
    """
    Проверяет является ли слово форматом (в любой форме)

    Args:
        word: Слово для проверки

    Returns:
        bool: True если это формат
    """
    word = word.lower().strip()
    # Проверяем точное совпадение с любым вариантом формата
    for base, variants in FORMAT_SYNONYMS.items():
        if word in variants:
            return True
    return False


def smart_parse_user_request(text: str) -> dict:
    """
    Пытается извлечь нишу, цель и формат из свободного текста

    Args:
        text: Текст пользователя

    Returns:
        dict: {'niche': str, 'goal': str, 'format': str}
    """
    t = text.lower()

    # === ЦЕЛЬ ===
    goal = None
    for g in GOALS:
        pattern = fr"\b{g}\w*"
        match = re.search(pattern, t)
        if match:
            goal = normalize_goal(match.group(0))
            break

    # === ФОРМАТ ===
    fmt = None

    # 1. Явное слово "формат"
    m = re.search(r"формат[:\s]+([a-zа-яё]+)", t)
    if m:
        fmt = normalize_format(m.group(1))

    # 2. Поиск по словарю форматов
    if not fmt:
        for f in FORMATS:
            pattern = fr"\b{f}\b"
            if re.search(pattern, t):
                fmt = normalize_format(f)
                break

    # === НИША ===
    niche = None

    # 1. Шаблоны "для X", "про X", "о X", "по X"
    # Важно: ищем ВСЕ совпадения, не только первое, чтобы пропустить форматы
    patterns = [
        r"про\s+([а-яё0-9 \-]+?)(?:\.|,|\s+(?:чтобы|для|про|формат|цель)|$)",  # "про X" - обычно это ниша
        r"(?:для|о|по)\s+([а-яё0-9 \-]+?)(?:\.|,|\s+(?:чтобы|для|про|формат|цель)|$)",
        r"ниш[аеу][\s:]+([а-яё0-9 \-]+?)(?:\.|,|$)",
    ]

    for pattern in patterns:
        # Ищем все совпадения паттерна
        matches = re.finditer(pattern, t, re.IGNORECASE)
        for m in matches:
            candidate = m.group(1).strip(" .,")
            # Фильтруем: стоп-слова, форматы, слишком короткие
            if (candidate and len(candidate) > 2 and
                candidate not in ["этого", "того", "этом"] and
                not is_format_word(candidate)):
                niche = candidate
                break
        if niche:
            break

    # 2. Запасной вариант: первая часть до запятой или двоеточия
    if not niche:
        # Убираем служебные слова в начале
        t_clean = re.sub(r"^(?:хочу|нужно|давай|сделай|создай|придумай)\s+", "", t)

        # Ищем первую осмысленную часть
        parts = re.split(r"[,:]", t_clean)
        if parts and len(parts[0].strip()) > 2:
            candidate = parts[0].strip()
            # Не берем если это цель или формат
            if candidate not in GOALS and candidate not in FORMATS:
                niche = candidate

    # 3. Еще один вариант: ищем существительное после глаголов действия
    if not niche:
        m = re.search(r"(?:создай|придумай|напиши|сгенерируй)\s+(?:идеи|контент|посты?)\s+(?:для|про|о)\s+([а-яё ]+?)(?:\.|,|$)", t)
        if m:
            niche = m.group(1).strip()

    return {
        "niche": niche or "",
        "goal": goal or "",
        "format": fmt or ""
    }


def looks_like_content_request(text: str) -> bool:
    """
    Проверяет выглядит ли текст как запрос на генерацию контента

    Args:
        text: Текст пользователя

    Returns:
        bool: True если похоже на запрос контента
    """
    t = text.lower()

    keywords = [
        "иде", "контент", "пост", "видео", "сторис", "reels", "shorts",
        "создай", "придумай", "напиши", "сгенерируй", "нужно",
        "хочу", "давай", "можешь", "помоги"
    ]

    return any(k in t for k in keywords)


def extract_missing_fields(parsed: dict) -> list:
    """
    Возвращает список недостающих полей

    Args:
        parsed: Результат smart_parse_user_request

    Returns:
        list: Список ключей недостающих полей ['niche', 'goal', 'format']
    """
    return [k for k, v in parsed.items() if not v]


# Для тестирования
if __name__ == "__main__":
    test_cases = [
        "Создай пост для фитнеса чтобы привлечь аудиторию",
        "Нужны идеи про кулинарию для инстаграм reels",
        "Хочу обучить людей про психологию",
        "Придумай видео для бизнеса",
        "Логопедия",
        "Давай идеи о путешествиях",
    ]

    for text in test_cases:
        result = smart_parse_user_request(text)
        print(f"\nТекст: {text}")
        print(f"Результат: {result}")
        print(f"Недостает: {extract_missing_fields(result)}")
