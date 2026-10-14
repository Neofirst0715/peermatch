#!/usr/bin/env python3
"""One command for the month.

    python run_month.py --folder ../data/2026-10            full run, calls the Claude API in step 2
    python run_month.py --folder ../data/2026-10 --no-api   skip step 2 and use the matches.json already there

Steps, each its own script so Rishabh can read or rerun one at a time:
  0  convert_export.py   happier-hour.csv -> needs.csv + helpers.csv
  1  prepare.py          -> prepared.json          names, emails and person codes removed
  2  match.py            -> matches.json           THE CLAUDE API CALL (the only one)
  3  check_matches.py    -> validated.json         rejects anything that breaks the rules
  4  tracker.py init     -> tracker.json           who is invited, who said yes
  5  build_data.py       -> frontend/data.json     what the page shows

Nothing here sends email or reads an inbox."""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(step, *args):
    print(f"\n== {step}")
    r = subprocess.run([sys.executable, str(HERE / step), *args], text=True)
    if r.returncode != 0:
        print(f"Stopped at {step}.")
        sys.exit(r.returncode)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True)
    p.add_argument("--max-asks", default="10")
    p.add_argument("--no-api", action="store_true", help="reuse matches.json instead of calling Claude")
    p.add_argument("--provider", default="claude", help="claude (default) or deepseek, passed to match.py")
    a = p.parse_args()
    f = Path(a.folder).resolve()
    run("convert_export.py", "--folder", str(f))
    run("prepare.py", str(f / "needs.csv"), str(f / "helpers.csv"), "--out", str(f / "prepared.json"))
    if a.no_api:
        if not (f / "matches.json").exists():
            print("PROBLEM: --no-api but there is no matches.json in the folder.")
            return 1
        print("\n== match.py skipped (--no-api), using the existing matches.json")
    else:
        run("match.py", "--folder", str(f), "--max-asks", a.max_asks, "--provider", a.provider)
    run("check_matches.py", str(f / "matches.json"), "--prepared", str(f / "prepared.json"),
        "--max-asks", a.max_asks, "--out", str(f / "validated.json"))
    run("tracker.py", "init", str(f / "validated.json"), "--tracker", str(f / "tracker.json"))
    run("build_data.py", "--folder", str(f))
    print("\nDone. Open frontend/index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
