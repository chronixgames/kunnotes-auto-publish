import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import reserve_month as base  # noqa: E402  (reuses reserve_one, main, _load_state, topic pools)
from playwright.sync_api import sync_playwright  # noqa: E402

KST = ZoneInfo("Asia/Seoul")

DAYS = int(os.environ.get("RESERVE_DAYS", "31"))
POSTS_PER_DAY = 3
START_DATE = datetime(2026, 10, 1, tzinfo=KST).date()
# Skip this many days from START_DATE (for resuming a partially-failed run without
# re-reserving days that already succeeded). 0 = start at October 1st.
START_OFFSET_DAYS = int(os.environ.get("RESERVE_START_OFFSET_DAYS", "0"))

# Three daily windows, as requested: local (KST) hour ranges, end-exclusive.
WINDOWS = [
    ("morning", 8, 12),
    ("afternoon", 15, 18),
    ("evening", 21, 24),  # 24 == up to 23:59
]

# Last two reserved September titles, used only to steer the AI prompt away from
# repeating very similar topics right at the boundary. Not sent to Tistory.
ANCHOR_TITLES = [
    "30년물 국채금리 상승하면 주식이 흔들리는 이유: 할인율·PER·대출금리 총정리",
    "장기 금리 상승기 주택 구매 체크리스트: 대출 부담·가격 조정·전세/월세",
]

IMAGE_STATE_PATH = Path("data/used_pixabay_image_ids.json")

# ---------------------------------------------------------------------------
# Persistent Pixabay image de-duplication (same approach proven in September).
# ---------------------------------------------------------------------------


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
        json.dumps(
            {"pixabay_ids": sorted(_USED_IMAGE_IDS), "updated_at": datetime.now(KST).isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def fetch_unique_pixabay_images(keywords, title):
    for attempt in range(12):
        retry_title = title if attempt == 0 else f"{title} image batch {attempt + 1}"
        candidates = _ORIGINAL_FETCH_IMAGES(keywords, retry_title) or []
        fresh, candidate_ids = [], set()
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

# ---------------------------------------------------------------------------
# Scheduling: 3 posts/day, each in its own window, random hour+minute, and the
# random draw is independent per day (so consecutive days don't line up).
# ---------------------------------------------------------------------------


def build_random_schedule(days: int, start_offset: int):
    rng = random.SystemRandom()
    schedule = []
    for day_index in range(start_offset, start_offset + days):
        d = START_DATE + timedelta(days=day_index)
        for _, start_hour, end_hour in WINDOWS:
            hour = rng.randrange(start_hour, end_hour)
            minute = rng.randrange(0, 60)
            if hour == 24:
                hour, minute = 23, 59
            schedule.append(datetime(d.year, d.month, d.day, hour, minute, tzinfo=KST))
    return schedule


# ---------------------------------------------------------------------------
# Topic pools (fresh for October; distinct wording from September's pools so a
# fallback never repeats what was already published).
# ---------------------------------------------------------------------------

INVESTMENT_TOPICS_OCT = [
    "4분기 배당 캘린더 확인하고 포트폴리오 점검하는 법", "미국 대선 이후 정책 변수와 증시 변동성 대응법",
    "TDF(타겟데이트펀드)로 노후 자산 자동 관리하는 법", "리츠 ETF와 직접 상가 투자, 수익률 비교",
    "환헤지형 ETF와 환노출형 ETF 언제 골라야 할까", "채권형 ETF 듀레이션으로 금리 리스크 가늠하기",
    "연말 배당락일 전에 꼭 확인해야 할 것", "고금리 예금 만기 후 재투자 전략 세우는 법",
    "미국 국채 10년물 금리와 성장주 밸류에이션 관계", "금 ETF vs 골드바, 세금·보관비용 비교",
    "월 배당 포트폴리오 구성할 때 현금흐름 계산법", "IRP 계좌 운용사 갈아타기 전 확인할 것",
    "연금저축펀드 수익률 낮을 때 점검해야 할 3가지", "청년형 소득공제 장기펀드 조건과 활용법",
    "미국 우량주 vs 배당성장주, 은퇴 포트폴리오 관점", "채권투자 초보자를 위한 신용등급 읽는 법",
    "리밸런싱 주기, 분기별 vs 반기별 비교", "코스피 밸류업 지수 관련 ETF 살펴보기",
    "환율 급등기 해외주식 매수 타이밍 판단법", "반도체·2차전지 섹터 ETF 비중 조절하는 법",
    "미국 금리 인하 사이클에서 유리한 자산군", "글로벌 분산투자, 선진국과 신흥국 비중 정하기",
    "퇴직금 IRP로 받을까 일시금으로 받을까", "예금자보호한도 5천만원, 자산 분산 저축 전략",
    "ETF 총보수(TER) 차이가 장기수익률에 미치는 영향", "물가연동국채로 인플레이션 헤지하는 법",
    "연말정산 절세 금융상품 총정리", "자녀 명의 투자계좌 만들 때 알아야 할 세금",
    "주식 양도소득세 대주주 요건 확인하는 법", "금융소득 2천만원 초과 시 세금 대응 전략",
    "퇴직연금 디폴트옵션 상품 고르는 기준",
]

REAL_ESTATE_TOPICS_OCT = [
    "가을 이사철 전세 시세 확인하는 법", "겨울 앞두고 확인할 난방비 절약형 주택 조건",
    "다주택자 양도세 중과 한시 배제 요건 정리", "무순위 청약(줍줍) 신청 전 확인할 것",
    "연립·다세대 매매 시 시세 파악하는 법", "부동산 리모델링 대출 상품 비교",
    "재개발 지분 쪼개기 규제와 투자 유의사항", "월세 세액공제 조건과 신청 방법",
    "부동산 등기 셀프로 하는 법과 주의사항", "깡통전세 위험 신호 체크리스트",
    "아파트 관리비 아끼는 실전 팁", "주택연금 vs 자녀 증여, 노후자산 활용법 비교",
    "공동주택 하자보수 청구 절차 총정리", "1주택자 일시적 2주택 비과세 요건",
    "부동산 대출 중도상환수수료 계산법", "지방 아파트 갭투자 리스크 재점검",
    "전세보증금 반환 지연 시 대응 절차", "재건축 초과이익환수 부담금 계산 예시",
    "오피스텔 주택수 포함 여부와 세금 영향", "생활형숙박시설 투자 시 주의할 점",
    "부동산 경매 명도 절차와 비용", "신혼부부 특별공급 조건 총정리",
    "주택 매수 시 중개수수료 협상하는 법", "부동산 가격 조정기 매수 타이밍 판단법",
    "임대차 3법 핵심 내용과 임차인 권리", "다가구주택 투자 시 확인할 서류",
    "부동산 PF 부실이 분양시장에 미치는 영향", "종부세 합산배제 신고 방법",
    "1기 신도시 이주 계획과 주변 시세 영향", "토지 투자 전 용도지역 확인하는 법",
    "부동산 취득 자금조달계획서 작성 요령",
]

NEWS_TOPICS_OCT = [
    "10월 한국은행 금융통화위원회 결과 정리", "미국 FOMC 10월 회의 결과와 국내 증시 영향",
    "국정감사에서 나온 금융권 주요 이슈 정리", "3분기 가계부채 통계 발표 요약",
    "9월 소비자물가지수(CPI) 발표 핵심 요약", "환율 변동성 확대 배경과 정부 대응",
    "국민연금 기금운용 계획 관련 소식", "가상자산 과세 유예 연장 여부 논의",
    "스테이블코인 관련 법안 국회 논의 현황", "금융감독원 불완전판매 제재 소식",
    "은행권 주담대 갈아타기 서비스 이용 현황", "카드사 리볼빙 서비스 규제 강화 소식",
    "청년 정책자금 대출 10월 접수 일정", "중소기업 정책자금 4분기 지원 계획",
    "보이스피싱 신종 수법과 예방 캠페인", "실손보험 청구 간소화 시행 확대 소식",
    "저신용자 대상 서민금융 지원 확대 소식", "온라인투자연계금융(P2P) 시장 동향",
    "핀테크 규제 샌드박스 신규 지정 소식", "코스피 외국인·기관 수급 동향 분석",
    "미국 국채금리와 국내 증시 상관관계 점검", "10월 수출입 동향 발표 요약",
    "연말 세정지원 대책 예고 소식", "금융위 상생금융 정책 추진 현황",
    "디지털 취약계층 금융 지원 대책", "가계대출 총량 관리 정책 현황",
    "기업대출 연체율 상승 배경 분석", "환율 방어를 위한 외환보유고 동향",
    "산업생산·소비 지표로 보는 경기 흐름", "글로벌 공급망 이슈와 국내 물가 영향",
    "4분기 국내 증시 변동성 요인 점검",
]

assert len(INVESTMENT_TOPICS_OCT) == 31 and len(REAL_ESTATE_TOPICS_OCT) == 31 and len(NEWS_TOPICS_OCT) == 31


def fallback_topics(days: int, start_offset: int):
    out = []
    for i in range(start_offset, start_offset + days):
        out.append({"category": "투자·금융·재테크 인사이트", "title": INVESTMENT_TOPICS_OCT[i % 31], "angle": "일반 투자자가 실제 의사결정에 활용할 수 있도록 핵심 지표와 위험요인을 설명", "source_url": ""})
        out.append({"category": "부동산·대출 인사이트", "title": REAL_ESTATE_TOPICS_OCT[i % 31], "angle": "대출·주거비·자산관리 관점에서 실제 계산과 판단 기준을 쉽게 설명", "source_url": ""})
        out.append({"category": "최신뉴스", "title": NEWS_TOPICS_OCT[i % 31], "angle": "발표된 사실과 배경을 정리하고 투자자·가계에 미치는 실질적 영향을 설명", "source_url": ""})
    return out


def build_topics(days: int, start_offset: int):
    planned = days * POSTS_PER_DAY
    topics = []
    try:
        items = base.main.fetch_items()
        from openai import OpenAI

        client = OpenAI()
        prompt = f'''한국어 금융·경제·재테크 블로그 kunnotes의 2026년 10월 예약발행 소재 {planned}개를 만든다.
9월 말까지 이미 발행/예약된 글 중 최근 두 편은 다음과 같다 (같은 주제·같은 제목을 다시 만들지 말 것):
- {ANCHOR_TITLES[0]}
- {ANCHOR_TITLES[1]}
총 {planned}개이며 하루 3개, 1번은 투자·금융·재테크, 2번은 부동산·대출·금리·자산관리, 3번은 최신 금융/경제 뉴스다.
같은 제목·같은 핵심 주제 반복 금지. 1번과 3번은 최신 금융 뉴스에서 확장하되 특정 날짜에만 의미 있는 단기 뉴스 제목은 피하고, 2번은 evergreen 주제로 구성한다.
각 항목은 category, title, angle, source_url 필드를 가진다. title에는 확인되지 않은 숫자나 단정적인 전망을 넣지 않는다.
JSON 배열만 반환한다.'''
        payload = json.dumps(items[:40], ensure_ascii=False)
        r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt + "\n\n최신 자료:\n" + payload)
        text = r.output_text
        candidate = json.loads(text[text.find("["):text.rfind("]") + 1])
        seen = set()
        for t in candidate:
            title = str(t.get("title", "")).strip()
            category = str(t.get("category", "")).strip()
            if title and category and title not in seen and title not in ANCHOR_TITLES:
                topics.append(t)
                seen.add(title)
            if len(topics) >= planned:
                break
        if len(topics) >= planned:
            print(f"TOPIC_PLAN={planned} posts generated via OpenAI")
            return topics[:planned]
        print(f"TOPIC_GENERATION_SHORT={len(topics)}; filling remainder from fallback pool")
    except Exception as exc:
        print(f"TOPIC_GENERATION_FALLBACK={type(exc).__name__}: {exc}")

    fallback = fallback_topics(days, start_offset)
    seen = {str(t.get("title", "")).strip() for t in topics}
    for t in fallback:
        if len(topics) >= planned:
            break
        if t["title"] not in seen:
            topics.append(t)
            seen.add(t["title"])
    return topics[:planned]


def main_reserve():
    state_path = base._load_state()
    topics = build_topics(DAYS, START_OFFSET_DAYS)
    planned = DAYS * POSTS_PER_DAY
    if len(topics) < planned:
        raise RuntimeError(f"Only {len(topics)} unique topics prepared; refusing partial reservation")

    schedule = build_random_schedule(DAYS, START_OFFSET_DAYS)
    print(f"RESERVATION_PLAN={len(schedule)} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")
    print("TIME_RULE=08:00-11:59 / 15:00-17:59 / 21:00-23:59, independently randomized per day")
    print(f"IMAGE_RULE=persistent Pixabay image IDs; current state count={len(_USED_IMAGE_IDS)}")
    print(f"START_OFFSET_DAYS={START_OFFSET_DAYS}")

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
    Path("out/october-reservation-result.json").write_text(
        json.dumps(
            {
                "planned": planned,
                "failed": failures,
                "completed": planned - len(failures),
                "first": schedule[0].isoformat(),
                "last": schedule[-1].isoformat(),
                "start_date": START_DATE.isoformat(),
                "start_offset_days": START_OFFSET_DAYS,
                "persistent_unique_pixabay_image_ids": True,
                "tracked_image_id_count": len(_USED_IMAGE_IDS),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if failures:
        first_failed_day = failures[0]["index"] // POSTS_PER_DAY
        raise RuntimeError(
            f"October reservation completed with {len(failures)} failures; see out/october-reservation-result.json. "
            f"To resume, re-run with start_offset around day {START_OFFSET_DAYS + first_failed_day}."
        )


if __name__ == "__main__":
    main_reserve()
