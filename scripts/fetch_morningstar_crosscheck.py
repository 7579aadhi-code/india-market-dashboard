#!/usr/bin/env python3
"""
fetch_morningstar_crosscheck.py

Best-effort secondary price cross-check against morningstar.com, layered on
top of the yfinance-based primary pipeline (fetch_market_data.py). Writes
data/morningstar_crosscheck.json.

IMPORTANT — known limitations, by design, not bugs:
  - Morningstar's quote pages are JS-rendered; a plain HTTP request gets an
    empty shell, so this uses a headless browser (Playwright) to actually
    render each page and read the displayed price.
  - Morningstar actively CAPTCHA-challenges automated traffic. In testing,
    roughly half of requests in a single run hit "Let's confirm you are
    human" instead of returning data — expect this to fail for some/most
    tickers on any given run, especially from shared CI IPs. Each ticker is
    fetched independently and failures don't block the others or the rest
    of the pipeline.
  - Only price LEVEL is checked, not % change — Morningstar's quote page
    doesn't expose a same-day previous-close/change figure in the rendered
    text, only Price / Open Price / Day Range.
  - Coverage is US/global indices only. Morningstar has no direct Nifty 50 /
    Sensex / Midcap150 / Smallcap250 index page (only India-domiciled funds
    that *track* these indices, which isn't the same number) — so this does
    not cross-check the India-specific figures at all.

This is a secondary sanity check, not a primary data source. It never
overwrites data/latest.json — it writes its own file, and the dashboard
displays it as "Morningstar (secondary check, best-effort)" alongside a
computed delta vs. the primary yfinance figure, or "unavailable this run"
when a ticker was blocked.

Run: python scripts/fetch_morningstar_crosscheck.py
"""
import datetime
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST_JSON = ROOT / "data" / "latest.json"
OUT_JSON = ROOT / "data" / "morningstar_crosscheck.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TARGETS = [
    {"key": "sp500", "label": "S&P 500", "url": "https://www.morningstar.com/indexes/spi/spx/quote",
     "primary_path": ("us_equity", "sp500", "close")},
    {"key": "dow", "label": "Dow Jones", "url": "https://www.morningstar.com/indexes/dji/!dji/quote",
     "primary_path": ("us_equity", "dow", "close")},
    {"key": "nasdaq", "label": "Nasdaq Composite", "url": "https://www.morningstar.com/indexes/xnas/@cco/quote",
     "primary_path": ("us_equity", "nasdaq", "close")},
    {"key": "ftse100", "label": "FTSE 100", "url": "https://www.morningstar.com/indexes/xlon/ukx/quote",
     "primary_path": None},  # not in data/latest.json; global_latest.json has it but that's a separate file
]

# Anything within this % of the primary figure is "consistent"; beyond it is flagged.
DISCREPANCY_THRESHOLD_PCT = 1.0


def scrape_price(page, url: str):
    """Render a Morningstar quote page and extract the 'Price' figure.
    Returns (price: float | None, status: str) where status is one of:
    'ok', 'blocked' (CAPTCHA/bot-check), 'not_found' (page loaded but no
    Price text present), 'error' (navigation/timeout/other failure)."""
    try:
        resp = page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        text = page.inner_text("body")
    except Exception as e:
        return None, f"error: {e}"

    if "confirm you are human" in text.lower() or (resp and resp.status == 202):
        return None, "blocked"

    idx = text.find("Price")
    if idx == -1:
        return None, "not_found"

    m = re.search(r"Price\s*\n?\s*([\d,]+\.\d+)", text[idx:idx + 60])
    if not m:
        return None, "not_found"

    try:
        return float(m.group(1).replace(",", "")), "ok"
    except ValueError:
        return None, "not_found"


def get_primary_value(path):
    if path is None or not LATEST_JSON.exists():
        return None
    try:
        d = json.loads(LATEST_JSON.read_text())
        v = d
        for key in path:
            v = v[key]
        return float(v) if v is not None else None
    except Exception:
        return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.", file=sys.stderr)
        sys.exit(1)

    results = {}
    print("=== Morningstar cross-check (best-effort, expect partial failures) ===")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for t in TARGETS:
            page = browser.new_page(user_agent=USER_AGENT)
            price, status = scrape_price(page, t["url"])
            page.close()

            primary_value = get_primary_value(t["primary_path"])
            delta_pct = None
            flag = None
            if price is not None and primary_value:
                delta_pct = round((price - primary_value) / primary_value * 100, 3)
                flag = "consistent" if abs(delta_pct) <= DISCREPANCY_THRESHOLD_PCT else "DISCREPANCY"

            results[t["key"]] = {
                "label": t["label"],
                "morningstar_price": price,
                "status": status,
                "primary_value": primary_value,
                "delta_pct_vs_primary": delta_pct,
                "flag": flag,
            }
            print(f"  {t['label']:20s} status={status:10s} morningstar={price} primary={primary_value} delta%={delta_pct}")
            time.sleep(2)  # small gap between requests — courtesy, not a guarantee against blocking
        browser.close()

    out = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "morningstar.com (scraped, best-effort secondary check — see script docstring for known limitations)",
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
