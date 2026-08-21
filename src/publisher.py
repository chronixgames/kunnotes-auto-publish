import base64
import binascii
import gzip
import json
import os
import re
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


def _clean_body(body):
    # 기존 크레딧 문구가 남아 있더라도 발행 전에 제거한다.
    credit_patterns = [
        r"Photo\s+by\s+[^<\n]+?\s+via\s+Pexels",
        r"Photo\s+by\s+[^<\n]+?\s+via\s+Pixabay",
        r"Photo\s+by\s+[^<\n]+?\s+via\s+Unsplash",
    ]
    cleaned = body
    for pattern in credit_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<p[^>]*>\s*</p>", "", cleaned)
    return cleaned


def _fill_body(page, body):
    body = _clean_body(body)
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
    normalized = []
    for raw in tags:
        for part in re.split(r"[,，|\n]+", str(raw)):
            tag = part.strip().lstrip("#").strip()
            if tag and tag not in normalized:
                normalized.append(tag)
    for tag in normalized[:10]:
        tag_input.fill(tag)
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)


def _open_photo_upload(page):
    # Tistory 신에디터의 파일 input을 직접 활성화하거나 첨부→사진 메뉴를 연다.
    if page.locator("#openFile").count():
        return
    attach = page.locator('button[class*="attach"], .btn_file, [aria-label*="첨부"]').first
    if attach.count():
        attach.click()
        page.wait_for_timeout(500)
    else:
        for btn in page.locator("button").all():
            try:
                if "첨부" in (btn.inner_text(timeout=500) or "") or "첨부" in (btn.get_attribute("aria-label") or ""):
                    btn.click()
                    page.wait_for_timeout(500)
                    break
            except Exception:
                pass
    menu = page.locator('[role="menuitem"], .mce-menu-item').filter(has_text="사진").first
    if menu.count():
        menu.click()
        page.wait_for_timeout(500)


def _upload_images(page, image_paths):
    paths = [str(p) for p in image_paths if p and Path(p).exists()][:3]
    if not paths:
        return []

    frame_body = page.frame_locator("iframe#editor-tistory_ifr").locator("body").first
    frame_body.wait_for(state="visible", timeout=20000)
    frame_body.click()

    for path in paths:
        _open_photo_upload(page)
        file_input = page.locator("#openFile, input[type='file']").first
        if not file_input.count():
            raise RuntimeError("Tistory image upload file input was not found")
        file_input.set_input_files(path)
        page.wait_for_timeout(2500)

    frame = page.frame_locator("iframe#editor-tistory_ifr")
    imgs = frame.locator("body img")
    deadline = 20
    for _ in range(deadline):
        if imgs.count() >= len(paths):
            break
        page.wait_for_timeout(1000)

    urls = imgs.evaluate_all("els => els.map(e => e.src).filter(Boolean)")
    urls = [u for u in urls if str(u).startswith("http")]
    return urls[:len(paths)]


def _replace_image_placeholders(body, image_urls):
    out = _clean_body(body)
    for i, url in enumerate(image_urls[:3], 1):
        img = (
            f"<figure style='margin:28px 0;text-align:center'>"
            f"<img src='{url}' alt='본문 주제 관련 이미지' "
            f"style='display:block;width:100%;max-width:900px;height:auto;margin:0 auto;border-radius:8px;' />"
            f"</figure>"
        )
        out = out.replace(f"<!--IMAGE{i}-->", img, 1)
    for i in range(len(image_urls[:3]) + 1, 4):
        out = out.replace(f"<!--IMAGE{i}-->", "")
    return out


def _set_representative_image(page):
    frame = page.frame_locator("iframe#editor-tistory_ifr")
    first_img = frame.locator("body img").first
    if not first_img.count():
        return False
    first_img.click()
    page.wait_for_timeout(800)

    selectors = [
        ".mce-represent-image-btn",
        "[class*='represent']",
        "[class*='thumbnail']",
        "button[aria-label*='대표']",
        "button[title*='대표']",
        "button[data-tooltip*='대표']",
        ".btn_represent",
        ".represent_img",
        "[class*='RepresentImg']",
        "[class*='representImg']",
    ]
    for selector in selectors:
        btn = page.locator(selector).first
        if btn.count():
            try:
                if btn.is_visible(timeout=1000):
                    btn.click()
                    page.wait_for_timeout(500)
                    return True
            except Exception:
                pass
    return False


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

        image_urls = _upload_images(page, post.get("image_paths", []))
        body = _replace_image_placeholders(post["body"], image_urls)
        _fill_body(page, body)
        page.wait_for_timeout(800)
        representative_set = _set_representative_image(page)
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
        print(f"IMAGES_UPLOADED={len(image_urls)}")
        print(f"REPRESENTATIVE_IMAGE_SET={representative_set}")
        browser.close()
        return current_url
