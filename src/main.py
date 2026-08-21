import hashlib, json, os, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import feedparser
from openai import OpenAI
from publisher import publish

KST = ZoneInfo("Asia/Seoul")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
POST_INDEX = os.getenv("POST_INDEX", "0")
FORCE_TOPIC = os.getenv("FORCE_TOPIC", "").strip()
IMAGE_URLS = [u.strip() for u in os.getenv("IMAGE_URLS", "").split(",") if u.strip()]
IMAGE_CREDITS = [c.strip() for c in os.getenv("IMAGE_CREDITS", "").split("|") if c.strip()]
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
- 제목 바로 아래 '핵심요약' 영역을 만들고 불릿 3~5개로 요점 압축
- 이후 번호가 붙은 <h2> 소제목 4~6개로 구성
- 각 소제목 아래 2~4개의 짧은 <p> 문단을 사용
- 필요하면 비교·계산·전망을 <table> HTML로 정리
- 중간에 핵심 포인트를 1~2개의 박스형 HTML 영역으로 강조할 수 있음. 이모지는 사용하지 않거나 전체 글에서 최대 1개만 사용
- 전문용어는 처음 나올 때 쉬운 말로 풀어서 설명
- 단순 뉴스 복사/번역이 아니라 '뉴스 → 의미 → 투자자에게 미치는 영향 → 실제 대응' 순서로 설명
- 뉴스에서 확인된 사실과 작성자의 해석을 명확히 구분
- 확인되지 않은 숫자·인용·수익률을 만들지 말 것
- 확실하지 않은 내용은 '~로 알려졌다', '~할 가능성이 있다', '향후 논의에 따라 달라질 수 있다'처럼 표현
- 투자 조언처럼 단정하지 말고 위험요인과 확인사항도 함께 설명
- 계산 예시는 반드시 '가정'이라고 표시
- 본문 안에 관련 이미지가 들어갈 위치를 <p><!--IMAGE1--></p>, <p><!--IMAGE2--></p>, <p><!--IMAGE3--></p> 순서로 최대 3곳 표시
- 마지막에는 <h2>핵심 정리</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리
- 그 다음 '참고자료' 영역을 만들고 실제 사용한 기사/기관 출처를 링크 형태로 1~3개 표기. 출처가 제공되지 않았다면 임의의 URL을 만들지 말고 '관련 공식자료 확인 필요'라고 적기
- 마지막에 정확한 면책 문구를 넣기: <p><em>본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>
- 본문에는 해시태그를 절대 넣지 말 것. 해시태그는 Tistory 태그 영역에 별도로 등록한다.
- '테스트', '테스트용', '샘플', '시험' 같은 표현은 절대 사용하지 말 것
- HTML 본문만 body에 넣고 body 안에 마크다운을 사용하지 말 것
- JSON으로 title, body, tags를 반환. tags는 # 없이 정확히 10개의 문자열 배열
'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt)
    text = r.output_text
    post = json.loads(text[text.find("{"):text.rfind("}") + 1])
    post["body"] = add_images(post["body"], IMAGE_URLS, IMAGE_CREDITS)
    tags = [str(t).lstrip("#").strip() for t in post.get("tags", []) if str(t).strip()][:10]
    defaults = ["재테크", "투자", "경제뉴스", "주식투자", "ETF", "자산관리", "투자전략", "금융정보", "경제공부", "재테크정보"]
    for candidate in defaults:
        if len(tags) >= 10:
            break
        if candidate not in tags:
            tags.append(candidate)
    post["tags"] = tags[:10]
    return post


def add_images(body, urls, credits):
    out = body
    for i, url in enumerate(urls[:3], 1):
        credit = credits[i - 1] if i - 1 < len(credits) else ""
        caption = f"<p style='text-align:center;font-size:12px;color:#888'>{credit}</p>" if credit else ""
        img = f"<figure style='margin:28px 0;text-align:center'><img src='{url}' alt='재테크와 투자 관련 이미지' style='max-width:100%;height:auto;' />{caption}</figure>"
        out = out.replace(f"<!--IMAGE{i}-->", img, 1)
    for i in range(len(urls[:3]) + 1, 4):
        out = out.replace(f"<!--IMAGE{i}-->", "")
    return out


def random_slot(day, window):
    _, sh, sm, eh, em = window
    start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=KST)
    end = datetime(day.year, day.month, day.day, eh, em, tzinfo=KST)
    seconds = int((end - start).total_seconds())
    seed = int(hashlib.sha256(f"{day.isoformat()}-{window[0]}".encode()).hexdigest()[:8], 16)
    return start + timedelta(seconds=random.Random(seed).randint(0, seconds))


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

    post = article(topic)
    slot = random_slot(now.date(), WINDOWS[index])
    output_post = {
        "slot_kst": slot.isoformat(),
        "title": post["title"],
        "tags": post["tags"],
        "body": post["body"],
        "source": topic.get("source_url", ""),
    }

    if not DRY_RUN:
        result_url = publish({"title": output_post["title"], "body": output_post["body"], "tags": output_post["tags"]})
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
