from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")


def replace_function(source: str, name: str, replacement: str) -> str:
    pattern = rf"(?ms)^def {re.escape(name)}\(.*?(?=^def |^if __name__ ==|\Z)"
    if re.search(pattern, source):
        return re.sub(pattern, replacement.rstrip() + "\n\n", source, count=1)
    marker = "\ndef normalize_tags(raw_tags):\n"
    if marker not in source:
        raise SystemExit(f"{marker.strip()} marker not found while repairing {name}")
    return source.replace(marker, "\n" + replacement.rstrip() + "\n" + marker, 1)


safe_normalize = r'''def normalize_generated_body(body):
    """Final deterministic cleanup; never add a closing section or disclaimer."""
    body = body or ""
    body = re.sub(r"<table\b[^>]*>.*?</table>", "", body, flags=re.I | re.S)
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
    body = re.sub(
        r"(?:※\s*)?본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다\.",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(r"<p[^>]*>\s*</p>", "", body, flags=re.I)
    return body.strip()
'''

safe_finalize = r'''def finalize_article_body(body):
    """Final deterministic cleanup; never add a closing section or disclaimer."""
    return normalize_generated_body(body)
'''

text = replace_function(text, "normalize_generated_body", safe_normalize)
text = replace_function(text, "finalize_article_body", safe_finalize)

parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
for call in [
    '    post["body"] = normalize_generated_body(post.get("body", ""))\n',
    '    post["body"] = finalize_article_body(post.get("body", ""))\n',
]:
    if call not in text:
        if parse_line not in text:
            raise SystemExit("JSON parse line not found while repairing calls")
        text = text.replace(parse_line, parse_line + call, 1)

path.write_text(text, encoding="utf-8")
print("Runtime publisher rules repaired: helpers defined and closing/disclaimer cleanup is non-additive.")
