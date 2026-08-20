import base64, hashlib, json, os, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import feedparser
from openai import OpenAI

KST = ZoneInfo("Asia/Seoul")
BLOG = os.getenv("TISTORY_BLOG_NAME", "kunnotes")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
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
    prompt = f'''너는 한국어 금융·경제 블로그 편집자다. 아래 소재를 바탕으로 사실관계를 과장하지 않고 약 3000자 분량의 독창적인 정보형 글을 작성한다.

소재: {json.dumps(topic, ensure_ascii=False)}

규칙:
- 검색 유입을 고려한 자연스러운 제목 1개
- 첫 문단에 핵심 요약
- 소제목 4~6개
- 뉴스 사실과 해석을 명확히 구분
- 투자 조언처럼 단정하지 말 것
- 확인되지 않은 수치/인용을 만들지 말 것
- 마지막에 '핵심 정리'와 관련 태그 8개
- 출처 URL을 본문 마지막에 표시
- 한국 독자가 읽기 편한 자연스러운 문체
JSON으로 title, body, tags를 반환'''
    r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt)
    text = r.output_text
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


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
    topics = choose_topics(items)
    output = []
    for topic, window in zip(topics, WINDOWS):
        post = article(topic)
        slot = random_slot(now.date(), window)
        output.append({"slot_kst": slot.isoformat(), "title": post["title"], "tags": post["tags"], "body": post["body"], "source": topic["source_url"]})
    os.makedirs("out", exist_ok=True)
    with open("out/today.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(), "dry_run": DRY_RUN, "posts": output}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"generated_at": now.isoformat(), "dry_run": DRY_RUN, "posts": [{"slot_kst": x["slot_kst"], "title": x["title"]} for x in output]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
