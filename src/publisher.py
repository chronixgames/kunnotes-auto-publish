import base64
import binascii
import gzip
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


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


def _repair_table_boundaries(body):
    """Keep headings, images, notices and closing sections outside malformed tables."""
    tokens = re.split(r"(<[^>]+>)", body)
    out = []
    table_depth = 0
    cell_depth = 0
    row_depth = 0
    block_start = re.compile(r"<(?:h[1-6]|hr|div|figure|blockquote|ul|ol)\b", re.IGNORECASE)

    for token in tokens:
        if token.startswith("<"):
            low = token.lower()

            if re.match(r"<table\b", low):
                table_depth += 1
            elif re.match(r"</table\b", low):
                if table_depth > 0 and cell_depth > 0:
                    out.append("</td>")
                    cell_depth = 0
                if table_depth > 0 and row_depth > 0:
                    out.append("</tr>")
                    row_depth = 0
                table_depth = max(0, table_depth - 1)
            elif re.match(r"<(?:td|th)\b", low):
                cell_depth += 1
            elif re.match(r"</(?:td|th)\b", low):
                if cell_depth > 0:
                    cell_depth -= 1
                elif table_depth == 0:
                    continue
            elif re.match(r"<tr\b", low):
                row_depth += 1
            elif re.match(r"</tr\b", low):
                if row_depth > 0:
                    row_depth -= 1
                elif table_depth == 0:
                    continue

            if table_depth > 0 and cell_depth > 0 and block_start.match(token):
                out.append("</td></tr></table>")
                table_depth = 0
                cell_depth = 0
                row_depth = 0
                out.append(token)
                continue

        if not token.startswith("<") or table_depth > 0 or not re.match(r"</(?:td|th|tr)\b", token, re.IGNORECASE):
            out.append(token)

    if table_depth > 0:
        if cell_depth > 0:
            out.append("</td>")
        if row_depth > 0:
            out.append("</tr>")
        out.append("</table>")

    return "".join(out)


def _style_tables(body):
    """Normalize table typography/alignment so generated tables render consistently."""
    body = _repair_table_boundaries(body)
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
    cell_style = "padding:11px 10px;line-height:1.6;text-align:center;vertical-align:middle;word-break:keep-all;overflow-wrap:anywhere;"
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
    """Return the first visible match; Tistory often keeps hidden duplicate toolbar."""
    loc = page.locator(selector)
    for i in range(loc.count()):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible(timeout=500):
                return candidate
        except Exception:
            continue
    return None


def _find_attach_button(page):
    selectors = [
        '[aria-label*="사진"]:visible',
        '[title*="사진"]:visible',
        '[data-name="image"]:visible',
        '[data-command="image"]:visible',
        'button[class*="image"]:visible',
        '[aria-label="첨부"]:visible',
        'button[class*="attach"]:visible',
        '.btn_file:visible',
        '[role="button"][aria-label*="첨부"]:visible',
    ]
    for selector in selectors:
        button = _visible_locator(page, selector)
        if button:
            return button

    for i in range(page.locator("button, [role='button']").count()):
        btn = page.locator("button, [role='button']").nth(i)
        try:
            if not btn.is_visible(timeout=300):
                continue
            label = " ".join([
                btn.get_attribute("aria-label") or "",
                btn.get_attribute("title") or "",
                btn.inner_text(timeout=300) or "",
            ])
            if any(word in label for word in ("사진", "이미지", "첨부")):
                return btn
        except Exception:
            pass
    return None


def _find_file_input(page):
    inputs = page.locator("input[type='file']")
    for i in range(inputs.count() - 1, -1, -1):
        candidate = inputs.nth(i)
        try:
            if candidate.is_attached():
                return candidate
        except Exception:
            pass
    return None


def _choose_photo_menu_item(page):
    selectors = [
        '[role="menuitem"]:visible',
        '.mce-menu-item:visible',
        'button:visible',
        '[role="option"]:visible',
    ]
    for selector in selectors:
        candidates = page.locator(selector)
        for i in range(candidates.count()):
            item = candidates.nth(i)
            try:
                if not item.is_visible(timeout=300):
                    continue
                text = " ".join([
                    item.get_attribute("aria-label") or "",
                    item.get_attribute("title") or "",
                    item.inner_text(timeout=300) or "",
                ])
                if "사진" in text or "이미지" in text:
                    return item
            except Exception:
                pass
    return None


def _set_file_for_upload(page, path):
    """Upload through an existing file input or the native Playwright file chooser."""
    existing = _find_file_input(page)
    if existing:
        existing.set_input_files(path)
        return

    attach = _find_attach_button(page)
    if not attach:
        raise RuntimeError("Tistory image/attachment button was not found")

    attach.scroll_into_view_if_needed()

    try:
        with page.expect_file_chooser(timeout=6000) as chooser_info:
            attach.click(timeout=10000)
            page.wait_for_timeout(300)
            menu_item = _choose_photo_menu_item(page)
            if menu_item:
                menu_item.click(timeout=10000)
        chooser_info.value.set_files(path)
        return
    except PlaywrightTimeoutError:
        pass

    menu_item = _choose_photo_menu_item(page)
    if menu_item:
        try:
            with page.expect_file_chooser(timeout=10000) as chooser_info:
                menu_item.click(timeout=10000)
            chooser_info.value.set_files(path)
            return
        except PlaywrightTimeoutError:
            pass

    page.wait_for_timeout(500)
    existing = _find_file_input(page)
    if existing:
        existing.set_input_files(path)
        return

    raise RuntimeError("Tistory image upload control opened, but no file input/file chooser was detected")


def _upload_images(page, image_paths):
    paths = [str(p) for p in image_paths if p and Path(p).exists()][:5]
    if not paths:
        return []

    frame_body = page.frame_locator("iframe#editor-tistory_ifr").locator("body").first
    frame_body.wait_for(state="visible", timeout=20000)
    frame_body.click()

    for path in paths:
        _set_file_for_upload(page, path)
        page.wait_for_timeout(2500)

    frame = page.frame_locator("iframe#editor-tistory_ifr")
    imgs = frame.locator("body img")
    deadline = 30
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
            f"<figure style='margin:0;text-align:center;line-height:0'>"
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
