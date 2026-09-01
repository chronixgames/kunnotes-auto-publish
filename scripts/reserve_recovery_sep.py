import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import reserve_month as base

KST = ZoneInfo("Asia/Seoul")
IMAGE_STATE_PATH = Path("data/used_pixabay_image_ids.json")

# These are the 21 September slots that failed in the previous run.
RECOVERY = [
    ("2026-09-14T08:01:00+09:00", "현금흐름 투자 설계도: 월배당·분기배당·채권이자 수입을 섞는 방법"),
    ("2026-09-14T15:20:00+09:00", "주택담보대출 상환방식(원리금균등·원금균등·만기일시) 선택 기준"),
    ("2026-09-18T08:05:00+09:00", "채권 ETF 입문: 듀레이션과 금리 민감도 한 번에 이해하기"),
    ("2026-09-18T15:42:00+09:00", "대출금리의 구조: 기준금리·가산금리·우대금리의 차이와 확인법"),
    ("2026-09-19T08:16:00+09:00", "미국 주식 ETF 고르기: 지수 선택(S&P500·나스닥·배당)부터"),
    ("2026-09-20T08:27:00+09:00", "환율이 수익률을 바꾸는 방식: 미국주식·달러자산 투자자가 보는 포인트"),
    ("2026-09-20T15:28:00+09:00", "변동금리 스트레스 테스트: 기준금리 1%p 변화에 내 이자가 얼마나 늘까"),
    ("2026-09-21T08:36:00+09:00", "ISA 계좌 활용법: 비과세·분리과세 구조와 ‘계좌 안에서’ 할 일"),
    ("2026-09-22T15:37:00+09:00", "전세보증금 보호 체크리스트: 보증보험, 선순위, 확정일자 한 번에"),
    ("2026-09-23T08:29:00+09:00", "월급쟁이 자산배분 기본기: 주식·채권·현금 비중을 정하는 질문 6개"),
    ("2026-09-23T15:47:00+09:00", "전세자금대출 핵심: 금리·보증기관·상환 조건 비교 가이드"),
    ("2026-09-24T08:44:00+09:00", "배당주 vs 리츠(REITs): 현금흐름 성격이 다른 이유"),
    ("2026-09-24T15:40:00+09:00", "리츠 투자자가 알아야 할 부동산 시장 지표: 공실률·임대료·캡레이트"),
    ("2026-09-26T15:39:00+09:00", "가계 재무제표 만들기: 자산·부채·현금흐름 1장으로 정리하는 법"),
    ("2026-09-27T08:25:00+09:00", "해외주식 환전 전략: 분할환전·자동환전·달러예수금 관리"),
    ("2026-09-27T15:46:00+09:00", "고정금리로 갈아탈 때 체크할 4가지: 금리차만 보면 생기는 오류"),
    ("2026-09-28T08:48:00+09:00", "주식·ETF 리밸런싱 규칙: ‘시간 기준’ vs ‘비중 기준’"),
    ("2026-09-28T15:49:00+09:00", "부동산 계약서 특약 예시: 분쟁 줄이는 문장 정리(체크리스트)"),
    ("2026-09-29T15:58:00+09:00", "에너지 가격이 오를 때 가계가 먼저 흔들리는 지점: 교통·난방·식비"),
    ("2026-09-30T08:15:00+09:00", "장기 금리(30년물)가 오르면 주식은 왜 흔들릴까: 할인율 관점 정리"),
    ("2026-09-30T15:00:00+09:00", "장기 금리 상승기 ‘주택 구매’ 의사결정 체크리스트"),
]

USED_IDS = set()
ORIGINAL_FETCH = base.main.fetch_pixabay_images


def load_state():
    if not IMAGE_STATE_PATH.exists():
        return set()
    data = json.loads(IMAGE_STATE_PATH.read_text(encoding="utf-8"))
    return {str(x) for x in data.get("pixabay_ids", [])}


USED_IDS = load_state()


def image_id(path):
    m = re.search(r"-(\d+)\.jpg$", str(path), re.I)
    return m.group(1) if m else None


def save_state():
    IMAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_STATE_PATH.write_text(
        json.dumps({"pixabay_ids": sorted(USED_IDS), "updated_at": datetime.now(KST).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Try the normal topic-specific search first, then broaden the search terms.
# IDs are committed to the persistent state only after the Tistory reservation succeeds.
PIVOTS = [
    ["stock market", "finance", "investment"],
    ["bank", "money", "finance"],
    ["real estate", "house", "mortgage"],
    ["business", "economy", "market"],
    ["office", "city", "architecture"],
    ["technology", "data center", "business"],
    ["gold", "currency", "money"],
]


_LAST_IDS = set()


def fetch_recovery_images(keywords, title):
    global _LAST_IDS
    for round_no in range(1, 16):
        candidates = []
        if round_no == 1:
            queries = list(keywords or [])[:5]
        else:
            pivot = PIVOTS[(round_no - 2) % len(PIVOTS)]
            queries = pivot + [str(x).strip() for x in (keywords or [])[:2] if str(x).strip()]
        paths = ORIGINAL_FETCH(queries, title) or []
        fresh = []
        ids = set()
        for path in paths:
            iid = image_id(path)
            if iid and iid not in USED_IDS and iid not in ids:
                fresh.append(path)
                ids.add(iid)
            else:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
        if len(fresh) >= 3:
            _LAST_IDS = set(list(ids)[:5])
            print(f"RECOVERY_IMAGES_OK={len(fresh[:5])}|ids={','.join(sorted(_LAST_IDS))}")
            return fresh[:5]
        for path in fresh:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        print(f"RECOVERY_IMAGE_RETRY={round_no}")
    raise RuntimeError("Could not obtain 3 unused Pixabay images for recovery")


base.main.fetch_pixabay_images = fetch_recovery_images


def main_reserve():
    state_path = base._load_state()
    failures = []
    print(f"RECOVERY_PLAN={len(RECOVERY)} September posts only")
    print("RECOVERY_RULE=retry only the 21 previously failed September slots; do not touch successful reservations or October")

    with base.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        try:
            for index, (when_text, title) in enumerate(RECOVERY, 1):
                when = datetime.fromisoformat(when_text)
                print(f"[{index}/{len(RECOVERY)}] target={when_text} topic={title}")
                _LAST_IDS.clear()
                try:
                    topic = {
                        "category": "투자·금융·재테크 인사이트" if index % 2 else "부동산·대출 인사이트",
                        "title": title,
                        "angle": "기존 Kunnotes 포스팅 규칙을 그대로 적용하고 실제 투자·자산관리 판단 기준을 쉽게 설명",
                        "source_url": "",
                    }
                    post = base.main.article(topic)
                    base.reserve_one(page, post, when)
                    USED_IDS.update(_LAST_IDS)
                    save_state()
                    time.sleep(1.5)
                    print(f"RECOVERY_RESERVED={when_text}|TITLE={post['title']}|IMAGE_IDS={','.join(sorted(_LAST_IDS))}")
                except Exception as exc:
                    failures.append({"index": index, "when": when_text, "title": title, "error": str(exc)})
                    print(f"RECOVERY_FAILED={index}|{type(exc).__name__}|{exc}")
                    if "TISTORY_SESSION_EXPIRED" in str(exc):
                        break
        finally:
            browser.close()

    Path("out").mkdir(parents=True, exist_ok=True)
    Path("out/month-reservation-result.json").write_text(json.dumps({
        "mode": "september-recovery",
        "planned": len(RECOVERY),
        "failed": failures,
        "completed": len(RECOVERY) - len(failures),
        "first": RECOVERY[0][0],
        "last": RECOVERY[-1][0],
        "successful_reservations_untouched": True,
        "october_untouched": True,
        "persistent_unique_pixabay_image_ids": True,
        "tracked_image_id_count": len(USED_IDS),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"September recovery completed with {len(failures)} failures; see out/month-reservation-result.json")


if __name__ == "__main__":
    main_reserve()
