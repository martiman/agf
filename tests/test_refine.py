#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="flow-refine-test-")
os.environ["FLOW_REFINE_DIR"] = TMP
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import refine as r

fails = 0


def check(name, cond, extra=""):
    global fails
    fails += 0 if cond else 1
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(extra)))


def raises(fn, *a):
    try:
        fn(*a)
    except r.RefineError as e:
        return str(e)
    return None


K = "APS-9001"
QS = [{"text": "Počítá se limit z objemu, nebo z počtu zastávek?", "why": "file.ts:12",
       "options": [{"label": "z objemu", "recommended": True}, {"label": "z počtu zastávek"}]},
      "Má se limit zobrazit i v mobilní aplikaci?"]
try:
    check("bad key refused", raises(r.ask, "aps-1; rm", QS) is not None)
    check("no questions refused", raises(r.ask, K, []) is not None)
    check("empty text refused", raises(r.ask, K, [{"text": "  "}]) is not None)
    check("too many questions refused", raises(r.ask, K, [{"text": "x"}] * 9) is not None)

    rec, new = r.ask(K, QS)
    check("ask: ids Q1,Q2 and stage", [q["id"] for q in new] == ["Q1", "Q2"] and rec["stage"] == "questions" and rec["round"] == 1)
    check("ask: summary says the human must act", r.summaries()[K]["open"] and r.summaries()[K]["pending"] == 2)
    rec, new = r.ask(K, [{"text": "Třetí?"}])
    check("ask: second round continues numbering", new[0]["id"] == "Q3" and rec["round"] == 2)
    r2, _ = r.ask("APS-9002", [{"text": "a\x00b\x1b[31m ok"}])
    check("control characters are stripped", "\x00" not in r2["questions"][0]["text"] and "\x1b" not in r2["questions"][0]["text"])
    check("a too long question is refused, not cut", "limit 400" in (raises(r.ask, "APS-9003", [{"text": "x" * 401}]) or ""))

    check("answer: unknown question", raises(r.answer, K, {"Q9": {"text": "x"}}) is not None)
    check("answer: invalid option", raises(r.answer, K, {"Q1": {"choice": "něco jiného"}}) is not None)
    check("answer: empty refused", raises(r.answer, K, {"Q1": {}}) is not None)
    rec = r.answer(K, {"Q1": {"choice": "z objemu"}, "Q2": {"text": "ano, jen čtení"}})
    check("partial answers keep stage questions", rec["stage"] == "questions" and r.summaries()[K]["pending"] == 1)
    check("answered question is final", raises(r.answer, K, {"Q1": {"text": "jinak"}}) is not None)
    rec = r.answer(K, {"Q3": {"defer": True}})
    check("all answered -> stage answered, agent must be told", rec["stage"] == "answered" and r.summaries()[K]["waiting_agent"] and not r.summaries()[K]["open"])

    rec, got = r.read_answers(K)
    check("agent gets 3 new answers", len(got) == 3 and got[0]["answer"]["choice"] == "z objemu")
    rec, got = r.read_answers(K)
    check("second read has nothing new", got == [] and not r.summaries()[K]["waiting_agent"])
    check("read_answers of unknown ticket", r.read_answers("APS-9999")[0] is None)

    D = {"problem": "Limit se vyhodnocuje jinak než v Dispečeru.", "where": "src/pages/Limit.vue:40", "expected": "Stejně jako Dispečer.",
         "ac": [{"text": "Limit 10 000: 8 000 = ok, 12 000 = přes limit.", "from": "Q1"}, {"text": "Mobilní aplikace limit jen zobrazuje."}],
         "decisions": [{"q": "Q1", "choice": "z objemu"}], "unresolved": []}
    check("draft needs AC", raises(r.draft, K, {"ac": []}) is not None)
    check("draft duplicate AC id refused", raises(r.draft, K, {"ac": [{"id": 1, "text": "a"}, {"id": 1, "text": "b"}]}) is not None)
    check("approve before draft refused", raises(r.approve, "APS-9002") is not None)
    rec = r.draft(K, D)
    check("draft stored, ids numbered, stage draft", rec["stage"] == "draft" and [a["id"] for a in rec["draft"]["ac"]] == [1, 2] and rec["draft"]["version"] == 1)
    check("draft awaits approval (open)", r.summaries()[K]["open"])
    check("edit unknown AC refused", raises(r.edit_ac, K, {"7": "x"}) is not None)
    check("edit empty refused", raises(r.edit_ac, K, {"1": " "}) is not None)
    rec = r.edit_ac(K, {"2": "Mobilní aplikace limit zobrazuje, ale nepočítá."})
    check("edit marks AC as edited", rec["draft"]["ac"][1]["edited"] and not rec["draft"]["ac"][0]["edited"])
    check("done before approval refused", raises(r.done, K, "x") is not None)
    rec = r.approve(K)
    check("approve binds the version", rec["stage"] == "approved" and rec["approved_version"] == 1 and r.summaries()[K]["waiting_agent"])
    check("edit after approval refused", raises(r.edit_ac, K, {"1": "x"}) is not None)
    rec = r.done(K, "zapsáno do pole AC")
    check("done -> written", rec["stage"] == "written" and rec["written_at"] and not r.summaries()[K]["open"] and not r.summaries()[K]["waiting_agent"])

    r.draft(K, D); r.approve(K)
    rec = r.draft(K, D)
    check("new draft voids approval and bumps version", rec["stage"] == "draft" and rec["approved_at"] is None and rec["draft"]["version"] == 3)
    r.approve(K)
    rec, _ = r.ask(K, [{"text": "Ještě jedna věc?"}])
    check("new questions void approval", rec["stage"] == "questions" and rec["approved_version"] is None)

    LONG = "Skript vrátí kompaktní JSON. " * 40
    rec = r.draft(K, dict(D, ac=[{"text": LONG}]))
    check("a long AC is kept in full", rec["draft"]["ac"][0]["text"] == LONG.strip() and len(LONG) > 400)
    check("an AC over 1500 characters is refused", "limit 1500" in (raises(r.draft, K, dict(D, ac=[{"text": "A" * 1501}])) or ""))
    check("a too long section is refused", "Sekce problem" in (raises(r.draft, K, dict(D, problem="x" * 4001)) or ""))
    check("a too long human answer is refused", raises(r.answer, "APS-9002", {"Q1": {"text": "x" * 1001}}) is not None)

    rec = r.draft(K, dict(D, problem="", ac=[{"text": "Rychle a správně apod."}] + [{"text": f"AC číslo {i}"} for i in range(2, 9)],
                          unresolved=["Co s importem?"]))
    labels = [c["label"] + " " + c["detail"] for c in r.draft_checks(rec)]
    check("checks: empty section, >7 AC, unresolved", any("Problém" in x for x in labels) and any("Počet AC: 8" in x for x in labels) and any("Nevyřešené" in x for x in labels))

    check("discard removes the mailbox", r.discard(K) and r.load(K) is None and not r.discard(K))
    mode = oct(os.stat(os.path.join(TMP, "APS-9002.json")).st_mode & 0o777)
    check("mailbox file is private (600)", mode == "0o600", mode)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
