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
    credit_patterns = [
        r"Photo\s+by\s+[^<\n]+?\s+via\s+(?:Pexels|Pixabay|Unsplash)",
        r"Photo\s+by\s+[^<\n]+?(?:Pexels|Pixabay|Unsplash)",
        r"(?:Photo|Image)\s+(?:credit|source)\s*:\s*[^<\n]+",
    ]
    cleaned = body
    for pattern in credit_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<p[^>]*>\s*</p>", "", cleaned)
    return cleaned


def _style_tables(body):
    """Normalize table typography/alignment so generated tables render consistently."""
    body = re.sub(
        r"<table(?![^>]*style=)",
        "<table style='width:100%;border-collapse:collapse;table-layout:fixed;'",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"<table([^>]*style=['\"])([^'\"]*)['\"]",
        lambda m: f"<table{m.group(1)}{m.group(2).rstrip(';')};width:100%;border-collapse:collapse;table-layout:fixed;'",
        body,
        flags=re.IGNORECASE,
    )
    cell_style = "padding:11px 10px;line-height:1.6;text-align:center;vertical-align:middle;word-break:keep-all;"
    body = re.sub(
        r"<(th|td)(?![^>]*style=)",
        lambda m: f"<{m.group(1)} style='{cell_style}'",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"<(th|td)([^>]*style=['\"])([^'\"]*)['\"]",
        lambda m: f"<{m.group(1)}{m.group(2)}{m.group(3).rstrip(';')};{cell_style}'",
        body,
        flags=re.IGNORECASE,
    )
    return body


def _fill_body(page, body):
    body = _style_tables(_clean_body(body))
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
            tag = part.strip().lstrip("#").strip().replace(",", "").replace("，", "")
            if tag and tag not in normalized:
                normalized.append(tag)
    for tag in normalized[:10]:
        tag_input.fill(tag)
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)


def _visible_locator(page, selector):
    """Return the first visible match; Tistory often keeps a hidden duplicate toolbar."""
    loc = page.locator(selector)
    for i in range(loc.count()):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible(timeout=500):
                return candidate
        except Exception:
            continue
    return None


def _open_photo_upload(page):
    # Tistory's toolbar can contain hidden duplicate attach buttons. Always target a visible one.
    file_input = page.locator("#openFile, input[type='file']").first
    if file_input.count() and file_input.is_visible(timeout=500):
        return

    selectors = [
        '[aria-label="첨부"]:visible',
        'button[class*="attach"]:visible',
        '.btn_file:visible',
        '[role="button"][aria-label*="첨부"]:visible',
    ]
    attach = None
    for selector in selectors:
        attach = _visible_locator(page, selector)
        if attach:
            break

    if attach:
        attach.scroll_into_view_if_needed()
        attach.click(timeout=10000)
        page.wait_for_timeout(500)
    else:
        for i in range(page.locator("button, [role='button']").count()):
            btn = page.locator("button, [role='button']").nth(i)
            try:
                if not btn.is_visible(timeout=300):
                    continue
                label = (btn.get_attribute("aria-label") or "") + " " + (btn.inner_text(timeout=300) or "")
                if "첨부" in label:
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=10000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                pass

    menu = _visible_locator(page, '[role="menuitem"], .mce-menu-item')
    if menu:
        try:
            candidates = page.locator('[role="menuitem"], .mce-menu-item')
            for i in range(candidates.count()):
                item = candidates.nth(i)
                if item.is_visible(timeout=300) and "사진" in (item.inner_text(timeout=300) or ""):
                    item.click(timeout=10000)
                    page.wait_for_timeout(500)
                    break
        except Exception:
            pass


def _upload_images(page, image_paths):
    paths = [str(p) for p in image_paths if p and Path(p).exists()][:5]
    if not paths:
        return []

    frame_body = page.frame_locator("iframe#editor-tistory_ifr").locator("body").first
    frame_body.wait_for(state="visible", timeout=20000)
    frame_body.click()

    for path in paths:
        _open_photo_upload(page)
        file_input = page.locator("#openFile, input[type='file']").first
        file_input.wait_for(state="attached", timeout=10000)
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
    out = _style_tables(_clean_body(body))
    for i, url in enumerate(image_urls[:5], 1):
        img = (
            f"<figure style='margin:28px 0;text-align:center'>"
            f"<img src='{url}' alt='본문 주제 관련 이미지' "
            f"style='display:block;width:100%;max-width:900px;height:auto;margin:0 auto;border-radius:8px;' />"
            f"</figure>"
        )
        out = out.replace(f"<!--IMAGE{i}-->", img, 1)
    for i in range(len(image_urls[:5]) + 1, 6):
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
        btn = _visible_locator(page, selector)
        if btn:
            try:
                btn.click(timeout=5000)
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
