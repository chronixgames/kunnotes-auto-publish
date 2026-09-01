import os
import random
import time
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import reserve_month as base
from publisher import _load_state
from playwright.sync_api import sync_playwright

KST = ZoneInfo("Asia/Seoul")
DAYS = int(os.environ.get("RESERVE_DAYS", "30"))
POSTS_PER_DAY = 2
START_DATE = datetime(2026, 9, 13, tzinfo=KST).date()
ANCHOR_TITLE = "9/12 배당주 투자 체크리스트 6가지: 배당수익률 함정 피하고 ‘지속가능한 배당’ 고르는 법"
IMAGE_STATE_PATH = Path("data/used_pixabay_image_ids.json")


def _load_used_image_ids():
    if not IMAGE_STATE_PATH.exists():
        return set()
    try:
        data = json.loads(IMAGE_STATE_PATH.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("pixabay_ids", []) if str(x).strip()}
    except Exception as exc:
        raise RuntimeError(f"Invalid image state file: {exc}")


_USED_IMAGE_IDS = _load_used_image_ids()
_ORIGINAL_FETCH_IMAGES = base.main.fetch_pixabay_images


def _image_id(path):
    match = re.search(r"-(\d+)\.jpg$", str(path), re.I)
    return match.group(1) if match else None


def _save_used_image_ids():
    IMAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_STATE_PATH.write_text(
        json.dumps({"pixabay_ids": sorted(_USED_IMAGE_IDS), "updated_at": datetime.now(KST).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_unique_pixabay_images(keywords, title):
    """Prevent Pixabay image-ID reuse across this run and future runs."""
    for attempt in range(12):
        retry_title = title if attempt == 0 else f"{title} image batch {attempt + 1}"
        candidates = _ORIGINAL_FETCH_IMAGES(keywords, retry_title) or []
        fresh = []
        candidate_ids = set()
        for path in candidates:
            image_id = _image_id(path)
            if not image_id or image_id in _USED_IMAGE_IDS or image_id in candidate_ids:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            candidate_ids.add(image_id)
            fresh.append(path)
        if len(fresh) >= 3:
            _USED_IMAGE_IDS.update(candidate_ids)
            _save_used_image_ids()
            print(f"UNIQUE_IMAGES_OK={len(fresh[:5])}|ids={','.join(sorted(candidate_ids))}")
            return fresh[:5]
        for path in fresh:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        print(f"DUPLICATE_IMAGE_RETRY={attempt + 1}")
    raise RuntimeError("Could not obtain at least 3 unused Pixabay images after 12 attempts")


base.main.fetch_pixabay_images = fetch_unique_pixabay_images


def build_random_schedule(days: int):
    """Two daily slots, 08:00-08:59 and 15:00-15:59, with unique minutes."""
    total = days * POSTS_PER_DAY
    if total > 60:
        raise RuntimeError("Unique-minute schedule supports at most 60 posts per batch")
    minutes = list(range(60))
    random.SystemRandom().shuffle(minutes)
    schedule = []
    for day in range(days):
        d = START_DATE + timedelta(days=day)
        schedule.append(datetime(d.year, d.month, d.day, 8, minutes[day * 2], tzinfo=KST))
        schedule.append(datetime(d.year, d.month, d.day, 15, minutes[day * 2 + 1], tzinfo=KST))
    return schedule


def build_topics():
    """Generate 60 topics explicitly continuing after the 9/12 anchor."""
    try:
        items = base.main.fetch_items()
        from openai import OpenAI
        client = OpenAI()
        prompt = '''한국어 금융·경제·재테크 블로그 kunnotes의 9/13~10/12 예약발행 소재 60개를 만든다.
기준점은 이미 발행/예약된 다음 글이다:
「9/12 배당주 투자 체크리스트 6가지: 배당수익률 함정 피하고 ‘지속가능한 배당’ 고르는 법」
이 글을 다시 만들지 말고, 그 다음 편부터 자연스럽게 이어지는 시리즈처럼 구성한다.
총 60개이며 하루 2개, 첫 번째는 투자·금융·재테크, 두 번째는 부동산·대출·금리·자산관리다.
같은 제목·같은 핵심 주제 반복 금지. 앞부분은 최신 금융 뉴스에서 확장하되 단기 뉴스에 종속되지 않는 검색형 제목으로 만들고, 나머지는 evergreen 소재로 구성한다.
배당주 다음 흐름으로 배당성장, 현금흐름, ETF, ISA/IRP, 미국주식, 금리·환율, 부동산·대출 등으로 자연스럽게 확장한다.
각 항목은 category, title, angle, source_url 필드를 가진다. title에는 확인되지 않은 숫자나 단정적인 전망을 넣지 않는다.
JSON 배열만 반환한다.'''
        payload = json.dumps(items[:36], ensure_ascii=False)
        r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt + "\n\n최신 자료:\n" + payload)
        text = r.output_text
        candidate = json.loads(text[text.find("["):text.rfind("]") + 1])
        topics = []
        seen = set()
        for t in candidate:
            title = str(t.get("title", "")).strip()
            category = str(t.get("category", "")).strip()
            if title and category and title != ANCHOR_TITLE and title not in seen:
                topics.append(t)
                seen.add(title)
            if len(topics) >= 60:
                break
        if len(topics) >= 60:
            print(f"TOPIC_ANCHOR={ANCHOR_TITLE}")
            print("TOPIC_PLAN=60 posts continuing after anchor")
            return topics[:60]
        print(f"TOPIC_GENERATION_SHORT={len(topics)}; using deterministic fallback")
    except Exception as exc:
        print(f"TOPIC_GENERATION_FALLBACK={type(exc).__name__}: {exc}")

    fallback = []
    for i in range(30):
        fallback.append({"category": "투자·금융·재테크 인사이트", "title": base.INVESTMENT_TOPICS[i], "angle": "9/12 배당주 글 이후 투자자가 실제 판단에 활용할 수 있는 핵심 기준을 설명", "source_url": ""})
        fallback.append({"category": "부동산·대출 인사이트", "title": base.REAL_ESTATE_TOPICS[i], "angle": "금리·대출·주거비와 자산관리 관점에서 실제 판단 기준을 설명", "source_url": ""})
    return fallback[:60]


def main_reserve():
    state_path = _load_state()
    topics = build_topics()
    planned = DAYS * POSTS_PER_DAY
    if len(topics) < planned:
        raise RuntimeError(f"Only {len(topics)} unique topics prepared; refusing partial month reservation")
    schedule = build_random_schedule(DAYS)
    print(f"RESERVATION_PLAN={len(schedule)} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")
    print(f"RESERVATION_RULE=after {START_DATE - timedelta(days=1)} existing posts")
    print("TIME_RULE=08:00-08:59 and 15:00-15:59; every minute unique across all 60 posts")
    print(f"IMAGE_RULE=persistent Pixabay image IDs; current state count={len(_USED_IMAGE_IDS)}")

    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        try:
            for idx, (topic, when) in enumerate(zip(topics, schedule), start=1):
                print(f"[{idx}/{planned}] target={when.isoformat()} topic={topic['title']}")
                try:
                    post = base.main.article(topic)
                    base.reserve_one(page, post, when)
                    time.sleep(1.5)
                except Exception as exc:
                    failures.append({"index": idx, "when": when.isoformat(), "title": topic.get("title", ""), "error": str(exc)})
                    print(f"RESERVE_FAILED={idx}|{type(exc).__name__}|{exc}")
                    if "TISTORY_SESSION_EXPIRED" in str(exc):
                        break
        finally:
            browser.close()

    _save_used_image_ids()
    Path("out").mkdir(parents=True, exist_ok=True)
    Path("out/month-reservation-result.json").write_text(json.dumps({
        "planned": planned,
        "failed": failures,
        "completed": planned - len(failures),
        "first": schedule[0].isoformat(),
        "last": schedule[-1].isoformat(),
        "start_date": START_DATE.isoformat(),
        "anchor_title": ANCHOR_TITLE,
        "randomized_times": True,
        "unique_minutes": True,
        "morning_window": "08:00-08:59",
        "afternoon_window": "15:00-15:59",
        "persistent_unique_pixabay_image_ids": True,
        "tracked_image_id_count": len(_USED_IMAGE_IDS),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"Month reservation completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    main_reserve()
