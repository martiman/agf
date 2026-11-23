#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import ac
import spec

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))


def text(t):
    return {"type": "paragraph", "content": [{"type": "text", "text": t}]}


def head(t):
    return {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": t}]}


def bullets(*items):
    return {"type": "bulletList", "content": [{"type": "listItem", "content": [text(i)]} for i in items]}


def doc(*n):
    return {"type": "doc", "version": 1, "content": list(n)}


def crit(*texts):
    return {"criteria": [{"id": i + 1, "text": t, "ticked": False} for i, t in enumerate(texts)]}


def st(res, cid):
    return next(c["status"] for c in res["checks"] if c["id"] == cid)


GOOD_DESC = doc(head("Problém"), text("Limit řidiče se vyhodnocuje jinak než v Dispečeru a řidič vidí jiné číslo."),
                head("Kde to je"), text("src/pages/DriverPage.vue:42 počítá limit z objemu."),
                head("Očekávané chování"), text("Limit se počítá jako v Dispečeru."))
GOOD_AC = crit("Když je objem 8 000 a limit 10 000, pak se zobrazí ok; při 12 000 se zobrazí upozornění.",
               "Pokud řidič nemá oprávnění, nezobrazí se tlačítko Uložit.")

r = spec.lint(GOOD_DESC, GOOD_AC, "Story")
check("good ticket: all scored checks ok", (r["score"], r["total"], r["block"]), (8, 8, 0))
check("good ticket: file:line recommendation is ok", st(r, "kde-radek"), "ok")

r = spec.lint(None, {"criteria": []}, "Story")
check("empty ticket: description fails, AC fail, per-AC checks skipped",
      (st(r, "popis"), st(r, "ac-cislovana"), st(r, "ac-testovatelna"), r["block"]), ("fail", "fail", "skip", 2))
r = spec.lint(doc(text("Krátké.")), {"criteria": []}, "Story")
check("short description fails", st(r, "popis"), "fail")
r = spec.lint(GOOD_DESC, {"criteria": [{"id": None, "text": "Když je limit překročen, pak se zobrazí upozornění.", "ticked": False}]}, "Story")
check("unnumbered AC fail the numbering check", st(r, "ac-cislovana"), "fail")
r = spec.lint(doc(head("Problém"), text("Dlouhý popis problému, který má dostatek znaků pro kontrolu délky popisu."),
                  head("Otevřené otázky"), bullets("Počítá se limit z objemu, nebo z počtu?", "Která role to smí?")), GOOD_AC, "Story")
check("open questions block (2)", (st(r, "otazky"), [c["detail"] for c in r["checks"] if c["id"] == "otazky"][0] == "2 otevřené otázky"), ("fail", True))
r = spec.lint(doc(head("Problém"), text("Dlouhý popis problému, který má dostatek znaků pro kontrolu délky popisu."),
                  head("Otevřené otázky"), text("Žádné.")), GOOD_AC, "Story")
check("'Žádné' under Otevřené otázky is not an open question", st(r, "otazky"), "ok")
r = spec.lint(GOOD_DESC, GOOD_AC, "Story", labels=["agent-ceka"])
check("label agent-ceka alone does not block (it only marks a hand-back)", st(r, "otazky"), "ok")

r = spec.lint(doc(head("Problém"), text("Dlouhý popis problému, který má dostatek znaků pro kontrolu délky popisu."),
                  head("Očekávané chování"), text("Funguje to.")), GOOD_AC, "Story")
check("Story without 'Kde to je' warns", st(r, "struktura"), "warn")
check("Bug does not need 'Kde to je'", st(spec.lint(doc(head("Problém"), text("Dlouhý popis problému, který má dostatek znaků pro kontrolu délky popisu."),
                                                      head("Očekávané chování"), text("Funguje to.")), GOOD_AC, "Bug"), "struktura"), "ok")
r = spec.lint(doc(text("Problém: tohle nefunguje a je to potřeba opravit v nejbližší době, protože to blokuje práci."),
                  text("Očekávané chování: funguje to."), text("Kde to je: src/a.vue:3")), GOOD_AC, "Story")
check("inline 'Problém: …' headers are recognised", st(r, "struktura"), "ok")

check("the word 'Problém' in a sentence is not a header",
      st(spec.lint(doc(text("Problém s přihlášením se objevuje u všech uživatelů a vypadá to na chybu v konfiguraci systému.")), GOOD_AC, "Bug"), "struktura"), "warn")

r = spec.lint(GOOD_DESC, crit(*["Když je to tak, pak se zobrazí A."] * 8), "Story")
check("more than 7 AC warns", st(r, "ac-pocet"), "warn")
r = spec.lint(GOOD_DESC, crit("Dobré.", "Když platí X, pak se zobrazí Y."), "Story")
check("too short AC is not testable", (st(r, "ac-testovatelna"), r["criteria"][0]["warns"] != []), ("warn", True))
r = spec.lint(GOOD_DESC, crit("Nová entita TelephonyCall:"), "Story")
check("an AC that is only a title (ends with a colon) is flagged", st(r, "ac-testovatelna"), "warn")
r = spec.lint(GOOD_DESC, crit("Trasa bez svozů má poslední svoz, příští svoz i dopravce prázdné.",
                              "Dotaz na svozy čte jen svozy tras dané provozovny, ne celou tabulku."), "Story")
check("a plain declarative statement is not flagged (calibration: no false warnings)", st(r, "ac-testovatelna"), "ok")
r = spec.lint(GOOD_DESC, crit("Na stage po nasazení klesne medián odpovědi pod 300 ms."), "Story")
check("a measurement in ms is not a business boundary", st(r, "ac-hranice"), "ok")
r = spec.lint(GOOD_DESC, crit("Limit 0 i prázdný limit se berou jako nulový limit."), "Story")
check("the value 0 is not a threshold", st(r, "ac-hranice"), "ok")
r = spec.lint(GOOD_DESC, crit("Aplikace je hezká a intuitivní pro uživatele."), "Story")
check("vague words are flagged per AC", (st(r, "ac-vagni"), any(w.startswith("vágní") for w in r["criteria"][0]["warns"])), ("warn", True))
r = spec.lint(GOOD_DESC, crit("Když limit přesáhne 10 000, pak se zobrazí upozornění."), "Story")
check("a limit with one number has no boundary", st(r, "ac-hranice"), "warn")
r = spec.lint(GOOD_DESC, crit("Když limit přesáhne 10 000 (8 000 = ok, 12 000 = přes), pak se zobrazí upozornění."), "Story")
check("a limit with a pair of numbers has a boundary", st(r, "ac-hranice"), "ok")
r = spec.lint(GOOD_DESC, crit("Při přihlášení se zobrazí 3 poslední tikety."), "Story")
check("a count without a limit word is not a boundary problem", st(r, "ac-hranice"), "ok")
r = spec.lint(GOOD_DESC, {"criteria": [{"id": None, "text": "Krátké.", "ticked": False}, {"id": None, "text": "Také krátké.", "ticked": False}]}, "Story")
check("unnumbered AC are reported individually", [c for c in r["checks"] if c["id"] == "ac-testovatelna"][0]["detail"], "AC #1, AC #2")

r = spec.lint(doc(head("Problém"), text("Dlouhý popis problému, který má dostatek znaků pro kontrolu délky popisu."),
                  head("Kde to je"), text("Stránka řidičů."), head("Očekávané chování"), text("Funguje.")), GOOD_AC, "Story")
check("missing file:line is info and not scored", (st(r, "kde-radek"), r["total"]), ("info", 8))

bad = spec.lint(doc(text("krátké")), crit("Rychle", "Limit 10 000 je překročen."), "Story")
for res, what in ((r, "good"), (bad, "bad"), (spec.lint(None, None, "Story"), "empty")):
    check(f"{what}: every check has label_k = [key, params]", all(c["label_k"][0].startswith("spec.") and isinstance(c["label_k"][1], dict) for c in res["checks"]), True)
    check(f"{what}: hint_k exists exactly when there is a hint; detail_k only with a detail (AC id lists have none)",
          all(bool(c.get("hint_k")) == bool(c["hint"]) and (not c.get("detail_k") or c["detail"]) for c in res["checks"]), True)
    check(f"{what}: every criterion has one warns_k per warning", all(len(c["warns"]) == len(c["warns_k"]) for c in res["criteria"]), True)
check("vague word: warns_k carries the word list", bad["criteria"][0]["warns_k"][-1], ["spec.warn.vague", {"list": "rychle"}])
check("open questions: plural parameter n", next(c["detail_k"] for c in spec.lint(doc(head("Otevřené otázky"), bullets("Jak?", "Kdy?")), GOOD_AC, "Story")["checks"] if c["id"] == "otazky"), ["spec.otazky.detail", {"n": 2}])

print("\n" + ("ALL PASSED" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
