import hashlib, json, os, random, re, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import feedparser
from openai import OpenAI
from publisher import publish

KST = ZoneInfo("Asia/Seoul")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
POST_INDEX = os.getenv("POST_INDEX", "0")
FORCE_TOPIC = os.getenv("FORCE_TOPIC", "").strip()
IMAGE_URLS = [u.strip() for u in os.getenv("IMAGE_URLS", "").split(",") if u.strip()]
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
FEEDS = [
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
]
WINDOWS = [("morning", 8, 0, 9, 0), ("lunch", 12, 0, 15, 0), ("evening", 21, 0, 23, 0)]


def fetch_items():
    items = []
    for url in FEEDS:
        feed = feedparser.parse(url)
        for e in feed.entries[:12]:
            title = e.get("title", "").strip()
            link = e.get("link", "").strip()
            summary = e.get("summary", "").strip()
            if title and link:
                items.append({"title": title, "link": link, "summary": summary})
    return items


def choose_topics(items):
    client = OpenAI()
    payload = json.dumps(items[:30], ensure_ascii=False)
    prompt = '''한국의 금융·경제·재테크 블로그 'kunnotes'에 오늘 발행할 소재 3개를 선정하라. 최신성, 검색 수요, 투자자 관심도, 서로 다른 카테고리라는 조건을 우선한다. 아래 3개 카테고리를 하루에 하나씩 배정한다: 투자·금융·재테크 인사이트 / 부동산 인사이트 / 최신뉴스. 동일 뉴스의 반복은 제외한다. JSON 배열로 category, title, angle, source_url을 반환하라.'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt + "\n\n자료:\n" + payload)
    text = r.output_text
    return json.loads(text[text.find("["):text.rfind("]") + 1])[:3]


def article(topic):
    client = OpenAI()
    prompt = f'''너는 한국어 금융·경제·재테크 블로그 'kunnotes'의 전문 편집자다. 아래 최신 뉴스 소재를 바탕으로 검색 유입을 고려한 독창적인 정보형 글을 작성한다.

소재: {json.dumps(topic, ensure_ascii=False)}

반드시 지켜라.
- 본문은 약 1,500~2,000자 분량
- 포스팅 스타일은 정보형 블로그이며, 딱딱한 뉴스 기사처럼 쓰지 말고 일반 투자자가 이해하기 쉽게 설명
- 검색자가 실제로 궁금해하는 내용을 중심으로 구체적인 SEO 제목 1개 작성
- 제목 바로 아래에는 반드시 아래와 같은 '핵심 요약' HTML 박스를 만들 것. 이 형식과 이모지를 유지하되 내용은 글의 실제 핵심으로 바꿀 것.
  <div style="margin:24px 0;padding:24px 22px;border:1px solid #cfe0ff;border-radius:18px;background:#f8fbff;line-height:1.8;">
    <div style="font-size:22px;font-weight:700;color:#1565c0;margin-bottom:14px;">📌 이번 포스팅 핵심 요약</div>
    <div style="margin:7px 0;">✅ 핵심 내용 1</div>
    <div style="margin:7px 0;">✅ 핵심 내용 2</div>
    <div style="margin:7px 0;">✅ 핵심 내용 3</div>
    <div style="margin:7px 0;">✅ 핵심 내용 4</div>
  </div>
- 핵심 요약은 4개 항목을 권장하고, 각 항목은 한 문장으로 짧고 명확하게 작성
- 핵심 요약의 각 항목은 '가능', '활용됨', '있음', '확인 필요'처럼 짧게 끝내고 긴 서술형 문장을 피할 것
- 이후 번호가 붙은 <h2> 소제목 4~6개로 구성
- 각 소제목 아래 2~4개의 짧은 <p> 문단을 사용하고 line-height:1.8 수준으로 읽기 편하게 구성
- 필요하면 비교·계산·전망을 <table> HTML로 정리하되, 모든 표의 헤더와 본문 셀은 가운데 정렬한다. 표 전체는 width:100%; border-collapse:collapse;로 만들고, th/td에 padding:11px 10px; line-height:1.6; text-align:center; vertical-align:middle;을 동일하게 적용한다.
- 표 안의 숫자와 텍스트는 좌우·상하 가운데 정렬로 통일해 줄간격과 위치가 어긋나지 않게 한다.
- 표는 가로 스크롤 없이 모바일에서도 읽기 좋게 구성하고, 핵심 수치나 결론은 굵게 표시
- 중요한 수치, 결론, 주의사항은 파란색·주황색·빨간색 등을 활용한 인라인 강조나 박스형 HTML로 시각화하되 과도하게 사용하지 말 것
- 주의 박스를 사용할 경우 같은 컬러 박스 안에서 반드시 첫 줄에 '[주의]'를 단독으로 배치하고, 실제 주의 내용은 그 바로 아래 줄에 배치
- 소제목은 왼쪽 세로선을 활용해 구분감 있게 작성하고, 전체적으로 깔끔한 정보형 블로그 디자인을 유지
- 표식/강조 박스 안에는 이미지를 절대 넣지 말 것. 표식 안의 문구는 짧고 간결하게 작성
- 전문용어는 처음 나올 때 쉬운 말로 풀어서 설명
- 단순 뉴스 복사/번역이 아니라 '뉴스 → 의미 → 투자자에게 미치는 영향 → 실제 대응' 순서로 설명
- 뉴스에서 확인된 사실과 작성자의 해석을 명확히 구분
- 확인되지 않은 숫자·인용·수익률을 만들지 말 것
- 확실하지 않은 내용은 '~로 알려졌다', '~할 가능성이 있다', '향후 논의에 따라 달라질 수 있다'처럼 표현
- 투자 조언처럼 단정하지 말고 위험요인과 확인사항도 함께 설명
- 계산 예시는 반드시 '가정'이라고 표시
- 본문 안에는 관련 이미지 위치를 <p><!--IMAGE1--></p>부터 <p><!--IMAGE5--></p>까지 순서대로 최대 5곳 표시한다. IMAGE1은 반드시 제목과 핵심 요약 박스 바로 뒤의 가장 위쪽 이미지 위치에 둔다. 나머지는 서로 다른 소제목 사이에 자연스럽게 배치한다.
- 이미지 위치의 앞뒤에는 불필요한 빈 줄이나 여백을 만들지 말 것
- 마지막에는 정확히 <h2>포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리
- 참고자료 영역은 만들지 말 것
- 마지막에 정확한 면책 문구를 넣기: <p><em>※ 본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>
- 본문에는 해시태그를 절대 넣지 말 것. 해시태그는 Tistory 태그 영역에 별도로 등록한다.
- 태그는 #과 콤마(,)를 포함하지 않은 순수 문자열 10개를 반환한다.
- '테스트', '테스트용', '샘플', '시험' 같은 표현은 절대 사용하지 말 것
- 이미지 하단에 사진작가·출처·Pexels·Pixabay 등의 영문 크레딧 문구를 본문에 넣지 말 것
- HTML 본문만 body에 넣고 body 안에 마크다운을 사용하지 말 것
- JSON으로 title, body, tags, image_keywords를 반환. tags는 #과 콤마 없이 정확히 10개의 문자열 배열. image_keywords는 본문 주제에 맞는 구체적인 영어 검색어 3~5개 배열
'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt)
    text = r.output_text
    post = json.loads(text[text.find("{"):text.rfind("}") + 1])

    image_paths = fetch_pixabay_images(post.get("image_keywords", []), post.get("title", topic.get("title", "")))
    if not image_paths and IMAGE_URLS:
        post["body"] = add_images(post["body"], IMAGE_URLS)
        post["image_paths"] = []
    else:
        post["image_paths"] = image_paths

    tags = normalize_tags(post.get("tags", []))
    defaults = ["재테크", "투자", "경제뉴스", "주식투자", "ETF", "자산관리", "투자전략", "금융정보", "경제공부", "재테크정보"]
    for candidate in defaults:
        if len(tags) >= 10:
            break
        if candidate not in tags:
            tags.append(candidate)
    post["tags"] = tags[:10]
    return post


def normalize_tags(raw_tags):
    tags = []
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[,，|\n]+", raw_tags)
    for raw in raw_tags or []:
        for part in re.split(r"[,，|\n]+", str(raw)):
            tag = part.strip().lstrip("#").strip().replace(",", "").replace("，", "")
            if tag and tag not in tags:
                tags.append(tag)
    return tags[:10]


def _safe_filename(text):
    text = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text).strip("-")
    return text[:60] or "kunnotes-image"


def fetch_pixabay_images(keywords, title):
    if not PIXABAY_API_KEY:
        print("PIXABAY_API_KEY is not configured; no automatic Pixabay images will be used.")
        return []

    query_parts = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    if not query_parts:
        query_parts = [title]

    target_count = random.randint(3, 5)
    out_dir = Path("out/images")
    out_dir.mkdir(parents=True, exist_ok=True)
    hits = []
    used_ids = set()

    try:
        for keyword in query_parts[:5]:
            params = urlencode({
                "key": PIXABAY_API_KEY,
                "q": keyword[:100],
                "lang": "en",
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "order": random.choice(["popular", "latest"]),
                "page": random.randint(1, 3),
                "per_page": 20,
            })
            req = Request("https://pixabay.com/api/?" + params, headers={"User-Agent": "kunnotes-auto-publish/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            keyword_hits = [h for h in data.get("hits", []) if h.get("largeImageURL") and h.get("id") not in used_ids]
            random.shuffle(keyword_hits)
            for hit in keyword_hits:
                hits.append(hit)
                used_ids.add(hit.get("id"))
                if len(hits) >= target_count:
                    break
            if len(hits) >= target_count:
                break

        if len(hits) < target_count:
            params = urlencode({
                "key": PIXABAY_API_KEY,
                "q": title[:100],
                "lang": "en",
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "order": "latest",
                "per_page": 30,
            })
            req = Request("https://pixabay.com/api/?" + params, headers={"User-Agent": "kunnotes-auto-publish/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            extra = [h for h in data.get("hits", []) if h.get("largeImageURL") and h.get("id") not in used_ids]
            random.shuffle(extra)
            hits.extend(extra[:target_count - len(hits)])

        if not hits:
            return []

        paths = []
        for index, hit in enumerate(hits[:target_count], 1):
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


def add_images(body, urls):
    out = body
    for i, url in enumerate(urls[:5], 1):
        img = f"<figure style='margin:0;padding:0;text-align:center;line-height:0'><img src='{url}' alt='본문 주제 관련 이미지' style='display:block;width:100%;max-width:900px;height:auto;margin:0 auto;border-radius:8px;' /></figure>"
        placeholder = f"<p><!--IMAGE{i}--></p>"
        out = out.replace(placeholder, img, 1)
        out = out.replace(f"<!--IMAGE{i}-->", img, 1)
    for i in range(len(urls[:5]) + 1, 6):
        out = out.replace(f"<p><!--IMAGE{i}--></p>", "", 1)
        out = out.replace(f"<!--IMAGE{i}-->", "", 1)
    return out


def wait_for_random_slot(day, window):
    _, sh, sm, eh, em = window
    start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=KST)
    end = datetime(day.year, day.month, day.day, eh, em, tzinfo=KST)
    seconds = int((end - start).total_seconds())
    target = start + timedelta(seconds=random.SystemRandom().randint(0, seconds))
    now = datetime.now(KST)
    delay = (target - now).total_seconds()
    if delay > 0:
        print(f"WAITING_FOR_RANDOM_SLOT={target.isoformat()}")
        time.sleep(delay)
    actual = datetime.now(KST)
    return target if actual <= end + timedelta(minutes=5) else actual


def main():
    now = datetime.now(KST)
    if FORCE_TOPIC:
        topic = {"title": FORCE_TOPIC, "angle": "한국 투자자 관점의 실전형 금융·재테크 분석", "source_url": ""}
        index = 0
    else:
        items = fetch_items()
        topics = choose_topics(items)
        try:
            index = int(POST_INDEX)
        except ValueError:
            index = 0
        if index < 0 or index >= len(topics):
            raise RuntimeError(f"POST_INDEX must be 0, 1, or 2; got {POST_INDEX}")
        topic = topics[index]
        wait_for_random_slot(now.date(), WINDOWS[index])

    post = article(topic)
    slot = datetime.now(KST)
    output_post = {
        "slot_kst": slot.isoformat(),
        "title": post["title"],
        "tags": post["tags"],
        "body": post["body"],
        "source": topic.get("source_url", ""),
        "image_paths": post.get("image_paths", []),
    }

    if not DRY_RUN:
        result_url = publish({"title": output_post["title"], "body": output_post["body"], "tags": output_post["tags"], "image_paths": output_post["image_paths"]})
        output_post["published_url"] = result_url
        print("PUBLISHED=true")
        print(f"PUBLISH_RESULT_URL={result_url}")
    else:
        print("PUBLISHED=false (DRY_RUN)")

    os.makedirs("out", exist_ok=True)
    with open("out/today.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(), "dry_run": DRY_RUN, "posts": [output_post]}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"generated_at": now.isoformat(), "dry_run": DRY_RUN, "post_index": index, "title": output_post["title"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
