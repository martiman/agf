#!/usr/bin/env python3
import os
import urllib.request

import refine

LOCAL_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
NOTE = " Zapisuje jen do lokální schránky dashboardu (~/.flow/refine), ne do Jiry."


def _ping(base):
    try:
        with open(os.path.join(os.environ.get("FLOW_HOME") or os.path.expanduser("~/.flow"), "secret")) as f:
            secret = f.read().strip()
        req = urllib.request.Request(base + "/ping", data=b"", method="POST", headers={"X-Flow-Secret": secret})
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=0.7).read()
    except Exception:
        pass


def _ac_lines(d):
    return "\n".join(f"  AC-{a['id']}: {a['text']}" + ("  (upraveno uživatelem)" if a.get("edited") else "") for a in d["ac"])


def _draft_text(d):
    out = [f"Problém: {d['problem'] or '(prázdné)'}", f"Kde to je: {d['where'] or '(prázdné)'}",
           f"Očekávané chování: {d['expected'] or '(prázdné)'}", "Akceptační kritéria:", _ac_lines(d)]
    if d["decisions"]:
        out.append("Rozhodnutí:")
        out += [f"  {x['q'] or '-'} · {x['choice']}" + (f" ({x['note']})" if x["note"] else "") for x in d["decisions"]]
    if d["unresolved"]:
        out.append("Otevřené otázky:")
        out += [f"  - {u}" for u in d["unresolved"]]
    return "\n".join(out)


def make_tools(FlowError, base):

    def guard(fn):
        def run(args):
            try:
                return fn(args)
            except refine.RefineError as e:
                raise FlowError(str(e))
        return run

    def key_of(args):
        return refine.valid_key(args.get("key"))

    @guard
    def flow_ask(args):
        key = key_of(args)
        rec, new = refine.ask(key, args.get("questions"))
        _ping(base)
        return (f"Zveřejněno {len(new)} otázek k {key} (kolo {rec['round']}): {', '.join(q['id'] for q in new)}.\n"
                f"Uživatel je uvidí v dashboardu ({base}, panel Zadání u {key} a Inbox) a dostane upozornění.\n"
                f"TEĎ SKONČETE TAH. Řekněte uživateli: „Otázky jsou v dashboardu u {key}. Odpovězte tam a napište pokračuj.“ "
                "Nečekejte ve smyčce a neptejte se stejných věcí znovu v chatu.")

    @guard
    def flow_answers(args):
        key = key_of(args)
        rec, new = refine.read_answers(key)
        if not rec:
            return f"K {key} není žádná schránka. Nejdřív položte otázky (flow_ask) nebo publikujte návrh (flow_draft)."
        lines = [f"{key} · stav: {rec['stage']} · kolo {rec['round']}"]
        for q in new:
            a = q["answer"]
            if a["defer"]:
                shown = "ODLOŽENO: uživatel teď nechce rozhodnout, zapište to jako otevřenou otázku"
            else:
                shown = " · ".join(x for x in (a["choice"], a["text"]) if x)
            lines.append(f"{q['id']} {q['text']}\n   → {shown}")
        if not new:
            lines.append("Žádné nové odpovědi.")
        pend = [q for q in rec["questions"] if q["answer"] is None]
        if pend:
            lines.append(f"Uživatel ještě neodpověděl na {len(pend)} otázek: {', '.join(q['id'] for q in pend)}.")
        st, d = rec["stage"], rec.get("draft")
        if st == "approved" and d:
            lines += [f"SCHVÁLENÝ NÁVRH (verze {rec['approved_version']}, schváleno {rec['approved_at']}):", _draft_text(d),
                      "Zapište ho do Jiry postupem ticket-refine (pole Acceptance Criteria, sekce popisu, komentář „Rozhodnutí D-n“, "
                      "čtení zpět) a pak zavolejte flow_done. Texty AC upravené uživatelem zapište přesně tak."]
        elif st == "draft":
            lines.append(f"Návrh v{d['version']} čeká na schválení uživatelem v dashboardu. Do Jiry zatím nezapisujte.")
        elif st == "written":
            lines.append(f"Návrh je zapsaný do Jiry ({rec['written_at']}).")
        elif new and not pend:
            lines.append("Zapracujte odpovědi do AC. Zbývají-li blokující otázky, zavolejte flow_ask, jinak publikujte návrh zadání přes flow_draft.")
        return "\n".join(lines)

    @guard
    def flow_draft(args):
        key = key_of(args)
        rec = refine.draft(key, args)
        _ping(base)
        v = rec["draft"]["version"]
        return (f"Návrh zadání v{v} k {key} je v dashboardu (panel Zadání). Uživatel ho prohlédne, případně upraví AC a schválí.\n"
                f"Do Jiry zatím NEZAPISUJTE. Řekněte uživateli: „Návrh je v dashboardu u {key}. Zkontrolujte ho, schvalte a napište pokračuj.“ "
                "Po schválení ho přečtete přes flow_answers.")

    @guard
    def flow_done(args):
        key = key_of(args)
        rec = refine.done(key, args.get("note"))
        _ping(base)
        return f"Zaznamenáno: návrh k {key} je zapsaný do Jiry ({rec['written_at']}). Dashboard ukáže „Zapsáno“."

    qs_schema = {"type": "array", "minItems": 1, "maxItems": refine.MAX_Q, "items": {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string", "description": "Samotná otázka, jedna věc, srozumitelně (do 400 znaků)."},
        "why": {"type": "string", "description": "Proč se ptáte: místo v kódu nebo dopad na AC (do 300 znaků)."},
        "options": {"type": "array", "maxItems": refine.MAX_OPT, "description": "2–4 možnosti k výběru; uživatel může vždy napsat i vlastní odpověď.",
                    "items": {"type": "object", "required": ["label"], "properties": {
                        "label": {"type": "string"}, "recommended": {"type": "boolean", "description": "Doporučená volba (jen jedna)."},
                        "note": {"type": "string"}}}}}}}
    key_schema = {"type": "string", "description": "Klíč tiketu, např. APS-2618."}
    return [
        {"name": "flow_ask", "annotations": LOCAL_WRITE, "fn": flow_ask,
         "description": "Zveřejní otázky pro uživatele v dashboardu (panel Zadání u tiketu, Inbox, upozornění). Používejte při doplňování zadání "
                        "(skill ticket-refine) místo chatové otázky, když uživatel chce dialog přes dashboard. Po zavolání SKONČETE tah a požádejte "
                        "uživatele, aby odpověděl a napsal „pokračuj“." + NOTE,
         "inputSchema": {"type": "object", "required": ["key", "questions"], "properties": {"key": key_schema, "questions": qs_schema}}},
        {"name": "flow_answers", "annotations": LOCAL_WRITE, "fn": flow_answers,
         "description": "Přečte nové odpovědi uživatele na otázky (označí je jako převzaté) a stav návrhu; po schválení vrátí schválený návrh "
                        "včetně úprav AC od uživatele. Volejte, když uživatel napíše „pokračuj“." + NOTE,
         "inputSchema": {"type": "object", "required": ["key"], "properties": {"key": key_schema}}},
        {"name": "flow_draft", "annotations": LOCAL_WRITE, "fn": flow_draft,
         "description": "Publikuje návrh zadání (Problém / Kde to je / Očekávané chování, číslovaná AC, rozhodnutí, nevyřešené otázky) k "
                        "prohlédnutí a schválení v dashboardu. Nový návrh ruší dřívější schválení. Do Jiry nezapisujte před schválením." + NOTE,
         "inputSchema": {"type": "object", "required": ["key", "ac"], "properties": {
             "key": key_schema,
             "problem": {"type": "string", "description": "Sekce Problém (česky, do 4000 znaků)."},
             "where": {"type": "string", "description": "Sekce Kde to je (soubor:řádek, stránky, endpointy)."},
             "expected": {"type": "string", "description": "Sekce Očekávané chování."},
             "ac": {"type": "array", "minItems": 1, "maxItems": refine.MAX_AC, "description": "Číslovaná akceptační kritéria.",
                    "items": {"type": "object", "required": ["text"], "properties": {
                        "id": {"type": "integer", "description": "Stabilní číslo AC (výchozí pořadí)."},
                        "text": {"type": "string", "description": "Jedno ověřitelné kritérium, u čísel s hraničním případem (do 1500 znaků; delší text se odmítne, neořezává se)."},
                        "from": {"type": "string", "description": "Id otázky, ze které AC vzniklo (např. Q1)."}}}},
             "decisions": {"type": "array", "description": "Rozhodnutí z odpovědí uživatele.", "items": {"type": "object", "required": ["choice"], "properties": {
                 "q": {"type": "string"}, "text": {"type": "string", "description": "Znění otázky."}, "choice": {"type": "string"}, "note": {"type": "string"}}}},
             "unresolved": {"type": "array", "items": {"type": "string"}, "description": "Otázky, které zůstaly otevřené."}}}},
        {"name": "flow_done", "annotations": LOCAL_WRITE, "fn": flow_done,
         "description": "Potvrdí, že schválený návrh je zapsaný do Jiry. Jde jen po schválení uživatelem." + NOTE,
         "inputSchema": {"type": "object", "required": ["key"], "properties": {"key": key_schema,
                         "note": {"type": "string", "description": "Co a kam se zapsalo (krátce)."}}}},
    ]
