"""Runtime safety patch for generated Tistory post HTML.

Keep the first generated '📌 포스팅을 마치며...' closing section intact,
remove accidental duplicate closing sections, and remove the temporary
kunnotes one-line introduction from generated posts.
"""

import re

try:
    import publisher

    _original_clean_body = publisher._clean_body

    _closing_pattern = re.compile(
        r"<h[1-6][^>]*>\s*(?:📌\s*)?포스팅을\s*마치며[^<]*</h[1-6]>"
        r".*?(?=<h[1-6]\b|<p[^>]*>\s*<em>\s*※\s*본\s*콘텐츠|$)",
        re.IGNORECASE | re.DOTALL,
    )

    _intro_text_pattern = re.compile(
        r"kunnotes\s*한\s*줄\s*소개\s*복잡한\s*금융\s*뉴스를\s*[‘'\"]?내\s*통장[’'\"]?\s*관점으로\s*번역해,?\s*바로\s*실행\s*가능한\s*재테크\s*체크리스트로\s*정리합니다\.?",
        re.IGNORECASE,
    )

    def _restore_closing_format(section):
        """Convert the first closing section to the old emoji callout format."""
        heading = re.search(
            r"<h[1-6][^>]*>\s*(?:📌\s*)?포스팅\s*을?\s*마치며[^<]*</h[1-6]>",
            section,
            re.IGNORECASE,
        )
        if not heading:
            return section

        heading_html = (
            "<div style='border-left:4px solid #1976d2;padding:10px 0 10px 16px;"
            "margin:24px 0 12px 0;line-height:1.6;'>"
            "<div style='font-size:22px;font-weight:700;'>📌 포스팅을 마치며...</div>"
            "</div>"
        )
        return section[:heading.start()] + heading_html + section[heading.end():]

    def _keep_first_closing_remove_duplicates(html):
        seen = 0

        def replace(match):
            nonlocal seen
            seen += 1
            return _restore_closing_format(match.group(0)) if seen == 1 else ""

        return _closing_pattern.sub(replace, html)

    def _clean_body_without_duplicate_closing(html):
        cleaned = _original_clean_body(html)
        cleaned = _intro_text_pattern.sub("", cleaned)
        cleaned = re.sub(r"<p[^>]*>\s*</p>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<div[^>]*>\s*</div>", "", cleaned, flags=re.IGNORECASE)
        return _keep_first_closing_remove_duplicates(cleaned)

    publisher._clean_body = _clean_body_without_duplicate_closing
except Exception as exc:
    print(f"sitecustomize publisher patch skipped: {exc}")
