#!/usr/bin/env python3
"""Step 1. Find the needs and helpers files, keep only people who agreed, hide names and emails.

Usual way (nothing to drag into a chat):
    python prepare.py --folder "/path/to/Volta peer match" [--month 2026-10] [--round] [--force]
  It finds a CSV with "need" and a CSV with "helper" in the folder, makes runs/<month>/ and writes
  runs/<month>/prepared.json there. Never overwrites a round that already has invitations (unless --force).
  --round starts the next round of the month (runs/2026-10-r2/), usually mid-month: needs that already have a
  result and helpers invited lately (cooldown_days, 30 unless changed) are left out of it.

Older way, with two explicit files:
    python prepare.py needs.csv helpers.csv [--out prepared.json]

prepared.json is the ONLY thing Claude matches on."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("needs", nargs="?")
    p.add_argument("helpers", nargs="?")
    p.add_argument("--out", default="prepared.json")
    p.add_argument("--folder")
    p.add_argument("--month")
    p.add_argument("--force", action="store_true")
    p.add_argument("--round", action="store_true", dest="new_round")
    a = p.parse_args()
    try:
        notes = []
        if a.folder:
            run, inputs = core.setup_run(a.folder, a.month, a.force, a.new_round)
            needs_path, helpers_path, out = inputs["needs"], inputs["helpers"], str(run / "prepared.json")
            notes = inputs["warnings"]
            settings = core.load_settings(a.folder)
        else:
            if not (a.needs and a.helpers):
                raise core.CheckError("give --folder, or both needs.csv and helpers.csv")
            needs_path, helpers_path, out, run, settings = a.needs, a.helpers, a.out, None, None
        needs = core.read_rows(needs_path, ["id", "topics", "note", "consent"])
        helpers = core.read_rows(helpers_path, ["id", "name", "email", "topics", "note", "consent"])
        prepared = core.prepare(needs, helpers)
        held = None
        if run:
            ledger = core.earlier_runs_ledger(a.folder, run.name, cooldown=settings["cooldown_days"])
            held = core.apply_ledger(prepared, ledger)
    except (core.CheckError, OSError) as e:
        print(f"PROBLEM: {e}")
        return 1
    core.write_json(out, prepared)
    n_need = sum(1 for e in prepared["entries"] if e["mode"] == "meet")
    n_help = sum(1 for e in prepared["entries"] if e["mode"] == "help")
    print(f"OK: {n_need} needs and {n_help} helpers can be matched. Wrote {out}. (volta-peer-match v{core.VERSION})")
    if run:
        print(f"Work folder for this month: {run}")
        print(f"Files used: {Path(needs_path).name}, {Path(helpers_path).name}")
        if settings and "laura_email" not in settings:
            print("Laura's email address is not saved yet. It is only needed when invitations are made (step 5), so do not stop for it now.")
    for n in notes:
        print(f"Note: {n}")
    if run and held:
        if held["needs_settled"]:
            print("Left out because they already have a result or an invitation in flight: " + ", ".join(held["needs_settled"]))
        if held["needs_skipped"]:
            print("Left out because Laura skipped them earlier: " + ", ".join(held["needs_skipped"]))
        if held["helpers_resting"]:
            print("Resting (invited lately, not invited again yet): "
                  + ", ".join(f"{r['help_id']} until {r['until']}" for r in held["helpers_resting"]))
    if run:
        carry = core.carried_over(a.folder, run.name, prepared)
        if carry["again"]:
            print(f"Carried over from {carry['from']}: {', '.join(carry['again'])} had no helper left last round "
                  "and are matched again this round.")
        if carry["missing"]:
            print(f"From {carry['from']}: {', '.join(carry['missing'])} had no helper left but are not in this month's "
                  "needs file (or no longer agreed). Add them back if the founder still wants help.")
    if prepared["left_out_no_consent"]:
        print("Left out (did not agree): " + ", ".join(prepared["left_out_no_consent"]))
    if prepared["do_not_pair"]:
        print("Never pair: " + ", ".join(f"{b['ask_id']}/{b['help_id']}" for b in prepared["do_not_pair"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
