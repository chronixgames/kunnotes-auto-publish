from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# Keep the final article rules deterministic, but never inject a function call
# before the function itself exists. This script runs after apply_post_rules.py.
old_close = "- 마지막에는 정확히 <h2>포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리"
new_close = "- '포스팅을 마치며...' 제목이나 마무리 섹션을 본문에 만들지 말 것"
text = text.replace(old_close, new_close)

old_disclaimer = "- 마지막에 정확한 면책 문구를 넣기: <p><em>본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>"
new_disclaimer = "- 본문에 면책 문구를 넣지 말 것"
text = text.replace(old_disclaimer, new_disclaimer)

# Ensure the helper is defined BEFORE its call is injected.
marker = "\ndef normalize_tags(raw_tags):\n"
helper = r'''

def finalize_article_body(body):
    """Final deterministic cleanup for Kunnotes text-first posts."""
    body = body or ""

    # Tables are disabled for these posts.
    body = re.sub(r"<table\b.*?</table>", "", body, flags=re.I | re.S)

    # Remove any generated closing section and everything after it.
    body = re.sub(
        r"<h[1-6][^>]*>\s*(?:📌\s*)?(?:포스팅을\s*마치며\.\.\.|핵심\s*정리|마무리|정리)\s*</h[1-6]>.*$",
        "",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(
        r"<p[^>]*>\s*(?:📌\s*)?포스팅을\s*마치며\.\.\.\s*</p>",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(
        r"<p[^>]*>.*?핵심 내용을 다시 확인하고 자신의 투자 상황에 맞는 대응 전략을 점검해보세요\..*?</p>",
        "",
        body,
        flags=re.I | re.S,
    )

    # Remove disclaimer text completely.
    body = re.sub(
        r"(?:※\s*)?본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다\.",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(r"<p[^>]*>\s*</p>", "", body, flags=re.I)

    return body.strip()
'''

if "def finalize_article_body(body):" not in text:
    if marker not in text:
        raise SystemExit("normalize_tags marker not found")
    text = text.replace(marker, helper + marker, 1)

parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
call = '    post["body"] = finalize_article_body(post.get("body", ""))\n'
if call not in text:
    if parse_line not in text:
        raise SystemExit("JSON parse line not found")
    text = text.replace(parse_line, parse_line + call, 1)

# Keep the model prompt itself aligned with the final cleanup rules.
text = text.replace(
    "- 표(table) HTML은 사용하지 말 것. 표 대신 문단, 리스트, 강조 박스로 설명할 것.",
    "- 표(table) HTML은 사용하지 말 것. 표 대신 문단, 리스트, 강조 박스로 설명할 것."
)

path.write_text(text, encoding="utf-8")
print("Applied final Kunnotes formatting rules safely")
