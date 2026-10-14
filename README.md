# Volta Peer Match

Founders who are stuck hear from founders who have been through it. Laura reviews one list a
month; nothing is sent until she says so.

## Layout

```
backend/     Python scripts, one per step. match.py is the only file that calls the Claude API.
frontend/    Static page (index.html, styles.css, app.js). Reads data.json. No build step.
data/YYYY-MM/ One folder per month: the export, the intermediate files, the tracker.
```

## Setup

macOS's system Python is externally managed, so install into the project's virtualenv instead of
globally:

```
python3 -m venv .venv
.venv/bin/python3 -m pip install anthropic openai
```

Use `.venv/bin/python3` below, or `source .venv/bin/activate` once per shell and then just `python3`.

## Monthly run

```
export ANTHROPIC_API_KEY=...          # Volta's key, never written to a file
.venv/bin/python3 backend/run_month.py --folder data/2026-10
open frontend/index.html
```

`--no-api` reuses the `matches.json` already in the folder (how the demo was produced).

## Run with the local server

```
cp .env.example .env   # fill in the key
.venv/bin/python3 backend/server.py
```

`.env` is read once at startup, only to fill in variables not already set in the shell; it is not
written to and should not be given to anyone else (it's in `.gitignore`).

The browser opens http://localhost:8787/ by itself. Uploading the CSV on the Import page runs the
whole month; Laura's actions are saved automatically to `data/<month>/tracker-page.json`.
Double-clicking `index.html` still works, but read-only: no upload.

The server uses only the Python standard library and listens on 127.0.0.1. The API key stays in the
environment (`ANTHROPIC_API_KEY` or `DEEPSEEK_API_KEY`), the same as for `run_month.py`. Without
`--provider`, it uses `VPM_PROVIDER`, then `claude`. `--port` changes the port.

## Steps and files

| Step | Script | Reads | Writes | Notes |
|---|---|---|---|---|
| 0 | convert_export.py | happier-hour.csv | needs.csv, helpers.csv | Column names live here only |
| 1 | prepare.py | needs.csv, helpers.csv | prepared.json | Removes names, emails, person codes |
| 2 | **match.py** | prepared.json, references/matching-rules.md | matches.json | **Claude API.** JSON schema output, temperature 0, one retry |
| 3 | check_matches.py | matches.json, prepared.json | validated.json | Rejects anything off the rules; no silent repair |
| 4 | tracker.py init | validated.json | tracker.json | One open invitation per helper |
| 5 | build_data.py | validated.json, the CSV, helpers.csv | frontend/data.json (+ data.js) | Names come back here, for Laura's page only |

Laura's actions on the page (approve, record a reply, mark introduced) live in the browser.
"Download tracker.json" on the Review page saves them to the month folder.

## What Claude sees and does not see

- Sees: the text founders typed about what they are stuck on and what they have lived through,
  as codes (M01, H07), plus the matching rules.
- Does not see: names, emails, companies, person codes, the original CSV.
- Does not do: send email, read email, approve anything. Its output is a proposal that
  `check_matches.py` can reject.

## Before real data

- A `Consent` column in the export (founders agree their answer may be used for introductions).
- Laura's real column names in `convert_export.py`, her address in `data/<month>/settings.json`
  (`{"laura_email": "...", "sender_name": "Laura", "provider": "gmail"}`).
- Where the key lives (a scheduled script or a small service), and who can open the page.
