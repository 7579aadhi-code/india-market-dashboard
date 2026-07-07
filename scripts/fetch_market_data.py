#!/usr/bin/env python3
"""
fetch_market_data.py
Fetches closing market data for the India Market Dashboard and writes data/latest.json.
Designed to run at ~8:30 AM IST (before Indian markets open at 9:15 AM IST),
so the "last completed session" returned by yfinance is always the prior trading day.

Data sources:
  - yfinance  : equity indices (India + US), commodities, FX, VIX, US 10Y yield
  - Web scrape: India 10Y G-Sec yield (multiple fallback sources)
  - Web scrape: Nifty 50 / Midcap 150 / Smallcap 250 PE (multiple fallback sources)
  - data/manual_overrides.json : median PEs, corp bond/CD/call rates (unchanged)

Run:
  python scripts/fetch_market_data.py
"""

import datetime
import json
import re
import sys
from pathlib import Path

import pytz
import requests
import yfinance as yf
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
LATEST_JSON = ROOT / "data" / "latest.json"
MANUAL_JSON = ROOT / "data" / "manual_overrides.json"
HISTORY_DIR = ROOT / "data" / "history"

IST = pytz.timezone("Asia/Kolkata")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ---------------------------------------------------------------------------
# yfinance helpers
# ---------------------------------------------------------------------------

def yf_last(ticker: str, precision: int = 2):
    """
    Return (session_date, close, pct_change) for the most recently completed session.
    Uses period="5d" so it always gets at least two rows for the % change calculation.
    Returns (None, None, None) on any error.
    """
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            print(f"  [WARN] No data for {ticker}", file=sys.stderr)
            return None, None, None
        close = round(float(hist["Close"].iloc[-1]), precision)
        dt = hist.index[-1]
        if hasattr(dt, "date"):
            dt = dt.date()
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            pct = round((close - prev) / prev * 100, 2) if prev else None
        else:
            pct = None
        return dt, close, pct
    except Exception as e:
        print(f"  [ERROR] yfinance {ticker}: {e}", file=sys.stderr)
        return None, None, None


def yf_52w(ticker: str):
    """Return (52w_high, 52w_low) from yfinance .info, or (None, None)."""
    try:
        info = yf.Ticker(ticker).info
        hi = info.get("fiftyTwoWeekHigh")
        lo = info.get("fiftyTwoWeekLow")
        return (round(float(hi), 2) if hi else None,
                round(float(lo), 2) if lo else None)
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# India 10Y G-Sec yield — web scraping with fallback chain
# ---------------------------------------------------------------------------

def _extract_india_10y_from_text(text: str):
    """Extract a plausible India 10Y yield (5.5–9.0%) from raw page text."""
    for m in re.findall(r'\b([5-9]\.\d{2})\b', text):
        v = float(m)
        if 5.50 <= v <= 9.00:
            return round(v, 2)
    return None


def _fetch_india_10y_dealplexus():
    url = "https://www.dealplexus.com/markets/india-10-year-gsec-yield"
    r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    return _extract_india_10y_from_text(BeautifulSoup(r.text, "lxml").get_text(" "))


def _fetch_india_10y_tradingeconomics():
    url = "https://tradingeconomics.com/india/government-bond-yield"
    r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    return _extract_india_10y_from_text(BeautifulSoup(r.text, "lxml").get_text(" "))


def _fetch_india_10y_macrotrends():
    """Macrotrends embeds historical data as a JS variable we can parse."""
    url = "https://www.macrotrends.net/2523/10-year-government-bond-yields-india"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    # Data is embedded as: var chartData = [[date, value], ...]
    m = re.search(r'var\s+chartData\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
    if m:
        rows = json.loads(m.group(1))
        for row in reversed(rows):
            # Each row: [date_str, value] where value is already in percent
            try:
                v = float(row[1])
                if 5.0 <= v <= 12.0:
                    return round(v, 2)
            except (IndexError, TypeError, ValueError):
                pass
    return None


def fetch_india_10y():
    """Try multiple sources; return the first plausible value, or None."""
    # tradingeconomics first — most reliable; dealplexus shown to serve stale data
    for fn in [_fetch_india_10y_tradingeconomics,
               _fetch_india_10y_macrotrends,
               _fetch_india_10y_dealplexus]:
        try:
            v = fn()
            if v is not None:
                print(f"  India 10Y: {v}% (via {fn.__name__})")
                return v
        except Exception as e:
            print(f"  [WARN] {fn.__name__}: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Nifty 50 valuation (PE / PB / Dividend Yield)
# ---------------------------------------------------------------------------

def _fetch_nifty50_val_niftyperatio():
    """nifty-pe-ratio.com — page title contains the current PE."""
    r = requests.get("https://nifty-pe-ratio.com/", headers=HEADERS, timeout=12)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    text = soup.get_text(" ")
    pe = pb = dy = None
    m = re.search(r'PE\s+Ratio\s+Today[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
    if m:
        pe = float(m.group(1))
    m = re.search(r'P[/\s]?B\s+(?:Ratio|Value)[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
    if m:
        pb = float(m.group(1))
    m = re.search(r'Dividend\s+Yield[:\s]+(\d+\.\d+)\s*%', text, re.IGNORECASE)
    if m:
        dy = float(m.group(1))
    return pe, pb, dy


def _fetch_nifty50_val_trendlyne():
    """trendlyne.com index PE page."""
    r = requests.get(
        "https://trendlyne.com/equity/PE/NIFTY/1887/nifty-50-price-to-earning-ratios/",
        headers=HEADERS, timeout=12)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "lxml").get_text(" ")
    m = re.search(r'PE\s+(?:ratio\s+)?(?:is|:)\s*(\d+\.\d+)', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), None, None
    return None, None, None


def fetch_nifty50_valuation():
    """Return (pe, pb, div_yield) — any may be None."""
    for fn in [_fetch_nifty50_val_niftyperatio, _fetch_nifty50_val_trendlyne]:
        try:
            pe, pb, dy = fn()
            if pe and 10 < pe < 50:
                print(f"  Nifty50 PE={pe}, PB={pb}, DY={dy} (via {fn.__name__})")
                return pe, pb, dy
        except Exception as e:
            print(f"  [WARN] {fn.__name__}: {e}", file=sys.stderr)
    return None, None, None


# ---------------------------------------------------------------------------
# Midcap 150 / Smallcap 250 PE
# ---------------------------------------------------------------------------

def _fetch_pe_indexpe(slug: str, lo: float = 10, hi: float = 80):
    """
    indexpe.in/{slug} — the page shows the current PE prominently.
    Valid range guard: lo <= PE <= hi.
    """
    url = f"https://indexpe.in/{slug}"
    r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "lxml").get_text(" ")
    # Look for numbers that plausibly represent a PE
    for m in re.findall(r'\b(\d{2}\.\d{1,2})\b', text):
        v = float(m)
        if lo <= v <= hi:
            return round(v, 2)
    return None


def fetch_midcap150_pe():
    for slug in ["nifty-midcap-150"]:
        try:
            v = _fetch_pe_indexpe(slug, lo=15, hi=60)
            if v:
                print(f"  Midcap150 PE={v}")
                return v
        except Exception as e:
            print(f"  [WARN] midcap PE ({slug}): {e}", file=sys.stderr)
    return None


def fetch_smallcap250_pe():
    for slug in ["nifty-smallcap-250"]:
        try:
            v = _fetch_pe_indexpe(slug, lo=15, hi=100)
            if v:
                print(f"  Smallcap250 PE={v}")
                return v
        except Exception as e:
            print(f"  [WARN] smallcap PE ({slug}): {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Valuation verdict
# ---------------------------------------------------------------------------

def valuation_verdict(pe, five_yr_median, ten_yr_median):
    if pe is None or five_yr_median is None:
        return "Data Pending"
    pct_diff_5yr = (pe - five_yr_median) / five_yr_median * 100
    if pct_diff_5yr > 5:
        return "Overvalued"
    if pct_diff_5yr < -5:
        return "Undervalued"
    return "Fairly Valued"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    now_ist = datetime.datetime.now(IST)
    print(f"=== India Dashboard Fetch — {now_ist.strftime('%Y-%m-%d %H:%M IST')} ===")

    manual = json.loads(MANUAL_JSON.read_text())
    try:
        prior = json.loads(LATEST_JSON.read_text())
    except Exception:
        prior = {}

    # Use yesterday's history file for bps changes, not the last-run file.
    # This prevents same-day re-runs from showing 0 bps when yield actually moved.
    def load_prior_day():
        today = now_ist.date()
        for delta in range(1, 6):  # look back up to 5 calendar days
            d = today - datetime.timedelta(days=delta)
            p = HISTORY_DIR / f"{d.isoformat()}.json"
            if p.exists():
                try:
                    return json.loads(p.read_text())
                except Exception:
                    pass
        return prior  # fallback to last run

    prior_day = load_prior_day()

    # ------------------------------------------------------------------ #
    # 1. India equity indices
    # ------------------------------------------------------------------ #
    print("\n[India equity]")
    nifty_dt, nifty_close, nifty_pct = yf_last("^NSEI")
    _, sensex_close, sensex_pct = yf_last("^BSESN")

    # Try both Yahoo Finance ticker variants for mid/small cap
    _, mid150_close, mid150_pct = yf_last("NIFTYMIDCAP150.NS")
    if mid150_close is None:
        _, mid150_close, mid150_pct = yf_last("^NIFMDCP150")

    _, small250_close, small250_pct = yf_last("NIFTYSMLCAP250.NS")
    if small250_close is None:
        _, small250_close, small250_pct = yf_last("^NIFSMCP250")

    # Determine session date from Nifty
    session_date = nifty_dt.isoformat() if nifty_dt else now_ist.date().isoformat()
    print(f"  Session date : {session_date}")
    print(f"  Nifty50      : {nifty_close}  ({nifty_pct}%)")
    print(f"  Sensex       : {sensex_close}  ({sensex_pct}%)")
    print(f"  Midcap150    : {mid150_close}  ({mid150_pct}%)")
    print(f"  Smallcap250  : {small250_close}  ({small250_pct}%)")

    # ------------------------------------------------------------------ #
    # 1b. India sector indices
    # ------------------------------------------------------------------ #
    print("\n[India sectors]")
    SECTOR_TICKERS = {
        "bank_nifty":  "^NSEBANK",
        "nifty_it":    "^CNXIT",
        "nifty_auto":  "^CNXAUTO",
        "nifty_fmcg":  "^CNXFMCG",
        "nifty_pharma":"^CNXPHARMA",
        "nifty_metal": "^CNXMETAL",
        "nifty_realty":"^CNXREALTY",
        "nifty_energy":"^CNXENERGY",
        "nifty_infra": "^CNXINFRA",
    }
    india_sectors = {}
    for key, ticker in SECTOR_TICKERS.items():
        _, close, pct = yf_last(ticker)
        india_sectors[key] = {"close": close, "pct_change": pct}
        print(f"  {key}: {close} ({pct}%)")

    # ------------------------------------------------------------------ #
    # 2. US equity indices
    # ------------------------------------------------------------------ #
    print("\n[US equity]")
    _, sp500_close, sp500_pct = yf_last("^GSPC")
    _, dow_close, dow_pct = yf_last("^DJI")
    _, nasdaq_close, nasdaq_pct = yf_last("^IXIC")
    print(f"  S&P500  : {sp500_close}  ({sp500_pct}%)")
    print(f"  Dow     : {dow_close}  ({dow_pct}%)")
    print(f"  Nasdaq  : {nasdaq_close}  ({nasdaq_pct}%)")

    # ------------------------------------------------------------------ #
    # 3. Bond yields
    # ------------------------------------------------------------------ #
    print("\n[Bond yields]")
    india_10y = fetch_india_10y()

    # ^TNX quotes the 10-year Treasury yield directly in percent (e.g. 4.49 = 4.49%)
    _, us_10y_raw, _ = yf_last("^TNX", precision=4)
    us_10y = round(float(us_10y_raw), 2) if us_10y_raw is not None else None
    print(f"  US 10Y  : {us_10y}%")

    prior_india_10y = (prior_day.get("india_debt") or {}).get("gsec_10y", {}).get("yield")
    prior_us_10y    = (prior_day.get("india_debt") or {}).get("us_10y",   {}).get("yield")

    # Sanity clamp: India G-Sec yields don't normally move more than 25 bps in a session.
    # A larger delta almost certainly means the scraper picked up a wrong number.
    if india_10y is not None and prior_india_10y is not None:
        if abs(india_10y - prior_india_10y) > 0.25:
            print(f"  [SANITY] India 10Y scraped {india_10y}% but prior was {prior_india_10y}% "
                  f"(delta {india_10y - prior_india_10y:+.2f}% > 50bps threshold) — "
                  f"reverting to prior value.", file=sys.stderr)
            india_10y = prior_india_10y

    india_10y_bps = round((india_10y - prior_india_10y) * 100) if (india_10y and prior_india_10y) else None
    us_10y_bps    = round((us_10y   - prior_us_10y)    * 100) if (us_10y    and prior_us_10y)    else None

    # ------------------------------------------------------------------ #
    # 4. Commodities
    # ------------------------------------------------------------------ #
    print("\n[Commodities]")
    _, gold_usd,   gold_pct   = yf_last("GC=F", precision=2)
    _, silver_usd, silver_pct = yf_last("SI=F", precision=3)
    _, brent_usd,  brent_pct  = yf_last("BZ=F", precision=2)
    _, wti_usd,    wti_pct    = yf_last("CL=F", precision=2)
    _, natgas_usd, natgas_pct = yf_last("NG=F", precision=3)
    _, copper_usd, copper_pct = yf_last("HG=F", precision=3)
    print(f"  Gold      : ${gold_usd}/oz  ({gold_pct}%)")
    print(f"  Silver    : ${silver_usd}/oz  ({silver_pct}%)")
    print(f"  Brent     : ${brent_usd}/bbl ({brent_pct}%)")
    print(f"  WTI       : ${wti_usd}/bbl  ({wti_pct}%)")
    print(f"  Nat. Gas  : ${natgas_usd}/MMBtu ({natgas_pct}%)")
    print(f"  Copper    : ${copper_usd}/lb ({copper_pct}%)")

    # ------------------------------------------------------------------ #
    # 4b. Crypto
    # ------------------------------------------------------------------ #
    print("\n[Crypto]")
    _, btc_usd, btc_pct = yf_last("BTC-USD", precision=0)
    _, eth_usd, eth_pct = yf_last("ETH-USD", precision=2)
    print(f"  BTC: ${btc_usd}  ({btc_pct}%)")
    print(f"  ETH: ${eth_usd}  ({eth_pct}%)")

    # ------------------------------------------------------------------ #
    # 5. Currency
    # ------------------------------------------------------------------ #
    print("\n[Currency]")
    _, usd_inr, _ = yf_last("USDINR=X", precision=3)
    if usd_inr is None:
        _, usd_inr, _ = yf_last("INR=X", precision=3)
    _, eur_inr, eur_inr_pct = yf_last("EURINR=X", precision=2)
    _, gbp_inr, gbp_inr_pct = yf_last("GBPINR=X", precision=2)
    prior_usd_inr = (prior_day.get("currency") or {}).get("usd_inr", {}).get("value")
    usd_inr_change = round(usd_inr - prior_usd_inr, 3) if (usd_inr and prior_usd_inr) else None
    print(f"  USD/INR : {usd_inr}  (Δ {usd_inr_change})")
    print(f"  EUR/INR : {eur_inr}  ({eur_inr_pct}%)")
    print(f"  GBP/INR : {gbp_inr}  ({gbp_inr_pct}%)")

    # ------------------------------------------------------------------ #
    # 6. India VIX
    # ------------------------------------------------------------------ #
    print("\n[India VIX]")
    _, vix_val, vix_pct = yf_last("^INDIAVIX", precision=2)
    vix_52h, vix_52l = yf_52w("^INDIAVIX")
    # Fall back to prior if yfinance doesn't return 52w
    if vix_52h is None:
        vix_52h = (prior.get("india_vix") or {}).get("wk52_high")
    if vix_52l is None:
        vix_52l = (prior.get("india_vix") or {}).get("wk52_low")
    print(f"  VIX : {vix_val}  ({vix_pct}%)  52w {vix_52l}–{vix_52h}")

    # ------------------------------------------------------------------ #
    # 6b. RBI Policy Rates — scrape rbi.org.in
    # ------------------------------------------------------------------ #
    print("\n[RBI Policy Rates]")
    rbi_rates = {}
    try:
        r = requests.get("https://www.rbi.org.in/scripts/bs_viewcontent.aspx?Id=4165",
                         headers=HEADERS, timeout=12)
        text = BeautifulSoup(r.text, "lxml").get_text(" ")
        m = re.search(r'(?:Repo\s+Rate|Policy\s+Repo)[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
        if m:
            rbi_rates["repo_rate"] = float(m.group(1))
        m = re.search(r'(?:Standing\s+Deposit\s+Facility|SDF)[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
        if m:
            rbi_rates["sdf_rate"] = float(m.group(1))
        m = re.search(r'(?:Marginal\s+Standing\s+Facility|MSF)[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
        if m:
            rbi_rates["msf_rate"] = float(m.group(1))
        m = re.search(r'CRR[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
        if m:
            rbi_rates["crr"] = float(m.group(1))
        m = re.search(r'SLR[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
        if m:
            rbi_rates["slr"] = float(m.group(1))
        print(f"  RBI rates: {rbi_rates}")
    except Exception as e:
        print(f"  [WARN] RBI rates: {e}", file=sys.stderr)
    # Fall back to prior only if it was live-scraped; otherwise use updated hardcoded rates.
    HARDCODED_RBI = {
        "repo_rate": 5.25, "sdf_rate": 5.00, "msf_rate": 5.50,
        "crr": 4.0, "slr": 18.0,
        "_source": "hardcoded_fallback_Jun2026"
    }
    prior_rbi = prior.get("rbi_policy") or {}
    if not rbi_rates.get("repo_rate"):
        prior_is_live = "_source" not in prior_rbi  # only trust prior if it came from live scraping
        if prior_rbi.get("repo_rate") and prior_is_live:
            rbi_rates = prior_rbi
        else:
            rbi_rates = HARDCODED_RBI

    # ------------------------------------------------------------------ #
    # 6c. NSE FII / DII net flows
    # ------------------------------------------------------------------ #
    print("\n[FII/DII flows]")
    fii_dii = {}
    try:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        r = requests.get(url, headers={**HEADERS,
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=12)
        rows = r.json()
        # Rows: list of dicts with 'category', 'date', 'buyValue', 'sellValue', 'netValue'
        latest_row = {row["category"]: row for row in rows}
        fii = latest_row.get("FII/FPI", {})
        dii = latest_row.get("DII", {})
        fii_dii = {
            "date": fii.get("date") or dii.get("date"),
            "fii_net_cr":  round(float(fii.get("netValue", 0)), 2) if fii.get("netValue") else None,
            "fii_buy_cr":  round(float(fii.get("buyValue", 0)), 2) if fii.get("buyValue") else None,
            "fii_sell_cr": round(float(fii.get("sellValue", 0)), 2) if fii.get("sellValue") else None,
            "dii_net_cr":  round(float(dii.get("netValue", 0)), 2) if dii.get("netValue") else None,
            "dii_buy_cr":  round(float(dii.get("buyValue", 0)), 2) if dii.get("buyValue") else None,
            "dii_sell_cr": round(float(dii.get("sellValue", 0)), 2) if dii.get("sellValue") else None,
        }
        print(f"  FII net: ₹{fii_dii.get('fii_net_cr')} Cr | DII net: ₹{fii_dii.get('dii_net_cr')} Cr")
    except Exception as e:
        print(f"  [WARN] FII/DII: {e}", file=sys.stderr)
        fii_dii = prior.get("fii_dii") or {}

    # ------------------------------------------------------------------ #
    # 7. Valuation (PE / PB / DY)
    # ------------------------------------------------------------------ #
    print("\n[Valuation]")
    nifty_pe, nifty_pb, nifty_dy = fetch_nifty50_valuation()
    midcap_pe   = fetch_midcap150_pe()
    smallcap_pe = fetch_smallcap250_pe()

    # Fall back to prior data if scraping failed
    prior_lc = (prior.get("valuation") or {}).get("large_cap", {})
    prior_mc = (prior.get("valuation") or {}).get("mid_cap",   {})
    prior_sc = (prior.get("valuation") or {}).get("small_cap", {})

    nifty_pe   = nifty_pe   or prior_lc.get("pe")
    nifty_pb   = nifty_pb   or prior_lc.get("pb")
    nifty_dy   = nifty_dy   or prior_lc.get("div_yield")
    midcap_pe  = midcap_pe  or prior_mc.get("pe")
    mid_pb     = prior_mc.get("pb")
    mid_dy     = prior_mc.get("div_yield")
    smallcap_pe = smallcap_pe or manual.get("smallcap250_current_pe", {}).get("value") or prior_sc.get("pe")
    sc_pb      = manual.get("smallcap250_pb",       {}).get("value") or prior_sc.get("pb")
    sc_dy      = manual.get("smallcap250_div_yield", {}).get("value") or prior_sc.get("div_yield")

    n50_5yr  = manual.get("nifty50_pe_5yr_median",   {}).get("value")
    n50_10yr = manual.get("nifty50_pe_10yr_median",   {}).get("value")
    mid_5yr  = manual.get("midcap150_pe_5yr_median",  {}).get("value")
    mid_10yr = manual.get("midcap150_pe_10yr_median", {}).get("value")
    sc_5yr   = manual.get("smallcap250_pe_5yr_median",  {}).get("value")
    sc_10yr  = manual.get("smallcap250_pe_10yr_median", {}).get("value")

    lc_verdict = valuation_verdict(nifty_pe,   n50_5yr,  n50_10yr)
    mc_verdict = valuation_verdict(midcap_pe,  mid_5yr,  mid_10yr)
    sc_verdict = valuation_verdict(smallcap_pe, sc_5yr,  sc_10yr)

    # ------------------------------------------------------------------ #
    # 8. Derived: INR commodity conversions
    # ------------------------------------------------------------------ #
    OZ_PER_KG = 31.1035

    def gold_mcx(g, fx):
        return int(round((g / OZ_PER_KG) * 10 * fx)) if g and fx else None

    def silver_mcx(s, fx):
        return int(round((s / OZ_PER_KG) * 1000 * fx)) if s and fx else None

    def brent_inr_conv(b, fx):
        return int(round(b * fx)) if b and fx else None

    # ------------------------------------------------------------------ #
    # 9. Buffett indicator
    # ------------------------------------------------------------------ #
    prior_buf = prior.get("buffett_indicator") or {}
    prior_day_buf = prior_day.get("buffett_indicator") or {}
    india_gdp_usd_tn = prior_buf.get("india_gdp_usd_tn", 4.15)

    bse_lakh_cr = bse_usd_tn = buffett_ratio = buffett_verdict = None
    prior_nifty    = (prior_day.get("india_equity") or {}).get("nifty50", {}).get("close")
    prior_lakh_cr  = prior_day_buf.get("bse_mcap_lakh_cr") or prior_buf.get("bse_mcap_lakh_cr")
    if prior_lakh_cr and prior_nifty and nifty_close:
        bse_lakh_cr = round(prior_lakh_cr * nifty_close / prior_nifty, 2)
    if bse_lakh_cr and usd_inr:
        bse_usd_tn = round(bse_lakh_cr / usd_inr, 2)
    if bse_usd_tn and india_gdp_usd_tn:
        buffett_ratio = round(bse_usd_tn / india_gdp_usd_tn * 100, 1)
        buffett_verdict = ("Overvalued" if buffett_ratio > 100 else
                           "Fairly Valued" if buffett_ratio >= 75 else "Undervalued")

    # ------------------------------------------------------------------ #
    # 10. BEER model / ERP
    # ------------------------------------------------------------------ #
    earnings_yield = round(100 / nifty_pe, 2) if nifty_pe else None
    beer_ratio = round(india_10y / earnings_yield, 2) if (india_10y and earnings_yield) else None
    erp = round(earnings_yield - india_10y, 2) if (india_10y and earnings_yield) else None
    beer_interp = (
        "Negative equity risk premium — bonds are relatively more attractive than equities on this simple model"
        if (erp is not None and erp < 0) else
        "Positive equity risk premium — equities are relatively more attractive than bonds on this simple model"
        if erp is not None else
        "Data pending"
    )

    # ------------------------------------------------------------------ #
    # 10b. Nifty 52-week High / Low
    # ------------------------------------------------------------------ #
    nifty_52h, nifty_52l = yf_52w("^NSEI")

    # ------------------------------------------------------------------ #
    # 11. Nifty 50 — 30-day price history for the chart
    # ------------------------------------------------------------------ #
    print("\n[30-day Nifty history]")
    nifty_history = []
    try:
        hist_df = yf.Ticker("^NSEI").history(period="45d", interval="1d", auto_adjust=True)
        for idx, row in hist_df.tail(30).iterrows():
            dt = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            nifty_history.append({"d": dt, "c": round(float(row["Close"]), 2)})
        print(f"  Got {len(nifty_history)} days of history")
    except Exception as e:
        print(f"  [WARN] 30d history: {e}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    # 13. Auto-summary  (was 11 before history step was added)
    # ------------------------------------------------------------------ #
    def pct_str(v):
        return f"{v:+.2f}%" if v is not None else "N/A"

    direction = "rose" if (nifty_pct or 0) > 0 else ("fell" if (nifty_pct or 0) < 0 else "was flat")
    rupee_dir = "firmed" if (usd_inr_change or 0) < 0 else "weakened"
    summary = (
        f"Nifty 50 {direction} {pct_str(nifty_pct)} to "
        f"{nifty_close:,.2f} on {session_date}; "
        f"India 10Y G-Sec {'at ' + str(india_10y) + '%' if india_10y else 'yield N/A'}; "
        f"rupee {rupee_dir} to {usd_inr:.3f}; "
        f"Gold ${gold_usd}/oz {pct_str(gold_pct)}; "
        f"{'ERP ' + pct_str(erp) + ' — bonds more attractive' if erp is not None and erp < 0 else 'ERP ' + pct_str(erp) if erp is not None else 'ERP N/A'}."
    )

    # ------------------------------------------------------------------ #
    # 12. Assemble JSON
    # ------------------------------------------------------------------ #
    generated_at = datetime.datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")

    data = {
        "as_of_date": session_date,
        "generated_at_ist": generated_at,
        "india_equity": {
            "nifty50":    {"close": nifty_close,   "pct_change": nifty_pct,
                           "wk52_high": nifty_52h, "wk52_low": nifty_52l},
            "sensex":     {"close": sensex_close,  "pct_change": sensex_pct},
            "midcap150":  {"close": mid150_close,  "pct_change": mid150_pct},
            "smallcap250":{"close": small250_close,"pct_change": small250_pct},
        },
        "valuation": {
            "large_cap": {
                "pe": nifty_pe, "pb": nifty_pb, "div_yield": nifty_dy,
                "verdict": lc_verdict,
            },
            "mid_cap": {
                "pe": midcap_pe, "pb": mid_pb, "div_yield": mid_dy,
                "verdict": mc_verdict,
            },
            "small_cap": {
                "pe": smallcap_pe, "pb": sc_pb, "div_yield": sc_dy,
                "verdict": sc_verdict,
                "note": "PB from manual_overrides (stale); div_yield not publicly available daily",
            },
        },
        "us_equity": {
            "sp500":  {"close": sp500_close,  "pct_change": sp500_pct},
            "dow":    {"close": dow_close,    "pct_change": dow_pct},
            "nasdaq": {"close": nasdaq_close, "pct_change": nasdaq_pct},
        },
        "india_debt": {
            "gsec_10y": {"yield": india_10y, "bps_change": india_10y_bps},
            "us_10y":   {"yield": us_10y,    "bps_change": us_10y_bps},
        },
        "commodities": {
            "gold_comex_usd_oz":  {"value": gold_usd,  "pct_change": gold_pct},
            "gold_mcx_inr_10g":   {
                "value": gold_mcx(gold_usd, usd_inr), "pct_change": gold_pct,
                "note": "approx conversion, not exact MCX settlement",
            },
            "silver_comex_usd_oz": {"value": silver_usd, "pct_change": silver_pct},
            "silver_mcx_inr_kg": {
                "value": silver_mcx(silver_usd, usd_inr), "pct_change": silver_pct,
                "note": "approx conversion, not exact MCX settlement",
            },
            "brent_usd_bbl":       {"value": brent_usd,  "pct_change": brent_pct},
            "brent_mcx_inr_bbl":   {
                "value": brent_inr_conv(brent_usd, usd_inr), "pct_change": brent_pct,
                "note": "approx conversion",
            },
            "wti_usd_bbl":         {"value": wti_usd,    "pct_change": wti_pct},
            "natgas_usd_mmbtu":    {"value": natgas_usd, "pct_change": natgas_pct},
            "copper_usd_lb":       {"value": copper_usd, "pct_change": copper_pct},
        },
        "crypto": {
            "bitcoin":  {"value": btc_usd, "pct_change": btc_pct, "pair": "BTC/USD"},
            "ethereum": {"value": eth_usd, "pct_change": eth_pct, "pair": "ETH/USD"},
        },
        "currency": {
            "usd_inr": {"value": usd_inr, "change": usd_inr_change},
            "eur_inr": {"value": eur_inr, "pct_change": eur_inr_pct},
            "gbp_inr": {"value": gbp_inr, "pct_change": gbp_inr_pct},
        },
        "rbi_policy": rbi_rates,
        "fii_dii": fii_dii,
        "india_vix": {
            "value": vix_val, "pct_change": vix_pct,
            "wk52_high": vix_52h, "wk52_low": vix_52l,
        },
        "buffett_indicator": {
            "bse_mcap_lakh_cr": bse_lakh_cr,
            "bse_mcap_usd_tn":  bse_usd_tn,
            "india_gdp_usd_tn": india_gdp_usd_tn,
            "ratio_pct": buffett_ratio,
            "verdict":   buffett_verdict,
            "note": "BSE mcap estimated proportionally from prior session scaled by Nifty move; India GDP carried from last manual figure",
        },
        "beer_model": {
            "earnings_yield_pct": earnings_yield,
            "gsec_10y_pct":       india_10y,
            "beer_ratio":         beer_ratio,
            "erp_pct":            erp,
            "interpretation":     beer_interp,
        },
        "summary": summary,
        "nifty_history": nifty_history,
        "india_sectors": india_sectors,
    }

    # ------------------------------------------------------------------ #
    # 13. Write outputs
    # ------------------------------------------------------------------ #
    LATEST_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nWrote {LATEST_JSON}")

    HISTORY_DIR.mkdir(exist_ok=True)
    hist_path = HISTORY_DIR / f"{session_date}.json"
    hist_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Archived to {hist_path}")


if __name__ == "__main__":
    main()
