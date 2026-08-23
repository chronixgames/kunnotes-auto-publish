from pathlib import Path

path = Path("src/main.py")
text = path.read_text(encoding="utf-8")

# Kunnotes posts are text-first: never generate HTML tables.
old_table_rules = [
    "- 필요하면 비교·계산·전망을 <table> HTML로 정리하되, 모든 표의 헤더와 본문 셀은 가운데 정렬한다. 표 전체는 width:100%; border-collapse:collapse;로 만들고, th/td에 padding:11px 10px; line-height:1.6; text-align:center; vertical-align:middle;을 동일하게 적용한다.",
    "- 표의 모든 <tr>은 동일한 열 개수를 유지하고 rowspan/colspan을 사용하지 말 것. 각 셀은 짧은 문구로 작성하고 셀 안에 이미지·이미지 placeholder를 절대 넣지 말 것. 표가 길어지면 문장을 줄여서 셀 높이를 과도하게 키우지 말 것.",
]
for rule in old_table_rules:
    text = text.replace(rule, "- 표 HTML은 사용하지 말고 모든 정보를 일반 문단과 소제목으로 풀어서 작성할 것.")

# Do not inject a call to an undefined helper. main.py already runs clean_body(),
# which removes accidental HTML tables and the unwanted closing blocks.
parse_line = '    post = json.loads(text[text.find("{"):text.rfind("}") + 1])\n'
text = text.replace(parse_line + '    post["body"] = remove_tables_from_body(post.get("body", ""))\n', parse_line, 1)

path.write_text(text, encoding="utf-8")
print("Disabled tables for Kunnotes posts")
