#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import time

tmp = tempfile.mkdtemp()
os.environ["FLOW_HOME"] = os.path.join(tmp, "flow")
os.environ["FLOW_APP_SESSIONS"] = os.path.join(tmp, "app")
os.environ["FLOW_CLAUDE_HOME"] = os.path.join(tmp, "claude")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import appsessions as a

fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def make(n, age_h, **kw):
    sid = "local_%08x-0000-0000-0000-%012x" % (n, n)
    d = os.path.join(os.environ["FLOW_APP_SESSIONS"], "u", "p")
    os.makedirs(d, exist_ok=True)
    rec = {"sessionId": sid, "cliSessionId": sid[6:], "cwd": "/x/repo", "title": "t%d" % n, "isArchived": False,
           "lastActivityAt": int((time.time() - age_h * 3600) * 1000), "completedTurns": 3, **kw}
    with open(os.path.join(d, sid + ".json"), "w") as f:
        json.dump(rec, f, separators=(",", ":"))
    return sid


old, fresh, running = make(1, 24 * 40), make(2, 0.1), make(3, 24 * 40)
rows = {r["id"]: r for r in a.listing(known_cli_ids=[running[6:]], busy_cli_ids=[running[6:]])}
check("lists all three", len(rows), 3)
check("fresh is busy", rows[fresh]["busy"]); check("old is not busy", rows[old]["busy"], False)
check("known flag", rows[running]["in_agf"]); check("unknown flag", rows[old]["in_agf"], False)

r = a.set_archived([old, fresh, running, "../etc/passwd", "local_nope"], True, busy_cli_ids=[running[6:]])
check("only the old one is archived", r["done"], [old])
check("busy ones and bad ids are skipped", sorted(x["id"] for x in r["skipped"]), sorted([fresh, running, "../etc/passwd", "local_nope"]))
p = os.path.join(os.environ["FLOW_APP_SESSIONS"], "u", "p", old + ".json")
check("flag written", json.load(open(p))["isArchived"], True)
check("other fields intact", json.load(open(p))["title"], "t1")
check("backup made", os.path.exists(os.path.join(r["backup"], old + ".json")))
check("backup holds the original flag", json.load(open(os.path.join(r["backup"], old + ".json")))["isArchived"], False)
check("log written", os.path.exists(a.LOG))
check("archiving twice is skipped", a.set_archived([old], True)["done"], [])
check("dry run writes nothing", a.set_archived([make(4, 24 * 50)], True, dry=True)["backup"], None)
check("restore", a.set_archived([old], False)["done"], [old])
check("restored flag", json.load(open(p))["isArchived"], False)
try:
    a.set_archived([], True); check("empty ids refused", False)
except ValueError:
    check("empty ids refused", True)
cl = os.environ["FLOW_CLAUDE_HOME"]
victim, other, young = make(10, 24 * 90), make(11, 24 * 90), make(12, 0.1)
os.makedirs(os.path.join(cl, "projects", "-x"))
for sid in (victim, other, young):
    open(os.path.join(cl, "projects", "-x", sid[6:] + ".jsonl"), "w").write("x" * 1000)
os.makedirs(os.path.join(cl, "projects", "-x", victim[6:], "subagents"))
open(os.path.join(cl, "projects", "-x", victim[6:], "subagents", "a.jsonl"), "w").write("y" * 500)
os.symlink("/etc", os.path.join(cl, "projects", "-x", "link"))
dr = a.delete_sessions([victim], dry=True)
check("dry run measures but deletes nothing", dr["done"] == [victim] and dr["bytes"] > 1500 and os.path.exists(os.path.join(cl, "projects", "-x", victim[6:] + ".jsonl")))
r = a.delete_sessions([victim, young, "../x"])
check("deleted only the old one", r["done"], [victim])
check("young and bad id skipped", sorted(x["id"] for x in r["skipped"]), sorted([young, "../x"]))
check("transcript gone", not os.path.exists(os.path.join(cl, "projects", "-x", victim[6:] + ".jsonl")))
check("subagent folder gone", not os.path.exists(os.path.join(cl, "projects", "-x", victim[6:])))
check("metadata gone", a._find(victim), None)
check("other session untouched", os.path.exists(os.path.join(cl, "projects", "-x", other[6:] + ".jsonl")) and a._find(other) is not None)
check("symlink untouched", os.path.islink(os.path.join(cl, "projects", "-x", "link")))
check("delete is logged", "delete" in open(a.LOG).read())
def rec(**kw):
    base = {"age_min": 24 * 60 * 40, "turns": 10, "first_prompt": "x", "last_reply": "y", "busy": False, "archived": False, "ticket": None}
    return a.recommend({**base, **kw}, kw.pop("st", None))["action"]
check("busy is kept", rec(busy=True), "keep")
check("empty old session is deleted", rec(turns=1), "delete")
check("missing transcript is deleted", rec(first_prompt=None, last_reply=None), "delete")
check("no ticket, old: archive", rec(), "archive")
check("fresh: keep", rec(age_min=60 * 24 * 3), "keep")
check("big old session without ticket is only reviewed", rec(turns=80), "review")
check("finished ticket: archive", a.recommend({"age_min": 60 * 24 * 3, "turns": 20, "ticket": "APS-1", "first_prompt": "x"}, "Done")["action"], "archive")
check("open ticket, recent: keep", a.recommend({"age_min": 60 * 24 * 3, "turns": 20, "ticket": "APS-1", "first_prompt": "x"}, "In Progress")["action"], "keep")
check("open ticket, long idle: review", a.recommend({"age_min": 60 * 24 * 40, "turns": 20, "ticket": "APS-1", "first_prompt": "x"}, "In Progress")["action"], "review")
check("big session with finished ticket is never deleted", a.recommend({"age_min": 60 * 24 * 90, "turns": 90, "ticket": "APS-1", "first_prompt": "x"}, "Done")["action"], "archive")
cases = [dict(busy=True), dict(archived=True), dict(turns=1), dict(first_prompt=None, last_reply=None), dict(), dict(age_min=60 * 24 * 3), dict(turns=80), dict(ticket="APS-1")]
check("every recommendation has reason_k", all(a.recommend({"age_min": 24 * 60 * 40, "turns": 10, "first_prompt": "x", "last_reply": "y", "ticket": None, **c}, "Done" if c.get("ticket") else None).get("reason_k") for c in cases), True)
sk = a.set_archived(["local_ffffffff-0000-0000-0000-000000000000"], True, [])["skipped"]
check("skipped item has why_k", bool(sk) and all(x.get("why_k") and x["why_k"][0].startswith("srv.why.") for x in sk), True)
try:
    a.set_archived([], True)
except ValueError as e:
    check("ids error has a key", getattr(e, "k", None) and e.k[0], "srv.ids")
print("ALL PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
