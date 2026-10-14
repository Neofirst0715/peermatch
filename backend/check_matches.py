#!/usr/bin/env python3
"""Step 3. Check the matches Claude wrote. If anything is off, the whole file is rejected.

With the folder: python check_matches.py --folder "/path/to/Volta peer match" [--month 2026-10]
  reads runs/<month>/matches.json and prepared.json, and writes validated.json next to them.
Older way: python check_matches.py matches.json [--prepared prepared.json] [--max-asks 7] [--out validated.json]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("matches", nargs="?")
    p.add_argument("--prepared")
    p.add_argument("--max-asks", type=int)
    p.add_argument("--out")
    p.add_argument("--folder")
    p.add_argument("--month")
    a = p.parse_args()
    try:
        if a.folder:
            ctx = core.folder_context(a.folder, a.month)
            matches = a.matches or ctx["matches"]
            prepared_path = a.prepared or ctx["prepared"]
            out = a.out or ctx["validated"]
            cap = a.max_asks or ctx["settings"]["max_asks"]
        else:
            if not a.matches:
                raise core.CheckError("give matches.json or --folder")
            matches, prepared_path = a.matches, a.prepared or "prepared.json"
            out, cap = a.out or "validated.json", a.max_asks or 7
        prepared = core.read_json(prepared_path)
        try:
            data = core.read_json(matches)
        except json.JSONDecodeError:
            raise core.CheckError("matches file is not valid JSON")
        validated = core.validate_matches(data, prepared, cap)
    except (core.CheckError, OSError) as e:
        print(f"REJECTED: {e}")
        print("Do not use this file. Show Laura 'No matches this month', or write the file again.")
        return 1
    core.write_json(out, validated)
    print(f"OK: {len(validated['matches'])} needs matched, {len(validated['skipped'])} left out (cap {cap}). Wrote {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
