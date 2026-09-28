import os
import time
import json
import asyncio
from playwright.async_api import async_playwright

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

MAX_PRICE = int(os.environ.get("MAX_PRICE", "20000"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))

AVITO_URL = "https://www.avito.ru/moskva/telefony/iphone_13"

CHAT_ID_FILE = "chat_id.json"
SEEN_FILE = "seen.json"


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_id():
    return load_json(CHAT_ID_FILE, {}).get("chat_id")


def set_chat_id(chat_id):
    save_json(CHAT_ID_FILE, {"chat_id": chat_id})


async def telegram(method, data=None):
    import aiohttp

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=data or {},
                timeout=20
            ) as response:

                print(
                    f"Telegram {method}: {response.status}",
                    flush=True
                )

                return await response.json()

    except Exception as e:

        print(
            f"Telegram error: {e}",
            flush=True
        )

        return {}


async def send_telegram(text):

    chat_id = get_chat_id()

    if not chat_id:

        print(
            "CHAT_ID ещё не сохранён. Напишите боту /start",
            flush=True
        )

        return False

    result = await telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True
        }
    )

    return result.get("ok", False)


async def check_telegram():

    offset_file = "telegram_offset.json"

    offset_data = load_json(
        offset_file,
        {}
    )

    params = {}

    if "offset" in offset_data:

        params["offset"] = offset_data["offset"]

    result = await telegram(
        "getUpdates",
        params
    )

    if not result.get("ok"):

        return

    for update in result.get("result", []):

        save_json(
            offset_file,
            {
                "offset": update["update_id"] + 1
            }
        )

        message = update.get("message")

        if not message:

            continue

        chat_id = message.get(
            "chat",
            {}
        ).get("id")

        if chat_id:

            set_chat_id(chat_id)

            print(
                f"CHAT_ID сохранён: {chat_id}",
                flush=True
            )

        text = message.get(
            "text",
            ""
        ).strip().lower()

        if text == "/start":

            await send_telegram(
                "🟢 Мониторинг запущен!\n\n"
                "Ищу iPhone 13 в Москве "
                f"до {MAX_PRICE} ₽."
            )

        elif text == "/status":

            await send_telegram(
                "🟢 Бот работает.\n"
                f"Лимит: {MAX_PRICE} ₽"
            )

        elif text == "/check":

            await send_telegram(
                "🔎 Проверяю Avito..."
            )


async def check_avito(browser):

    print(
        "🌐 Открываю Avito через Chromium...",
        flush=True
    )

    page = await browser.new_page()

    try:

        await page.goto(
            AVITO_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print(
            f"Avito URL: {page.url}",
            flush=True
        )

        await page.wait_for_timeout(5000)

        title = await page.title()

        print(
            f"Заголовок страницы: {title}",
            flush=True
        )

        content = await page.locator("body").inner_text()

        print(
            f"Размер текста страницы: {len(content)}",
            flush=True
        )

        if (
            "captcha" in content.lower()
            or
            "подтвердите" in content.lower()
        ):

            print(
                "⚠️ Avito запросил проверку.",
                flush=True
            )

            return

        cards = page.locator(
            '[data-marker="item"]'
        )

        count = await cards.count()

        print(
            f"Карточек найдено: {count}",
            flush=True
        )

        seen = set(
            load_json(
                SEEN_FILE,
                []
            )
        )

        for i in range(count):

            card = cards.nth(i)

            try:

                title_element = card.locator(
                    'a[data-marker="item-title"]'
                )

                title = await title_element.inner_text()

                href = await title_element.get_attribute(
                    "href"
                )

                price_element = card.locator(
                    '[data-marker="item-price"]'
                )

                price_text = await price_element.inner_text()

                digits = "".join(
                    c for c in price_text
                    if c.isdigit()
                )

                if not digits:

                    continue

                price = int(digits)

                if price > MAX_PRICE:

                    continue

                if not href:

                    continue

                if href.startswith("/"):

                    url = (
                        "https://www.avito.ru"
                        + href
                    )

                else:

                    url = href

                if url in seen:

                    continue

                message = (
                    "📱 НОВОЕ ОБЪЯВЛЕНИЕ\n\n"
                    f"{title}\n"
                    f"💰 {price} ₽\n\n"
                    f"{url}"
                )

                if await send_telegram(message):

                    seen.add(url)

                    save_json(
                        SEEN_FILE,
                        list(seen)
                    )

                    print(
                        "📨 Отправлено:",
                        title,
                        flush=True
                    )

            except Exception as e:

                print(
                    f"Ошибка карточки: {e}",
                    flush=True
                )

    except Exception as e:

        print(
            f"❌ Ошибка Avito: {e}",
            flush=True
        )

    finally:

        await page.close()


async def main():

    print(
        "БОТ ЗАПУСТИЛСЯ",
        flush=True
    )

    print(
        "🚀 Avito iPhone Monitor",
        flush=True
    )

    print(
        f"💰 Лимит: {MAX_PRICE} ₽",
        flush=True
    )

    print(
        f"⏱ Интервал: {CHECK_INTERVAL} секунд",
        flush=True
    )

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        while True:

            try:

                print(
                    "📨 Проверяю Telegram...",
                    flush=True
                )

                await check_telegram()

                print(
                    "🔎 Проверяю Avito...",
                    flush=True
                )

                await check_avito(
                    browser
                )

                print(
                    f"😴 Следующая проверка через {CHECK_INTERVAL} секунд",
                    flush=True
                )

                await asyncio.sleep(
                    CHECK_INTERVAL
                )

            except Exception as e:

                print(
                    f"❌ Ошибка: {e}",
                    flush=True
                )

                await asyncio.sleep(30)


asyncio.run(main())
