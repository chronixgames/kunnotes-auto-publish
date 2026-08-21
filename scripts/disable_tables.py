from pathlib import Path
import re

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# From this point forward, Kunnotes posts are text-first: no HTML tables.
old_table_rules = [
    "- 필요하면 비교·계산·전망을 <table> HTML로 정리하되, 모든 표의 헤더와 본문 셀은 가운데 정렬한다. 표 전체는 width:100%; border-collapse:collapse;로 만들고, th/td에 padding:11px 10px; line-height:1.6; text-align:center; vertical-align:middle;을 동일하게 적용한다.",
    "- 표의 모든 <tr>은 동일한 열 개수를 유지하고 rowspan/colspan을 사용하지 말 것. 각 셀은 짧은 문구로 작성하고 셀 안에 이미지·이미지 placeholder를 절대 넣지 말 것. 표가 길어지면 문장을 줄여서 셀 높이를 과도하게 키우지 말 것.",
]
for rule in old_table_rules:
    text = text.replace(rule, "- 표 HTML은 사용하지 말고 모든 정보를 일반 문단과 소제목으로 풀어서 작성할 것.")

# Remove any table that the model nevertheless generates, preserving its cell text as paragraphs.
parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
if 'post["body"] = remove_tables_from_body' not in text and parse_line in text:
    text = text.replace(parse_line, parse_line + '    post["body"] = remove_tables_from_body(post.get("body", ""))\n', 1)

if 'def remove_tables_from_body(body):' not in text:
    marker = '\ndef normalize_tags(raw_tags):\n'
    fn = r'''

def remove_tables_from_body(body):
    """Convert any accidental HTML tables into clean paragraph text."""
    def convert_table(match):
        table = match.group(0)
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.I | re.S)
        paragraphs = []
        for row in rows:
            cells = re.findall(r"<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>", row, flags=re.I | re.S)
            values = []
            for cell in cells:
                value = re.sub(r"<[^>]+>", " ", cell)
                value = re.sub(r"\s+", " ", value).strip()
                if value:
                    values.append(value)
            if values:
                paragraphs.append("<p>" + " · ".join(values) + "</p>")
        return "".join(paragraphs)

    return re.sub(r"<table\b.*?</table>", convert_table, body or "", flags=re.I | re.S)
'''
    if marker in text:
        text = text.replace(marker, fn + marker, 1)
    else:
        raise SystemExit("normalize_tags marker not found")

path.write_text(text, encoding="utf-8")
print("Disabled tables for Kunnotes posts")
