from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# Stronger table rules: every row must have the same number of cells; no images/placeholders inside tables.
old_table = "- 필요하면 비교·계산·전망을 <table> HTML로 정리하되, 모든 표의 헤더와 본문 셀은 가운데 정렬한다. 표 전체는 width:100%; border-collapse:collapse;로 만들고, th/td에 padding:11px 10px; line-height:1.6; text-align:center; vertical-align:middle;을 동일하게 적용한다."
new_table = old_table + "\n- 표의 모든 <tr>은 동일한 열 개수를 유지하고 rowspan/colspan을 사용하지 말 것. 각 셀은 짧은 문구로 작성하고 셀 안에 이미지·이미지 placeholder를 절대 넣지 말 것. 표가 길어지면 문장을 줄여서 셀 높이를 과도하게 키우지 말 것."
text = text.replace(old_table, new_table)

# Closing heading and disclaimer styling.
old_close = "- 마지막에는 정확히 <h2>포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리"
new_close = "- 마지막에는 정확히 <h2>📌 포스팅을 마치며...</h2>를 넣고 독자가 기억할 핵심을 간결하게 정리"
text = text.replace(old_close, new_close)

old_disclaimer = "- 마지막에 정확한 면책 문구를 넣기: <p><em>본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>"
new_disclaimer = "- 마지막에 정확한 면책 문구를 넣기: <p><em>※ 본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>"
text = text.replace(old_disclaimer, new_disclaimer)

# Make the model's caution-box structure deterministic.
old_caution = "- 중요한 수치·결론·주의사항은 색상으로 시각화할 것. 주의 박스는 첫 줄에 정확히 '[주의]'를 단독으로 표시하고 실제 내용은 다음 줄에 배치할 것. 박스 안에는 이미지, 표, 이미지 placeholder를 절대 넣지 말 것"
new_caution = old_caution + ". [주의]는 반드시 박스의 첫 번째 줄에만 배치하고, 내용은 두 번째 줄부터 간결한 문장으로 배치할 것."
text = text.replace(old_caution, new_caution)

# Inject a deterministic final body normalizer.
parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
if 'post["body"] = finalize_article_body' not in text:
    text = text.replace(parse_line, parse_line + '    post["body"] = finalize_article_body(post.get("body", ""))\n', 1)

if 'def finalize_article_body(body):' not in text:
    marker = '\ndef normalize_tags(raw_tags):\n'
    fn = r'''

def finalize_article_body(body):
    body = body or ""

    # Never allow media/placeholders inside tables.
    def clean_table(match):
        table = match.group(0)
        table = re.sub(r"<!--IMAGE[1-5]-->", "", table, flags=re.I)
        table = re.sub(r"<figure\b[^>]*>.*?</figure>", "", table, flags=re.I | re.S)
        table = re.sub(r"<img\b[^>]*>", "", table, flags=re.I)

        rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table, flags=re.I | re.S)
        if not rows:
            return table
        counts = []
        for row in rows:
            counts.append(len(re.findall(r"<(?:th|td)\b", row, flags=re.I)))
        target = max(counts) if counts else 0
        if target:
            rebuilt = []
            for row in rows:
                current = len(re.findall(r"<(?:th|td)\b", row, flags=re.I))
                if current < target:
                    row = row.replace("</tr>", "<td style='padding:11px 10px;line-height:1.6;text-align:center;vertical-align:middle;word-break:keep-all;'></td>" * (target-current) + "</tr>", 1)
                rebuilt.append(row)
            for old, new in zip(rows, rebuilt):
                table = table.replace(old, new, 1)
        table = re.sub(r"\srowspan\s*=\s*['\"]?\d+['\"]?", "", table, flags=re.I)
        table = re.sub(r"\scolspan\s*=\s*['\"]?\d+['\"]?", "", table, flags=re.I)
        table = re.sub(r"<table(?![^>]*style=)", "<table style='width:100%;border-collapse:collapse;table-layout:fixed;'", table, flags=re.I)
        return table

    body = re.sub(r"<table\b.*?</table>", clean_table, body, flags=re.I | re.S)

    # Enforce the requested closing heading and add a visual emoji.
    body = re.sub(r"<h2([^>]*)>\s*(?:📌\s*)?(?:핵심 정리|마무리|정리|포스팅을 마치며\.\.\.)\s*</h2>", r"<h2\1>📌 포스팅을 마치며...</h2>", body, flags=re.I)
    if not re.search(r"<h2[^>]*>\s*📌\s*포스팅을 마치며\.\.\.\s*</h2>", body, flags=re.I):
        body += "<h2>📌 포스팅을 마치며...</h2><p>핵심 내용을 다시 확인하고 자신의 투자 상황에 맞는 대응 전략을 점검해보세요.</p>"

    # Disclaimer always begins with a visible symbol.
    body = re.sub(r"(?:※\s*)?본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다\.", "※ 본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.", body)
    if "본 콘텐츠는 정보 제공을 위한 것" not in body:
        body += "<p><em>※ 본 콘텐츠는 정보 제공을 위한 것이며, 투자·세무 판단의 근거가 되는 조언이 아닙니다.</em></p>"

    # Caution boxes: [주의] must be first line, content underneath; remove any accidental media.
    def clean_caution(match):
        box = match.group(0)
        box = re.sub(r"<img\b[^>]*>|<figure\b[^>]*>.*?</figure>|<!--IMAGE[1-5]-->", "", box, flags=re.I | re.S)
        plain = re.sub(r"<[^>]+>", " ", box)
        if "[주의]" in plain:
            box = re.sub(r"\[주의\]", "", box, count=1)
            box = re.sub(r"(<div[^>]*>)", r"\1<div style='font-weight:700;margin-bottom:8px;'>[주의]</div>", box, count=1, flags=re.I)
        return box
    body = re.sub(r"<div[^>]*(?:background|border)[^>]*>.*?</div>", clean_caution, body, flags=re.I | re.S)

    return body
'''
    text = text.replace(marker, fn + marker, 1)

path.write_text(text, encoding="utf-8")
print("Applied final Kunnotes formatting rules")
