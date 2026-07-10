# Rules for any automated agent (scheduled task, CI job, or Claude session) touching this repo

This file exists because the pipeline broke once already: a scheduled agent rewrote the
data schema, the fetch scripts, and the entire `index.html` (adding Chart.js, new sections,
an external RSS call, and a `ALPHA_VANTAGE_KEY` GitHub secret) without updating
`global-markets.html` to match — the live site crashed for days before anyone noticed.
These rules exist to stop that class of failure from recurring, silently or otherwise.

## Hard rules

1. **Never push a change that breaks `scripts/validate_pages.py`.** That script actually
   loads both HTML pages in a headless browser and checks for console errors, uncaught
   exceptions, and known failure-text markers. If you changed a data schema (added/renamed/
   removed a field in `data/latest.json`, `data/global_latest.json`, or
   `data/manual_overrides.json`), you MUST update every HTML page that reads that field in
   the same change, then run `python scripts/validate_pages.py` locally/in-CI and confirm it
   passes before committing. The GitHub Actions workflow already gates the commit/push step
   on this — do not bypass, skip, or weaken that gate.
2. **Don't redesign, add libraries, add external API calls/secrets, or add new data sections
   unless the user explicitly asked for that in the current task.** Keeping data fresh is not
   license to restyle the dashboard, swap frameworks, or expand scope. If you think a change
   would clearly help, say so and ask — don't just do it during a routine data-refresh run.
3. **If you add a new GitHub Actions secret, a new third-party API dependency, or any new
   credential, say so explicitly in the commit message and (if this is an interactive
   session) tell the user directly** — don't let it happen silently inside an autonomous run.
4. **Only one system should own writing `data/*.json` and pushing to `main` at a time.**
   Currently that's the `update-dashboard.yml` GitHub Actions workflow. If you're a
   Claude-scheduled task, check whether GitHub Actions already owns this before adding a
   second automated writer — two systems racing on the same files is how corrupted/
   conflicting commits happen.
5. **Prefer failing loudly over publishing something broken.** If data can't be fetched or
   a page won't validate, let the job fail (it's visible in the Actions tab and to anyone
   who checks) rather than pushing a best-effort guess that might crash the live site.

## Where things live
- `data/latest.json` — India dashboard data, updated by `scripts/fetch_market_data.py`
- `data/global_latest.json` — Global markets data, updated by `scripts/fetch_global_data.py`
- `data/manual_overrides.json` — fields with no reliable free API (see its own `_comment`)
- `sync_html.py` — inlines the JSON files into `index.html` / `global-markets.html`
- `scripts/validate_pages.py` — the safety net; run it after any change touching data shape
  or the HTML/JS that reads it
- `.github/workflows/update-dashboard.yml` — the only automated writer to `main`
