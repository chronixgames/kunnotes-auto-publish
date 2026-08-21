from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# Keep the generated summary short and checklist-like.
text = text.replace(
    "- 핵심 요약은 4개 항목을 권장하고, 각 항목은 한 문장으로 짧고 명확하게 작성",
    "- 핵심 요약은 4개 항목으로 작성하고, 서술형 문장보다 '가능성 있음', '활용 가능', '확인 필요', '분산 필요'처럼 짧은 명사형·체크형 표현으로 끝낼 것. 각 항목은 12~22자 정도로 간결하게 작성"
)

# Clean caution boxes and prohibit media inside callouts.
text = text.replace(
    "- 중요한 수치, 결론, 주의사항은 파란색·주황색·빨간색 등을 활용한 인라인 강조나 박스형 HTML로 시각화하되 과도하게 사용하지 말 것",
    "- 중요한 수치·결론·주의사항은 색상으로 시각화할 것. 주의 박스는 첫 줄에 정확히 '[주의]'를 단독으로 표시하고 실제 내용은 다음 줄에 배치할 것. 박스 안에는 이미지, 표, 이미지 placeholder를 절대 넣지 말 것"
)

# Put image placeholders only in safe positions and demand topic-specific search terms.
text = text.replace(
    "- 본문 안에는 관련 이미지 위치를 <p><!--IMAGE1--></p>부터 <p><!--IMAGE5--></p>까지 순서대로 최대 5곳 표시한다. IMAGE1은 반드시 제목과 핵심 요약 박스 바로 뒤의 가장 위쪽 이미지 위치에 둔다. 나머지는 서로 다른 소제목 사이에 자연스럽게 배치한다.",
    "- 본문 안에는 관련 이미지 위치를 <!--IMAGE1-->부터 <!--IMAGE5-->까지 표시한다. 이미지 위치는 제목·핵심 요약·표·주의 박스 안에 절대 넣지 말고 일반 본문 문단과 소제목 사이의 독립된 위치에 둔다. IMAGE1은 핵심 요약 박스 바로 뒤에 둔다. 나머지는 서로 다른 소제목 사이에 둔다. image_keywords는 글 주제를 직접 설명하는 구체적인 영어 검색어 3~5개로 작성한다(예: interest rate graph finance, bond market, Bank of Korea building). 관광지·랜드마크 등 주제와 무관한 검색어는 금지한다."
)

# Remove reference section requirement and keep the requested closing heading.
text = text.replace(
    "- 마지막에는 정확히 <h2>포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리\n- 그 다음 '참고자료' 영역을 만들고 실제 사용한 기사/기관 출처를 링크 형태로 1~3개 표기. 출처가 제공되지 않았다면 임의의 URL을 만들지 말고 '관련 공식자료 확인 필요'라고 적기",
    "- 마지막에는 정확히 <h2>포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 2~3문장으로 간결하게 정리\n- 참고자료 영역은 만들지 말 것"
)

# Add deterministic cleanup after the model response is parsed.
parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
if 'post["body"] = normalize_generated_body' not in text:
    if parse_line not in text:
        raise SystemExit("JSON parse line not found")
    text = text.replace(
        parse_line,
        parse_line + '    post["body"] = normalize_generated_body(post.get("body", ""))\n',
        1,
    )

# Add the sanitizer before normalize_tags.
if 'def normalize_generated_body(body):' not in text:
    marker = '\ndef normalize_tags(raw_tags):\n'
    sanitizer = r'''

def normalize_generated_body(body):
    """Remove unsafe placeholder placement and enforce the final article ending."""
    body = body or ""

    # Never leave image placeholders inside tables or visual callout boxes.
    body = re.sub(r"<!--IMAGE[1-5]-->", "", body, flags=re.IGNORECASE)

    # Remove any reference-material section from the generated article.
    body = re.sub(
        r"<h2[^>]*>\s*참고자료\s*</h2>.*?(?=<h2[^>]*>|$)",
        "",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body = re.sub(
        r"<h3[^>]*>\s*참고자료\s*</h3>.*?(?=<h2[^>]*>|<h3[^>]*>|$)",
        "",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Normalize closing heading.
    body = re.sub(
        r"<h2([^>]*)>\s*(?:핵심 정리|마무리|정리)\s*</h2>",
        r"<h2\1>포스팅을 마치며...</h2>",
        body,
        flags=re.IGNORECASE,
    )
    if not re.search(r"<h2[^>]*>\s*포스팅을 마치며\.\.\.\s*</h2>", body, flags=re.IGNORECASE):
        body += "<h2>포스팅을 마치며...</h2><p>핵심 내용을 다시 확인하고 자신의 투자 상황에 맞는 대응 전략을 점검해보세요.</p>"

    if "본 콘텐츠는 정보 제공을 위한 것" not in body:
        body += "<p><em>본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>"

    # Reinsert exactly 3~5 image slots after safe content boundaries.
    sections = re.split(r"(?=<h2\b)", body, flags=re.IGNORECASE)
    if sections:
        sections[0] = sections[0].rstrip() + "<!--IMAGE1-->"
        slot = 2
        for i in range(1, len(sections)):
            if slot > 5:
                break
            # Do not put an image after the final closing section.
            heading = re.search(r"<h2\b[^>]*>(.*?)</h2>", sections[i], flags=re.IGNORECASE | re.DOTALL)
            if heading and "포스팅을 마치며" in re.sub(r"<[^>]+>", "", heading.group(1)):
                continue
            sections[i] = sections[i].rstrip() + f"<!--IMAGE{slot}-->"
            slot += 1
        body = "".join(sections)

    return body
'''
    if marker not in text:
        raise SystemExit("normalize_tags marker not found")
    text = text.replace(marker, sanitizer + marker, 1)

# Replace Pixabay selection with relevance scoring using Pixabay's own tags metadata.
start = text.find("def fetch_pixabay_images(keywords, title):")
end = text.find("\ndef add_images(body, urls):", start)
if start == -1 or end == -1:
    raise SystemExit("Pixabay function boundaries not found")

new_function = r'''def fetch_pixabay_images(keywords, title):
    if not PIXABAY_API_KEY:
        print("PIXABAY_API_KEY is not configured; no automatic Pixabay images will be used.")
        return []

    query_parts = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if not query_parts:
        query_parts = [title]

    target_count = random.randint(3, 5)
    out_dir = Path("out/images")
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    used_ids = set()

    def score_hit(hit, query):
        tags = str(hit.get("tags", "")).lower()
        page_url = str(hit.get("pageURL", "")).lower()
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3]
        haystack = f"{tags} {page_url}"
        score = sum(1 for token in tokens if token in haystack)
        return score if (not tokens or score > 0) else -1

    try:
        for keyword in query_parts[:5]:
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
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

            for _, _, hit in ranked:
                candidates.append(hit)
                used_ids.add(hit.get("id"))
                if len(candidates) >= target_count:
                    break
            if len(candidates) >= target_count:
                break

        # Title-based fallback, still requiring relevance.
        if len(candidates) < target_count:
            params = urlencode({
                "key": PIXABAY_API_KEY,
                "q": title[:100],
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
                score = score_hit(hit, title)
                if score >= 1:
                    ranked.append((score, random.random(), hit))
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            for _, _, hit in ranked:
                candidates.append(hit)
                used_ids.add(hit.get("id"))
                if len(candidates) >= target_count:
                    break

        if not candidates:
            return []

        paths = []
        for index, hit in enumerate(candidates[:target_count], 1):
            image_url = hit["largeImageURL"]
            filename = out_dir / f"{index:02d}-{_safe_filename(title)}-{hit.get('id', index)}.jpg"
            req_img = Request(image_url, headers={"User-Agent": "kunnotes-auto-publish/1.0"})
            with urlopen(req_img, timeout=45) as resp:
                filename.write_bytes(resp.read())
            paths.append(str(filename))
        print(f"PIXABAY_IMAGES_SELECTED={len(paths)}")
        return paths
    except Exception as exc:
        print(f"Pixabay image fetch failed: {exc}")
        return []
'''

text = text[:start] + new_function + text[end:]
path.write_text(text, encoding="utf-8")
print("Applied Kunnotes formatting rules to src/main.py")
