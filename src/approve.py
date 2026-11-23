#!/usr/bin/env python3
import hashlib
import json
import os
import re
import time
import urllib.error

import ac
import jira
from msg import k

HOME = os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow")
CONFIG = os.path.join(HOME, "config.json")
LOG = os.environ.get("FLOW_APPROVE_LOG") or os.path.join(HOME, "approve.log")
KEY_RE = re.compile(r"^APS-\d+$")
FROM_STATUSES = ("TO DO", "Backlog")
MIN_REASON = 10
_state = {"last": 0.0, "recent": []}


class ApproveError(Exception):
    def __init__(self, status, message, mk=None):
        super().__init__(message)
        self.status = status
        self.mk = mk


def cfg():
    try:
        with open(CONFIG) as f:
            d = json.load(f).get("approve") or {}
    except (OSError, ValueError, AttributeError):
        d = {}
    names = jira.status_names()
    refined = set(ac.config()["refined_statuses"])
    return {"enabled": d.get("enabled", True) is not False,
            "refined_exists": None if names is None else bool(refined & names)}


def fingerprint(t):
    a = t.get("ac") or {}
    data = [t.get("updated"), t.get("status"), [c.get("text") for c in a.get("criteria", [])], a.get("total")]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()[:16]


def plan(key):
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise ApproveError(400, "Neplatný klíč tiketu.", k("approve.srv.bad_key"))
    info = jira.info([key], force=True)
    if not info.get("enabled"):
        raise ApproveError(503, "Jira není nastavená (JIRA_EMAIL / JIRA_API_TOKEN).", k("approve.srv.no_jira"))
    t = (info.get("tickets") or {}).get(key)
    if not t:
        raise ApproveError(502 if info.get("reason") else 404,
                           f"Tiket {key} se nepodařilo načíst" + (f" ({info['reason']})" if info.get("reason") else "") + ".",
                           k("approve.srv.load_failed_reason", ticket=key, reason=info["reason"]) if info.get("reason")
                           else k("approve.srv.load_failed", ticket=key))
    refined = set(ac.config()["refined_statuses"])
    status = t.get("status")
    a = t.get("ac") or {}
    if status in refined:
        raise ApproveError(409, "AC už jsou schválená (tiket je ve stavu REFINED).", k("approve.srv.already_refined"))
    if status not in FROM_STATUSES:
        raise ApproveError(409, f"Tiket je ve stavu {status}. AC se schvalují z TO DO, před začátkem vývoje.", k("approve.srv.wrong_status", status=status))
    if a.get("gate") in (None, "unknown"):
        raise ApproveError(502, "Stav AC se nepodařilo načíst z Jiry, schválení teď nejde bezpečně provést.", k("approve.srv.gate_unknown"))
    sp = a.get("spec")
    if not sp:
        raise ApproveError(502, "Kontrola zadání není k dispozici, schválení teď nejde bezpečně provést.", k("approve.srv.no_spec"))
    numbering = next((c for c in sp["checks"] if c["id"] == "ac-cislovana"), None)
    if not numbering or numbering["status"] != "ok":
        raise ApproveError(409, "Tiket nemá číslovaná AC (AC-1, AC-2, …), není co schvalovat.", k("approve.srv.no_numbering"))
    try:
        offered = jira.transitions(key)
    except Exception as e:
        raise ApproveError(502, f"Dostupné přechody se nepodařilo načíst ({type(e).__name__}).", k("approve.srv.transitions_failed", error=type(e).__name__))
    tr = next((x for x in offered if (x.get("to") or {}).get("name") in refined), None)
    if not tr:
        raise ApproveError(409, "Workflow tomuto tiketu zatím nenabízí přechod do REFINED.", k("approve.srv.no_transition"))
    blocks = [{"id": c["id"], "label": c["label"], "detail": c.get("detail", ""), "label_k": c.get("label_k"), "detail_k": c.get("detail_k")}
              for c in sp["checks"]
              if c["status"] == "fail" and c["severity"] == "block" and c["id"] != "ac-cislovana"]
    return {
        "key": key, "summary": t.get("summary"), "status": status, "gate": a.get("gate"), "assignee": t.get("assignee"),
        "transition": {"id": str(tr["id"]), "name": tr.get("name"), "to": tr["to"]["name"]},
        "criteria": [{"id": c.get("id"), "text": c.get("text"), "ticked": bool(c.get("ticked"))} for c in a.get("criteria", [])],
        "score": sp["score"], "total": sp["total"],
        "blocks": blocks, "requires_reason": bool(blocks),
        "warns": [c["label"] for c in sp["checks"] if c["status"] == "warn"],
        "warns_k": [c.get("label_k") for c in sp["checks"] if c["status"] == "warn"],
        "fingerprint": fingerprint(t),
    }


def _guard(key):
    now = time.time()
    _state["recent"] = [r for r in _state["recent"] if now - r[0] < 600]
    if now - _state["last"] < 2:
        raise ApproveError(429, "Příliš rychle za sebou, zkuste to za chvíli.", k("approve.srv.too_fast"))
    if len(_state["recent"]) >= 20:
        raise ApproveError(429, "Limit 20 schválení za 10 minut.", k("approve.srv.limit"))
    if any(r[1] == key and now - r[0] < 60 for r in _state["recent"]):
        raise ApproveError(429, "Tento tiket se právě schvaloval, počkejte minutu.", k("approve.srv.same_twice"))
    _state["last"] = now
    _state["recent"].append((now, key))


def audit(**rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def execute(key, fp, confirm, reason=None):
    if confirm is not True:
        raise ApproveError(400, "Chybí výslovné potvrzení.", k("approve.srv.no_confirm"))
    p = plan(key)
    if p["fingerprint"] != fp:
        audit(key=key, result="refused: changed since the dialog was opened")
        raise ApproveError(409, "Tiket se od otevření dialogu změnil (AC nebo stav). Otevřete schválení znovu a zkontrolujte AC.", k("approve.srv.changed"))
    reason = (reason or "").strip() if isinstance(reason, str) else ""
    if p["requires_reason"] and len(reason) < MIN_REASON:
        raise ApproveError(400, f"Kontrola zadání hlásí blokující věci. Napište důvod (aspoň {MIN_REASON} znaků), zapíše se do komentáře v Jiře.",
                           k("approve.srv.need_reason", min=MIN_REASON))
    try:
        _guard(key)
    except ApproveError as e:
        audit(key=key, result="refused: " + str(e))
        raise
    try:
        jira.do_transition(key, p["transition"]["id"])
    except urllib.error.HTTPError as e:
        audit(key=key, transition=p["transition"], result=f"failed: HTTP {e.code}")
        raise ApproveError(502, f"Jira přechod odmítla (HTTP {e.code}). Chybí oprávnění, nebo přechod blokuje pravidlo workflow.",
                           k("approve.srv.jira_refused", code=e.code))
    except Exception as e:
        audit(key=key, transition=p["transition"], result=f"failed: {type(e).__name__}")
        raise ApproveError(502, f"Přechod se nepodařilo provést ({type(e).__name__}).", k("approve.srv.transition_failed", error=type(e).__name__))
    comment = None
    if p["requires_reason"]:
        text = ("Schválení AC z dashboardu přes výhrady kontroly zadání (" + "; ".join(b["label"] for b in p["blocks"]) +
                "). Důvod: " + reason)
        try:
            jira.add_comment(key, text)
            comment = True
        except Exception:
            comment = False
    jira.invalidate(key)
    after = ((jira.info([key], force=True).get("tickets") or {}).get(key) or {}).get("status")
    audit(key=key, transition=p["transition"], **{"from": p["status"]}, to=after or p["transition"]["to"],
          score=f"{p['score']}/{p['total']}", overridden=[b["id"] for b in p["blocks"]], reason=reason or None,
          comment=comment, result="ok")
    return {"ok": True, "key": key, "from": p["status"], "to": after or p["transition"]["to"], "comment": comment}
