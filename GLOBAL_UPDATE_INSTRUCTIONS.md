# Global Markets Snapshot — Update Instructions
(run every 30 min by the scheduled agent "global-markets-update")

Goal: keep `data/global_latest.json` close to real-time so `global-markets.html` is
useful for a quick check right after India's 3:30pm IST close (and at any other time
someone opens it).

## Steps

1. Use WebSearch / WebFetch to find the current value + % change for:
   - Asia-Pacific: Nikkei 225 (Japan), Hang Seng (Hong Kong), Shanghai Composite (China),
     KOSPI Composite (South Korea), S&P/ASX 200 (Australia), Straits Times Index / STI
     (Singapore)
   - Europe: FTSE 100 (UK), DAX 40 (Germany), CAC 40 (France)
   - US: S&P 500, Dow Jones, Nasdaq Composite
2. Also refresh: GBP/USD, EUR/USD, USD/SGD, USD/JPY, and UK 10Y Gilt / Singapore 10Y /
   US 10Y Treasury yields (yields don't need to be searched every run if unchanged in the
   last few hours — but do re-check at least every few runs, don't let them go stale for days).
3. For each region, set `session_status` to a short note on whether that region's markets
   are currently open, mid-session, or closed relative to IST right now (e.g. "FTSE 100
   currently trading — live intraday figure" vs "US markets closed, showing last session's
   close"). Compute this from the current IST time, not by guessing.
4. If a figure conflicts across sources (this has happened with KOSPI before), pick the
   figure from the most authoritative/most recent-looking source, and add a `"note"` field
   on that index flagging it for the next run to re-verify — do not silently pick one without
   flagging if the discrepancy is large (>1 percentage point).
5. Write a fresh one-sentence `summary` describing the overall global risk tone right now
   (e.g. broad rally vs risk-off, which regions are diverging).
6. Set `generated_at_ist` to the current run timestamp in IST (ISO 8601, +05:30).
7. Overwrite `data/global_latest.json` with the new values, following the exact same schema
   as the existing file.
8. Run `python3 sync_html.py` from the project root — this inlines both `data/latest.json` /
   `data/manual_overrides.json` into `index.html` AND `data/global_latest.json` into
   `global-markets.html`. Do not hand-edit the data blocks inside either HTML file directly.
9. If a figure cannot be found with reasonable confidence, leave it `null` rather than
   fabricating a number, and don't overwrite a previously-good value with a guess.

## Notes
- This task runs every 30 minutes, all day — most runs will find markets partway through a
  session for at least one region. That's expected; just report the session_status honestly.
- Keep this file and `data/latest.json`/`data/manual_overrides.json` (India dashboard) fully
  independent — this task should never touch India-dashboard files, and the 8am India update
  task should never touch `data/global_latest.json`.
