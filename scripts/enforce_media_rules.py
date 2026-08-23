from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# Final article cleanup: no closing section, no disclaimer, exactly 3 topic images.
start = text.find("def normalize_generated_body(body):")
end = text.find("\ndef normalize_tags(raw_tags):", start)
if start == -1 or end == -1:
    raise SystemExit("normalize_generated_body function not found")

normalizer = r'''def normalize_generated_body(body):
    body = body or ""

    # Remove tables and all old image placeholders before placing clean image slots.
    body = re.sub(r"<table\b.*?</table>", "", body, flags=re.I | re.S)
    body = re.sub(r"<!--IMAGE[1-5]-->", "", body, flags=re.I)

    # Remove all closing/disclaimer/reference material requested by the editor.
    body = re.sub(r"<h[1-6][^>]*>\s*(?:📌\s*)?(?:포스팅을\s*마치며\.\.\.|핵심\s*정리|마무리|정리)\s*</h[1-6]>.*$", "", body, flags=re.I | re.S)
    body = re.sub(r"<p[^>]*>.*?(?:포스팅을\s*마치며\.\.\.|핵심 내용을 다시 확인하고 자신의 투자 상황에 맞는 대응 전략을 점검해보세요\.).*?</p>", "", body, flags=re.I | re.S)
    body = re.sub(r"<p[^>]*>.*?본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다\..*?</p>", "", body, flags=re.I | re.S)
    body = re.sub(r"<h[1-6][^>]*>\s*참고자료\s*</h[1-6]>.*$", "", body, flags=re.I | re.S)
    body = re.sub(r"(?:※\s*)?본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다\.", "", body, flags=re.I)

    # Insert exactly three image slots at safe boundaries.
    sections = re.split(r"(?=<h2\b)", body, flags=re.I)
    if sections:
        sections[0] = sections[0].rstrip() + "<!--IMAGE1-->"
        placed = 1
        for i in range(1, len(sections)):
            if placed >= 3:
                break
            heading = re.search(r"<h2\b[^>]*>(.*?)</h2>", sections[i], flags=re.I | re.S)
            if heading and any(word in re.sub(r"<[^>]+>", "", heading.group(1)) for word in ("포스팅을 마치며", "핵심 정리", "마무리")):
                continue
            placed += 1
            sections[i] = sections[i].rstrip() + f"<!--IMAGE{placed}-->"
        body = "".join(sections)

    return body.strip()
'''
text = text[:start] + normalizer + text[end:]

# Replace the image search function with a strict relevance-first implementation.
start = text.find("def fetch_pixabay_images(keywords, title):")
end = text.find("\ndef add_images(body, urls):", start)
if start == -1 or end == -1:
    raise SystemExit("fetch_pixabay_images function boundaries not found")

image_fn = r'''def fetch_pixabay_images(keywords, title):
    if not PIXABAY_API_KEY:
        print("PIXABAY_API_KEY is not configured; no automatic Pixabay images will be used.")
        return []

    banned = {"marketing", "business", "shopping", "travel", "tourism", "lifestyle", "fashion", "people", "teamwork", "success"}
    raw = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    query_parts = [k for k in raw if not any(b in k.lower() for b in banned)]
    query_parts += [
        f"{title} finance investment",
        "inflation tax investment strategy",
        "investment portfolio financial planning",
    ]

    target_count = 3
    out_dir = Path("out/images")
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    used_ids = set()
    finance_terms = {
        "finance", "financial", "investment", "investing", "investor", "money", "economy",
        "economic", "inflation", "tax", "taxes", "portfolio", "stock", "stocks", "market",
        "interest", "rate", "bond", "wealth", "saving", "savings", "bank", "fund", "etf",
    }

    def score_hit(hit, query):
        tags = str(hit.get("tags", "")).lower()
        page_url = str(hit.get("pageURL", "")).lower()
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3 and t not in banned]
        haystack = f"{tags} {page_url}"
        query_score = sum(1 for token in tokens if token in haystack)
        finance_score = sum(1 for token in finance_terms if token in haystack)
        # Reject generic stock-photo results with no financial signal.
        if finance_score < 1:
            return -1
        return query_score * 3 + finance_score

    try:
        for keyword in query_parts[:6]:
            params = urlencode({
                "key": PIXABAY_API_KEY,
                "q": keyword[:100],
                "lang": "en",
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "order": "popular",
                "per_page": 30,
            })
            req = Request("https://pixabay.com/api/?" + params, headers={"User-Agent": "kunnotes-auto-publish/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ranked = []
            for hit in data.get("hits", []):
                if not hit.get("largeImageURL") or hit.get("id") in used_ids:
                    continue
                score = score_hit(hit, keyword)
                if score >= 1:
                    ranked.append((score, random.random(), hit))
            ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
            for _, _, hit in ranked:
                candidates.append(hit)
                used_ids.add(hit.get("id"))
                if len(candidates) >= target_count:
                    break
            if len(candidates) >= target_count:
                break

        if len(candidates) < target_count:
            print(f"PIXABAY_RELEVANT_IMAGES_ONLY={len(candidates)}")
        if not candidates:
            return []

        paths = []
        for index, hit in enumerate(candidates[:target_count], 1):
            filename = out_dir / f"{index:02d}-{_safe_filename(title)}-{hit.get('id', index)}.jpg"
            req_img = Request(hit["largeImageURL"], headers={"User-Agent": "kunnotes-auto-publish/1.0"})
            with urlopen(req_img, timeout=45) as resp:
                filename.write_bytes(resp.read())
            paths.append(str(filename))
        print(f"PIXABAY_IMAGES_SELECTED={len(paths)}")
        return paths
    except Exception as exc:
        print(f"PIXABAY_IMAGE_ERROR={exc}")
        return []
'''
text = text[:start] + image_fn + text[end:]

# Make the generated post request exactly three images.
text = text.replace("<!--IMAGE1-->부터 <p><!--IMAGE5--></p>까지 순서대로 최대 5곳", "<!--IMAGE1-->부터 <!--IMAGE3-->까지 순서대로 정확히 3곳")
text = text.replace("<!--IMAGE1-->부터 <!--IMAGE5-->까지 표시한다", "<!--IMAGE1-->부터 <!--IMAGE3-->까지 표시한다")
text = text.replace("최대 5곳", "정확히 3곳")
text = text.replace("image_keywords는 본문 주제에 맞는 구체적인 영어 검색어 3~5개 배열", "image_keywords는 본문 주제에 맞는 구체적인 영어 검색어 3~5개 배열")

path.write_text(text, encoding="utf-8")
print("Enforced: no closing section/disclaimer, exactly 3 relevant finance images")
