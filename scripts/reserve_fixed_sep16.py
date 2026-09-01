import os
import random
import re
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import reserve_month as base

KST = ZoneInfo("Asia/Seoul")
START_DATE = datetime(2026, 9, 16, tzinfo=KST).date()
END_DATE = datetime(2026, 9, 30, tzinfo=KST).date()
POSTS_PER_DAY = 2
TOTAL_POSTS = ((END_DATE - START_DATE).days + 1) * POSTS_PER_DAY

# Keep Pixabay images unique across every post in this run.
_used_image_ids = set()
_original_fetch_images = base.main.fetch_pixabay_images


def _image_id(path):
    name = Path(path).name
    m = re.search(r"-(\d+)\.jpg$", name, re.I)
    return m.group(1) if m else name


def unique_fetch_pixabay_images(keywords, title):
    for attempt in range(12):
        paths = _original_fetch_images(keywords, title)
        ids = [_image_id(p) for p in paths]
        if paths and len(ids) == len(set(ids)) and not (_used_image_ids & set(ids)):
            _used_image_ids.update(ids)
            print(f"UNIQUE_IMAGES_OK={len(paths)}|ids={','.join(ids)}")
            return paths
        for p in paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        print(f"DUPLICATE_IMAGE_RETRY={attempt + 1}")
    raise RuntimeError("Could not obtain a fully unique image set for this post after 12 attempts")


base.main.fetch_pixabay_images = unique_fetch_pixabay_images


def build_schedule():
    minutes = random.sample(range(60), TOTAL_POSTS)
    schedule = []
    for day_index in range((END_DATE - START_DATE).days + 1):
        d = START_DATE + timedelta(days=day_index)
        schedule.append(datetime(d.year, d.month, d.day, 8, minutes[day_index * 2], tzinfo=KST))
        schedule.append(datetime(d.year, d.month, d.day, 15, minutes[day_index * 2 + 1], tzinfo=KST))
    return schedule


def build_topics():
    topics = base.build_topics()
    anchor = "9/12 배당주 투자 체크리스트 6가지: 배당수익률 함정 피하고 ‘지속가능한 배당’ 고르는 법"
    titles = [str(t.get("title", "")).strip() for t in topics]
    if anchor in titles:
        start = titles.index(anchor) + 1
        topics = topics[start:]
    filtered = [t for t in topics if str(t.get("title", "")).strip() != anchor]
    if len(filtered) < TOTAL_POSTS:
        raise RuntimeError(f"Only {len(filtered)} topics available after anchor; need {TOTAL_POSTS}")
    print(f"TOPIC_ANCHOR={anchor}")
    print(f"TOPIC_PLAN={TOTAL_POSTS} posts starting after anchor")
    return filtered[:TOTAL_POSTS]


def main_reserve():
    state_path = base._load_state()
    topics = build_topics()
    schedule = build_schedule()
    print(f"RESERVATION_PLAN={TOTAL_POSTS} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")
    for i, when in enumerate(schedule, 1):
        print(f"SCHEDULE_{i:02d}={when.isoformat()}")

    failures = []
    with base.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        try:
            for idx, (topic, when) in enumerate(zip(topics, schedule), 1):
                print(f"[{idx}/{TOTAL_POSTS}] target={when.isoformat()} topic={topic['title']}")
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

    Path("out").mkdir(parents=True, exist_ok=True)
    Path("out/month-reservation-result.json").write_text(json.dumps({
        "planned": TOTAL_POSTS,
        "failed": failures,
        "completed": TOTAL_POSTS - len(failures),
        "first": schedule[0].isoformat(),
        "last": schedule[-1].isoformat(),
        "start_date": str(START_DATE),
        "end_date": str(END_DATE),
        "randomized_times": True,
        "unique_minutes": True,
        "unique_images_within_run": True,
        "morning_window": "08:00-08:59",
        "afternoon_window": "15:00-15:59",
        "anchor_title": "9/12 배당주 투자 체크리스트 6가지: 배당수익률 함정 피하고 ‘지속가능한 배당’ 고르는 법"
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"Reservation completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    import time
    main_reserve()
