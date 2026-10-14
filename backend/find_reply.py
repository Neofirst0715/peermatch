#!/usr/bin/env python3
"""Step 6. A helper's reply came in. Which invitation is it about?

With the folder: python find_reply.py --sender helper@example.com [--ref M01-H01] --folder "/path/to/Volta peer match"
Without:         python find_reply.py --sender ... [--ref ...] --helpers helpers.csv [--tracker tracker.json]
Uses the Ref code if given, otherwise the sender's address. If it is unclear it says so: it never guesses."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sender")
    p.add_argument("--ref")
    p.add_argument("--helpers")
    p.add_argument("--tracker")
    p.add_argument("--folder")
    p.add_argument("--month")
    a = p.parse_args()
    try:
        if not a.sender and not a.ref:
            raise core.CheckError("give --sender, --ref or both")
        ctx = core.folder_context(a.folder, a.month) if a.folder else None
        helpers_path = a.helpers or (ctx["helpers"] if ctx else None)
        if not helpers_path:
            raise core.CheckError("give --helpers or --folder")
        helper_rows = core.read_rows(helpers_path, ["id", "email"])
        paths = [a.tracker] if a.tracker else ([str(rp / "tracker.json") for rp in core.month_runs(a.folder, ctx["run"])
                                                if (rp / "tracker.json").exists()] if ctx else ["tracker.json"])
        hits, last_error = [], None
        for tp in paths:                       # a reply may belong to any round of the month
            try:
                hits.append(core.find_reply(core.read_json(tp), helper_rows, sender=a.sender, ref=a.ref))
            except core.CheckError as e:
                last_error = e
        if not hits:
            raise last_error or core.CheckError("no open invitation matches this reply")
        if len(hits) > 1:
            raise core.CheckError("the reply fits invitations in more than one round: ask Laura, or use the Ref code")
        found = hits[0]
    except (core.CheckError, OSError, json.JSONDecodeError) as e:
        print(f"PROBLEM: {e}")
        return 1
    print(json.dumps(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
