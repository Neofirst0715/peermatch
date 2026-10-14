#!/usr/bin/env python3
"""Step 7. After a helper said yes, build the introduction email to the founder AND the helper.
This is the only script that reads the founder's name and email (optional columns in needs.csv).

With the folder:  python make_intro.py ask-1 --folder "/path/to/Volta peer match"
Without:          python make_intro.py ask-1 --needs needs.csv --helpers helpers.csv
                    [--provider gmail|outlook|outlook-personal|mailto] [--sender-name Laura] [--tracker tracker.json]
Prints JSON with to, subject, body and send_link. Laura reads it and presses Send herself."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ask")
    p.add_argument("--needs")
    p.add_argument("--helpers")
    p.add_argument("--provider", choices=core.PROVIDERS)
    p.add_argument("--sender-name")
    p.add_argument("--tracker")
    p.add_argument("--folder")
    p.add_argument("--month")
    a = p.parse_args()
    try:
        ctx = core.folder_context(a.folder, a.month, ask=a.ask) if a.folder else None
        st = ctx["settings"] if ctx else core.DEFAULT_SETTINGS
        tracker_path = a.tracker or (ctx["tracker"] if ctx else "tracker.json")
        needs_path = a.needs or (ctx["needs"] if ctx else None)
        helpers_path = a.helpers or (ctx["helpers"] if ctx else None)
        if not (needs_path and helpers_path):
            raise core.CheckError("give --needs and --helpers, or --folder")
        provider = a.provider or st["provider"]
        sender = a.sender_name or st["sender_name"]
        tracker = core.read_json(tracker_path)
        ask = core.find_ask(tracker, a.ask)
        if ask["status"] not in ("yes", "introduced"):
            raise core.CheckError(f"{a.ask} is {ask['status']}: the helper must say yes first")
        hid = ask["candidates"][ask["idx"]]["help_id"]
        founder = next((r for r in core.read_rows(needs_path, ["id"]) if r["id"] == ask["ask_id"]), None)
        helper = next((r for r in core.read_rows(helpers_path, ["id"]) if r["id"] == hid), None)
        if founder is None or helper is None:
            raise core.CheckError("the founder or the helper is missing from the files")
        intro = core.build_intro(founder, helper, sender, provider, account=st.get("laura_email"))
    except (core.CheckError, OSError, json.JSONDecodeError) as e:
        print(f"PROBLEM: {e}")
        return 1
    print(json.dumps(intro, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
