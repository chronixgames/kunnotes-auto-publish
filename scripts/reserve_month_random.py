import os
import random
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import reserve_month as base
from publisher import _load_state
from playwright.sync_api import sync_playwright

KST = ZoneInfo("Asia/Seoul")
DAYS = int(os.environ.get("RESERVE_DAYS", "30"))
POSTS_PER_DAY = 2


def build_random_schedule(days: int):
    """Create two daily reservation slots with varied hours/minutes.

    Morning: 08:00-09:59 KST
    Afternoon: 15:00-16:59 KST
    Every post gets a different minute across the full 60-post month.
    """
    now = datetime.now(KST)
    first_day = now.date()

    # If today's afternoon window has already passed, start tomorrow.
    if now >= now.replace(hour=17, minute=0, second=0, microsecond=0):
        first_day += timedelta(days=1)

    # 60 posts -> use each minute 00-59 exactly once across the month.
    minutes = list(range(60))
    random.shuffle(minutes)
    schedule = []

    for day in range(days):
        d = first_day + timedelta(days=day)
        mm = minutes[day * 2]
        am = minutes[day * 2 + 1]

        # Vary the hour as well, while keeping the requested morning/afternoon windows.
        mh = random.choice((8, 9))
        ah = random.choice((15, 16))

        schedule.append(datetime(d.year, d.month, d.day, mh, mm, tzinfo=KST))
        schedule.append(datetime(d.year, d.month, d.day, ah, am, tzinfo=KST))

    return schedule


def main_reserve():
    state_path = _load_state()
    topics = base.build_topics()
    planned = DAYS * POSTS_PER_DAY
    if len(topics) < planned:
        raise RuntimeError(f"Only {len(topics)} unique topics prepared; refusing partial month reservation")

    schedule = build_random_schedule(DAYS)
    print(f"RESERVATION_PLAN={len(schedule)} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")
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
            "randomized_times": True,
            "unique_minutes": True,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if failures:
        raise RuntimeError(f"Month reservation completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    main_reserve()
