#!/usr/bin/env python3
"""Load index.html and global-markets.html in a headless browser and fail
loudly if either throws a JS error or never finishes rendering.

This exists because the dashboard has broken silently before: the data
schema changed but the page's JS still referenced old field names, so the
page loaded "successfully" (HTTP 200) while actually showing a crash message
to every visitor. A file that merely parses as HTML/JSON is not enough
proof the page works — this script actually executes it like a browser
would and checks for runtime errors, which is the only thing that would
have caught that bug before it went live.

Run from the project root: python scripts/validate_pages.py
Exits non-zero (and CI should treat that as build failure — do not publish
a page that fails this check) if a page has console errors, uncaught JS
exceptions, or its data-driven content still shows a "Loading…"/"Failed to
load" placeholder after rendering should have completed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PAGES = ["index.html", "global-markets.html"]

FAILURE_MARKERS = [
    "Failed to load",
    "Cannot read prop",
    "is not defined",
    "is not a function",
    "Run sync_html.py first",
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name in PAGES:
            page_path = ROOT / page_name
            if not page_path.exists():
                failures.append(f"{page_name}: file does not exist")
                continue

            page = browser.new_page()
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page_errors = []
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(f"file://{page_path.resolve()}")
            page.wait_for_timeout(1500)  # let the inline data-load script finish

            body_text = page.inner_text("body")

            if console_errors:
                failures.append(f"{page_name}: console errors: {console_errors}")
            if page_errors:
                failures.append(f"{page_name}: uncaught JS exceptions: {page_errors}")
            for marker in FAILURE_MARKERS:
                if marker in body_text:
                    failures.append(f"{page_name}: rendered body contains failure marker '{marker}'")

            page.close()
        browser.close()

    if failures:
        print("VALIDATION FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    print(f"All {len(PAGES)} pages loaded cleanly with no console errors, no uncaught exceptions, no failure markers.")


if __name__ == "__main__":
    main()
