#!/usr/bin/env python3
"""Step 5. Turn the checked matches into the one file the page reads: frontend/data.json.

    python build_=ata.py --folder ../data/2026-10 [--out ../frontend/data.json]

Reads  happier-hour.csv  (for the Directory: name, company, stage, what they entered)
       helpers.csv       (helper emails for the invitation)
       validated.json    (only matches that passed check_matches.py; never matches.json directly)
       settings.json     (optional: laura_email, sender_name, provider)
Writes data.json         {items, left, people, total}

Names appear here because this file is for Laura's page, which only she opens. The AI step
never sees it. Swaps are decided here, by code: A's first helper is B and B's first helper is A."""
import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402
from convert_export import COLUMNS as C  # noqa: E402

DEFAULTS = {"laura_email": "laura@example.com", "sender_name": "Laura", "provider": "gmail"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True)
    p.add_argument("--csv", default="happier-hour.csv")
    p.add_argument("--out", default=str(Path(__file__).parent.parent / "frontend" / "data.json"))
    a = p.parse_args()
    folder = Path(a.folder)
    settings = dict(DEFAULTS)
    if (folder / "settings.json").exists():
        settings.update(core.read_json(folder / "settings.json"))

    with open(folder / a.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    helpers = {h["id"]: h for h in core.read_rows(folder / "helpers.csv", ["id", "name", "email"])}
    v = core.read_json(folder / "validated.json")
    P = lambda code: rows[int(code[1:]) - 1]  # M07 / H07 -> row 7
    yes = lambda r, col: (r.get(col) or "").strip().lower() == "yes"

    def meet(x, y):
        if yes(x, "Going to next Founders Lunch") and yes(y, "Going to next Founders Lunch"):
            return "Founders Lunch"
        if yes(x, "Going to next CEO Breakfast") and yes(y, "Going to next CEO Breakfast"):
            return "CEO Breakfast"
        return ""

    first = {m["ask_id"]: m["candidates"][0]["help_id"] for m in v["matches"]}
    items = []
    for m in v["matches"]:
        f = P(m["ask_id"])
        cands = []
        for c in m["candidates"]:
            h, ref = P(c["help_id"]), f"{m['ask_id']}-{c['help_id']}"
            inv = core.build_invite(helpers[c["help_id"]], c, ref, settings["laura_email"],
                                    settings["sender_name"], settings["provider"])
            cands.append({"hid": c["help_id"], "ref": ref, "name": h[C["name"]], "company": h[C["company"]],
                          "role": h.get("Role", ""), "lived": h[C["lived"]], "reason": c["reason"],
                          "to": inv["to"], "subject": inv["subject"], "body": inv["body"],
                          "link": inv["send_link"], "meet": meet(f, h)})
        partner = "M" + first[m["ask_id"]][1:]           # the need of my first helper
        mutual = first.get(partner) == "H" + m["ask_id"][1:]
        items.append({"id": m["ask_id"], "name": f[C["name"]], "company": f[C["company"]],
                      "email": helpers["H" + m["ask_id"][1:]]["email"], "doing": f.get("Working on now", ""),
                      "stuck": f[C["stuck"]], "topic": f.get(C["topic"], ""), "cands": cands,
                      "swap": partner if mutual else ""})
    left = [{"id": s["id"], "name": P(s["id"])[C["name"]], "company": P(s["id"])[C["company"]],
             "stuck": P(s["id"])[C["stuck"]], "reason": s["reason"]} for s in v["skipped"]]
    matched = {i["id"] for i in items}
    people = []
    for k, r in enumerate(rows, 1):
        code = f"M{k:02d}"
        people.append({"id": code, "hid": f"H{k:02d}", "name": r[C["name"]], "company": r[C["company"]],
                       "role": r.get("Role", ""), "what": r.get("What the company does", ""),
                       "stage": r.get("Stage", ""), "size": r.get("Team size", ""), "loc": r.get("Location", ""),
                       "comes": r.get("Comes into Volta", ""), "topic": r.get(C["topic"], ""),
                       "doing": r.get("Working on now", ""), "stuck": r[C["stuck"]], "lived": r[C["lived"]],
                       "can": r[C["can"]], "lunch": yes(r, "Going to next Founders Lunch"),
                       "breakfast": yes(r, "Going to next CEO Breakfast"),
                       "email": helpers[f"H{k:02d}"]["email"], "matched": code in matched})
    data = {"month": folder.name, "laura_email": settings["laura_email"], "items": items, "left": left,
            "people": people, "total": len(rows),
            "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    core.write_json(a.out, data)
    js = Path(a.out).with_suffix('.js')  # same content for file:// use, where fetch is blocked
    js.write_text('window.VPM_DATA=' + json.dumps(data, ensure_ascii=False) + ';\n', encoding='utf-8')
    swaps = [i["id"] for i in items if i["swap"]]
    print(f"OK: {len(items)} matches ({len(swaps)//2} swap), {len(left)} without. Wrote {a.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
