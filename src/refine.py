#!/usr/bin/env python3
import contextlib
import fcntl
import json
import os
import re
import time

from msg import k

DIR = os.environ.get("FLOW_REFINE_DIR") or os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "refine")
KEY_RE = re.compile(r"^APS-\d+$")
MAX_Q, MAX_OPT, MAX_AC, MAX_DEC, MAX_UNRES = 8, 4, 12, 20, 10
KEEP_WRITTEN_DAYS = 14


class RefineError(ValueError):
    def __init__(self, message, mk=None):
        super().__init__(message)
        self.mk = mk


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _clean(value, n):
    s = "" if value is None else str(value)
    s = "".join(ch for ch in s if ch == "\n" or ch.isprintable())
    return s.strip()[:n]


MAX_AC_LEN = 1500


def _strict(value, n, what, wk=None):
    s = _clean(value, 10 ** 9)
    if len(s) > n:
        raise RefineError(f"{what} je příliš dlouhé ({len(s)} znaků, limit {n}). Zkraťte to nebo rozdělte; text se neořezává.",
                          [wk[0], dict(wk[1], len=len(s), max=n)] if wk else None)
    return s


def valid_key(key):
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise RefineError("Neplatný klíč tiketu (čekám tvar APS-123).", k("refine.srv.bad_key"))
    return key


def _path(key):
    return os.path.join(DIR, key + ".json")


@contextlib.contextmanager
def _locked():
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    with open(os.path.join(DIR, ".lock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def load(key):
    try:
        with open(_path(key)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(rec):
    rec["updated_at"] = _now()
    tmp = _path(rec["key"]) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(rec["key"]))


def _new(key):
    return {"key": key, "stage": "questions", "round": 0, "questions": [], "draft": None,
            "approved_version": None, "approved_at": None, "written_at": None, "note": "",
            "created_at": _now(), "updated_at": _now(), "history": []}


def _log(rec, event, detail=""):
    rec["history"] = (rec.get("history") or [])[-49:] + [{"ts": _now(), "ev": event, "detail": detail}]


def _pending(rec):
    return [q for q in rec["questions"] if q["answer"] is None]



def ask(key, questions):
    valid_key(key)
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_Q:
        raise RefineError(f"Zadejte 1 až {MAX_Q} otázek.")
    with _locked():
        rec = load(key) or _new(key)
        rec["round"] += 1
        n = max([int(q["id"][1:]) for q in rec["questions"]] or [0])
        new = []
        for q in questions:
            if isinstance(q, str):
                q = {"text": q}
            if not isinstance(q, dict):
                raise RefineError("Otázka musí být text nebo objekt s polem text.")
            text = _strict(q.get("text"), 400, "Text otázky")
            if not text:
                raise RefineError("Otázka bez textu.")
            opts = []
            for o in (q.get("options") or [])[:MAX_OPT]:
                d = o if isinstance(o, dict) else {"label": o}
                label = _strict(d.get("label"), 120, "Možnost odpovědi")
                if label:
                    opts.append({"label": label, "recommended": d.get("recommended") is True, "note": _strict(d.get("note"), 400, "Poznámka k možnosti")})
            n += 1
            item = {"id": f"Q{n}", "round": rec["round"], "text": text, "why": _strict(q.get("why"), 300, "Důvod otázky"),
                    "options": opts, "answer": None, "consumed": False}
            if q.get("source") == "jira":
                item["source"], item["src_text"] = "jira", _clean(q.get("src_text"), 600)
            new.append(item)
        rec["questions"] += new
        rec["stage"] = "questions"
        rec["approved_version"] = rec["approved_at"] = rec["written_at"] = None
        _log(rec, "ask", f"kolo {rec['round']}: {len(new)} otázek")
        _save(rec)
        return rec, new


def read_answers(key):
    valid_key(key)
    with _locked():
        rec = load(key)
        if not rec:
            return None, []
        new = [q for q in rec["questions"] if q["answer"] and not q["consumed"]]
        if new:
            for q in new:
                q["consumed"] = True
            _log(rec, "read", f"{len(new)} odpovědí převzato agentem")
            _save(rec)
        return rec, new


def _draft_text(d, key, n, label):
    return _strict(d.get(key), n, "Sekce " + label) if isinstance(d, dict) else ""


def draft(key, d):
    valid_key(key)
    if not isinstance(d, dict):
        raise RefineError("Návrh musí být objekt.")
    ac_in = d.get("ac")
    if not isinstance(ac_in, list) or not 1 <= len(ac_in) <= MAX_AC:
        raise RefineError(f"Návrh musí mít 1 až {MAX_AC} akceptačních kritérií (pole ac).")
    ac, used = [], set()
    for i, a in enumerate(ac_in, 1):
        a = a if isinstance(a, dict) else {"text": a}
        text = _strict(a.get("text"), MAX_AC_LEN, f"AC {i}")
        if not text:
            raise RefineError(f"AC {i} nemá text.")
        try:
            aid = int(a.get("id", i))
        except (TypeError, ValueError):
            raise RefineError(f"AC {i} má neplatné id.")
        if aid in used or aid < 1:
            raise RefineError(f"Id AC-{aid} se opakuje nebo je neplatné.")
        used.add(aid)
        ac.append({"id": aid, "text": text, "from": _clean(a.get("from"), 20), "edited": False})
    decisions = []
    for dc in (d.get("decisions") or [])[:MAX_DEC]:
        if isinstance(dc, dict) and _clean(dc.get("choice"), 10 ** 9):
            decisions.append({"q": _clean(dc.get("q"), 20), "text": _strict(dc.get("text"), 500, "Znění otázky v rozhodnutí"),
                              "choice": _strict(dc.get("choice"), 500, "Volba v rozhodnutí"), "note": _strict(dc.get("note"), 500, "Poznámka k rozhodnutí")})
    unresolved = [_strict(u, 500, "Otevřená otázka") for u in (d.get("unresolved") or [])[:MAX_UNRES] if _clean(u, 10 ** 9)]
    with _locked():
        rec = load(key) or _new(key)
        version = (rec["draft"] or {}).get("version", 0) + 1
        rec["draft"] = {"version": version, "problem": _draft_text(d, "problem", 4000, "problem"),
                        "where": _draft_text(d, "where", 4000, "where"), "expected": _draft_text(d, "expected", 4000, "expected"),
                        "ac": ac, "decisions": decisions, "unresolved": unresolved, "at": _now()}
        rec["stage"] = "draft"
        rec["approved_version"] = rec["approved_at"] = rec["written_at"] = None
        _log(rec, "draft", f"verze {version}")
        _save(rec)
        return rec


def done(key, note=""):
    valid_key(key)
    with _locked():
        rec = load(key)
        if not rec or rec["stage"] != "approved":
            raise RefineError("Zapsat lze jen schválený návrh. Stav: " + (rec["stage"] if rec else "žádná schránka") +
                              ". Počkejte na schválení v dashboardu.")
        rec["stage"], rec["written_at"], rec["note"] = "written", _now(), _clean(note, 300)
        _log(rec, "done", rec["note"])
        _save(rec)
        return rec



def answer(key, answers):
    valid_key(key)
    if not isinstance(answers, dict) or not answers:
        raise RefineError("Chybí odpovědi.", k("refine.srv.no_answers"))
    with _locked():
        rec = load(key)
        if not rec:
            raise RefineError("K tiketu není žádná schránka.", k("refine.srv.no_mailbox"))
        by_id = {q["id"]: q for q in rec["questions"]}
        for qid, a in answers.items():
            q = by_id.get(qid)
            if not q:
                raise RefineError(f"Neznámá otázka {qid}.", k("refine.srv.unknown_q", qid=qid))
            if q["answer"] is not None:
                raise RefineError(f"Otázka {qid} už je zodpovězená.", k("refine.srv.q_answered", qid=qid))
            a = a if isinstance(a, dict) else {}
            choice, text, defer = _strict(a.get("choice"), 120, f"Volba u {qid}", k("refine.srv.too_long_choice", qid=qid, len=0, max=0)) or None, \
                _strict(a.get("text"), 1000, f"Odpověď na {qid}", k("refine.srv.too_long_answer", qid=qid, len=0, max=0)), a.get("defer") is True
            if choice and q["options"] and choice not in [o["label"] for o in q["options"]]:
                raise RefineError(f"Neplatná volba u {qid}.", k("refine.srv.bad_choice", qid=qid))
            if not (choice or text or defer):
                raise RefineError(f"Odpověď na {qid} je prázdná.", k("refine.srv.empty_answer", qid=qid))
            q["answer"] = {"choice": choice, "text": text, "defer": defer, "at": _now()}
        if not _pending(rec) and rec["stage"] == "questions":
            rec["stage"] = "answered"
        _log(rec, "answer", ", ".join(sorted(answers)))
        _save(rec)
        return rec


def edit_ac(key, edits):
    valid_key(key)
    with _locked():
        rec = load(key)
        if not rec or rec["stage"] != "draft" or not rec["draft"]:
            raise RefineError("AC lze upravit jen v návrhu čekajícím na schválení.", k("refine.srv.ac_not_editable"))
        by_id = {str(a["id"]): a for a in rec["draft"]["ac"]}
        for aid, text in (edits or {}).items():
            a, t = by_id.get(str(aid)), _strict(text, MAX_AC_LEN, f"AC-{aid}", k("refine.srv.too_long_ac", aid=aid, len=0, max=0))
            if not a:
                raise RefineError(f"Neznámé AC-{aid}.", k("refine.srv.unknown_ac", aid=aid))
            if not t:
                raise RefineError(f"AC-{aid} nesmí být prázdné.", k("refine.srv.ac_empty", aid=aid))
            if t != a["text"]:
                a["text"], a["edited"] = t, True
        _log(rec, "edit", ", ".join(str(k) for k in edits))
        _save(rec)
        return rec


def approve(key):
    valid_key(key)
    with _locked():
        rec = load(key)
        if not rec or rec["stage"] != "draft" or not rec["draft"]:
            raise RefineError("Schválit lze jen návrh zadání, který agent publikoval.", k("refine.srv.not_approvable"))
        rec["stage"], rec["approved_version"], rec["approved_at"] = "approved", rec["draft"]["version"], _now()
        _log(rec, "approve", f"verze {rec['approved_version']}")
        _save(rec)
        return rec


def discard(key):
    valid_key(key)
    with _locked():
        try:
            os.remove(_path(key))
            return True
        except OSError:
            return False



def summary(rec):
    pend = _pending(rec)
    unconsumed = [q for q in rec["questions"] if q["answer"] and not q["consumed"]]
    st = rec["stage"]
    return {"stage": st, "round": rec["round"], "pending": len(pend), "unconsumed": len(unconsumed),
            "open": (st == "questions" and bool(pend)) or st == "draft",
            "waiting_agent": bool(unconsumed) or st == "approved",
            "version": (rec.get("draft") or {}).get("version"), "updated_at": rec["updated_at"],
            "written_at": rec.get("written_at")}


def summaries():
    out = {}
    try:
        names = os.listdir(DIR)
    except OSError:
        return out
    for n in names:
        if n.endswith(".json") and KEY_RE.match(n[:-5]):
            rec = load(n[:-5])
            if rec:
                out[rec["key"]] = summary(rec)
    return out


def prune():
    cutoff = time.time() - KEEP_WRITTEN_DAYS * 86400
    try:
        names = os.listdir(DIR)
    except OSError:
        return
    for n in names:
        p = os.path.join(DIR, n)
        if n.endswith(".json") and os.path.getmtime(p) < cutoff:
            rec = load(n[:-5])
            if rec and rec.get("stage") == "written":
                os.remove(p)


def draft_checks(rec):
    d, checks = rec.get("draft"), []
    if not d:
        return checks
    for sec, label in (("problem", "Problém"), ("where", "Kde to je"), ("expected", "Očekávané chování")):
        checks.append({"status": "ok" if d[sec] else "warn", "label": f"Sekce „{label}“ je vyplněná",
                       "detail": "" if d[sec] else "Prázdná sekce se do popisu nezapíše.",
                       "label_k": k("refine.srv.sec_filled", name=label),
                       "detail_k": None if d[sec] else k("refine.srv.sec_empty")})
    n = len(d["ac"])
    checks.append({"status": "ok" if n <= 7 else "warn", "label": f"Počet AC: {n}",
                   "detail": "" if n <= 7 else "Víc než 7 kritérií: zvažte rozdělení tiketu.",
                   "label_k": k("refine.srv.ac_count", n=n), "detail_k": None if n <= 7 else k("refine.srv.ac_many")})
    try:
        import spec
        for a in d["ac"]:
            for w, wk in spec._criterion_warn_pairs(a["text"]):
                checks.append({"status": "warn", "label": f"AC-{a['id']}", "detail": w, "detail_k": wk})
    except Exception:
        pass
    pend = len(_pending(rec))
    if pend:
        checks.append({"status": "warn", "label": f"Nezodpovězené otázky: {pend}", "detail": "Agent je ještě nezapracoval.",
                       "label_k": k("refine.srv.pending", n=pend), "detail_k": k("refine.srv.pending_detail")})
    if d["unresolved"]:
        checks.append({"status": "warn", "label": f"Nevyřešené otázky v návrhu: {len(d['unresolved'])}",
                       "detail": "Zapíšou se do sekce „Otevřené otázky“ a brání schválení AC v Jiře.",
                       "label_k": k("refine.srv.unresolved", n=len(d["unresolved"])), "detail_k": k("refine.srv.unresolved_detail")})
    return checks



_PROPOSAL = re.compile(r"\s*(?:Návrh|Doporučení)\s*:\s*", re.I)


def import_jira(key, texts):
    valid_key(key)
    have = {q.get("src_text") for q in (load(key) or {}).get("questions", []) if q.get("source") == "jira"}
    new = []
    for t in texts or []:
        t = _clean(t, 600)
        if not t or t in have:
            continue
        m = _PROPOSAL.search(t)
        question, proposal = (t[:m.start()], t[m.end():]) if m else (t, "")
        question = question.strip() or t
        q = {"text": question[:400], "source": "jira", "src_text": t, "why": "Převzato z částí „Otevřené otázky“ v popisu tiketu."}
        if proposal.strip():
            pr = proposal.strip()
            q["options"] = [{"label": "Přijmout návrh: " + (pr if len(pr) <= 96 else pr[:95] + "…"), "recommended": True, "note": pr[:400]}]
        new.append(q)
    if not new:
        return load(key), []
    rec, added = ask(key, new[:MAX_Q])
    return rec, added


def postable(rec):
    return [q for q in rec["questions"] if q["answer"] and not q["answer"].get("defer") and not q.get("posted_at")]


def mark_posted(key, qids, label):
    with _locked():
        rec = load(key)
        if not rec:
            raise RefineError("K tiketu není žádná schránka.", k("refine.srv.no_mailbox"))
        for q in rec["questions"]:
            if q["id"] in qids:
                q["posted_at"], q["posted_as"] = _now(), label
                if q.get("source") == "jira":
                    q["consumed"] = True
        _log(rec, "posted", ", ".join(sorted(qids)))
        _save(rec)
        return rec
