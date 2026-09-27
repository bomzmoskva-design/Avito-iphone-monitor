import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup as BS

# ⚙️ Настройки бота (переменные окружения)
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") # Может быть None для всех чатов

MAX_PRICE = int(os.getenv("MAX_PRICE", "20000"))      # Максимальная цена
CHECK_INTERVAL = int(os.getenv("INTERVAL_CHECK", "600")) # Проверка каждые 10 минут (в секундах)

# ⚙️ Фильтр объявлений — только iPhone 13
IPHONE_13_KEYWORDS = ["iphone 13", "айфон 13"] # Список ключевых слов
IPHONE_13_PATTERN = re.compile("|".join(IPHONE_13_KEYWORDS), flags=re.I) 

SEARCH_URLS = [
    "https://www.avito.ru/moskva/telefony/iphone",
]
STATE_FILE = "seen.json"

def load_seen():
    """Загружает список уже отправленных ID объявлений."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    """Сохраняет последние 2000 уникальных ID объявлений."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-2000:], f, ensure_ascii=False)

def send_telegram(text, chat_id=None):
    """
    Отправляет сообщение в Telegram.
    
    Если CHAT_ID не задано как переменная окружения,
    бот будет отвечать только тому пользователю, который написал команду /start.
    """
    if not chat_id and CHAT_ID is None:
        print("Telegram: чат не найден")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": chat_id or CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    print("Telegram:", response.status_code)

def get_price(price_text):
    """
    Извлекает число из строки цены.
    Например: '19 990 ₽' -> 19990
              '15 000 руб.' -> 15000
    """
    numbers = re.sub(r"[^\d]", "", price_text)
    return int(numbers) if numbers else None


def get_ads(url):
    """
    Парсит страницу Avito и возвращает подходящие объявления.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; "
            "K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        print("Ошибка запроса Avito:", e)
        return []

    soup = BS(response.text, "html.parser")

    result = []

    for item in soup.select('[data-marker="item"]'):
        link = item.select_one('a[data-marker="item-title"]')
        
        # Пропускаем объявление без ссылки или названия
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        href = link.get("href")

        # ✅ ФИЛЬТР ПО МОДЕЛИ
        # Пропускаем все объявления, где нет слова iPhone 13 или Айфон 13
        if IPHONE_13_PATTERN.search(title) is None:
            continue

        # Приводим относительную ссылку к абсолютной
        if href.startswith("/"):
            href = "https://www.avito.ru" + href

        price_element = item.select_one('[data-marker="item-price"]')
        price_text = price_element.get_text(" ", strip=True) if price_element else ""
        price = get_price(price_text)

        # Пропускаем объявления без цены или выше лимита
        if price is None or price > MAX_PRICE:
            continue

        result.append({
            "title": title,
            "price": price,
            "url": href,
        })

    return result


def check_avito():
    """
    Ищет новые объявления на Avito и отправляет их в Telegram.
    """
    seen = load_seen()          # Загружаем уже отправленные ID
    new_count = 0              # Счётчик новых объявлений

    for search_url in SEARCH_URLS:
        ads = get_ads(search_url)

        print("Подходящих объявлений:", len(ads))

        for ad in ads:
            # Используем URL как уникальный идентификатор
            ad_id = ad["url"]

            # Если такое объявление уже было отправлено — пропускаем его
            if ad_id in seen:
                continue

            seen.add(ad_id)
            new_count += 1

            message = (
                "🚨 НОВЫЙ iPHONE\n\n"
                f"📱 {ad['title']}\n"
                f"💰 {ad['price']:,} ₽\n\n"
                f"🔗 {ad['url']}\n\n"
                f"⚙️ Лимит: {MAX_PRICE:,} ₽"
            )

            send_telegram(message)

            # Делаем паузу между сообщениями, чтобы не забанили
            time.sleep(1)

    save_seen(seen)           # Сохраняем обновленный список отправленных ID
    print(f"Новых объявлений отправлено: {new_count}")


def check_telegram():
    """
    Обрабатывает команды от пользователя через Telegram API.
    Поддерживает команды /start и /status.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    try:
        response = requests.get(
            url,
            params={"timeout": 1},
            timeout=10,
        )

        data = response.json()

        if not data.get("ok"):
            print("Ошибка Telegram:", data)
            return

        updates = data.get("result", [])

        for update in updates:
            message = update.get("message")

            if not message:
                continue

            chat_id = message["chat"]["id"]
            text = message.get("text", "").strip().lower()

            # Команда /start — приветствие
            if text == "/start":
                send_telegram(
                    "👋 Привет!\n\n"
                    "Я Avito-монитор iPhone.\n\n"
                    f"📍 Москва\n"
                    f"💰 Максимальная цена: {MAX_PRICE:,} ₽\n"
                    "🔄 Проверка каждые 10 минут.\n\n"
                    "Я буду присылать новые подходящие объявления.",
                    chat_id,
                )
            
            # Команда /status — текущее состояние
            elif text == "/status":
                send_telegram(
                    "🟢 Бот работает.\n\n"
                    f"📍 Москва\n"
                    f"💰 Лимит: {MAX_PRICE:,} ₽\n"
                    "🔄 Интервал: 10 минут",
                    chat_id,
                )

    except Exception as e:
        print("Ошибка Telegram:", e)


def main():
    """
    Основной цикл работы бота.
    Каждые CHECK_INTERVAL секунд проверяет Avito и Telegram.
    """
    print("=" * 40)
    print("🚀 Avito iPhone Monitor запущен")
    print(f"💰 Максимальная цена: {MAX_PRICE:,} ₽")
    print(f"⏱ Проверка каждые {CHECK_INTERVAL // 60} минут")
    print("=" * 40)

    while True:
        print("\n📨 Проверяем Telegram...")
        check_telegram()

        print("🔎 Проверяем Avito...")
        check_avito()

        print(
            f"😴 Следующая проверка через "
            f"{CHECK_INTERVAL // 60} минут..."
        )

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
