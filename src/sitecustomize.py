"""Runtime safety patch for generated Tistory post HTML.

Python imports sitecustomize during interpreter startup when this directory is
on sys.path. The publisher module is imported here and its body cleaner is
wrapped so every generated closing section titled '포스팅을 마치며...' is
removed before the HTML reaches Tistory. This also handles accidental duplicate
closing sections.
"""

import re

try:
    import publisher

    _original_clean_body = publisher._clean_body

    def _remove_closing_sections(html):
        pattern = re.compile(
            r"<h[1-6][^>]*>\s*(?:📌\s*)?포스팅을\s*마치며[^<]*</h[1-6]>"
            r".*?(?=<h[1-6]\b|<p[^>]*>\s*<em>\s*※\s*본\s*콘텐츠|$)",
            re.IGNORECASE | re.DOTALL,
        )
        previous = None
        cleaned = html
        while cleaned != previous:
            previous = cleaned
            cleaned = pattern.sub("", cleaned)
        return cleaned

    def _clean_body_without_closing(html):
        return _remove_closing_sections(_original_clean_body(html))

    publisher._clean_body = _clean_body_without_closing
except Exception as exc:
    print(f"sitecustomize publisher patch skipped: {exc}")
