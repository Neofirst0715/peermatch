"""Shared logic for the volta-peer-match skill. Standard library only, no internet."""
import csv
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

VERSION = "1.3"   # shown in script output so you can tell which version is running
HYPE_WORDS = {"perfect", "perfectly", "ideal", "amazing", "excellent",
              "fantastic", "incredible", "best", "great"}
MAX_WORDS = 25
MAX_CANDIDATES = 3
TRUE_WORDS = {"true", "yes", "y", "1", "x"}
EMAIL_RE = re.compile(r"^[^@\s?&,;<>]+@[^@\s?&,;<>]+\.[^@\s?&,;<>]+$")
BUSY = ("invited", "yes", "introduced")   # statuses where the current candidate's helper is "busy"
OPEN = BUSY


class CheckError(Exception):
    """Something is wrong with the input or with Claude's matching."""


def load_dotenv(path=None):
    """Read KEY=VALUE lines from the project's .env file into os.environ, skipping blank lines
    and lines starting with #, and only filling keys not already set (so a real export wins)."""
    path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------- reading files

def is_yes(value):
    return str(value or "").strip().lower() in TRUE_WORDS


def split_topics(text):
    return [t.strip().lower() for t in re.split(r"[;,]", text or "") if t.strip()]


def read_rows(path, required):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [(c or "").strip().lower() for c in (reader.fieldnames or [])]
        missing = [c for c in required if c not in cols]
        if missing:
            raise CheckError(f"{path}: missing column(s): {', '.join(missing)}")
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()} for raw in reader]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- the folder, the runs, the settings

SETTINGS_FILE = "settings.json"
DEFAULT_SETTINGS = {"provider": "gmail", "sender_name": "Laura", "max_asks": 7, "reply_label": "volta-replies", "remind_days": 3,
                    "answer_target": 80, "cooldown_days": 30}
SETTING_KEYS = ("laura_email", "provider", "sender_name", "max_asks", "reply_label", "remind_days", "answer_target", "cooldown_days")


def find_inputs(folder):
    """Find needs and helpers files in Laura's folder, so nothing has to be dragged into a chat.
    Looks only at the top level of the folder: a CSV with 'need' / 'helper' in its name.
    Returns the paths and any warnings. Never reads the contents."""
    folder = Path(folder)
    if not folder.is_dir():
        raise CheckError(f"{folder} is not a folder")
    files = [p for p in folder.iterdir()
             if p.is_file() and not p.name.startswith((".", "~$"))]
    found, warnings = {}, []
    for key, word in (("needs", "need"), ("helpers", "helper")):
        csvs = sorted((p for p in files if p.suffix.lower() == ".csv" and word in p.name.lower()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        others = [p for p in files if p.suffix.lower() in (".numbers", ".xlsx", ".xls") and word in p.name.lower()]
        if not csvs:
            if others:
                raise CheckError(f"found {others[0].name} but no {key} CSV: export it as CSV into the same folder")
            raise CheckError(f"no {key} CSV in {folder}: put a CSV with '{word}' in its name there")
        found[key] = csvs[0]
        if len(csvs) > 1:
            warnings.append(f"several {key} files: using the newest, {csvs[0].name}; ignoring "
                            + ", ".join(p.name for p in csvs[1:]))
        for o in others:
            if o.stat().st_mtime > csvs[0].stat().st_mtime + 1:
                warnings.append(f"{o.name} is newer than {csvs[0].name}: if you edited it, export the CSV again")
    return {"needs": str(found["needs"]), "helpers": str(found["helpers"]), "warnings": warnings}


RUN_RE = re.compile(r"^(\d{4}-\d{2})(?:-r(\d+))?$")


def run_sort_key(name):
    m = RUN_RE.match(name)
    return (m.group(1), int(m.group(2) or 1)) if m else (name, 1)


def run_base(name):
    """2026-10 and 2026-10-r2 are rounds of the same month."""
    return run_sort_key(name)[0]


def run_dir(folder, month):
    return Path(folder) / "runs" / month


def list_runs(folder):
    runs = Path(folder) / "runs"
    return sorted((p.parent for p in runs.glob("*/run.json")), key=lambda p: run_sort_key(p.name)) if runs.is_dir() else []


def month_runs(folder, run_name):
    return [p for p in list_runs(folder) if run_base(p.name) == run_base(run_name)]


def latest_run_dir(folder):
    found = list_runs(folder)
    if not found:
        raise CheckError("no run in this folder yet: start one with prepare.py --folder")
    return found[-1]


def locate_ask_run(folder, aid):
    """Ask numbers continue from round to round, so a number belongs to one run. Newest first."""
    for p in reversed(list_runs(folder)):
        t = p / "tracker.json"
        if t.exists() and any(a["aid"] == aid for a in read_json(t)["asks"]):
            return p
    raise CheckError(f"no such need: {aid}")


def setup_run(folder, month=None, force=False, new_round=False):
    """Make the folder for this round's work. Never overwrites a round that already has invitations."""
    base = month or datetime.date.today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", base):
        raise CheckError("month must look like 2026-10")
    inputs = find_inputs(folder)
    existing = [p for p in list_runs(folder) if run_base(p.name) == base]
    n = 1
    if new_round:
        n = max([run_sort_key(p.name)[1] for p in existing] or [0]) + 1
    name = base if n == 1 else f"{base}-r{n}"
    d = run_dir(folder, name)
    if (d / "tracker.json").exists() and not force:
        raise CheckError(f"a run for {name} already exists and has invitations. Start the next round with --round, "
                         "continue this one with tracker.py status --folder, or use --force to start over")
    d.mkdir(parents=True, exist_ok=True)
    if force:
        for fname in ("validated.json", "tracker.json", "matches.json"):
            (d / fname).unlink(missing_ok=True)
    write_json(d / "run.json", {"month": base, "run": name, "round": n,
                                "needs_file": Path(inputs["needs"]).name,
                                "helpers_file": Path(inputs["helpers"]).name,
                                "created": datetime.date.today().isoformat()})
    return d, inputs


def next_ask_number(folder, run_name):
    """Ask numbers keep counting across the rounds of a month: round 2 starts after the last ask of round 1."""
    top = 0
    for p in month_runs(folder, run_name):
        if p.name == run_name or not (p / "tracker.json").exists():
            continue
        for a in read_json(p / "tracker.json")["asks"]:
            top = max(top, int(a["aid"].split("-")[-1]))
    return top + 1


def folder_context(folder, month=None, ask=None):
    """All the paths and settings for a run. `month` is a run name (2026-10 or 2026-10-r2). With `ask`, the run that holds it."""
    if month:
        d = run_dir(folder, month)
    elif ask:
        d = locate_ask_run(folder, ask)
    else:
        d = latest_run_dir(folder)
    if not (d / "run.json").exists():
        raise CheckError(f"no run for {month} in {folder}")
    meta = read_json(d / "run.json")
    return {"dir": d, "month": meta["month"], "run": d.name,
            "needs": str(Path(folder) / meta["needs_file"]),
            "helpers": str(Path(folder) / meta["helpers_file"]),
            "prepared": str(d / "prepared.json"), "matches": str(d / "matches.json"),
            "validated": str(d / "validated.json"), "tracker": str(d / "tracker.json"),
            "settings": load_settings(folder)}


def load_settings(folder):
    p = Path(folder) / SETTINGS_FILE
    out = dict(DEFAULT_SETTINGS)
    if p.exists():
        out.update(read_json(p))
    return out


def save_settings(folder, updates):
    """Validate and store Laura's settings (her address, provider, cap, reply label)."""
    clean = {}
    for key, value in updates.items():
        if key not in SETTING_KEYS:
            raise CheckError(f"unknown setting {key}")
        value = str(value).strip()
        if key == "laura_email" and not EMAIL_RE.match(value):
            raise CheckError("laura_email is not a valid address")
        if key == "provider" and value not in PROVIDERS:
            raise CheckError(f"provider must be one of {', '.join(PROVIDERS)}")
        if key == "max_asks":
            if not value.isdigit() or not 1 <= int(value) <= 50:
                raise CheckError("max_asks must be a number from 1 to 50")
            value = int(value)
        if key == "remind_days":
            if not value.isdigit() or not 1 <= int(value) <= 30:
                raise CheckError("remind_days must be a number from 1 to 30")
            value = int(value)
        if key == "cooldown_days":
            if not value.isdigit() or not 1 <= int(value) <= 180:
                raise CheckError("cooldown_days must be a number from 1 to 180")
            value = int(value)
        if key == "answer_target":
            if not value.isdigit() or not 1 <= int(value) <= 100:
                raise CheckError("answer_target must be a number from 1 to 100 (a percentage)")
            value = int(value)
        if key in ("sender_name", "reply_label") and (not value or len(value) > 60 or '"' in value):
            raise CheckError(f"{key} must be 1 to 60 characters, without quotes")
        clean[key] = value
    p = Path(folder) / SETTINGS_FILE
    current = read_json(p) if p.exists() else {}
    current.update(clean)
    write_json(p, current)
    return current


# ---------------------------------------------------------------- step 1: prepare

def prepare(need_rows, helper_rows):
    """Keep only people who agreed. Remove names, emails and person ids before Claude sees anything.
    Returns the data Claude matches on, the pairs that must never be made, and who was left out."""
    seen, eligible, no_consent = set(), [], []
    for mode, rows in (("meet", need_rows), ("help", helper_rows)):
        for r in rows:
            if not r.get("id"):
                raise CheckError("a row has no id")
            if r["id"] in seen:
                raise CheckError(f"duplicate id {r['id']}")
            seen.add(r["id"])
            if not is_yes(r.get("consent")):
                no_consent.append(r["id"])
                continue
            eligible.append({"mode": mode, "id": r["id"], "person": r.get("person", ""),
                             "role": r.get("role") or "founder",
                             "topics": split_topics(r.get("topics")),
                             "format": r.get("format") or None,
                             "note": r.get("note", "")})
    blocked = sorted({(a["id"], h["id"])
                      for a in eligible if a["mode"] == "meet"
                      for h in eligible if h["mode"] == "help"
                      if a["person"] and a["person"] == h["person"]})
    visible = [{k: e[k] for k in ("id", "role", "mode", "topics", "format", "note")} for e in eligible]
    return {"entries": visible,
            "do_not_pair": [{"ask_id": a, "help_id": h} for a, h in blocked],
            "left_out_no_consent": no_consent}


# ---------------------------------------------------------------- step 3: check Claude's matches

def _one_sentence(text):
    text = text.strip()
    return text.endswith(".") and len(re.findall(r"[.!?](\s|$)", text)) == 1


def _check_sentence(text, label):
    if not isinstance(text, str) or "\n" in text or not _one_sentence(text):
        raise CheckError(f"{label} is not one sentence")
    words = re.findall(r"[A-Za-z']+", text.lower())
    if len(words) > MAX_WORDS:
        raise CheckError(f"{label} is too long")
    if HYPE_WORDS & set(words):
        raise CheckError(f"hype word in {label}")
    return text.strip()


# Words that describe WHAT KIND of company or product a founder has. The invitation goes to a helper before the founder
# has agreed to be named, so it may say the topic ("SOC 2") but not these, unless the helper's own words use them.
DETAIL_WORDS = {"b2b", "b2c", "saas", "software", "product", "products", "app", "apps", "platform", "enterprise",
                "startup", "company", "fintech", "healthtech", "edtech", "marketplace"}


def _stem(word):
    word = word.lower()
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def _stems(text):
    return [_stem(w) for w in re.findall(r"[A-Za-z0-9]+", (text or "").lower())]


def _check_invite_detail(invite, helper, label):
    """The invite line names the topic ("SOC 2", "HIPAA compliance"), never what kind of company or product the founder has.
    A word from the list is allowed only when the helper's own words use it (a helper may have worked on "clinic software")."""
    helper_words = set(_stems(helper.get("note", ""))) | set(_stems(" ".join(helper.get("topics", []))))
    leaked = sorted({w for w in re.findall(r"[A-Za-z0-9]+", invite.lower())
                     if w in DETAIL_WORDS and _stem(w) not in helper_words})
    if leaked:
        raise CheckError(f"{label} describes the founder's company or product ({', '.join(leaked)}): "
                         "name the topic only")


def validate_matches(data, prepared, max_asks):
    """Returns {"matches": [...], "skipped": [...]} or raises CheckError. Nothing is repaired."""
    if not isinstance(data, dict) or not isinstance(data.get("matches"), list) \
            or not isinstance(data.get("skipped"), list):
        raise CheckError("matches file does not have the expected shape")
    by_id = {e["id"]: e for e in prepared["entries"]}
    blocked = {(b["ask_id"], b["help_id"]) for b in prepared["do_not_pair"]}
    if len(data["matches"]) > max_asks:
        raise CheckError("more needs than the cap")

    matches, seen_asks, first_choices = [], set(), set()
    for m in data["matches"]:
        if not isinstance(m, dict):
            raise CheckError("a match is not an object")
        a = m.get("ask_id")
        if a not in by_id or by_id[a]["mode"] != "meet":
            raise CheckError(f"unknown or wrong-role need {a}")
        if a in seen_asks:
            raise CheckError(f"need {a} appears twice")
        cands = m.get("candidates")
        if not isinstance(cands, list) or not 1 <= len(cands) <= MAX_CANDIDATES:
            raise CheckError(f"need {a} must have 1 to {MAX_CANDIDATES} candidates")
        out, seen_helps = [], set()
        for rank, c in enumerate(cands):
            if not isinstance(c, dict):
                raise CheckError("a candidate is not an object")
            h = c.get("help_id")
            if h not in by_id or by_id[h]["mode"] != "help":
                raise CheckError(f"unknown or wrong-role helper {h}")
            if (a, h) in blocked:
                raise CheckError(f"blocked pair {a}/{h}")
            if h in seen_helps:
                raise CheckError(f"helper {h} listed twice for {a}")
            if c.get("confidence") != "high":
                raise CheckError(f"confidence is not 'high' for {a}/{h}")
            reason = _check_sentence(c.get("reason"), f"reason for {a}/{h}")
            invite = _check_sentence(c.get("invite_line"), f"invite_line for {a}/{h}")
            _check_invite_detail(invite, by_id[h], f"invite_line for {a}/{h}")
            if not ({"you", "your"} & set(re.findall(r"[A-Za-z']+", invite.lower()))):
                raise CheckError(f"invite_line is not addressed to the helper for {a}/{h}")
            if rank == 0:
                if h in first_choices:
                    raise CheckError(f"helper {h} is first choice for two needs")
                first_choices.add(h)
            seen_helps.add(h)
            out.append({"help_id": h, "confidence": "high", "reason": reason, "invite_line": invite})
        seen_asks.add(a)
        matches.append({"ask_id": a, "candidates": out})

    skipped = []
    for s in data["skipped"]:
        if not isinstance(s, dict) or s.get("id") not in by_id or not isinstance(s.get("reason"), str):
            raise CheckError("a skipped item is malformed")
        skipped.append({"id": s["id"], "reason": s["reason"]})
    return {"matches": matches, "skipped": skipped}


# ---------------------------------------------------------------- step 5: one helper at a time

def build_tracker(validated, today=None, start=1):
    return {"created": (today or datetime.date.today()).isoformat(),
            "asks": [{"aid": f"ask-{i}", "ask_id": m["ask_id"], "candidates": m["candidates"],
                      "idx": 0, "status": "pending", "history": []}
                     for i, m in enumerate(validated["matches"], start=start)],
            "skipped": validated["skipped"]}


def find_ask(tracker, aid):
    for a in tracker["asks"]:
        if a["aid"] == aid:
            return a
    raise CheckError(f"no such need: {aid}")


def busy_helpers(tracker, except_aid=None):
    return {a["candidates"][a["idx"]]["help_id"]
            for a in tracker["asks"] if a["aid"] != except_aid and a["status"] in OPEN}


def available_index(tracker, ask, extra_busy=()):
    busy = busy_helpers(tracker, except_aid=ask["aid"]) | set(extra_busy)
    for i in range(ask["idx"], len(ask["candidates"])):
        if ask["candidates"][i]["help_id"] not in busy:
            return i
    return None


def current_candidate(tracker, ask):
    if ask["status"] in OPEN:
        return ask["candidates"][ask["idx"]]
    if ask["status"] == "pending":
        i = available_index(tracker, ask)
        return None if i is None else ask["candidates"][i]
    return None


def approve(tracker, ask, today=None, extra_busy=()):
    if ask["status"] != "pending":
        raise CheckError(f"{ask['aid']} is {ask['status']}, so it cannot be approved")
    i = available_index(tracker, ask, extra_busy)
    if i is None:
        ask["status"] = "exhausted"
        raise CheckError("every helper who fits is already invited for another need")
    ask["idx"] = i
    ask["status"] = "invited"
    ask["invited_at"] = (today or datetime.date.today()).isoformat()
    ask.pop("sent_at", None)          # a new invitation starts unsent: never inherit the last helper's date
    return ask["candidates"][i]


def _move_on(ask, outcome, iso=None):
    """The current invitation ended without a yes. Keep its dates in the history, then start the next one clean."""
    ask["history"].append({"help_id": ask["candidates"][ask["idx"]]["help_id"], "outcome": outcome,
                           "sent_at": ask.get("sent_at"), "answered_at": iso if outcome == "no" else None,
                           "question_at": ask.pop("question_at", None)})
    ask.pop("sent_at", None)
    ask["idx"] += 1
    ask["status"] = "pending" if ask["idx"] < len(ask["candidates"]) else "exhausted"


def record(tracker, ask, outcome, today=None):
    """outcome: yes | no | noreply | skip | introduced | sent | told | question"""
    iso = (today or datetime.date.today()).isoformat()
    if outcome == "question":
        if ask["status"] != "invited":
            raise CheckError(f"{ask['aid']} is {ask['status']}: only an open invitation can get a question")
        ask["question_at"] = iso
        return
    if outcome == "sent":
        if ask["status"] != "invited":
            raise CheckError(f"{ask['aid']} is {ask['status']}: only an invited need can be marked as sent")
        ask["sent_at"] = iso
        return
    if outcome == "told":
        if ask["status"] != "exhausted":
            raise CheckError(f"{ask['aid']} is {ask['status']}: the founder is only told when no helper is left")
        ask["founder_told_at"] = iso
        return
    if outcome == "skip":
        if ask["status"] != "pending":
            raise CheckError(f"{ask['aid']} is {ask['status']}, so it cannot be skipped")
        ask["status"] = "skipped"
        return
    if outcome == "introduced":
        if ask["status"] != "yes":
            raise CheckError(f"{ask['aid']} is {ask['status']}: only a need whose helper said yes can be marked as introduced")
        ask["status"] = "introduced"
        ask["introduced_at"] = iso
        return
    if ask["status"] != "invited":
        raise CheckError(f"{ask['aid']} has no open invitation")
    if outcome == "yes":
        ask["history"].append({"help_id": ask["candidates"][ask["idx"]]["help_id"], "outcome": "yes",
                               "sent_at": ask.get("sent_at"), "answered_at": iso,
                               "question_at": ask.pop("question_at", None)})
        ask["status"] = "yes"
        ask["yes_at"] = iso
    elif outcome in ("no", "noreply"):
        _move_on(ask, outcome, iso)
    else:
        raise CheckError(f"unknown outcome {outcome}")


def attention(tracker, days=3, today=None):
    """What Laura may have forgotten.
    no_helper_left     a need ran out of helpers and the founder has not been told
    questions          a helper asked a question and is waiting for Laura's reply
    yes_not_introduced a helper said yes but no introduction is marked as sent
    overdue_invitations an invitation was SENT `days` or more days ago with no answer
    not_sent           an invitation was prepared but is not marked as sent
    waiting_approval   needs nobody approved or skipped yet
    A need that was matched again in a later round counts only in its newest round."""
    today = today or datetime.date.today()
    age = lambda iso: (today - datetime.date.fromisoformat(iso)).days if iso else None
    out = {"no_helper_left": [], "questions": [], "yes_not_introduced": [], "overdue_invitations": [],
           "not_sent": [], "waiting_approval": []}
    for a in tracker["asks"]:
        if not a.get("_latest", True):
            continue
        helper = a["candidates"][a["idx"]]["help_id"] if a["idx"] < len(a["candidates"]) else None
        row = {"aid": a["aid"], "ask_id": a["ask_id"], "help_id": helper}
        if a["status"] == "exhausted" and not a.get("founder_told_at"):
            out["no_helper_left"].append({"aid": a["aid"], "ask_id": a["ask_id"]})
        elif a["status"] == "yes":
            out["yes_not_introduced"].append({**row, "days": age(a.get("yes_at"))})
        elif a["status"] == "invited":
            if a.get("question_at"):
                out["questions"].append({**row, "days": age(a["question_at"])})
            elif a.get("sent_at"):
                d = age(a["sent_at"])
                if d is not None and d >= days:
                    out["overdue_invitations"].append({**row, "days": d})
            else:
                out["not_sent"].append({**row, "days": age(a.get("invited_at"))})
        elif a["status"] == "pending":
            out["waiting_approval"].append({"aid": a["aid"], "ask_id": a["ask_id"],
                                            "days": age(a.get("_created") or tracker.get("created"))})
    return out


def due_invitations(tracker, days=3, today=None):
    """Open invitations that have waited at least `days` days with no answer (counted from the day it was sent)."""
    today = today or datetime.date.today()
    out = []
    for a in tracker["asks"]:
        start = a.get("sent_at") or a.get("invited_at")
        if a["status"] == "invited" and start:
            waited = (today - datetime.date.fromisoformat(start)).days
            if waited >= days:
                out.append({"aid": a["aid"], "ask_id": a["ask_id"],
                            "help_id": a["candidates"][a["idx"]]["help_id"], "days": waited})
    return out


def normalize_email(addr):
    """Gmail treats name+tag@gmail.com as name@gmail.com, and replies usually come from the plain address."""
    addr = (addr or "").strip().lower()
    if "@" not in addr:
        return addr
    local, domain = addr.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.split("+", 1)[0], "gmail.com"
    return f"{local}@{domain}"


def find_reply(tracker, helper_rows, sender=None, ref=None):
    """Which open invitation does a reply belong to? Uses the Ref code if there is one,
    otherwise the sender's address. Never guesses: if it is unclear, it says so."""
    email_of = {h["id"]: normalize_email(h.get("email")) for h in helper_rows}
    open_asks = [a for a in tracker["asks"] if a["status"] == "invited"]
    sender = normalize_email(sender)
    if ref:
        hits = [a for a in open_asks
                if f"{a['ask_id']}-{a['candidates'][a['idx']]['help_id']}" == ref.strip()]
        if not hits:
            raise CheckError(f"no open invitation has the reference {ref}")
    else:
        hits = [a for a in open_asks
                if sender and email_of.get(a["candidates"][a["idx"]]["help_id"]) == sender]
        if not hits:
            raise CheckError("no open invitation was sent to that address")
        if len(hits) > 1:
            raise CheckError("several open invitations went to that address: ask Laura which one, "
                             "or use the Ref code in the email")
    a = hits[0]
    hid = a["candidates"][a["idx"]]["help_id"]
    return {"aid": a["aid"], "ask_id": a["ask_id"], "help_id": hid,
            "sender_matches": bool(sender) and email_of.get(hid) == sender}


# ---------------------------------------------------------------- step 4: the email links

def compose_link(provider, to, subject, body, account=None):
    """A link that opens a ready-to-send email. The body is plain text: links cannot hold buttons.
    `account` is the Gmail address to write from. Without it Gmail uses whichever of the browser's signed-in
    accounts happens to be first, which is not necessarily Laura's."""
    q = lambda s: quote(s, safe="")
    t = quote(to, safe="@,")          # several recipients are separated by commas
    if provider == "gmail":
        who = f"authuser={q(account)}&" if account else ""
        return f"https://mail.google.com/mail/?{who}view=cm&fs=1&to={t}&su={q(subject)}&body={q(body)}"
    if provider == "outlook":
        return f"https://outlook.office.com/mail/deeplink/compose?to={t}&subject={q(subject)}&body={q(body)}"
    if provider == "outlook-personal":
        return f"https://outlook.live.com/mail/0/deeplink/compose?to={t}&subject={q(subject)}&body={q(body)}"
    if provider == "mailto":
        return f"mailto:{t}?subject={q(subject)}&body={q(body)}"
    raise CheckError(f"unknown provider {provider}")


PROVIDERS = ("gmail", "outlook", "outlook-personal", "mailto")


PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net"}


def build_invite(helper, candidate, ref, laura_email, sender_name, provider):
    """The invitation to one helper. Contains one sentence about the founder, never their words.

    The text is plain and asks the helper to reply YES. A long mailto link inside a plain-text
    email gets cut off by mail programs (only the address becomes a link), so it is NOT put in
    the body. A helper has at most one open invitation per month, so a reply from them already
    says which need it is about. `yes_link` is still returned for drafts that can hold a real button."""
    if not EMAIL_RE.match(helper.get("email", "")):
        raise CheckError(f"helper {helper.get('id')} has no valid email address")
    if not EMAIL_RE.match(laura_email):
        raise CheckError("Laura's email address is not valid")
    first = (helper.get("name") or "").split(" ")[0]
    body = (
        f"Hi{' ' + first if first else ''},\n\n"
        "A fellow Volta founder is working on something where your experience could help.\n\n"
        f"{candidate['invite_line']}\n\n"
        "Would you be open to a 20-minute intro? If you say yes, I'll introduce you by name. "
        "If not, nothing happens and they won't know.\n\n"
        "To say yes, just reply YES to this email. Not a good time? You can ignore it.\n\n"
        f"{sender_name}\n\n"
        f"(Ref: {ref})"
    )
    subject = "A fellow founder could use your experience"
    out = {"skill_version": VERSION, "to": helper["email"], "subject": subject, "body": body, "ref": ref,
           "send_link": compose_link(provider, helper["email"], subject, body, account=laura_email),
           "yes_link": compose_link("mailto", laura_email, f"YES - {ref}", "Yes, please introduce us.")}
    if helper["email"].split("@")[-1].lower() in PLACEHOLDER_DOMAINS:
        out["warning"] = (f"{helper['email']} looks like a placeholder address. "
                          "Check helpers.csv has the real email before sending.")
    return out


def build_intro(founder, helper, sender_name, provider, account=None):
    """The introduction, written after the helper said yes. This is the ONLY place a founder's
    name and email are used. The founder agreed that their answer may be used to suggest introductions."""
    for who, row in (("founder", founder), ("helper", helper)):
        if not (row.get("name") or "").strip():
            raise CheckError(f"the {who} ({row.get('id')}) has no name in the file")
        if not EMAIL_RE.match(row.get("email", "")):
            raise CheckError(f"the {who} ({row.get('id')}) has no valid email address in the file")
    f1, h1 = founder["name"].split(" ")[0], helper["name"].split(" ")[0]
    wants = founder.get("note") or ", ".join(split_topics(founder.get("topics"))) or "help from another founder"
    offers = helper.get("note") or ", ".join(split_topics(helper.get("topics"))) or "relevant experience"
    body = (
        f"Hi {f1} and {h1},\n\n"
        f"{h1} has agreed to a 20-minute chat. Here is why I thought of you both:\n\n"
        f"- {f1} is working on: {wants}\n"
        f"- {h1} has: {offers}\n\n"
        "I'll leave you two to find a time. Thank you both.\n\n"
        f"{sender_name}"
    )
    subject = f"Introduction: {founder['name']} and {helper['name']}"
    to = f"{founder['email']},{helper['email']}"
    out = {"skill_version": VERSION, "to": to, "subject": subject, "body": body,
           "send_link": compose_link(provider, to, subject, body, account=account)}
    bad = [r["email"] for r in (founder, helper) if r["email"].split("@")[-1].lower() in PLACEHOLDER_DOMAINS]
    if bad:
        out["warning"] = f"{', '.join(bad)} look like placeholder addresses. Check the files have the real ones."
    return out


# ---------------------------------------------------------------- when nobody is left: a note to the founder

def build_founder_note(founder, sender_name, provider, account=None):
    """Sent only when a need has run out of helpers. It never says who was asked or who said no."""
    if not (founder.get("name") or "").strip():
        raise CheckError(f"the founder ({founder.get('id')}) has no name in the file")
    if not EMAIL_RE.match(founder.get("email", "")):
        raise CheckError(f"the founder ({founder.get('id')}) has no valid email address in the file")
    first = founder["name"].split(" ")[0]
    body = (
        f"Hi {first},\n\n"
        "Thank you for telling us what you need help with. We looked for someone in the community "
        "who could help right now, and have not found a match yet.\n\n"
        "We will look again in the next matching round and get in touch as soon as there is someone. "
        "If your request has changed, or you would like to add a line about what would help most, "
        "just reply to this email.\n\n"
        f"{sender_name}"
    )
    subject = "Your request to the Volta community"
    out = {"skill_version": VERSION, "to": founder["email"], "subject": subject, "body": body,
           "send_link": compose_link(provider, founder["email"], subject, body, account=account)}
    if founder["email"].split("@")[-1].lower() in PLACEHOLDER_DOMAINS:
        out["warning"] = f"{founder['email']} looks like a placeholder address. Check the needs file has the real one."
    return out


# ---------------------------------------------------------------- calendar reminders (links Laura clicks, nothing automatic)

def _ics_escape(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Lines in an .ics file may not be longer than 75 characters: continue on the next line after a space."""
    out, first = [], True
    while len(line) > 73:
        out.append(line[:73] if first else " " + line[:73])
        line, first = line[73:], False
    out.append(line if first else " " + line)
    return out


def google_day_link(day, account=None):
    """Opens Google Calendar on that day, where the event is. (We never learn the event's own id, so no link to the event.)"""
    who = f"?authuser={quote(account, safe='')}" if account else ""
    return f"https://calendar.google.com/calendar/r/day/{day.year}/{day.month}/{day.day}{who}"


def reminder_title(ref):
    return f"Volta peer match: check for a reply ({ref})"


REMINDER_DETAILS = ("Open Claude on your Volta peer match folder and say: check for replies. "
                    "If there is still no answer, decide whether to try the next helper.")


def google_event_link(ref, due, account=None):
    day = due.strftime("%Y%m%d")
    who = f"&authuser={quote(account, safe='')}" if account else ""
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(reminder_title(ref), safe='')}&details={quote(REMINDER_DETAILS, safe='')}"
            f"&dates={day}T090000/{day}T093000{who}")


def build_reminder(ask, helper_code, start, days, now=None, account=None):
    """A calendar event `days` days after the invitation was sent, at 09:00. No names in it: calendars are often shared."""
    due = start + datetime.timedelta(days=days)
    ref = f"{ask['ask_id']}-{helper_code}"
    title, details = reminder_title(ref), REMINDER_DETAILS
    day = due.strftime("%Y%m%d")
    link = google_event_link(ref, due, account)
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//volta-peer-match//EN", "BEGIN:VEVENT",
             f"UID:{ref}-{day}@volta-peer-match", f"DTSTAMP:{stamp}",
             f"DTSTART:{day}T090000", f"DTEND:{day}T093000",
             f"SUMMARY:{_ics_escape(title)}", f"DESCRIPTION:{_ics_escape(details)}",
             "BEGIN:VALARM", "TRIGGER:PT0M", "ACTION:DISPLAY", "DESCRIPTION:Volta peer match", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    folded = [piece for line in lines for piece in _ics_fold(line)]
    return {"title": title, "date": due.isoformat(), "google_link": link,
            "google_day_link": google_day_link(due, account), "ics": "\r\n".join(folded) + "\r\n"}


def detect_platform():
    """Where we are. Set VPM_NO_DESKTOP=1 to say "never open a window, a file or an app": the tests do, so that running
    them on a Mac cannot touch Laura's calendar or pop up windows."""
    return "no-desktop" if os.environ.get("VPM_NO_DESKTOP") else sys.platform


def open_ics(path, platform=None, runner=None):
    """On a Mac, open the .ics file so Calendar shows its "add this event" window. Laura still clicks to confirm.
    Anywhere else, say so and do nothing."""
    platform = platform or detect_platform()
    if platform != "darwin":
        return {"opened": False,
                "message": "This computer is not a Mac. Double-click the .ics file, or use the Google Calendar link."}
    (runner or subprocess.run)(["open", str(path)], check=False)
    return {"opened": True, "message": "Calendar should now show the event. Laura clicks Add to save it."}


# ---------------------------------------------------------------- the month so far

def monthly_report(tracker, days=3, today=None, names=None, target=80):
    """Numbers for Laura and for the first-month review. Each invitation counts once, with its own dates.
    An invitation is judged on "answered within `days` days" only once it is answered or `days` days old,
    so yesterday's invitation does not drag the rate down. A reply of any kind counts as an answer: a YES, a
    "not now", or a question. With several rounds, every invitation of every round counts; the lists show each need once."""
    today = today or datetime.date.today()
    names = names or {}
    D = datetime.date.fromisoformat
    records = []
    for a in tracker["asks"]:
        for h in a.get("history", []):
            records.append({"outcome": h["outcome"], "sent": h.get("sent_at"), "answered": h.get("answered_at"),
                            "question": h.get("question_at")})
        if a["status"] == "invited" and a.get("sent_at"):
            records.append({"outcome": "open", "sent": a["sent_at"], "answered": None, "question": a.get("question_at")})
    eligible = in_time = too_early = unknown = 0
    for r in records:
        replied = [d for d in ((r["answered"] if r["outcome"] in ("yes", "no") else None), r["question"]) if d]
        if not r["sent"] or (r["outcome"] in ("yes", "no") and not r["answered"] and not r["question"]):
            unknown += 1
        elif replied:
            eligible += 1
            in_time += (D(min(replied)) - D(r["sent"])).days <= days
        elif r["outcome"] == "noreply" or (today - D(r["sent"])).days >= days:
            eligible += 1
        else:
            too_early += 1
    label = lambda a: f"{names[a['ask_id']]} ({a['ask_id']})" if names.get(a["ask_id"]) else a["ask_id"]
    introduced, open_ = [], []
    for a in tracker["asks"]:
        if not a.get("_latest", True):
            continue
        if a["status"] == "introduced":
            introduced.append(label(a))
        elif a["status"] == "yes":
            open_.append((label(a), "a helper said yes, the introduction is not sent"))
        elif a["status"] == "invited" and a.get("question_at"):
            open_.append((label(a), "the helper asked a question and is waiting for Laura's reply"))
        elif a["status"] == "invited":
            open_.append((label(a), "waiting for the helper's answer" if a.get("sent_at") else "invitation prepared, not marked as sent"))
        elif a["status"] == "exhausted":
            open_.append((label(a), "no helper left" + ("" if a.get("founder_told_at") else ", founder not told yet")))
    return {
        "invitations": len(records),
        "yes": sum(r["outcome"] == "yes" for r in records),
        "not_now": sum(r["outcome"] == "no" for r in records),
        "questions": sum(bool(r["question"]) for r in records),
        "silent": sum(r["outcome"] == "noreply" and not r["question"] for r in records),
        "introduced_count": len(introduced),
        "judged": eligible, "answered_in_time": in_time,
        "pct": round(100 * in_time / eligible) if eligible else None,
        "too_early": too_early, "dates_unknown": unknown,
        "target": target, "days": days,
        "introduced": introduced, "not_completed": open_,
        "waiting_approval": sum(a["status"] == "pending" and a.get("_latest", True) for a in tracker["asks"]),
    }


def render_report(rep):
    if rep["invitations"] == 0:
        extra = f" {rep['waiting_approval']} need(s) are waiting for Laura's approval." if rep["waiting_approval"] else ""
        return "So far this month: no invitation has been marked as sent yet." + extra
    d = rep["days"]
    lines = [f"So far this month: about {rep['invitations']} invitation(s) sent.",
             f"- At least {rep['yes']} YES, at least {rep['introduced_count']} introduction(s) completed."
             + (f" {rep['questions']} helper question(s), counted as answers." if rep["questions"] else "")]
    if rep["judged"]:
        rate = f"{rep['answered_in_time']} of {rep['judged']} answered within {d} days ({rep['pct']}%, target {rep['target']}%)"
        lines.append(f"- {rate}. An answer is a YES, a \"not now\" or a question; silence counts as no answer.")
    else:
        lines.append(f"- Too early to say how many answered within {d} days.")
    if rep["too_early"]:
        lines.append(f"- {rep['too_early']} more invitation(s) are still inside their {d} days and not judged yet.")
    if rep["dates_unknown"]:
        lines.append(f"- {rep['dates_unknown']} invitation(s) have no recorded date, so they are left out of that rate.")
    lines.append("- Introduced: " + (", ".join(rep["introduced"]) if rep["introduced"] else "nobody yet") + ".")
    if rep["not_completed"]:
        lines.append("- Not completed yet: " + "; ".join(f"{who}: {why}" for who, why in rep["not_completed"]) + ".")
    if rep["waiting_approval"]:
        lines.append(f"- {rep['waiting_approval']} need(s) are still waiting for Laura's approval.")
    return "\n".join(lines)


# ---------------------------------------------------------------- the reminders a need has made, and tidying them up

def active_reminders(ask):
    return [r for r in ask.get("reminders", []) if not r.get("handled")]


def add_reminder_record(ask, ref, date_iso, made_at_iso, via=None):
    """One entry per invitation (a need can have several: every change of helper makes a new one)."""
    lst = ask.setdefault("reminders", [])
    for r in lst:
        if r["ref"] == ref:
            if via and not r.get("via"):
                r["via"] = via
            return True
    lst.append({"ref": ref, "date": date_iso, "made_at": made_at_iso, "via": via, "handled": False})
    return False


def _run_osascript(args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=700)
    if r.returncode != 0:
        raise CheckError("Calendar script failed: " + (r.stderr.strip().splitlines() or ["unknown error"])[0])
    return r.stdout


def add_reminder_window(ask, ref, date_text, google_url, ics_path, script_path, platform=None, runner=None):
    """Mac only. A window asks: Google Calendar / Mac Calendar / No thanks, and does what she clicks.
    Links to the .ics file do not work in the chat (the app opens them as plain text), so this is how Mac Calendar is reached."""
    platform = platform or detect_platform()
    if platform != "darwin":
        return {"ran": False, "choice": None,
                "message": "This is not a Mac, so no window was opened. Give Laura the Google Calendar link as text."}
    out = ((runner or _run_osascript)(["osascript", str(script_path), date_text, google_url, str(ics_path)]) or "").strip().splitlines()
    choice = out[-1] if out else "unknown"
    entry = next((r for r in ask.get("reminders", []) if r["ref"] == ref), None)
    if entry is not None and choice in ("mac", "google", "none"):
        entry["via"] = {"mac": "mac", "google": "google", "none": "declined"}[choice]
    return {"ran": True, "choice": choice, "message": ""}


def cleanup_reminders(ask, script_path, platform=None, runner=None, only_ref=None):
    """Mac only. For each reminder of a need that is no longer needed, show the Keep / Show / Delete window.
    Each reminder is asked about once: whatever Laura chose, it is then handled. If nobody clicked, it stays open."""
    platform = platform or detect_platform()
    if platform != "darwin":
        return {"ran": False, "results": [],
                "message": "This is not a Mac, so nothing was opened. Tell Laura the title and date of the reminder "
                           "so she can delete it herself if she wants."}
    results = []
    for r in active_reminders(ask):
        if only_ref and r["ref"] != only_ref:
            continue
        quiet = r.get("via") != "mac"          # if we never opened it in Mac Calendar, do not nag when nothing is there
        args = ["osascript", str(script_path), r["ref"]] + (["quiet"] if quiet else [])
        outcome = ((runner or _run_osascript)(args) or "").strip().splitlines()
        outcome = outcome[-1] if outcome else "unknown"
        if outcome in ("deleted", "kept", "shown", "none"):
            r["handled"] = True
        r["last_cleanup"] = outcome
        results.append({"ref": r["ref"], "outcome": outcome})
    return {"ran": True, "results": results, "message": ""}


# ---------------------------------------------------------------- rounds: one view of a month, and what the next round leaves out

def combined_tracker(folder, run_name):
    """Every round of the month in one tracker, so status, reminders and the report see everything.
    Each ask is marked with its round's date, and `_latest` says whether it is the newest ask for its need."""
    asks, newest = [], {}
    for p in month_runs(folder, run_name):
        tp = p / "tracker.json"
        if not tp.exists():
            continue
        t = read_json(tp)
        for a in t["asks"]:
            a = dict(a)
            a["_created"], a["_run"] = t.get("created"), p.name
            asks.append(a)
            newest[a["ask_id"]] = a
    for a in asks:
        a["_latest"] = newest[a["ask_id"]] is a
    return {"asks": asks, "created": None, "skipped": []}


def busy_in_other_rounds(folder, run_name):
    out = set()
    for p in month_runs(folder, run_name):
        if p.name != run_name and (p / "tracker.json").exists():
            out |= busy_helpers(read_json(p / "tracker.json"))
    return out


def earlier_runs_ledger(folder, run_name, today=None, cooldown=30):
    """What earlier rounds and months already did, so a new round does not repeat it.
    needs_settled   a helper said yes, an invitation is in flight, or the introduction is done
    needs_skipped   Laura skipped them
    helpers_resting invited within the last `cooldown` days (any outcome): not invited again yet"""
    today = today or datetime.date.today()
    here = run_sort_key(run_name)
    status, last = {}, {}
    def bump(helper, iso):
        if iso and (helper not in last or iso > last[helper]):
            last[helper] = iso
    for p in list_runs(folder):
        if run_sort_key(p.name) >= here or not (p / "tracker.json").exists():
            continue
        t = read_json(p / "tracker.json")
        for a in t["asks"]:
            status[a["ask_id"]] = a["status"]
            fallback = a.get("invited_at") or t.get("created")
            for h in a.get("history", []):
                bump(h["help_id"], h.get("sent_at") or fallback)
            if a["status"] in ("invited", "yes", "introduced") and a["idx"] < len(a["candidates"]):
                bump(a["candidates"][a["idx"]]["help_id"], a.get("sent_at") or fallback)
    resting = []
    for helper, iso in last.items():
        until = datetime.date.fromisoformat(iso) + datetime.timedelta(days=cooldown)
        if until > today:
            resting.append({"help_id": helper, "last_invited": iso, "until": until.isoformat()})
    return {"needs_settled": sorted(k for k, v in status.items() if v in ("invited", "yes", "introduced")),
            "needs_skipped": sorted(k for k, v in status.items() if v == "skipped"),
            "helpers_resting": sorted(resting, key=lambda r: r["help_id"])}


def apply_ledger(prepared, ledger):
    """Take the needs that already have a result, and the helpers who are resting, out of what Claude matches on."""
    gone = set(ledger["needs_settled"]) | set(ledger["needs_skipped"]) | {r["help_id"] for r in ledger["helpers_resting"]}
    held = {"needs_settled": [], "needs_skipped": [], "helpers_resting": []}
    kept = []
    for e in prepared["entries"]:
        if e["id"] not in gone:
            kept.append(e)
        elif e["id"] in ledger["needs_settled"]:
            held["needs_settled"].append(e["id"])
        elif e["id"] in ledger["needs_skipped"]:
            held["needs_skipped"].append(e["id"])
        else:
            held["helpers_resting"].append(next(r for r in ledger["helpers_resting"] if r["help_id"] == e["id"]))
    prepared["entries"] = kept
    ids = {e["id"] for e in kept}
    prepared["do_not_pair"] = [b for b in prepared["do_not_pair"] if b["ask_id"] in ids and b["help_id"] in ids]
    prepared["held_back"] = held
    return held


def supersede_earlier_asks(folder, run_name, matches):
    """A need that is matched again in a new round is no longer open in the old one: it cannot be approved there."""
    wanted = {m["ask_id"] for m in matches}
    changed = []
    for p in month_runs(folder, run_name):
        if p.name == run_name or not (p / "tracker.json").exists():
            continue
        t = read_json(p / "tracker.json")
        touched = False
        for a in t["asks"]:
            if a["ask_id"] in wanted and a["status"] in ("pending", "exhausted"):
                a["status"] = "superseded"
                touched = True
                changed.append(a["aid"])
        if touched:
            write_json(p / "tracker.json", t)
    return changed


# ---------------------------------------------------------------- the next round

def previous_run_dir(folder, month):
    older = [p for p in list_runs(folder) if run_sort_key(p.name) < run_sort_key(month)]
    return older[-1] if older else None


def carried_over(folder, month, prepared):
    """Needs that ran out of helpers last round. They are matched again if they are still in this month's needs file."""
    prev = previous_run_dir(folder, month)
    if prev is None or not (prev / "tracker.json").exists():
        return {"from": None, "again": [], "missing": []}
    tracker = read_json(prev / "tracker.json")
    wanted = [a["ask_id"] for a in tracker["asks"] if a["status"] == "exhausted"]
    here = {e["id"] for e in prepared["entries"] if e["mode"] == "meet"}
    return {"from": prev.name, "again": [w for w in wanted if w in here], "missing": [w for w in wanted if w not in here]}
