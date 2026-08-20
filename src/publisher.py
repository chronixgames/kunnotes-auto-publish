import base64
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def _load_state():
    state = os.environ.get("TISTORY_STORAGE_STATE")
    if not state:
        raise RuntimeError("TISTORY_STORAGE_STATE is required for publishing")
    raw = base64.b64decode(state).decode("utf-8")
    state_path = Path("/tmp/tistory-state.json")
    state_path.write_text(raw, encoding="utf-8")
    return state_path


def _fill_body(page, body):
    iframe = page.locator("iframe#editor-tistory_ifr").first
    if iframe.count():
        page.frame_locator("iframe#editor-tistory_ifr").locator("body").fill(body)
        return
    editable = page.locator('[contenteditable="true"]').first
    if editable.count():
        editable.fill(body)
        return
    raise RuntimeError("Tistory body editor was not found")


def publish(post):
    state_path = _load_state()
    blog = os.environ.get("TISTORY_BLOG_NAME", "kunnotes")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        page.goto(f"https://{blog}.tistory.com/manage/newpost/?type=post", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        if "login" in page.url.lower() or "accounts.kakao" in page.url.lower():
            raise RuntimeError("Tistory session expired; refresh TISTORY_STORAGE_STATE")
        title = page.locator("#post-title-inp, input[placeholder*='제목'], input[name='title']").first
        title.wait_for(state="visible", timeout=20000)
        title.fill(post["title"])
        _fill_body(page, post["body"])
        layer = page.locator("#publish-layer-btn").first
        if layer.count():
            layer.click()
        else:
            page.get_by_text("완료", exact=True).last.click()
        public = page.locator("#open20").first
        if public.count():
            public.check()
        else:
            page.get_by_text("공개", exact=True).last.click()
        publish_button = page.locator("#publish-btn").first
        if publish_button.count():
            publish_button.click()
        else:
            page.get_by_text("공개 발행", exact=True).last.click()
        page.wait_for_timeout(3000)
        current_url = page.url
        if "/manage/newpost" in current_url:
            raise RuntimeError("Tistory publish did not complete; still on new-post page")
        browser.close()
        return current_url
