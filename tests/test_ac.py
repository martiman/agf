#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import ac

CFG = dict(ac.DEFAULTS)


def para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def doc(*nodes):
    return {"type": "doc", "version": 1, "content": list(nodes)}


def tasks(*items):
    return {"type": "taskList", "content": [
        {"type": "taskItem", "attrs": {"state": "DONE" if d else "TODO"},
         "content": [{"type": "text", "text": t}]} for t, d in items]}


def move(at, to):
    return {"created": at, "items": [{"field": "status", "toString": to}]}


def ac_edit(at, frm, to):
    return {"created": at, "items": [{"field": "Acceptance Criteria", "fieldId": "customfield_10606",
                                      "fromString": frm, "toString": to}]}


AC_FIELD = doc(tasks(("AC-1 limit: 12 000 = over", False), ("AC-2 boundary: 10 000 = ok", False)))
T = lambda d, h="10:00:00": f"2026-11-{d}T{h}.000+0100"
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def gate(field=None, desc=None, hist=(), status="TO DO"):
    return ac.analyze(field, desc, list(hist), status, CFG)


r = gate(field=AC_FIELD)
check("field: two numbered criteria", (r["source"], r["total"], [c["id"] for c in r["criteria"]]), ("field", 2, [1, 2]))
r = gate(desc=doc(para("Problém: x"), para("AC-1: a"), para("AC-02 b"), para("Poznámka")))
check("description: AC-n lines only, AC-02 normalised", (r["source"], [c["id"] for c in r["criteria"]]), ("description", [1, 2]))
r = gate(field=doc(tasks(("bez čísla", True))))
check("field: unnumbered kept, ticked counted", (r["total"], r["ticked"], r["criteria"][0]["id"]), (1, 1, None))
check("no AC at all -> none", gate(desc=doc(para("jen popis")))["gate"], "none")

check("TO DO with AC -> draft", gate(field=AC_FIELD)["gate"], "draft")
check("TO DO without AC -> none", gate()["gate"], "none")
check("REFINED, no edits -> approved",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED")], status="REFINED")["gate"], "approved")
check("In Progress after REFINED -> approved",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), move(T("11"), "In Progress")], status="In Progress")["gate"], "approved")
check("AC edited after REFINED -> changed",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), ac_edit(T("11"), "* AC-1 a", "* AC-1 b")], status="REFINED")["gate"], "changed")
check("AC edited BEFORE REFINED -> approved",
      gate(field=AC_FIELD, hist=[ac_edit(T("09"), "", "* AC-1 a"), move(T("10"), "REFINED")], status="REFINED")["gate"], "approved")
check("ticking a checkbox after REFINED is not a change",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), ac_edit(T("11"), "* [ ] AC-1 limit", "* [x] AC-1 limit")], status="In Progress")["gate"], "approved")
check("sent back to TO DO -> draft",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), move(T("11"), "TO DO")], status="TO DO")["gate"], "draft")
check("re-approved after edit -> approved again",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), ac_edit(T("11"), "a", "b"), move(T("11", "12:00:00"), "TO DO"),
                                 move(T("12"), "REFINED")], status="REFINED")["gate"], "approved")
check("WAITING after REFINED stays approved",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"), move(T("11"), "WAITING")], status="WAITING")["gate"], "approved")
check("WAITING before any REFINED -> draft (not started)",
      gate(field=AC_FIELD, hist=[move(T("10"), "WAITING")], status="WAITING")["gate"], "draft")
check("In Progress, never REFINED -> legacy",
      gate(field=AC_FIELD, hist=[move(T("10"), "In Progress")], status="In Progress")["gate"], "legacy")
check("ACCEPTED, no history -> legacy", gate(status="ACCEPTED")["gate"], "legacy")
check("DECLINED -> closed", gate(field=AC_FIELD, status="DECLINED")["gate"], "closed")
check("description edit counts only when AC come from description",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"),
                                 {"created": T("11"), "items": [{"field": "description", "fromString": "a", "toString": "b"}]}],
           status="REFINED")["gate"], "approved")
check("missing from/to strings count as a change",
      gate(field=AC_FIELD, hist=[move(T("10"), "REFINED"),
                                 {"created": T("11"), "items": [{"field": "Acceptance Criteria", "fieldId": "customfield_10606"}]}],
           status="REFINED")["gate"], "changed")

r = gate(field=AC_FIELD, hist=[move(T("10"), "In Progress"), move(T("12"), "TO DO"), move(T("14", "09:30:00"), "TO DO")], status="TO DO")
check("status_since = the last move into the current status", (r["status_since"] or "").startswith("2026-11-14T09:30"), True)
check("status_since is None without any move", gate(field=AC_FIELD, status="TO DO")["status_since"], None)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
