#!/usr/bin/env python3
"""Step 5. Build the invitation for the helper who is currently invited on one need.
Run this ONLY after Laura approved and tracker.py approve succeeded.

With the folder (her address, provider and name come from settings.json):
    python make_invite.py ask-1 --folder "/path/to/Volta peer match"
Without:
    python make_invite.py ask-1 --helpers helpers.csv --laura-email laura@example.org
         [--provider gmail|outlook|outlook-personal|mailto] [--sender-name Laura] [--tracker tracker.json]
Prints JSON with to, subject, body, send_link (opens a ready-to-send email) and yes_link."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ask")
    p.add_argument("--helpers")
    p.add_argument("--laura-email")
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
        helpers_path = a.helpers or (ctx["helpers"] if ctx else None)
        laura = a.laura_email or st.get("laura_email")
        provider = a.provider or st["provider"]
        sender = a.sender_name or st["sender_name"]
        if not helpers_path:
            raise core.CheckError("give --helpers or --folder")
        if not laura:
            raise core.CheckError("Laura's email address is not known: ask her, then save it with settings.py")
        tracker = core.read_json(tracker_path)
        ask = core.find_ask(tracker, a.ask)
        if ask["status"] != "invited":
            raise core.CheckError(f"{a.ask} is {ask['status']}: Laura must approve it first")
        cand = ask["candidates"][ask["idx"]]
        rows = core.read_rows(helpers_path, ["id", "name", "email"])
        helper = next((r for r in rows if r["id"] == cand["help_id"]), None)
        if helper is None:
            raise core.CheckError(f"helper {cand['help_id']} is not in {helpers_path}")
        invite = core.build_invite(helper, cand, f"{ask['ask_id']}-{cand['help_id']}", laura, sender, provider)
    except (core.CheckError, OSError, json.JSONDecodeError) as e:
        print(f"PROBLEM: {e}")
        return 1
    print(json.dumps(invite, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
