#!/usr/bin/env python3
"""Step 0. Turn the Happier Hour export (one row per founder) into the two files prepare.py expects.

    python convert_export.py --folder ../data/2026-10 [--csv happier-hour.csv]

Writes needs.csv   : what each founder is stuck on         (id M01.., person P01..)
       helpers.csv : what each founder has lived through   (id H01.., same person code, name + email)

Column names come from COLUMNS below. When Laura's real export uses other names, change them here
and nowhere else. A 'Consent' column is honoured when present; without one every row counts as agreed,
which is fine for the sample and must be confirmed with Laura before any real data is used."""
import argparse
import csv
import sys
from pathlib import Path

COLUMNS = {
    "name": "Name", "company": "Company", "email": "Email",
    "stuck": "Stuck on", "lived": "Lived through", "can": "Can help with",
    "topic": "Happier Hour sign-up topic", "consent": "Consent",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True)
    p.add_argument("--csv", default="happier-hour.csv")
    a = p.parse_args()
    folder = Path(a.folder)
    src = folder / a.csv
    with open(src, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"PROBLEM: {src} has no rows")
        return 1
    C = COLUMNS
    missing = [C[k] for k in ("name", "company", "stuck", "lived", "can") if C[k] not in rows[0]]
    if missing:
        print("PROBLEM: missing columns: " + ", ".join(missing))
        return 1
    has_email, has_consent = C["email"] in rows[0], C["consent"] in rows[0]

    with open(folder / "needs.csv", "w", newline="", encoding="utf-8") as fn, \
         open(folder / "helpers.csv", "w", newline="", encoding="utf-8") as fh:
        needs, helpers = csv.writer(fn), csv.writer(fh)
        needs.writerow(["id", "person", "topics", "format", "note", "consent"])
        helpers.writerow(["id", "person", "name", "email", "role", "topics", "format", "note", "consent"])
        for i, r in enumerate(rows, 1):
            person = f"P{i:02d}"
            topic = (r.get(C["topic"]) or "").strip().lower()
            consent = (r.get(C["consent"]) or "yes").strip() if has_consent else "yes"
            email = (r.get(C["email"]) or "").strip() if has_email else \
                r[C["name"]].split()[0].lower() + "@example.com"  # sample data has no email column
            needs.writerow([f"M{i:02d}", person, topic, "advice", r[C["stuck"]].strip(), consent])
            helpers.writerow([f"H{i:02d}", person, r[C["name"]].strip(), email, "founder", topic, "chat",
                              f"{r[C['lived']].strip()}. Can help with: {r[C['can']].strip()}", consent])
    print(f"OK: {len(rows)} founders -> needs.csv and helpers.csv in {folder}"
          + ("" if has_email else " (no Email column: placeholder addresses used)")
          + ("" if has_consent else " (no Consent column: everyone treated as agreed)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
