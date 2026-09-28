import os
import time
import json
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

MAX_PRICE = int(os.environ.get("MAX_PRICE", "20000"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))

AVITO_URL = "https://www.avito.ru/moskva/telefony/iphone"

CHAT_ID_FILE = "chat_id.json"
OFFSET_FILE = "telegram_offset.json"
SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_id():
    return load_json(CHAT_ID_FILE, {}).get("chat_id")


def set_chat_id(chat_id):
    save_json(CHAT_ID_FILE, {"chat_id": chat_id})


def telegram_url(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_telegram(text):
    chat_id = get_chat_id()

    if not chat_id:
        print("CHAT_ID ещё не сохранён. Напишите боту /start", flush=True)
        return False

    try:
        response = requests.post(
            telegram_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=20
        )

        print(
            f"Telegram sendMessage: {response.status_code}",
            flush=True
        )

        return response.status_code == 200

    except requests.RequestException as e:
        print(f"Ошибка Telegram: {e}", flush=True)
        return False


def check_telegram():
    offset = load_json(OFFSET_FILE, {}).get("offset")

    params = {
        "timeout": 5
    }

    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(
            telegram_url("getUpdates"),
            params=params,
            timeout=15
        )

        print(
            f"Telegram getUpdates: {response.status_code}",
            flush=True
        )

        if response.status_code != 200:
            print(response.text[:500], flush=True)
            return

        data = response.json()

        for update in data.get("result", []):

            save_json(
                OFFSET_FILE,
                {
                    "offset": update["update_id"] + 1
                }
            )

            message = update.get("message")

            if not message:
                continue

            chat_id = message.get("chat", {}).get("id")

            if chat_id:
                set_chat_id(chat_id)
                print(
                    f"Сохранён CHAT_ID: {chat_id}",
                    flush=True
                )

            text = message.get("text", "").strip().lower()

            if text == "/start":

                send_telegram(
                    f"Мониторинг запущен!\n\n"
                    f"Ищу iPhone 13 в Москве до {MAX_PRICE} ₽."
                )

            elif text == "/status":

                send_telegram(
                    f"Бот работает.\n"
                    f"Лимит: {MAX_PRICE} ₽\n"
                    f"Проверка каждые {CHECK_INTERVAL} сек."
                )

            elif text == "/check":

                send_telegram(
                    "Проверяю Avito прямо сейчас..."
                )

                check_avito()

    except requests.RequestException as e:

        print(
            f"Ошибка Telegram: {e}",
            flush=True
        )


def get_ads():

    print("Открываю Avito...", flush=True)

    try:

        response = requests.get(
            AVITO_URL,
            headers=HEADERS,
            timeout=30
        )

    except requests.RequestException as e:

        print(
            f"Ошибка соединения с Avito: {e}",
            flush=True
        )

        return []

    print(
        f"Avito HTTP: {response.status_code}",
        flush=True
    )

    print(
        f"Размер ответа: {len(response.text)}",
        flush=True
    )

    if response.status_code in (403, 429):

        print(
            "Avito ограничил запрос.",
            flush=True
        )

        return []

    if "captcha" in response.text.lower():

        print(
            "Avito показал CAPTCHA.",
            flush=True
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    cards = soup.select(
        '[data-marker="item"]'
    )

    print(
        f"Карточек найдено: {len(cards)}",
        flush=True
    )

    ads = []

    for card in cards:

        title_link = card.select_one(
            'a[data-marker="item-title"]'
        )

        if not title_link:
            continue

        title = title_link.get_text(
            " ",
            strip=True
        )

        href = title_link.get(
            "href",
            ""
        )

        if not href:
            continue

        if href.startswith("/"):

            url = (
                "https://www.avito.ru"
                + href
            )

        else:

            url = href

        title_lower = title.lower()

        if (
            "iphone 13" not in title_lower
            and
            "айфон 13" not in title_lower
        ):
            continue

        price_element = card.select_one(
            '[data-marker="item-price"]'
        )

        if not price_element:
            continue

        price_text = price_element.get_text(
            " ",
            strip=True
        )

        digits = ""

        for character in price_text:

            if character.isdigit():

                digits += character

        if not digits:
            continue

        price = int(digits)

        if price > MAX_PRICE:
            continue

        ads.append(
            {
                "title": title,
                "price": price,
                "url": url
            }
        )

    return ads


def check_avito():

    print(
        "Проверяю Avito...",
        flush=True
    )

    ads = get_ads()

    print(
        f"Подходящих объявлений: {len(ads)}",
        flush=True
    )

    seen = set(
        load_json(
            SEEN_FILE,
            []
        )
    )

    for ad in ads:

        if ad["url"] in seen:
            continue

        message = (
            "НОВОЕ ОБЪЯВЛЕНИЕ\n\n"
            f"{ad['title']}\n"
            f"Цена: {ad['price']} ₽\n\n"
            f"{ad['url']}"
        )

        if send_telegram(message):

            seen.add(
                ad["url"]
            )

            save_json(
                SEEN_FILE,
                list(seen)
            )

            print(
                "Объявление отправлено",
                flush=True
            )


print(
    "БОТ ЗАПУСТИЛСЯ",
    flush=True
)

print(
    "Avito iPhone Monitor запущен",
    flush=True
)

print(
    f"Лимит цены: {MAX_PRICE} ₽",
    flush=True
)

print(
    f"Интервал: {CHECK_INTERVAL} секунд",
    flush=True
)

while True:

    try:

        print(
            "Проверяю Telegram...",
            flush=True
        )

        check_telegram()

        print(
            "Проверяю Avito...",
            flush=True
        )

        check_avito()

        print(
            f"Следующая проверка через {CHECK_INTERVAL} секунд",
            flush=True
        )

        time.sleep(
            CHECK_INTERVAL
        )

    except Exception as e:

        print(
            f"Ошибка: {type(e).__name__}: {e}",
            flush=True
        )

        time.sleep(30)
