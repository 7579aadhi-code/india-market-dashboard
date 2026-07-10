# Health Monitor Instructions
(run periodically by the scheduled agent "dashboard-health-monitor")

You have the repo owner's standing permission to diagnose and fix problems with this
dashboard automatically, without asking for confirmation first — commit and push fixes
directly. Still follow AGENT_RULES.md (no scope creep, no silent new secrets/dependencies,
don't bypass the validation gate). This monitor exists to catch anything that slips through
despite that gate — infra failures, stale data, GitHub Pages issues.

## Steps

1. Working directory: /Users/aadhithyaraj/india-market-dashboard. Run `git pull origin main`
   first so you're checking the current state, not a stale local copy.

2. **Check the last few GitHub Actions runs**: `gh run list --workflow=update-dashboard.yml --limit 5`
   - If the most recent scheduled run failed:
     - `gh run view <id>` to see why.
     - If the failure looks like a GitHub-side infra issue (e.g. "job not acquired by
       Runner", a 5xx from GitHub, or a network timeout unrelated to this repo's code),
       just re-trigger it: `gh workflow run update-dashboard.yml`, wait for it to finish,
       and confirm success. No code change needed for this case.
     - If the failure is a real error in our code (a Python exception in a fetch script, or
       `scripts/validate_pages.py` failing), read the actual log
       (`gh run view <id> --log-failed`), diagnose the root cause, fix it in the relevant
       file, run `python scripts/validate_pages.py` locally to confirm the fix works, then
       commit and push. Re-trigger the workflow afterward to confirm it now succeeds.
   - If data hasn't updated in more than ~36 hours (check `as_of_date` / `generated_at_ist`
     in `data/latest.json` and `data/global_latest.json` against current IST time), treat
     that as a failure even if the workflow shows green, and investigate why data is stale.

3. **Spot-check the live site**: fetch both
   `https://7579aadhi-code.github.io/india-market-dashboard/` and
   `https://7579aadhi-code.github.io/india-market-dashboard/global-markets.html` and confirm
   neither contains obvious failure text ("Failed to load", "Cannot read prop", "is not
   defined", a blank body, etc.) and that `generated_at_ist`/`as_of_date` shown is recent.
   If GitHub Pages itself looks stuck (Actions succeeded but the live page still shows old
   content after several minutes), check
   `gh run list --workflow="pages build and deployment" --limit 3` for a Pages-side failure.

4. **If you fix something**, the commit message must explain what was broken and what you
   changed — this is the only audit trail since this task doesn't message the user on every
   routine run. Example: `git commit -m "Auto-fix: KOSPI ticker changed on yfinance, updated
   scripts/fetch_global_data.py"`.

5. **If you cannot resolve something** after a genuine attempt (e.g. a paid data source is
   down, GitHub itself is having a widespread outage, something needs a human decision like
   a new paid API key), leave the repo in whatever the safest state is (don't push something
   you're not confident in) and write a note to `MONITOR_LOG.md` (create if missing) with a
   timestamp and what's blocked, so it's visible next time someone looks, rather than
   silently retrying forever.

6. Do not use destructive git operations (`push --force`, `reset --hard`, deleting branches).
   Normal commits and pushes only.

7. **`scripts/fetch_morningstar_crosscheck.py` failing or showing `"status": "blocked"` for
   some/all tickers is NORMAL, not a bug.** Morningstar actively CAPTCHA-challenges automated
   traffic; that step runs with `continue-on-error: true` in the workflow specifically because
   this is expected. Do NOT spend effort "fixing" Morningstar blocks, do NOT treat that step's
   failure/skip as a reason to flag the overall run as broken, and do NOT try to work around
   Morningstar's bot-detection (e.g. rotating user agents, adding delays/retries beyond what's
   already there, proxies) — that would cross from "best-effort scraping" into "deliberately
   evading anti-bot measures," which is a different and worse thing to automate. If Morningstar
   changes its page structure entirely (not blocking, but `status: "not_found"` for a ticker
   that used to work) that's a legitimate thing to fix in the scraper's price-extraction regex.
