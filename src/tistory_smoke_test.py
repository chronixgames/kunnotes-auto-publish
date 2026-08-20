import os
from datetime import datetime
from publisher import publish
from playwright.sync_api import sync_playwright


def main():
    blog = os.environ.get("TISTORY_BLOG_NAME", "kunnotes")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"[자동발행 테스트] Kunnotes {stamp}"
    body = f"자동발행 테스트 글입니다. {stamp}에 Playwright를 통해 Tistory에 공개 발행되었습니다."

    result_url = publish({"title": title, "body": body})
    print(f"PUBLISH_RESULT_URL={result_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://{blog}.tistory.com/rss", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        rss = page.locator("body").inner_text()
        browser.close()

    if title not in rss:
        raise RuntimeError("Publish click completed, but the test title was not found in the public RSS feed")
    print("TISTORY_PUBLIC_RSS_VERIFIED=true")
    print(f"TEST_TITLE={title}")


if __name__ == "__main__":
    main()
