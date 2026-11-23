#!/usr/bin/env python3
import json
import re
import os
import sys
import tempfile
import urllib.error

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, HERE)
import ac
import approve
import jira
import spec

fails = 0


def check(name, got, want=True):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def p(t):
    return {"type": "paragraph", "content": [{"type": "text", "text": t}]}


def h(t):
    return {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": t}]}


DESC = {"type": "doc", "version": 1, "content": [
    h("Problém"), p("Limit řidiče se vyhodnocuje jinak než v Dispečeru a řidič vidí jiné číslo."),
    h("Kde to je"), p("src/pages/DriverPage.vue:42 počítá limit z objemu."), h("Očekávané chování"), p("Limit se počítá jako v Dispečeru.")]}
CRIT = [{"id": 1, "text": "Když je objem 8 000 a limit 10 000, pak se zobrazí ok; při 12 000 se zobrazí upozornění.", "ticked": False},
        {"id": 2, "text": "Pokud řidič nemá oprávnění, nezobrazí se tlačítko Uložit.", "ticked": False}]


def make(status="TO DO", crit=CRIT, labels=(), updated="2026-11-18T10:00:00.000+0100", desc=None):
    sp = spec.lint(desc or DESC, {"criteria": crit}, "Story", list(labels))
    return {"status": status, "updated": updated, "summary": "Limit řidiče", "assignee": "Martin", "labels": list(labels),
            "ac": {"gate": "draft", "criteria": crit, "total": len(crit), "ticked": 0, "spec": sp}}


TICKETS, CALLS = {}, []
OFFERED = [{"id": "11", "name": "To Do", "to": {"name": "TO DO"}},
           {"id": "81", "name": "Schválit AC", "to": {"name": "REFINED"}},
           {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}}]
STATE = {"enabled": True, "reason": None, "transition_error": None, "offered": OFFERED}


def fake_info(keys, force=False):
    if not STATE["enabled"]:
        return {"enabled": False, "reason": "chybí JIRA_EMAIL", "tickets": {}}
    return {"enabled": True, "reason": None, "tickets": {k: TICKETS[k] for k in keys if k in TICKETS}}


def fake_do_transition(key, tid):
    if STATE["transition_error"]:
        raise STATE["transition_error"]
    CALLS.append(("transition", key, tid))
    TICKETS[key]["status"] = "REFINED"


jira.info = fake_info
jira.transitions = lambda key: STATE["offered"]
jira.do_transition = fake_do_transition
jira.add_comment = lambda key, text: CALLS.append(("comment", key, text))
jira.invalidate = lambda key=None: None
jira.status_names = lambda project="APS": {"TO DO", "REFINED", "In Progress"}
tmp = tempfile.mkdtemp()
approve.LOG = os.path.join(tmp, "approve.log")
approve.CONFIG = os.path.join(tmp, "config.json")


def reset(**tickets):
    TICKETS.clear()
    TICKETS.update(tickets)
    CALLS.clear()
    STATE.update(enabled=True, transition_error=None, offered=OFFERED)
    approve._state.update(last=0.0, recent=[])
    if os.path.exists(approve.LOG):
        os.remove(approve.LOG)


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except approve.ApproveError as e:
        return e.status, str(e)
    return None, None


reset(**{"APS-1": make()})
pl = approve.plan("APS-1")
check("plan: the transition is found by its TARGET status", (pl["transition"]["id"], pl["transition"]["to"]), ("81", "REFINED"))
check("plan: lists the AC and the readiness, no blockers", (len(pl["criteria"]), pl["score"], pl["requires_reason"]), (2, 8, False))
check("plan writes nothing", CALLS, [])
STATE["offered"] = [{"id": "5", "name": "Cokoli jiného", "to": {"name": "REFINED"}}]
check("plan: a differently named transition to REFINED is still found", approve.plan("APS-1")["transition"]["id"], "5")

reset(**{"APS-1": make(status="In Progress")})
check("plan refuses a ticket that is already in development", refused(approve.plan, "APS-1")[0], 409)
reset(**{"APS-1": make(status="REFINED")})
check("plan refuses an already approved ticket", "už jsou schválená" in (refused(approve.plan, "APS-1")[1] or ""), True)
reset(**{"APS-1": make(crit=[])})
check("plan refuses a ticket without numbered AC", refused(approve.plan, "APS-1")[0], 409)
reset(**{"APS-1": make()})
STATE["offered"] = [OFFERED[0], OFFERED[2]]
check("plan refuses when the workflow offers no transition to REFINED", "nenabízí přechod do REFINED" in (refused(approve.plan, "APS-1")[1] or ""), True)
STATE["offered"] = OFFERED
check("plan refuses a bad key", refused(approve.plan, "XYZ-1; drop")[0], 400)
check("plan refuses a missing ticket", refused(approve.plan, "APS-999")[0], 404)
STATE["enabled"] = False
check("plan refuses when Jira is not set up", refused(approve.plan, "APS-1")[0], 503)

reset(**{"APS-1": make()})
fp = approve.plan("APS-1")["fingerprint"]
check("execute needs an explicit confirmation", (refused(approve.execute, "APS-1", fp, False)[0], CALLS), (400, []))
check("execute needs confirm to be exactly True", (refused(approve.execute, "APS-1", fp, "yes")[0], CALLS), (400, []))
check("execute with a foreign fingerprint is refused", (refused(approve.execute, "APS-1", "0" * 16, True)[0], CALLS), (409, []))
TICKETS["APS-1"]["ac"]["criteria"][0]["text"] = "Změněné AC, které člověk neviděl."
check("the fingerprint changes when an AC text changes", approve.plan("APS-1")["fingerprint"] != fp)
check("approving what was NOT seen is refused (AC edited after the dialog opened)", (refused(approve.execute, "APS-1", fp, True)[0], CALLS), (409, []))

reset(**{"APS-1": make()})
fp = approve.plan("APS-1")["fingerprint"]
TICKETS["APS-1"]["updated"] = "2026-11-18T11:00:00.000+0100"
check("a later update of the ticket changes the fingerprint too", approve.plan("APS-1")["fingerprint"] != fp)

reset(**{"APS-1": make()})
fp = approve.plan("APS-1")["fingerprint"]
res = approve.execute("APS-1", fp, True)
check("execute: exactly one write, the transition", CALLS, [("transition", "APS-1", "81")])
check("execute: result reports the new status, no comment without an override", (res["ok"], res["from"], res["to"], res["comment"]), (True, "TO DO", "REFINED", None))
audit = [json.loads(x) for x in open(approve.LOG)]
check("execute is audited", (audit[-1]["result"], audit[-1]["key"], audit[-1]["to"]), ("ok", "APS-1", "REFINED"))
check("a repeated click on an already approved ticket is refused (409)", refused(approve.execute, "APS-1", fp, True)[0], 409)
TICKETS["APS-1"]["status"] = "TO DO"
fp2 = approve.plan("APS-1")["fingerprint"]
check("the same ticket approved twice within a minute is rate-limited (429)", (refused(approve.execute, "APS-1", fp2, True)[0], len(CALLS)), (429, 1))

ASKING = {"type": "doc", "version": 1, "content": DESC["content"] + [h("Otevřené otázky"), p("Má limit platit i pro víkendy?")]}
reset(**{"APS-2": make(labels=["agent-ceka"])})
check("the label agent-ceka alone is no blocker", approve.plan("APS-2")["requires_reason"], False)
reset(**{"APS-2": make(desc=ASKING)})
pl = approve.plan("APS-2")
check("a blocker (an open question) makes the reason required", (pl["requires_reason"], [b["id"] for b in pl["blocks"]]), (True, ["otazky"]))
fp = pl["fingerprint"]
check("without a reason nothing is written", (refused(approve.execute, "APS-2", fp, True)[0], CALLS), (400, []))
check("a too short reason is refused", (refused(approve.execute, "APS-2", fp, True, "ok")[0], CALLS), (400, []))
res = approve.execute("APS-2", fp, True, "Otázky řeším s produktovým vlastníkem zítra, AC jsou jinak hotová.")
kinds = [c[0] for c in CALLS]
check("with a reason: transition first, then the comment", kinds, ["transition", "comment"])
check("the comment carries the blocker and the reason", ("Žádné nevyřešené otázky" in CALLS[1][2], "produktovým vlastníkem" in CALLS[1][2]), (True, True))
check("the audit records the overridden check and the reason", (json.loads(list(open(approve.LOG))[-1])["overridden"], res["comment"]), (["otazky"], True))

reset(**{"APS-1": make()})
fp = approve.plan("APS-1")["fingerprint"]
STATE["transition_error"] = urllib.error.HTTPError("u", 400, "bad", {}, None)
st, msg = refused(approve.execute, "APS-1", fp, True)
check("Jira refuses the transition: clear 502, no comment, audited", (st, "HTTP 400" in msg, CALLS, json.loads(list(open(approve.LOG))[-1])["result"]), (502, True, [], "failed: HTTP 400"))

check("approval is enabled by default and REFINED exists", (approve.cfg()["enabled"], approve.cfg()["refined_exists"]), (True, True))
json.dump({"approve": {"enabled": False}}, open(approve.CONFIG, "w"))
check("`flow approve off` switches it off", approve.cfg()["enabled"], False)
jira.status_names = lambda project="APS": {"TO DO", "In Progress"}
check("refined_exists is False while the status is not in the project", approve.cfg()["refined_exists"], False)

try:
    approve.plan("nope")
except approve.ApproveError as e:
    check("ApproveError carries mk = [key, params]", e.mk, ["approve.srv.bad_key", {}])
check("every approve error key lives in approve.srv.*", all(m.startswith("approve.srv.") for m in re.findall(r'k\("([\w.]+)"', open(approve.__file__).read()) if m.startswith("approve")), True)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
