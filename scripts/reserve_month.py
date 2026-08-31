import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main
from publisher import (
    _load_state,
    _upload_images,
    _replace_image_placeholders,
    _fill_body,
    _set_representative_image,
    _fill_tags,
)
from playwright.sync_api import sync_playwright

KST = ZoneInfo("Asia/Seoul")
BLOG = os.environ.get("TISTORY_BLOG_NAME", "kunnotes").strip()
DAYS = int(os.environ.get("RESERVE_DAYS", "30"))
POSTS_PER_DAY = 2

# Evergreen fallback pool. The first post of each day focuses on investment/finance;
# the second focuses on housing, loans, rates or household asset management.
INVESTMENT_TOPICS = [
    "미국 금리 방향이 한국 주식시장에 미치는 영향",
    "S&P500 ETF 장기투자에서 가장 먼저 확인할 지표",
    "VOO와 SPY 차이와 장기투자자 선택 기준",
    "나스닥100 ETF 투자 전 꼭 확인해야 할 위험요인",
    "월배당 ETF의 장점과 놓치기 쉬운 함정",
    "커버드콜 ETF가 고배당처럼 보이는 이유",
    "배당성장주와 고배당주의 차이",
    "미국 빅테크 투자 비중을 정할 때 보는 기준",
    "반도체 ETF 투자에서 사이클을 보는 방법",
    "AI 관련주 투자에서 실적보다 먼저 확인할 것",
    "로봇 산업 성장주를 고를 때 확인할 핵심 지표",
    "방산주 장기투자에서 수주잔고가 중요한 이유",
    "금 가격이 오를 때 주식과 채권은 어떻게 움직일까",
    "달러 강세와 원화 투자자의 해외주식 수익률 관계",
    "환율이 미국 주식 투자수익에 미치는 실제 영향",
    "채권 ETF 투자에서 금리와 듀레이션 이해하기",
    "ISA 계좌에서 ETF를 고를 때 세금까지 보는 방법",
    "IRP와 연금저축에서 ETF를 활용하는 기본 전략",
    "장기투자에서 분할매수가 유리한 상황과 불리한 상황",
    "주가가 급락했을 때 손절과 추가매수 판단 기준",
    "수익률보다 중요한 투자 포트폴리오의 변동성 관리",
    "현금 비중을 얼마나 가져가야 하는지 판단하는 방법",
    "주식 포트폴리오 리밸런싱은 언제 해야 할까",
    "대형주와 중소형 성장주의 투자비중을 정하는 기준",
    "고위험 고수익 투자에서 반드시 관리해야 할 손실 한도",
    "미국 주식 장기투자자가 세금과 환율을 함께 보는 이유",
    "ETF 순자산과 거래량이 투자 판단에 중요한 이유",
    "주식 투자에서 PER만 보면 안 되는 이유",
    "기업 실적 발표에서 매출과 영업이익을 읽는 방법",
    "배당수익률이 높은 주식이 항상 좋은 투자는 아닌 이유",
]

REAL_ESTATE_TOPICS = [
    "한국 기준금리 변화가 주택담보대출 금리에 미치는 영향",
    "주택담보대출 고정금리와 변동금리 선택 기준",
    "대출 갈아타기 전에 반드시 계산해야 할 비용",
    "DSR이 주택 구매 가능 금액을 결정하는 방식",
    "신용대출과 주택담보대출을 함께 받을 때 주의할 점",
    "전세대출 금리와 전세가격의 관계",
    "전세와 월세 중 어떤 방식이 유리한지 계산하는 법",
    "서울 아파트 가격을 볼 때 거래량이 중요한 이유",
    "부동산 시장에서 실거래가와 호가를 구분하는 방법",
    "아파트 매수 전 반드시 확인해야 할 등기부등본 항목",
    "신축 아파트와 구축 아파트 가격 차이를 판단하는 기준",
    "재건축과 재개발 투자에서 사업 단계가 중요한 이유",
    "분양권과 입주권의 차이와 투자 위험",
    "청약통장 활용법과 가점제·추첨제 이해하기",
    "생애최초 주택구입자가 확인해야 할 금융 혜택",
    "주택 구매 시 취득세와 보유세를 함께 계산하는 방법",
    "아파트 보유 시 재산세와 종합부동산세 기본 구조",
    "부동산 투자에서 임대수익률 계산을 제대로 하는 방법",
    "상가 투자에서 공실률과 임대료보다 먼저 볼 것",
    "오피스텔 투자 수익률 계산에서 빠지기 쉬운 비용",
    "부동산 시장에서 인구와 입주물량을 함께 보는 방법",
    "서울과 수도권 부동산 가격 차이를 만드는 요인",
    "신도시와 택지지구 투자에서 교통계획 확인하는 법",
    "금리 인하가 부동산 시장에 항상 호재는 아닌 이유",
    "전세가율로 아파트 매수 위험을 판단하는 방법",
    "부동산 매수 시 자기자본과 대출 비중을 정하는 기준",
    "대출 원리금 상환액을 월소득과 비교하는 방법",
    "부동산 투자에서 레버리지의 장점과 위험",
    "주택 매도 시 양도소득세를 미리 확인해야 하는 이유",
    "부동산과 주식 중 자산배분 비중을 정하는 방법",
]


def fallback_topics():
    out = []
    for i in range(DAYS):
        inv = INVESTMENT_TOPICS[i % len(INVESTMENT_TOPICS)]
        re_topic = REAL_ESTATE_TOPICS[i % len(REAL_ESTATE_TOPICS)]
        out.append({"category": "투자·금융·재테크 인사이트", "title": inv, "angle": "일반 투자자가 실제 의사결정에 활용할 수 있도록 핵심 지표와 위험요인을 설명", "source_url": ""})
        out.append({"category": "부동산·대출 인사이트", "title": re_topic, "angle": "대출·주거비·자산관리 관점에서 실제 계산과 판단 기준을 쉽게 설명", "source_url": ""})
    return out


def build_topics():
    """Try to seed the first part with current finance RSS topics, then fill the month with evergreen topics."""
    topics = []
    try:
        items = main.fetch_items()
        if items:
            import json
            from openai import OpenAI
            client = OpenAI()
            prompt = '''한국어 금융·경제·재테크 블로그 kunnotes의 30일 예약발행용 소재를 만든다.
총 60개를 JSON 배열로 반환한다. 하루 2개씩 사용하며 각 날짜의 1번은 투자·금융·재테크, 2번은 부동산·대출·금리·자산관리다.
앞 10일은 제공된 최신 금융 뉴스에서 확장한 주제를 우선하되, 특정 날짜에만 의미가 있는 단기 뉴스 제목은 피한다.
나머지는 검색 수요가 지속되는 evergreen 주제로 구성한다. 같은 주제 반복 금지.
각 항목은 category, title, angle, source_url 필드를 가진다.
본문은 나중에 생성하므로 제목에 확인되지 않은 숫자나 단정적인 전망을 넣지 않는다.'''
            payload = json.dumps(items[:36], ensure_ascii=False)
            r = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.2"), input=prompt + "\n\n최신 자료:\n" + payload)
            text = r.output_text
            candidate = json.loads(text[text.find("["):text.rfind("]") + 1])
            seen = set()
            for t in candidate:
                title = str(t.get("title", "")).strip()
                category = str(t.get("category", "")).strip()
                if title and title not in seen and category:
                    topics.append(t)
                    seen.add(title)
                if len(topics) >= 60:
                    break
    except Exception as exc:
        print(f"TOPIC_POOL_FALLBACK={type(exc).__name__}: {exc}")

    fallback = fallback_topics()
    seen = {str(t.get("title", "")).strip() for t in topics}
    for t in fallback:
        if len(topics) >= 60:
            break
        if t["title"] not in seen:
            topics.append(t)
            seen.add(t["title"])
    return topics[:60]


def _click_publish_layer(page):
    layer = page.locator("#publish-layer-btn").first
    if layer.count():
        layer.click()
    else:
        page.get_by_text("완료", exact=True).last.click()
    page.wait_for_timeout(700)


def _schedule_in_dialog(page, when):
    # Tistory's reservation dialog exposes a 예약 button, calendar and hour/minute spinbuttons.
    page.get_by_role("button", name="예약", exact=True).click()
    page.wait_for_timeout(300)

    date_button = page.get_by_role("button", name=re.compile(r"^\d{4}-\d{2}-\d{2}$"))
    date_button.first.wait_for(state="visible", timeout=10000)
    if not date_button.first.inner_text().startswith(when.strftime("%Y-%m")):
        raise RuntimeError(f"Tistory calendar is not on target month: {when:%Y-%m}")
    date_button.first.click()
    page.get_by_role("table", name="일주일요일과 한달날짜").get_by_role("button", name=str(when.day), exact=True).click()
    page.get_by_role("spinbutton", name="시간").fill(str(when.hour))
    page.get_by_role("spinbutton", name="분").fill(str(when.minute))


def reserve_one(page, post, when):
    page.goto(f"https://{BLOG}.tistory.com/manage/newpost/?type=post", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1800)
    url = page.url.lower()
    if "login" in url or "accounts.kakao" in url:
        raise RuntimeError("TISTORY_SESSION_EXPIRED")

    title = page.locator("#post-title-inp, input[placeholder*='제목'], input[name='title']").first
    title.wait_for(state="visible", timeout=20000)
    title.fill(post["title"])

    image_urls = _upload_images(page, post.get("image_paths", []))
    body = _replace_image_placeholders(post.get("body", ""), image_urls)
    _fill_body(page, body)
    page.wait_for_timeout(600)
    representative = _set_representative_image(page)
    _fill_tags(page, post.get("tags", []))

    _click_publish_layer(page)
    public = page.locator("#open20").first
    if public.count():
        public.check()
    else:
        try:
            page.get_by_role("radio", name="공개").check()
        except Exception:
            pass
    _schedule_in_dialog(page, when)

    submit = page.get_by_role("button", name="공개 발행", exact=True)
    submit.click()
    try:
        submit.wait_for(state="detached", timeout=15000)
    except Exception:
        page.wait_for_timeout(1500)

    print(f"RESERVED={when.isoformat()}|TITLE={post['title']}|REPRESENTATIVE={representative}|IMAGES={len(image_urls)}")


def main_reserve():
    state_path = _load_state()
    topics = build_topics()
    if len(topics) < 60:
        raise RuntimeError(f"Only {len(topics)} unique topics prepared; refusing partial month reservation")

    now = datetime.now(KST)
    first_day = now.date()
    if now >= now.replace(hour=15, minute=18, second=0, microsecond=0):
        first_day = first_day + timedelta(days=1)

    schedule = []
    for day in range(DAYS):
        d = first_day + timedelta(days=day)
        schedule.append(datetime(d.year, d.month, d.day, 8, 7, tzinfo=KST))
        schedule.append(datetime(d.year, d.month, d.day, 15, 17, tzinfo=KST))

    print(f"RESERVATION_PLAN={len(schedule)} posts from {schedule[0].isoformat()} to {schedule[-1].isoformat()}")

    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        try:
            for idx, (topic, when) in enumerate(zip(topics, schedule), start=1):
                print(f"[{idx}/60] target={when.isoformat()} topic={topic['title']}")
                try:
                    post = main.article(topic)
                    reserve_one(page, post, when)
                    time.sleep(1.5)
                except Exception as exc:
                    failures.append({"index": idx, "when": when.isoformat(), "title": topic.get("title", ""), "error": str(exc)})
                    print(f"RESERVE_FAILED={idx}|{type(exc).__name__}|{exc}")
                    if "TISTORY_SESSION_EXPIRED" in str(exc):
                        break
        finally:
            browser.close()

    Path("out").mkdir(parents=True, exist_ok=True)
    Path("out/month-reservation-result.json").write_text(
        __import__("json").dumps({"planned": 60, "failed": failures, "completed": 60 - len(failures), "first": schedule[0].isoformat(), "last": schedule[-1].isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if failures:
        raise RuntimeError(f"Month reservation completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    main_reserve()
