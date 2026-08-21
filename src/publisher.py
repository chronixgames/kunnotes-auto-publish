import base64
import binascii
import gzip
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def _load_state():
    parts = [os.environ.get(f"TISTORY_STORAGE_STATE_{i}", "") for i in range(1, 4)]
    state = "".join(parts).strip()
    if not state:
        state = os.environ.get("TISTORY_STORAGE_STATE", "").strip()
    if not state:
        raise RuntimeError("TISTORY_STORAGE_STATE_1/2/3 are required for publishing")

    compact = "".join(state.split())
    raw = None
    errors = []

    try:
        decoded = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=False)
        if decoded[:2] == b"\x1f\x8b":
            raw = gzip.decompress(decoded).decode("utf-8")
        else:
            decoded_text = decoded.decode("utf-8").strip()
            if decoded_text.startswith("{"):
                json.loads(decoded_text)
                raw = decoded_text
            else:
                errors.append(f"decoded data is neither gzip nor JSON (prefix={decoded[:8].hex()})")
    except (binascii.Error, ValueError, OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"base64/state decode failed: {exc}")

    if raw is None and compact.startswith("{"):
        try:
            json.loads(compact)
            raw = compact
        except json.JSONDecodeError as exc:
            errors.append(f"plain JSON parse failed: {exc}")

    if raw is None:
        raise RuntimeError(
            "Invalid Tistory storage state. Expected base64(gzip(JSON)), base64(JSON), or plain JSON. "
            f"Combined length={len(compact)}. " + "; ".join(errors)
        )

    state_path = Path("/tmp/tistory-state.json")
    state_path.write_text(raw, encoding="utf-8")
    return state_path


def _fill_body(page, body):
    iframe = page.locator("iframe#editor-tistory_ifr").first
    if iframe.count():
        frame_body = page.frame_locator("iframe#editor-tistory_ifr").locator("body").first
        frame_body.wait_for(state="visible", timeout=20000)
        frame_body.evaluate("(el, html) => { el.innerHTML = html; el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:null})); el.dispatchEvent(new Event('change', {bubbles:true})); }", body)
        return
    editable = page.locator('[contenteditable="true"]').first
    if editable.count():
        editable.wait_for(state="visible", timeout=20000)
        editable.evaluate("(el, html) => { el.innerHTML = html; el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:null})); el.dispatchEvent(new Event('change', {bubbles:true})); }", body)
        return
    raise RuntimeError("Tistory body editor was not found")


def _fill_tags(page, tags):
    if not tags:
        return
    tag_input = page.locator("#tagText, input[placeholder*='태그'], input[placeholder*='tag']").first
    if not tag_input.count():
        raise RuntimeError("Tistory tag input was not found")
    tag_input.wait_for(state="visible", timeout=10000)
    for tag in tags[:10]:
        tag = str(tag).lstrip("#").strip()
        if not tag:
            continue
        tag_input.fill(tag)
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)


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
            raise RuntimeError("Tistory session expired; refresh Tistory storage state")
        title = page.locator("#post-title-inp, input[placeholder*='제목'], input[name='title']").first
        title.wait_for(state="visible", timeout=20000)
        title.fill(post["title"])
        _fill_body(page, post["body"])
        _fill_tags(page, post.get("tags", []))

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

        try:
            page.locator("#publish-btn").first.wait_for(state="hidden", timeout=15000)
        except Exception:
            try:
                page.get_by_text("공개 발행", exact=True).last.wait_for(state="hidden", timeout=5000)
            except Exception:
                pass

        page.wait_for_timeout(2000)
        current_url = page.url
        browser.close()
        return current_url
