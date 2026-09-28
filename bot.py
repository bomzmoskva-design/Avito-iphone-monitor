import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup as BS
from urllib.parse import urljoin


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

MAX_PRICE = int(os.getenv("MAX_PRICE", "20000"))
CHECK_INTERVAL = int(os.getenv("INTERVAL_CHECK", "600"))

SEARCH_URLS = [
    "https://www.avito.ru/moskva/telefony/iphone"
]

# Сейчас ищем iPhone 13
IPHONE_KEYWORDS = [
    "iphone 13",
    "айфон 13",
]

IPHONE_PATTERN = re.compile(
    "|".join(re.escape(x) for x in IPHONE_KEYWORDS),
    re.I
)

STATE_FILE = "seen.json"
CHAT_FILE = "chat_id.json"
OFFSET_FILE = "telegram_offset.json"


# =========================
# СОХРАНЕНИЕ CHAT ID
# =========================

def load_chat_id():
    try:
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("chat_id")
    except Exception:
        return None


def save_chat_id(chat_id):
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump({"chat_id": chat_id}, f)


# =========================
# TELEGRAM OFFSET
# =========================

def load_offset():
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("offset", 0)
    except Exception:
        return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


# =========================
# УЖЕ ОТПРАВЛЕННЫЕ
# =========================

def load_seen():

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))

    except Exception:
        return set()


def save_seen(seen):

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            list(seen)[-2000:],
            f,
            ensure_ascii=False
        )


# =========================
# TELEGRAM
# =========================

def send_telegram(text, chat_id=None):

    if chat_id is None:
        chat_id = load_chat_id()

    if not chat_id:
        print("❌ Telegram: CHAT_ID не найден")
        return False

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

        data = response.json()

        print("Telegram:", response.status_code, data)

        return data.get("ok", False)

    except Exception as e:

        print("❌ Ошибка Telegram:", e)

        return False


# =========================
# ЦЕНА
# =========================

def get_price(price_text):

    numbers = re.sub(r"[^\d]", "", price_text)

    if not numbers:
        return None

    try:
        return int(numbers)
    except:
        return None


# =========================
# AVITO
# =========================

def get_ads(url):

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Linux; Android 12) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0.0.0 Mobile Safari/537.36",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "*/*;q=0.8",

        "Accept-Language":
            "ru-RU,ru;q=0.9",

        "Cache-Control":
            "no-cache",

    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        print(
            "Avito:",
            response.status_code,
            "размер:",
            len(response.text)
        )

    except Exception as e:

        print("❌ Ошибка запроса Avito:", e)

        return []


    # Проверяем защиту Avito

    text_lower = response.text.lower()

    if response.status_code in [403, 429]:

        print(
            "⚠️ Avito заблокировал автоматический запрос:",
            response.status_code
        )

        return []


    if "captcha" in text_lower:

        print("⚠️ Avito показал CAPTCHA")

        return []


    soup = BS(response.text, "html.parser")


    # Ищем карточки
    items = soup.select('[data-marker="item"]')

    print("Карточек найдено:", len(items))


    if not items:

        print(
            "⚠️ Avito не вернул карточки объявлений."
        )

        return []


    result = []


    for item in items:

        # Название + ссылка
        link = item.select_one(
            'a[data-marker="item-title"]'
        )

        if not link:

            # запасной вариант
            link = item.select_one(
                'a[href*="/obyavlenie/"]'
            )

        if not link:
            continue


        title = link.get_text(
            " ",
            strip=True
        )

        href = link.get("href")


        if not href:
            continue


        # Полная ссылка
        href = urljoin(
            "https://www.avito.ru",
            href
        )


        # Фильтр iPhone 13

        if not IPHONE_PATTERN.search(title):

            continue


        # Цена

        price_element = item.select_one(
            '[data-marker="item-price"]'
        )

        if price_element:

            price_text = price_element.get_text(
                " ",
                strip=True
            )

        else:

            # запасной вариант
            price_element = item.select_one(
                '[itemprop="price"]'
            )

            if price_element:

                price_text = (
                    price_element.get("content")
                    or price_element.get_text(
                        " ",
                        strip=True
                    )
                )

            else:

                price_text = ""


        price = get_price(price_text)


        if price is None:

            continue


        if price > MAX_PRICE:

            continue


        result.append({

            "title": title,

            "price": price,

            "url": href

        })


    return result


# =========================
# ПРОВЕРКА AVITO
# =========================

def check_avito():

    seen = load_seen()

    new_count = 0


    for search_url in SEARCH_URLS:

        print(
            "\n🔎 Проверяем:",
            search_url
        )


        ads = get_ads(search_url)


        print(
            "Подходящих объявлений:",
            len(ads)
        )


        for ad in ads:

            ad_id = ad["url"]


            if ad_id in seen:

                continue


            # Сначала запоминаем
            seen.add(ad_id)

            new_count += 1


            message = (

                "🚨 НОВЫЙ IPHONE\n\n"

                f"📱 {ad['title']}\n"

                f"💰 {ad['price']:,} ₽\n"

                f"📍 Москва\n\n"

                f"🔗 {ad['url']}\n\n"

                f"⚙️ Лимит: {MAX_PRICE:,} ₽"

            )


            print(
                "📤 Отправляем:",
                ad["title"],
                ad["price"]
            )


            send_telegram(message)


            time.sleep(1)


    save_seen(seen)


    print(
        f"✅ Новых объявлений: {new_count}"
    )


# =========================
# TELEGRAM КОМАНДЫ
# =========================

def check_telegram():

    offset = load_offset()


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/getUpdates"
    )


    try:

        response = requests.get(

            url,

            params={
                "offset": offset,
                "timeout": 1
            },

            timeout=10
        )


        data = response.json()


        if not data.get("ok"):

            print(
                "❌ Ошибка Telegram:",
                data
            )

            return


        updates = data.get(
            "result",
            []
        )


        for update in updates:

            # Очень важно:
            # запоминаем следующий offset

            update_id = update["update_id"]

            save_offset(update_id + 1)


            message = update.get(
                "message"
            )


            if not message:

                continue


            chat_id = message["chat"]["id"]

            text = (
                message
                .get("text", "")
                .strip()
                .lower()
            )


            # Сохраняем chat_id

            save_chat_id(chat_id)


            # /start

            if text == "/start":

                send_telegram(

                    "👋 Привет!\n\n"

                    "🤖 Я Avito-монитор iPhone.\n\n"

                    "📍 Москва\n"

                    f"💰 Максимальная цена: "
                    f"{MAX_PRICE:,} ₽\n"

                    f"🔄 Проверка каждые "
                    f"{CHECK_INTERVAL // 60} минут.\n\n"

                    "🟢 Мониторинг запущен.\n"

                    "Я буду присылать "
                    "новые подходящие объявления.",

                    chat_id

                )


            # /status

            elif text == "/status":

                send_telegram(

                    "🟢 Бот работает.\n\n"

                    "📍 Москва\n"

                    f"💰 Лимит: "
                    f"{MAX_PRICE:,} ₽\n"

                    f"🔄 Интервал: "
                    f"{CHECK_INTERVAL // 60} минут\n"

                    "📱 Модель: iPhone 13",

                    chat_id

                )


            # /check

            elif text == "/check":

                send_telegram(

                    "🔎 Проверяю Avito...",

                    chat_id

                )

                check_avito()


    except Exception as e:

        print(
            "❌ Ошибка Telegram:",
            e
        )


# =========================
# MAIN
# =========================

def main():

    print("=" * 50)

    print(
        "🚀 Avito iPhone Monitor запущен"
    )

    print(
        f"💰 Максимальная цена: "
        f"{MAX_PRICE:,} ₽"
    )

    print(
        f"⏱ Проверка каждые "
        f"{CHECK_INTERVAL // 60} минут"
    )

    print("=" * 50)


    while True:

        print(
            "\n📨 Проверяем Telegram..."
        )

        check_telegram()


        print(
            "\n🔎 Проверяем Avito..."
        )

        check_avito()


        print(
            f"\n😴 Следующая проверка "
            f"через {CHECK_INTERVAL // 60} минут..."
        )


        time.sleep(
            CHECK_INTERVAL
        )


if __name__ == "__main__":

    main()
