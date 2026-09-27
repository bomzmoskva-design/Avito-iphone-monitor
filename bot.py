import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Максимальная цена
MAX_PRICE = int(os.getenv("MAX_PRICE", "20000"))

# Проверка каждые 10 минут
CHECK_INTERVAL = 600

SEARCH_URLS = [
    "https://www.avito.ru/moskva/telefony/iphone",
]

STATE_FILE = "seen.json"


def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-2000:], f, ensure_ascii=False)


def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = CHAT_ID

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
            timeout=20,
        )

        print("Telegram:", response.status_code)

    except Exception as e:
        print("Ошибка Telegram:", e)


def get_price(price_text):
    """
    Извлекает число из строки цены.
    Например:
    '19 990 ₽' -> 19990
    '15 000 руб.' -> 15000
    """

    if not price_text:
        return None

    numbers = re.sub(r"[^\d]", "", price_text)

    if not numbers:
        return None

    try:
        return int(numbers)
    except ValueError:
        return None


def get_ads(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; "
            "K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30,
        )
    except Exception as e:
        print("Ошибка запроса Avito:", e)
        return []

    print("Avito HTTP:", response.status_code)

    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    result = []

    for item in soup.select('[data-marker="item"]'):

        link = item.select_one('a[data-marker="item-title"]')

        if not link:
            continue

        title = link.get_text(" ", strip=True)
        href = link.get("href")

        if not href:
            continue

        if href.startswith("/"):
            href = "https://www.avito.ru" + href

        price_element = item.select_one(
            '[data-marker="item-price"]'
        )

        price_text = (
            price_element.get_text(" ", strip=True)
            if price_element
            else ""
        )

        price = get_price(price_text)

        # Отбрасываем объявления без цены
        if price is None:
            continue

        # Фильтр по максимальной цене
        if price > MAX_PRICE:
            continue

        result.append({
            "title": title,
            "price": price,
            "url": href,
        })

    return result


def check_avito():
    seen = load_seen()
    new_count = 0

    for search_url in SEARCH_URLS:

        try:
            ads = get_ads(search_url)

            print("Подходящих объявлений:", len(ads))

            for ad in ads:

                ad_id = ad["url"]

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

                time.sleep(1)

        except Exception as e:
            print("Ошибка проверки Avito:", e)

    save_seen(seen)

    print(f"Новых объявлений отправлено: {new_count}")


def check_telegram():
    """
    Проверяем команды Telegram.
    /start — приветствие.
    """

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    try:
        response = requests.get(
            url,
            params={
                "timeout": 1,
            },
            timeout=10,
        )

        data = response.json()

        if not data.get("ok"):
            print("Ошибка Telegram:", data)
            return

        updates = data.get("result", [])

        if not updates:
            return

        for update in updates:

            message = update.get("message")

            if not message:
                continue

            chat_id = message["chat"]["id"]
            text = message.get("text", "")

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

    print("=" * 40)
    print("🚀 Avito iPhone Monitor запущен")
    print(f"💰 Максимальная цена: {MAX_PRICE:,} ₽")
    print("⏱ Проверка каждые 10 минут")
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
