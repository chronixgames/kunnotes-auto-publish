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

# Existing posts are already reserved through 2026-09-12.
# Start this new batch on 2026-09-13 and reserve 30 days x 2 posts.
START_DATE = datetime(2026, 9, 13, tzinfo=KST).date()

# Keep Pixabay image IDs unique across the entire 60-post batch.
_USED_IMAGE_IDS = set()
_ORIGINAL_FETCH_IMAGES = base.main.fetch_pixabay_images


def _image_id(path):
    match = re.search(r"-(\d+)\.jpg$", str(path))
    return match.group(1) if match else None


def fetch_unique_pixabay_images(keywords, title):
    """Generate images while preventing Pixabay image-ID reuse across posts."""
    selected = []
    for attempt in range(8):
        retry_title = title if attempt == 0 else f"{title} image batch {attempt + 1}"
        candidates = _ORIGINAL_FETCH_IMAGES(keywords, retry_title) or []
        for path in candidates:
            image_id = _image_id(path)
            if image_id and image_id in _USED_IMAGE_IDS:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            if image_id:
                _USED_IMAGE_IDS.add(image_id)
            selected.append(path)
            if len(selected) >= 3:
                return selected
    return selected


# article() resolves fetch_pixabay_images from the main module namespace.
base.main.fetch_pixabay_images = fetch_unique_pixabay_images


def build_random_schedule(days: int):
    """Create two daily reservation slots with varied minutes.

    Morning: 08:00-08:59 KST
    Afternoon: 15:00-15:59 KST
    Every post gets a different minute across the full 60-post batch.
    """
    if days * POSTS_PER_DAY > 60:
        raise RuntimeError("Unique-minute schedule supports at most 60 posts per batch")

    minutes = list(range(60))
    random.SystemRandom().shuffle(minutes)
    schedule = []

    for day in range(days):
        d = START_DATE + timedelta(days=day)
        am = minutes[day * 2]
        pm = minutes[day * 2 + 1]
        schedule.append(datetime(d.year, d.month, d.day, 8, am, tzinfo=KST))
        schedule.append(datetime(d.year, d.month, d.day, 15, pm, tzinfo=KST))

    return schedule


def main_reserve():
    state_path = _load_state()
    topics = base.build_topics()
    planned = DAYS * POSTS_PER_DAY
    if len(topics) < planned:
        raise RuntimeError(f"Only {len(topics)} unique topics prepared; refusing partial month reservation")

    schedule = build_random_schedule(DAYS)
    print(f"RESERVATION_PLAN={len(schedule)} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")
    print("RESERVATION_RULE=after 2026-09-12 existing posts")
    print("TIME_RULE=08:00-08:59 and 15:00-15:59; every minute unique across all 60 posts")
    print("IMAGE_RULE=Pixabay image IDs unique across all 60 posts")
    for i, when in enumerate(schedule, start=1):
        print(f"SCHEDULE_{i:02d}={when.isoformat()}")

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
                    failures.append({
                        "index": idx,
                        "when": when.isoformat(),
                        "title": topic.get("title", ""),
                        "error": str(exc),
                    })
                    print(f"RESERVE_FAILED={idx}|{type(exc).__name__}|{exc}")
                    if "TISTORY_SESSION_EXPIRED" in str(exc):
                        break
        finally:
            browser.close()

    Path("out").mkdir(parents=True, exist_ok=True)
    Path("out/month-reservation-result.json").write_text(
        json.dumps({
            "planned": planned,
            "failed": failures,
            "completed": planned - len(failures),
            "first": schedule[0].isoformat(),
            "last": schedule[-1].isoformat(),
            "start_date": START_DATE.isoformat(),
            "randomized_times": True,
            "unique_minutes": True,
            "morning_window": "08:00-08:59",
            "afternoon_window": "15:00-15:59",
            "unique_pixabay_image_ids": True,
            "existing_posts_until": "2026-09-12",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if failures:
        raise RuntimeError(f"Month reservation completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    main_reserve()
