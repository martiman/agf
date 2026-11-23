#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime

CONFIG = os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "config.json")
DEFAULTS = {
    "refined_statuses": ["REFINED"],
    "ac_field": "customfield_10606",
    "ac_field_name": "Acceptance Criteria",
}
EARLY = {"TO DO", "Backlog"}
BEFORE_START = {"TO DO", "Backlog", "WAITING", "DECLINED"}
AC_RE = re.compile(r"^\s*AC[-\s]?0*(\d+)\s*[:.)–-]?\s*(.*)$", re.I)


def config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg



def _inline(node):
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return " "
    return "".join(_inline(c) for c in node.get("content", []) or [])


def adf_lines(node):
    if not isinstance(node, dict):
        return []
    t = node.get("type")
    if t in ("paragraph", "heading"):
        s = _inline(node).strip()
        return [(s, None)] if s else []
    if t == "taskItem":
        s = _inline(node).strip()
        return [(s, (node.get("attrs") or {}).get("state") == "DONE")] if s else []
    out = []
    for c in node.get("content", []) or []:
        out += adf_lines(c)
    return out


def _criteria(lines, keep_unnumbered):
    out = []
    for text, ticked in lines:
        m = AC_RE.match(text)
        if m:
            out.append({"id": int(m.group(1)), "text": (m.group(2) or text)[:200], "ticked": ticked})
        elif keep_unnumbered:
            out.append({"id": None, "text": text[:200], "ticked": ticked})
    return out



def _ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"\[[ x]\]", " ", s)
    s = re.sub(r"\((/|x|i|!)\)", " ", s)
    s = re.sub(r"[*_{}\[\]#>|~`-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _content_changed(item):
    frm, to = item.get("fromString"), item.get("toString")
    if frm is None and to is None:
        return True
    return _norm(frm) != _norm(to)



def analyze(field_adf, desc_adf, histories, status, cfg=None):
    cfg = cfg or config()
    refined = set(cfg["refined_statuses"])

    field_lines = adf_lines(field_adf)
    if field_lines:
        source, criteria = "field", _criteria(field_lines, True)
    else:
        crit = _criteria(adf_lines(desc_adf), False)
        source, criteria = ("description", crit) if crit else (None, [])
    ac_present = bool(criteria)

    moves, ac_changes = [], []
    for h in histories or []:
        ts = _ts(h.get("created"))
        if ts is None:
            continue
        for it in h.get("items", []):
            if it.get("field") == "status":
                moves.append((ts, it.get("toString")))
            elif it.get("fieldId") == cfg["ac_field"] or it.get("field") == cfg["ac_field_name"]:
                if _content_changed(it):
                    ac_changes.append(ts)
            elif it.get("field") == "description" and source == "description":
                if _content_changed(it):
                    ac_changes.append(ts)

    approved_at = max((ts for ts, to in moves if to in refined), default=None)
    started = status not in BEFORE_START and status not in refined or any(
        to not in BEFORE_START and to not in refined for _, to in moves
    )
    changed_at = max((c for c in ac_changes if approved_at and c > approved_at), default=None)

    if status == "DECLINED":
        gate = "closed"
    elif approved_at and (status in refined or status not in EARLY):
        gate = "changed" if changed_at else "approved"
    elif approved_at:
        gate = "draft" if ac_present else "none"
    elif started:
        gate = "legacy"
    else:
        gate = "draft" if ac_present else "none"

    since = max((ts for ts, to in moves if to == status), default=None)

    return {
        "gate": gate,
        "status_since": since.isoformat() if since else None,
        "source": source,
        "criteria": criteria[:30],
        "total": len(criteria),
        "ticked": sum(1 for c in criteria if c["ticked"]),
        "approved_at": approved_at.isoformat() if approved_at else None,
        "ac_changed_at": changed_at.isoformat() if changed_at else None,
    }
