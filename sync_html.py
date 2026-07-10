#!/usr/bin/env python3
"""Inline data/*.json files into their corresponding HTML pages.

Run this after updating any of the JSON data files, so the dashboards work
standalone via file:// without needing a local server. The scheduled
daily-update and global-refresh agents run this automatically as their last
step (see UPDATE_INSTRUCTIONS.md and GLOBAL_UPDATE_INSTRUCTIONS.md).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# (html file, [(placeholder marker id, json file), ...])
PAGES = [
    (ROOT / "index.html", [
        ("data-latest", ROOT / "data" / "latest.json"),
        ("data-manual", ROOT / "data" / "manual_overrides.json"),
        ("data-global", ROOT / "data" / "global_latest.json"),
        ("data-morningstar", ROOT / "data" / "morningstar_crosscheck.json"),
    ]),
    (ROOT / "global-markets.html", [
        ("data-global", ROOT / "data" / "global_latest.json"),
    ]),
]


def sync_page(html_path: Path, blocks):
    html = html_path.read_text()
    for marker_id, json_path in blocks:
        if json_path.exists():
            data = json.loads(json_path.read_text())
        else:
            # Best-effort data files (e.g. morningstar_crosscheck.json) may not
            # exist yet on a fresh checkout or if that script hasn't run —
            # degrade to an empty object rather than failing the whole build.
            print(f"  [note] {json_path.name} not found, using empty placeholder for '{marker_id}'", file=sys.stderr)
            data = {}
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        pattern = rf'(<script id="{marker_id}" type="application/json">\n).*?(\n</script>)'
        html, n = re.subn(pattern, lambda m: m.group(1) + payload + m.group(2), html, count=1, flags=re.DOTALL)
        if n != 1:
            print(f"ERROR: could not find placeholder '{marker_id}' in {html_path.name}", file=sys.stderr)
            sys.exit(1)
    html_path.write_text(html)
    print(f"{html_path.name} synced with {', '.join(str(b[1].relative_to(ROOT)) for b in blocks)}")


def main():
    for html_path, blocks in PAGES:
        sync_page(html_path, blocks)


if __name__ == "__main__":
    main()
