import os
import json
import time
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEARCH_URLS = [
    "https://www.avito.ru/moskva/telefony/iphone",
]

STATE_FILE = "seen.json"


def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-1000:], f, ensure_ascii=False)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )


def get_ads(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12) "
            "AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        print("Avito HTTP:", response.status_code)
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

        price = item.select_one('[data-marker="item-price"]')
        price_text = price.get_text(" ", strip=True) if price else ""

        result.append({
            "title": title,
            "price": price_text,
            "url": href,
        })

    return result


def main():
    seen = load_seen()
    new_count = 0

    for search_url in SEARCH_URLS:
        try:
            ads = get_ads(search_url)

            for ad in ads:
                ad_id = ad["url"]

                if ad_id in seen:
                    continue

                seen.add(ad_id)
                new_count += 1

                message = (
                    "🚨 НОВОЕ ОБЪЯВЛЕНИЕ\n\n"
                    f"📱 {ad['title']}\n"
                    f"💰 {ad['price']}\n\n"
                    f"🔗 {ad['url']}"
                )

                send_telegram(message)
                time.sleep(1)

        except Exception as e:
            print("Ошибка:", e)

    save_seen(seen)

    print(f"Новых объявлений: {new_count}")


if __name__ == "__main__":
    main()
