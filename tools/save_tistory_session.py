from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("tistory-state.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded")
    print("브라우저에서 티스토리에 로그인하세요. 로그인 완료 후 이 터미널로 돌아와 Enter를 누르세요.")
    input()
    context.storage_state(path=str(OUT))
    browser.close()

print(f"저장 완료: {OUT.resolve()}")
print("중요: 이 파일은 절대 GitHub에 커밋하지 마세요.")
