#!/usr/bin/env python3
"""Step 5. Keeps track of who was invited, who said yes or no. One helper at a time.

  python tracker.py init validated.json          (with --folder, validated.json is found for you)
  python tracker.py status                       the table, then "Needs attention"
  python tracker.py approve ask-1                Laura approved: the current helper is now invited
  python tracker.py sent ask-1 [--date D]        Laura SENT the invitation (the 3-day clock starts here)
  python tracker.py yes ask-1 [--date D]         the helper said yes
  python tracker.py no ask-1                     the helper said not now: next helper is up
  python tracker.py noreply ask-1                no reply: next helper is up
  python tracker.py question ask-1 [--date D]    the helper asked a question instead of answering: counts as an
                                                 answer, stops the reminder, Laura replies herself
  python tracker.py skip ask-1                   Laura skips this need
  python tracker.py introduced ask-1 [--date D]  Laura sent the introduction
  python tracker.py told ask-1 [--date D]        Laura told the founder that nobody is left (for now)
  python tracker.py due [--days 3]               invitations sent that many days ago with no answer
  python tracker.py report [--no-names]          the month so far: invitations, YES, introductions, % answered in time,
                                                 and which founders are introduced and which are still open
--date is for when you learn about something later (for example from the Sent folder): YYYY-MM-DD.
Add --folder "/path/to/Volta peer match" to use that month's tracker (the latest run, or --month 2026-10),
or --tracker path.json to use a specific file (default tracker.json)."""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vpm_core as core  # noqa: E402


def show(tracker):
    for a in tracker["asks"]:
        cur = core.current_candidate(tracker, a)
        who = cur["help_id"] if cur else "-"
        hist = ", ".join(f"{h['help_id']}:{h['outcome']}" for h in a["history"]) or "-"
        since = ""
        if a["status"] == "invited":
            since = f" sent {a['sent_at']}" if a.get("sent_at") else f" prepared {a.get('invited_at', '?')}, not marked sent"
            if a.get("question_at"):
                since += f", the helper asked a question on {a['question_at']}"
        note = ""
        if a["status"] == "pending" and cur is None:
            note = "  (everyone who fits is invited for another need)"
        live = core.active_reminders(a)
        if live:
            since += ", reminder " + ", ".join(r["date"] for r in live)
        print(f"{a['aid']:7} need {a['ask_id']:5} {a['status']:10} helper {who:5} history {hist}{since}{note}")
    if tracker.get("skipped"):
        print("Left out: " + ", ".join(f"{s['id']} ({s['reason']})" for s in tracker["skipped"]))


def show_attention(tracker, days):
    att = core.attention(tracker, days)
    when = lambda d, word: f"{word} {d} days ago" if d is not None else "date unknown"
    lines = []
    if att["no_helper_left"]:
        lines.append(f"- {len(att['no_helper_left'])} need(s) have NO helper left and the founder has not been told: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']})" for r in att["no_helper_left"]))
    if att["questions"]:
        lines.append(f"- {len(att['questions'])} helper(s) asked a question and are waiting for Laura's reply: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']}, {when(r['days'], 'asked')})" for r in att["questions"]))
    if att["yes_not_introduced"]:
        lines.append(f"- {len(att['yes_not_introduced'])} helper(s) said yes but no introduction is marked as sent: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']}, {when(r['days'], 'yes')})" for r in att["yes_not_introduced"]))
    if att["overdue_invitations"]:
        lines.append(f"- {len(att['overdue_invitations'])} invitation(s) were sent {days} days ago or more with no answer: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']}, {r['days']} days)" for r in att["overdue_invitations"]))
    if att["not_sent"]:
        lines.append(f"- {len(att['not_sent'])} invitation(s) were prepared but are not marked as sent: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']}, {when(r['days'], 'prepared')})" for r in att["not_sent"]))
    if att["waiting_approval"]:
        first = att["waiting_approval"][0]["days"]
        lines.append(f"- {len(att['waiting_approval'])} need(s) still waiting for Laura to approve or skip: "
                     + ", ".join(f"{r['aid']} ({r['ask_id']})" for r in att["waiting_approval"])
                     + (f" (list made {first} days ago)" if first is not None else ""))
    print("Needs attention:" if lines else "Nothing needs attention.")
    for line in lines:
        print(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["init", "status", "due", "report", "approve", "sent", "yes", "no", "noreply",
                                       "skip", "introduced", "told", "question"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--tracker")
    p.add_argument("--folder")
    p.add_argument("--month")
    p.add_argument("--days", type=int)
    p.add_argument("--date")
    p.add_argument("--no-names", action="store_true")
    a = p.parse_args()
    try:
        ask_commands = ("approve", "sent", "yes", "no", "noreply", "skip", "introduced", "told", "question")
        ctx = None
        if a.folder:
            ctx = core.folder_context(a.folder, a.month, ask=a.arg if a.command in ask_commands else None)
        tracker_path = a.tracker or (ctx["tracker"] if ctx else "tracker.json")
        days = a.days or (ctx["settings"]["remind_days"] if ctx else core.DEFAULT_SETTINGS["remind_days"])
        when = None
        if a.date:
            try:
                when = datetime.date.fromisoformat(a.date)
            except ValueError:
                raise core.CheckError("--date must look like 2026-10-04")
            if when > datetime.date.today():
                raise core.CheckError("--date is in the future")
        if a.command == "init":
            source = a.arg or (ctx["validated"] if ctx else None)
            if not source:
                raise core.CheckError("init needs validated.json (or --folder)")
            validated = core.read_json(source)
            start = core.next_ask_number(a.folder, ctx["run"]) if ctx else 1
            core.write_json(tracker_path, core.build_tracker(validated, start=start))
            replaced = core.supersede_earlier_asks(a.folder, ctx["run"], validated["matches"]) if ctx else []
            print(f"OK: wrote {tracker_path}")
            if replaced:
                print("These asks from an earlier round are matched again here and can no longer be approved there: "
                      + ", ".join(replaced))
            show(core.read_json(tracker_path))
            return 0
        whole = core.combined_tracker(a.folder, ctx["run"]) if ctx else None
        # the newest round may have been prepared but not matched yet, so it has no tracker: only commands about one ask need it
        tracker = whole if (ctx and a.command in ("status", "due", "report")) else core.read_json(tracker_path)
        if a.command == "status":
            if ctx:
                runs = core.month_runs(a.folder, ctx["run"])
                for rp in runs:
                    if (rp / "tracker.json").exists():
                        if len(runs) > 1:
                            print(f"-- round {core.run_sort_key(rp.name)[1]} ({rp.name})")
                        show(core.read_json(rp / "tracker.json"))
                show_attention(whole, days)
            else:
                show(tracker)
                show_attention(tracker, days)
            return 0
        if a.command == "report":
            names = {}
            if ctx and not a.no_names:
                try:
                    names = {r["id"]: r.get("name", "") for r in core.read_rows(ctx["needs"], ["id"])}
                except (OSError, core.CheckError):
                    names = {}
            target = ctx["settings"]["answer_target"] if ctx else core.DEFAULT_SETTINGS["answer_target"]
            print(core.render_report(core.monthly_report(whole or tracker, days, names=names, target=target)))
            return 0
        if a.command == "due":
            due = core.due_invitations(whole or tracker, days)
            if not due:
                print(f"Nothing has waited {days} days or more.")
            for d in due:
                print(f"{d['aid']} (need {d['ask_id']}, helper {d['help_id']}) has waited {d['days']} days. "
                      "Ask Laura: no reply, try the next helper?")
            return 0
        if not a.arg:
            raise core.CheckError(f"{a.command} needs a need id such as ask-1")
        ask = core.find_ask(tracker, a.arg)
        if a.command == "approve":
            extra = core.busy_in_other_rounds(a.folder, ctx["run"]) if ctx else ()
            cand = core.approve(tracker, ask, today=when, extra_busy=extra)
            result = {"ask": ask["aid"], "ask_id": ask["ask_id"], "help_id": cand["help_id"],
                      "ref": f"{ask['ask_id']}-{cand['help_id']}"}
            core.write_json(tracker_path, tracker)
            print(json.dumps(result))
            return 0
        core.record(tracker, ask, a.command, today=when)
        core.write_json(tracker_path, tracker)
        nxt = core.current_candidate(tracker, ask)
        print(f"OK: {ask['aid']} is now {ask['status']}" + (f", next helper {nxt['help_id']}" if nxt and ask["status"] == "pending" else ""))
        return 0
    except (core.CheckError, OSError, json.JSONDecodeError) as e:
        print(f"PROBLEM: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
