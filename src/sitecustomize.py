"""Runtime safety patch for generated Tistory post HTML.

Keep the first generated '📌 포스팅을 마치며...' closing section intact,
but remove any accidental duplicate closing sections that appear later.
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

    def _keep_first_closing_remove_duplicates(html):
        seen = 0

        def replace(match):
            nonlocal seen
            seen += 1
            return match.group(0) if seen == 1 else ""

        return _closing_pattern.sub(replace, html)

    def _clean_body_without_duplicate_closing(html):
        cleaned = _original_clean_body(html)
        return _keep_first_closing_remove_duplicates(cleaned)

    publisher._clean_body = _clean_body_without_duplicate_closing
except Exception as exc:
    print(f"sitecustomize publisher patch skipped: {exc}")
