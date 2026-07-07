#!/usr/bin/env python3
"""
fetch_global_data.py
Fetches global market data (equities, FX, bond yields) and writes data/global_latest.json.
100% free — uses only yfinance. No API key required.

Run:
  python scripts/fetch_global_data.py
"""

import datetime
import json
import sys
from pathlib import Path

import pytz
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
GLOBAL_JSON = ROOT / "data" / "global_latest.json"
IST = pytz.timezone("Asia/Kolkata")


def yf_last(ticker: str, precision: int = 2):
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            return None, None, None
        close = round(float(hist["Close"].iloc[-1]), precision)
        dt = hist.index[-1]
        if hasattr(dt, "date"):
            dt = dt.date()
        pct = None
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            pct = round((close - prev) / prev * 100, 2) if prev else None
        return dt, close, pct
    except Exception as e:
        print(f"  [WARN] {ticker}: {e}", file=sys.stderr)
        return None, None, None


def main():
    now_ist = datetime.datetime.now(IST)
    print(f"=== Global Market Fetch — {now_ist.strftime('%Y-%m-%d %H:%M IST')} ===")

    # ── Asia-Pacific ─────────────────────────────────────────────────────────
    print("\n[Asia-Pacific]")
    apac_tickers = [
        ("Nikkei 225",              "Japan",       "^N225",    0),
        ("Hang Seng",               "Hong Kong",   "^HSI",     0),
        ("Shanghai Composite",      "China",       "000001.SS",2),
        ("KOSPI",                   "South Korea", "^KS11",    2),
        ("S&P/ASX 200",             "Australia",   "^AXJO",    2),
        ("Straits Times Index",     "Singapore",   "^STI",     2),
        ("Taiwan TAIEX",            "Taiwan",      "^TWII",    2),
        ("Jakarta Composite",       "Indonesia",   "^JKSE",    0),
    ]
    apac_indices = []
    for name, country, ticker, dec in apac_tickers:
        _, close, pct = yf_last(ticker, precision=dec)
        print(f"  {name}: {close} ({pct}%)")
        apac_indices.append({"name": name, "country": country,
                              "ticker": ticker, "close": close, "pct_change": pct})

    # ── Europe ───────────────────────────────────────────────────────────────
    print("\n[Europe]")
    europe_tickers = [
        ("FTSE 100",   "United Kingdom", "^FTSE",  0),
        ("DAX 40",     "Germany",        "^GDAXI", 2),
        ("CAC 40",     "France",         "^FCHI",  2),
        ("Euro Stoxx 50","Europe",       "^STOXX50E",2),
        ("IBEX 35",    "Spain",          "^IBEX",  0),
        ("SMI",        "Switzerland",    "^SSMI",  0),
    ]
    europe_indices = []
    for name, country, ticker, dec in europe_tickers:
        _, close, pct = yf_last(ticker, precision=dec)
        print(f"  {name}: {close} ({pct}%)")
        europe_indices.append({"name": name, "country": country,
                                "ticker": ticker, "close": close, "pct_change": pct})

    # ── Americas ─────────────────────────────────────────────────────────────
    print("\n[Americas]")
    us_tickers = [
        ("S&P 500",       "USA",    "^GSPC",  2),
        ("Dow Jones",     "USA",    "^DJI",   0),
        ("Nasdaq Composite","USA",  "^IXIC",  2),
        ("Russell 2000",  "USA",    "^RUT",   2),
        ("S&P/TSX",       "Canada", "^GSPTSE",2),
        ("Bovespa",       "Brazil", "^BVSP",  0),
    ]
    us_indices = []
    for name, country, ticker, dec in us_tickers:
        _, close, pct = yf_last(ticker, precision=dec)
        print(f"  {name}: {close} ({pct}%)")
        us_indices.append({"name": name, "country": country,
                            "ticker": ticker, "close": close, "pct_change": pct})

    # ── FX (all USD crosses + INR crosses) ───────────────────────────────────
    print("\n[Currencies]")
    fx_tickers = [
        ("EUR/USD",  "eurusd",   "EURUSD=X",  4),
        ("GBP/USD",  "gbpusd",   "GBPUSD=X",  4),
        ("USD/JPY",  "usdjpy",   "USDJPY=X",  2),
        ("USD/SGD",  "usdsgd",   "USDSGD=X",  4),
        ("AUD/USD",  "audusd",   "AUDUSD=X",  4),
        ("USD/CNY",  "usdcny",   "USDCNY=X",  4),
        ("USD/KRW",  "usdkrw",   "USDKRW=X",  2),
        ("EUR/INR",  "eurinr",   "EURINR=X",  2),
        ("GBP/INR",  "gbpinr",   "GBPINR=X",  2),
        ("JPY/INR",  "jpyinr",   "JPYINR=X",  4),
        ("AUD/INR",  "audinr",   "AUDINR=X",  2),
    ]
    currencies = {}
    for label, key, ticker, dec in fx_tickers:
        _, rate, pct = yf_last(ticker, precision=dec)
        print(f"  {label}: {rate} ({pct}%)")
        currencies[key] = {"pair": label, "rate": rate, "pct_change": pct}

    # ── Global Bond Yields (via yfinance) ─────────────────────────────────────
    print("\n[Bond Yields]")
    yield_tickers = [
        ("US 2Y Treasury",  "us_2y",  "^IRX", 2),
        ("US 10Y Treasury", "us_10y", "^TNX", 2),
        ("US 30Y Treasury", "us_30y", "^TYX", 2),
    ]
    bond_yields = {}
    for name, key, ticker, dec in yield_tickers:
        _, val, pct = yf_last(ticker, precision=dec)
        bps = None
        print(f"  {name}: {val}%")
        bond_yields[key] = {"name": name, "yield": val, "bps_change": bps}

    # ── VIX & fear gauges ────────────────────────────────────────────────────
    print("\n[VIX / Fear]")
    _, us_vix, us_vix_pct = yf_last("^VIX", precision=2)
    _, vxn, vxn_pct = yf_last("^VXN", precision=2)
    print(f"  CBOE VIX: {us_vix} ({us_vix_pct}%)")
    print(f"  VXN (Nasdaq VIX): {vxn} ({vxn_pct}%)")

    # ── Assemble ─────────────────────────────────────────────────────────────
    generated_at = now_ist.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    data = {
        "generated_at_ist": generated_at,
        "as_of_date": now_ist.date().isoformat(),
        "note": "All data via yfinance. Prices reflect last completed trading session for each exchange.",
        "regions": {
            "asia_pacific": {
                "session_status": "closed",
                "indices": apac_indices,
            },
            "europe": {
                "session_status": "closed",
                "indices": europe_indices,
            },
            "us": {
                "session_status": "closed",
                "indices": us_indices,
            },
        },
        "currencies": currencies,
        "bond_yields": bond_yields,
        "volatility": {
            "us_vix":  {"value": us_vix, "pct_change": us_vix_pct, "name": "CBOE VIX"},
            "us_vxn":  {"value": vxn,    "pct_change": vxn_pct,    "name": "Nasdaq VXN"},
        },
    }

    GLOBAL_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nWrote {GLOBAL_JSON}")


if __name__ == "__main__":
    main()
