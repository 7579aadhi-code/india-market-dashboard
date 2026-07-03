# Daily Update Instructions (run by the scheduled agent at 8:00 AM IST)

Goal: refresh `data/latest.json` with **yesterday's closing data** (the most recently
completed trading session as of 8am IST) and leave `data/manual_overrides.json` untouched
unless you have a genuinely better-sourced number for one of its fields.

## Steps

1. Read `data/latest.json` and `data/manual_overrides.json` to see the current values (for
   sanity-checking, not for copying stale numbers forward).
2. Use WebSearch / WebFetch to find, for the most recent closed trading session:
   - India: Nifty 50, Sensex, Nifty Midcap 150, Nifty Smallcap 250 — close + % change
   - Index valuation (NSE publishes PE/PB/DY per index, e.g. via nseindia.com or
     niftyindices.com "Historical PE PB DIV" reports, or aggregator sites like
     trendlyne.com / niftype.com / screener.in): PE, PB, dividend yield for Nifty 50,
     Nifty Midcap 150, Nifty Smallcap 250.
   - US: S&P 500, Dow Jones, Nasdaq Composite — close + % change
   - India 10Y G-Sec yield + bps change vs prior session (tradingeconomics.com,
     investing.com, CCIL tenorwise yields)
   - US 10Y Treasury yield + bps change (FRED DGS10, CNBC US10Y, tradingeconomics.com)
   - Commodities: Gold COMEX $/oz, Silver COMEX $/oz, Brent crude $/bbl, each with % change
   - USD/INR rate + one-line driver of the day's move
   - India VIX: value, % change, 52-week high/low
   - BSE total market cap (bseindia.com "Market Cap" key statistics) in ₹ crore, converted
     to ₹ lakh crore and USD trillion using the day's USD/INR rate
   - India nominal GDP estimate (IMF/RBI/MOSPI — this changes rarely, quarterly at most;
     don't re-search this every day, just carry forward unless a new official estimate
     was published)
3. Compute derived fields yourself (do not search for these):
   - Gold MCX ₹/10g ≈ (Gold $/oz ÷ 31.1035) × 10 × USD/INR — label as "approx conversion,
     not exact MCX settlement" since it excludes import duty/GST/local premium
   - Silver MCX ₹/kg ≈ (Silver $/oz ÷ 31.1035) × 1000 × USD/INR — same caveat
   - Brent ₹/bbl ≈ Brent $/bbl × USD/INR — same caveat
   - Buffett ratio = BSE Mcap (USD tn) ÷ India GDP (USD tn) × 100.
     Verdict: <75% Undervalued, 75-100% Fairly Valued, >100% Overvalued
   - Nifty 50 earnings yield = 1 ÷ Nifty 50 PE × 100
   - BEER ratio = India 10Y G-Sec yield ÷ Nifty 50 earnings yield
   - Equity Risk Premium (ERP) = Nifty 50 earnings yield − India 10Y G-Sec yield
     Interpretation: ERP > 0 → equities attractive vs bonds; ERP < 0 → bonds relatively
     more attractive; note the direction explicitly in `beer_model.interpretation`.
   - Large/Mid/Small cap valuation verdict: compare current PE to the 5yr/10yr median PE
     (from `manual_overrides.json`, or freshly-sourced numbers if you found reliable ones).
     PE below both medians → Undervalued. Within ~5% of median → Fairly Valued. Meaningfully
     above both → Overvalued. Use judgement, and if PE data is missing, verdict = "Data Pending".
4. For fields with NO reliable free daily source (AAA/AA corporate bond yields at 5/3/1yr,
   12M/3M CD rates, Call Rate, T-Repo, 5yr/10yr median PE for all three caps): do **not**
   guess. Read the existing value from `data/manual_overrides.json` and use it as-is in the
   dashboard, keeping its "manual" badge. Only update `manual_overrides.json` if you found a
   credible, explicitly-dated source for one of these (e.g. a CRISIL/FBIL/CCIL page) — cite
   the source in that field's `source` key.
5. Write a fresh one-sentence `summary` capturing the day's main narrative (e.g. what drove
   the index move, whether valuations look stretched, rate/currency context).
6. Overwrite `data/latest.json` with the new values, following the exact same schema as the
   existing file. Set `as_of_date` to the trading session's date and `generated_at_ist` to
   the current run timestamp in IST (ISO 8601, +05:30).
7. Also copy the new `data/latest.json` into `data/history/YYYY-MM-DD.json` (session date) so
   there's a running archive.
8. After writing the new `data/latest.json`, run `python3 sync_html.py` from the project root.
   This inlines the current contents of `data/latest.json` and `data/manual_overrides.json`
   directly into `index.html` (between the `<script id="data-latest">` /
   `<script id="data-manual">` tags), so the dashboard works standalone via `file://` with no
   local server needed. Do not hand-edit `index.html`'s data blocks yourself — always go
   through the JSON files + `sync_html.py`, since the script does the substitution
   deterministically. Only touch the HTML/CSS/JS outside those two `<script>` blocks if you're
   changing layout or logic, not data.
9. If any live figure could not be found with reasonable confidence, leave the corresponding
   field `null` in `latest.json` rather than fabricating a number — the dashboard renders
   `null` as "N/A".

## Notes
- Times/sessions: at 8:00 AM IST the Indian market has not yet opened for the day, so
  "today's" data point is always the previous completed session's close (Indian markets are
  closed weekends/holidays — on Mon/post-holiday runs, the relevant session is the last
  trading day, not literally "yesterday").
- Keep numeric precision reasonable: index levels to 2 decimals, % changes to 2 decimals,
  yields/ratios to 2 decimals, INR commodity conversions to whole rupees.
