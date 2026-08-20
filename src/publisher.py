import base64, json, os
from pathlib import Path
from playwright.sync_api import sync_playwright


def publish(post):
    state = os.environ.get("TISTORY_STORAGE_STATE")
    if not state:
        raise RuntimeError("TISTORY_STORAGE_STATE is required for publishing")
    raw = base64.b64decode(state).decode("utf-8")
    state_path = Path("/tmp/tistory-state.json")
    state_path.write_text(raw, encoding="utf-8")
    blog = os.environ.get("TISTORY_BLOG_NAME", "kunnotes")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        page.goto(f"https://{blog}.tistory.com/manage/newpost/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            raise RuntimeError("Tistory session expired; refresh TISTORY_STORAGE_STATE")
        # Tistory editor DOM can change. Keep selectors centralized for easy maintenance.
        title = page.locator('input[placeholder*="제목"], input[name="title"]').first
        title.fill(post["title"])
        editor = page.locator('[contenteditable="true"]').first
        editor.fill(post["body"])
        # Save as scheduled/publish. The exact UI can change; fail closed rather than silently publishing elsewhere.
        publish_button = page.get_by_text("공개 발행", exact=True).first
        if publish_button.count() == 0:
            publish_button = page.get_by_text("발행", exact=True).first
        publish_button.click()
        page.wait_for_timeout(1500)
        # Do not click ambiguous confirmation controls automatically.
        browser.close()
