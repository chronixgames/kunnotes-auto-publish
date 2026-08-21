import base64, hashlib, json, os, random, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import feedparser
from openai import OpenAI
from publisher import publish

KST = ZoneInfo("Asia/Seoul")
BLOG = os.getenv("TISTORY_BLOG_NAME", "kunnotes")
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
WINDOWS = [("morning", 7, 30, 10, 0), ("lunch", 11, 30, 14, 30), ("evening", 18, 0, 22, 0)]


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
    prompt = '''한국 재테크/투자 블로그의 오늘 소재 3개를 선정하라. 최신성, 투자자 관심도, 서로 다른 주제라는 조건을 우선한다. 동일 뉴스의 반복은 제외한다. JSON 배열로 title, angle, source_url을 반환하라.'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt + "\n\n자료:\n" + payload)
    text = r.output_text
    return json.loads(text[text.find("["):text.rfind("]") + 1])[:3]


def article(topic):
    client = OpenAI()
    prompt = f'''너는 한국어 금융·경제·재테크 블로그의 전문 편집자다. 아래 소재를 바탕으로 검색 유입을 고려한 독창적인 정보형 글을 작성한다.

소재: {json.dumps(topic, ensure_ascii=False)}

반드시 지켜라.
- 본문은 약 3,000~3,500자 분량
- 검색자가 실제로 궁금해하는 내용을 중심으로 작성
- 자연스러운 SEO 제목 1개
- 제목 직후 핵심 요약 문단
- 소제목 4~6개를 <h2>로 작성
- 각 소제목 아래 2~4개의 <p> 문단
- 필요한 경우 표는 <table> HTML로 작성
- 단순 뉴스 복사/번역이 아니라 한국 투자자가 이해하기 쉽게 배경과 의미를 설명
- 뉴스 사실과 해석을 명확히 구분
- 확인되지 않은 숫자·인용·수익률을 만들지 말 것
- 투자 조언처럼 단정하지 말고 위험요인과 확인사항도 설명
- 계산 예시는 '가정'이라고 명시
- 본문 안에 이미지가 들어갈 위치를 <p><!--IMAGE1--></p>, <p><!--IMAGE2--></p>, <p><!--IMAGE3--></p> 순서로 3곳 표시
- 글 마지막에는 <h2>핵심 정리</h2>를 넣고 핵심 내용을 정리
- 마지막에 정확히 10개의 해시태그를 한 줄에 작성. 각각 #으로 시작
- '테스트', '테스트용', '샘플', '시험' 같은 표현은 절대 사용하지 말 것
- HTML 본문만 body에 넣고, body 안에 마크다운을 사용하지 말 것
- JSON으로 title, body, tags를 반환. tags는 # 없이 10개 문자열 배열
'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt)
    text = r.output_text
    post = json.loads(text[text.find("{"):text.rfind("}") + 1])
    post["body"] = add_images(post["body"], IMAGE_URLS, IMAGE_CREDITS)
    tags = [str(t).lstrip("#").strip() for t in post.get("tags", [])][:10]
    while len(tags) < 10:
        defaults = ["재테크", "투자", "배당투자", "주식투자", "현금흐름", "자산관리", "경제공부", "투자전략", "재테크정보", "금융정보"]
        candidate = defaults[len(tags)]
        if candidate not in tags:
            tags.append(candidate)
    post["tags"] = tags
    hashtag_line = " ".join(f"#{t}" for t in tags)
    if hashtag_line not in post["body"]:
        post["body"] += f"<p><strong>관련 해시태그</strong><br>{hashtag_line}</p>"
    return post


def add_images(body, urls, credits):
    if not urls:
        return body.replace("<!--IMAGE1-->", "").replace("<!--IMAGE2-->", "").replace("<!--IMAGE3-->", "")
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
    items = fetch_items()
    topics = choose_topics(items) if not FORCE_TOPIC else []

    try:
        index = int(POST_INDEX)
    except ValueError:
        index = 0

    if FORCE_TOPIC:
        topic = {"title": FORCE_TOPIC, "angle": "한국 투자자 관점의 실전형 재테크 가이드", "source_url": ""}
    else:
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
        result_url = publish({"title": output_post["title"], "body": output_post["body"]})
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
