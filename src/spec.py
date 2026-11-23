#!/usr/bin/env python3
import re

import ac
from msg import k

SECTION_KEYS = {"problém": "problem", "kde to je": "where", "očekávané chování": "expected",
                "otevřené otázky": "questions", "dopad": "impact", "neověřeno": "unverified"}
SECTION_RE = re.compile(r"^\s*(problém|kde to je|očekávané chování|otevřené otázky|dopad|neověřeno)\s*:?\s*(.*)$", re.I | re.S)
NONE_RE = re.compile(r"^\s*(žádné|žádná|nejsou|nic|n/?a|—|–|-)\W*$", re.I)
VAGUE_RE = re.compile(r"\b(apod\.?|atd\.?|případně|podle potřeby|rychl\w*|správně|vhodn\w*|přiměřen\w*|adekvátn\w*|"
                      r"hezk\w*|intuitivn\w*|jednoduch\w*|uživatelsky přívětiv\w*)", re.I)
LIMIT_RE = re.compile(r"(limit|maxim|minim|nejvýš|nejméně|alespoň|aspoň|více než|méně než|přesáhn|překroč|"
                      r"\b(?:nad|pod)\s+\d|>=|<=)", re.I)
NUM_RE = re.compile(r"(?<![\w-])\d[\d  ]*(?:[.,]\d+)?")
MEASURE_RE = re.compile(r"\s*(?:ms|px|s|%)\b", re.I)
FILELINE_RE = re.compile(r"[\w./-]+\.(?:vue|ts|cs|py|sql|json|md):\d+")
MAX_AC = 7
MIN_DESC = 60


def _blocks(adf):
    out = []

    def walk(n):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "heading":
            out.append(("heading", ac._inline(n).strip()))
        elif t == "paragraph":
            out.append(("text", ac._inline(n).strip()))
        elif t == "taskItem":
            out.append(("item", ac._inline(n).strip()))
        elif t == "listItem":
            own = [ac._inline(c).strip() for c in n.get("content", []) or [] if c.get("type") == "paragraph"]
            out.append(("item", " ".join(x for x in own if x)))
            for c in n.get("content", []) or []:
                if c.get("type") != "paragraph":
                    walk(c)
        else:
            for c in n.get("content", []) or []:
                walk(c)
    walk(adf)
    return [(k, x) for k, x in out if x]


def _sections(blks):
    secs, cur = {}, None
    for kind, text in blks:
        m = SECTION_RE.match(text)
        if m and (kind == "heading" or not m.group(2).strip()
                  or re.match(r"^\s*" + re.escape(m.group(1)) + r"\s*:", text, re.I)):
            cur = SECTION_KEYS[m.group(1).lower()]
            secs.setdefault(cur, [])
            if m.group(2).strip():
                secs[cur].append(m.group(2).strip())
        elif kind == "heading":
            cur = None
        elif cur:
            secs[cur].append(text)
    return secs


def _numbers(text):
    vals = set()
    for m in NUM_RE.finditer(text):
        digits = re.sub(r"[^\d.,]", "", m.group(0)).replace(",", ".")
        if not digits or float(digits.rstrip(".") or 0) == 0:
            continue
        if MEASURE_RE.match(text[m.end():]):
            continue
        vals.add(digits)
    return vals


def _criterion_warn_pairs(text):
    warns = []
    t = text.strip()
    if len(t.split()) < 4 or t.endswith(":"):
        warns.append(("příliš krátké nebo jen nadpis (napište tvrzení, které jde ověřit)", k("spec.warn.short")))
    if LIMIT_RE.search(text) and len(_numbers(text)) == 1:
        warns.append(("číslo bez hraničního případu (uveďte hodnotu na hranici i za ní)", k("spec.warn.boundary")))
    v = sorted({m.group(0).lower() for m in VAGUE_RE.finditer(text)})
    if v:
        warns.append(("vágní: " + ", ".join(v), k("spec.warn.vague", list=", ".join(v))))
    return warns


def _criterion_warns(text):
    return [w for w, _ in _criterion_warn_pairs(text)]


def _check(cid, label, status, severity, detail="", hint="", detail_k=None, hint_k=None):
    c = {"id": cid, "label": label, "status": status, "severity": severity, "detail": detail, "hint": hint,
         "label_k": k("spec.%s.label" % cid.replace("-", "_"), **({"max": MAX_AC} if cid == "ac-pocet" else {}))}
    if detail and detail_k:
        c["detail_k"] = detail_k
    if hint and hint_k:
        c["hint_k"] = hint_k
    return c


def _id(cid, what):
    return "spec.%s.%s" % (cid.replace("-", "_"), what)


def lint(description_adf, ac_result, issue_type=None, labels=None):
    blks = _blocks(description_adf) if isinstance(description_adf, dict) else []
    text = "\n".join(t for _, t in blks)
    secs = _sections(blks)
    crit = (ac_result or {}).get("criteria") or []
    numbered = [c for c in crit if c.get("id") is not None]
    checks = []

    n = len(re.sub(r"\s+", " ", text).strip())
    checks.append(_check("popis", "Popis není prázdný", "ok" if n >= MIN_DESC else "fail", "block",
                         f"{n} znaků" if n < MIN_DESC else "", "Popište problém a očekávané chování aspoň několika větami.",
                         k(_id("popis", "detail"), n=n), k(_id("popis", "hint"))))

    need = ["problem", "expected"] if (issue_type or "").lower() == "bug" else ["problem", "where", "expected"]
    names = {"problem": "Problém", "where": "Kde to je", "expected": "Očekávané chování"}
    miss = [names[k] for k in need if k not in secs]
    checks.append(_check("struktura", "Struktura Problém / Kde to je / Očekávané chování", "ok" if not miss else "warn", "warn",
                         ("chybí: " + ", ".join(miss)) if miss else "", "Doplňte chybějící sekce, ať je zadání čitelné stejně jako ostatní.",
                         k(_id("struktura", "detail"), list=", ".join(miss)), k(_id("struktura", "hint"))))

    if numbered:
        checks.append(_check("ac-cislovana", "Existují číslovaná AC (AC-1, AC-2, …)", "ok", "block", f"{len(numbered)} AC",
                             detail_k=k("spec.n_ac", n=len(numbered))))
    elif crit:
        checks.append(_check("ac-cislovana", "Existují číslovaná AC (AC-1, AC-2, …)", "fail", "block", "AC jsou bez čísel",
                             "Očíslujte AC jako AC-1:, AC-2: … (čísla se po schválení nemění).",
                             k(_id("ac-cislovana", "detail_unnumbered")), k(_id("ac-cislovana", "hint_unnumbered"))))
    else:
        checks.append(_check("ac-cislovana", "Existují číslovaná AC (AC-1, AC-2, …)", "fail", "block", "AC nejsou napsaná",
                             "Napište AC jako AC-1:, AC-2: … (jedna ověřitelná věta). Pomůže „Doplnit zadání“.",
                             k(_id("ac-cislovana", "detail_none")), k(_id("ac-cislovana", "hint_none"))))

    pairs = [_criterion_warn_pairs(c.get("text") or "") for c in crit]
    per = [[w for w, _ in ps] for ps in pairs]
    if crit:
        label_of = lambda i: ("AC-%s" % crit[i]["id"]) if crit[i].get("id") is not None else "AC #%d" % (i + 1)
        checks.append(_check("ac-pocet", f"Nejvýš {MAX_AC} AC", "ok" if len(crit) <= MAX_AC else "warn", "warn",
                             f"{len(crit)} AC" if len(crit) > MAX_AC else "", "Příliš mnoho AC bývá znamení, že tiket je potřeba rozdělit.",
                             k("spec.n_ac", n=len(crit)), k(_id("ac-pocet", "hint"))))
        for cid, label, test in (
                ("ac-testovatelna", "Každé AC je úplné tvrzení (ne nadpis)", lambda w: any(x.startswith("příliš krátké") for x in w)),
                ("ac-hranice", "Číselná AC mají hraniční případ", lambda w: any(x.startswith("číslo bez") for x in w)),
                ("ac-vagni", "AC bez vágních slov", lambda w: any(x.startswith("vágní") for x in w))):
            bad = [label_of(i) for i, w in enumerate(per) if test(w)]
            hints = {"ac-testovatelna": "Přepište na tvrzení, které jde ověřit, např. „když … pak …“ nebo s číselným příkladem.",
                     "ac-hranice": "Doplňte příklad na hranici i za ní (limit 10 000: 8 000 = ok, 12 000 = přes).",
                     "ac-vagni": "Nahraďte slova jako „rychle“, „správně“, „apod.“ konkrétním číslem nebo chováním."}
            checks.append(_check(cid, label, "ok" if not bad else "warn", "warn", ", ".join(bad), hints[cid], hint_k=k(_id(cid, "hint"))))
    else:
        for cid, label in (("ac-pocet", f"Nejvýš {MAX_AC} AC"), ("ac-testovatelna", "Každé AC je jedna ověřitelná věta"),
                           ("ac-hranice", "Číselná AC mají hraniční případ"), ("ac-vagni", "AC bez vágních slov")):
            c = _check(cid, label, "skip", "warn", "ověří se, až budou AC", detail_k=k("spec.skip.detail"))
            c["label_k"] = k(_id(cid, "label_skip")) if cid == "ac-testovatelna" else c["label_k"]
            checks.append(c)

    q = [x for x in secs.get("questions", []) if not NONE_RE.match(x)]
    asks = "agent-ceka" in (labels or [])
    if q:
        nq = len(q)
        noun = "otevřená otázka" if nq == 1 else "otevřené otázky" if 2 <= nq <= 4 else "otevřených otázek"
        checks.append(_check("otazky", "Žádné nevyřešené otázky", "fail", "block", f"{nq} {noun}", "Odpovězte na otázky a smažte je z „Otevřené otázky“.",
                             k(_id("otazky", "detail"), n=nq), k(_id("otazky", "hint"))))
    else:
        checks.append(_check("otazky", "Žádné nevyřešené otázky", "ok", "block",
                             "štítek agent-ceka značí jen předání k posouzení, schválením ho sundáte" if asks else "",
                             detail_k=k(_id("otazky", "detail_label"))))

    if "where" in secs:
        has = bool(FILELINE_RE.search(" ".join(secs["where"])))
        checks.append(_check("kde-radek", "„Kde to je“ odkazuje na soubor:řádek", "ok" if has else "info", "info",
                             "" if has else "bez čísla řádku", "Doporučení: uveďte soubor:řádek, ať agent rychle najde místo.",
                             k(_id("kde-radek", "detail")), k(_id("kde-radek", "hint"))))

    scored = [c for c in checks if c["severity"] != "info"]
    return {
        "score": sum(1 for c in scored if c["status"] == "ok"),
        "total": len(scored),
        "block": sum(1 for c in scored if c["status"] == "fail" and c["severity"] == "block"),
        "checks": checks,
        "questions": [x[:600] for x in q][:10],
        "criteria": [{"id": c.get("id"), "warns": per[i], "warns_k": [wk for _, wk in pairs[i]]} for i, c in enumerate(crit)],
    }
