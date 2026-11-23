#!/usr/bin/env python3
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def para(t):
    return {"type": "paragraph", "content": [{"type": "text", "text": t}]}


def head(t):
    return {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": t}]}


def ac_list(items):
    return {"type": "bulletList", "content": [{"type": "listItem", "content": [para(f"AC-{i + 1}: {t}")]} for i, t in enumerate(items)]}


def desc(problem, where, expected, ac=(), questions=()):
    c = [head("Problém"), para(problem), head("Kde to je"), para(where), head("Očekávané chování"), para(expected)]
    if ac:
        c.append(ac_list(ac))
    if questions:
        c += [head("Otevřené otázky")] + [para(q) for q in questions]
    return {"type": "doc", "version": 1, "content": c}


NOW = "2026-11-22T09:00:00.000+0100"
T = {
    "APS-9001": ("[TRIS] Zobrazit poznámku svazu v rekapitulaci", "TO DO", "Story", "Demo Uživatel", [],
                 desc("Poznámka svozu se v rekapitulaci nezobrazuje.", "src/pages/CollectionRecap.vue:120", "Poznámka je vidět pod adresou."), "sprint"),
    "APS-9002": ("[TRIS] Limit řidiče podle objemu", "TO DO", "Story", "Demo Uživatel", ["agent-ceka"],
                 desc("Limit řidiče se vyhodnocuje jinak než v Dispečeru a řidič vidí jiné číslo.", "src/pages/DriverPage.vue:42 počítá limit z objemu.",
                      "Limit se počítá jako v Dispečeru.",
                      ["Když je objem 8 000 a limit 10 000, pak se zobrazí ok; při 12 000 se zobrazí upozornění.",
                       "Pokud řidič nemá oprávnění, nezobrazí se tlačítko Uložit."]), "sprint"),
    "APS-9003": ("[APS.API] Export svozů do CSV", "TO DO", "Story", "Demo Uživatel", [],
                 desc("Export svozů nejde stáhnout.", "Controllers/ExportController.cs:88", "Export vrací CSV s hlavičkou.",
                      ["Když je v exportu 100 svozů, pak CSV obsahuje 101 řádků včetně hlavičky."],
                      ["Má export respektovat filtr podle regionu?"]), "sprint"),
    "APS-9004": ("[TRIS] Filtr svozů podle trasy", "REFINED", "Story", "Demo Uživatel", [],
                 desc("Filtr podle trasy chybí.", "src/pages/CollectionList.vue:55", "Filtr je v hlavičce seznamu.",
                      ["Když vyberu trasu T1, pak seznam obsahuje jen svozy trasy T1."]), "sprint"),
    "APS-9005": ("[APS.API] Oprava stránkování u zákazníků", "In Progress", "Bug", "Demo Uživatel", [],
                 desc("Druhá stránka vrací stejné záznamy.", "Services/CustomerService.cs:140", "Stránky na sebe navazují.",
                      ["Když skip = 20 a top = 20, pak se vrátí záznamy 21 až 40."]), "sprint"),
    "APS-9006": ("[TRIS] Tmavý režim", "TO DO", "Story", None, [], desc("Aplikace nemá tmavý režim.", "src/theme", "Uživatel si může zvolit tmavý režim."), "backlog"),
    "APS-9007": ("[TRIS] Hromadná změna trasy", "TO DO", "Story", None, [], desc("Trasu jde měnit jen po jednom svozu.", "src/pages/CollectionList.vue:300", "Jde změnit trasu u více svozů najednou.",
                 ["Když vyberu 3 svozy a změním trasu, pak mají všechny 3 novou trasu."]), "backlog"),
}

if os.environ.get("DEMO_LANG") == "en":
    ME = "Demo User"
    T = {
        "APS-9001": ("[TRIS] Show the collection note in the recap", "TO DO", "Story", ME, [],
                     desc("The collection note is not shown in the recap.", "src/pages/CollectionRecap.vue:120", "The note is visible under the address."), "sprint"),
        "APS-9002": ("[TRIS] Driver limit by volume", "TO DO", "Story", ME, ["agent-ceka"],
                     desc("The driver limit is evaluated differently than in Dispatch and the driver sees another number.", "src/pages/DriverPage.vue:42 computes the limit from the volume.",
                          "The limit is computed as in Dispatch.",
                          ["When the volume is 8,000 and the limit 10,000, then ok is shown; at 12,000 a warning is shown.",
                           "If the driver has no permission, the Save button is not shown."]), "sprint"),
        "APS-9003": ("[APS.API] Export collections to CSV", "TO DO", "Story", ME, [],
                     desc("The collections export cannot be downloaded.", "Controllers/ExportController.cs:88", "The export returns a CSV with a header.",
                          ["When the export has 100 collections, then the CSV has 101 rows including the header."],
                          ["Should the export respect the region filter?"]), "sprint"),
        "APS-9004": ("[TRIS] Filter collections by route", "REFINED", "Story", ME, [],
                     desc("The route filter is missing.", "src/pages/CollectionList.vue:55", "The filter is in the list header.",
                          ["When I select route T1, then the list contains only collections of route T1."]), "sprint"),
        "APS-9005": ("[APS.API] Fix paging of customers", "In Progress", "Bug", ME, [],
                     desc("The second page returns the same records.", "Services/CustomerService.cs:140", "Pages follow each other.",
                          ["When skip = 20 and top = 20, then records 21 to 40 are returned."]), "sprint"),
        "APS-9006": ("[TRIS] Dark mode", "TO DO", "Story", None, [], desc("The app has no dark mode.", "src/theme", "The user can choose dark mode."), "backlog"),
        "APS-9007": ("[TRIS] Bulk route change", "TO DO", "Story", None, [], desc("The route can only be changed one collection at a time.", "src/pages/CollectionList.vue:300", "The route of several collections can be changed at once.",
                     ["When I select 3 collections and change the route, then all 3 have the new route."]), "backlog"),
    }
if os.environ.get("DEMO_LANG") == "en":
    T.update({
        "APS-9008": ("[APS.API] Add a region filter to the CSV export", "DEVDONE", "Story", ME, [],
                     desc("The CSV export ignores the region filter.", "Controllers/ExportController.cs:95", "The export contains only collections of the selected region.",
                          ["When region North is selected, then the CSV contains only North collections."]), "sprint"),
        "APS-9009": ("[TRIS] Offline mode of the driver app", "Accepting", "Story", ME, [],
                     desc("Drivers lose entered data without a connection.", "src/pages/DriverPage.vue:210", "Entered data is kept and sent when the connection returns.",
                          ["When the connection drops while saving, then the form data is kept and sent after reconnect."]), "sprint"),
        "APS-9010": ("[TRIS] Fix the date format in the recap", "ACCEPTED", "Bug", ME, [],
                     desc("Dates in the recap show the US format.", "src/utils/format.ts:18", "Dates use the day.month.year format.",
                          ["When the date is 3 March 2026, then the recap shows 3. 3. 2026."]), "sprint"),
        "APS-9011": ("[APS.API] Round invoice totals correctly", "RELEASE-CANDIDATE", "Bug", ME, [],
                     desc("Invoice totals differ by one cent from the ledger.", "Services/InvoiceService.cs:77", "Totals are rounded half up per line.",
                          ["When a line costs 10.005, then it is rounded to 10.01."]), "sprint"),
        "APS-9012": ("[TRIS] Cluster markers on the route map", "In Progress", "Story", ME, [],
                     desc("The map is unreadable with many stops.", "src/components/RouteMap.vue:64", "Close markers are clustered.",
                          ["When more than 50 markers are in view, then they are shown as clusters."]), "sprint"),
    })

STATE = {k: {"status": v[1], "updated": NOW, "labels": list(v[4])} for k, v in T.items()}
CAT = {"TO DO": "new", "REFINED": "new", "Done": "done"}
WRITES = []


def fields(k):
    s, st = T[k], STATE[k]
    return {"summary": s[0], "status": {"name": st["status"], "statusCategory": {"key": CAT.get(st["status"], "indeterminate")}},
            "issuetype": {"name": s[2]}, "assignee": {"displayName": s[3]} if s[3] else None, "updated": st["updated"], "parent": None, "labels": st["labels"]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, _, qs = self.path.partition("?")
        from urllib.parse import parse_qs
        q = parse_qs(qs)
        if path.endswith("/search/jql"):
            jql = (q.get("jql") or [""])[0]
            m = re.search(r"key in \(([^)]*)\)", jql)
            if m:
                keys = [k.strip() for k in m.group(1).split(",") if k.strip() in T]
            elif "sprint is EMPTY" in jql or "futureSprints" in jql:
                keys = [k for k, v in T.items() if v[6] == "backlog"]
            else:
                keys = [k for k, v in T.items() if v[6] == "sprint"]
            return self._send({"issues": [{"key": k, "fields": fields(k)} for k in keys], "isLast": True})
        m = re.match(r"/rest/api/3/issue/(APS-\d+)$", path)
        if m and m.group(1) in T:
            return self._send({"fields": {"description": T[m.group(1)][5], "customfield_10606": None}, "changelog": {"histories": [], "total": 0}})
        if path.endswith("/transitions"):
            return self._send({"transitions": [{"id": "11", "name": "To Do", "to": {"name": "TO DO"}}, {"id": "81", "name": "REFINED", "to": {"name": "REFINED"}},
                                               {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}}]})
        if path.endswith("/statuses"):
            return self._send([{"statuses": [{"name": "TO DO"}, {"name": "REFINED"}, {"name": "In Progress"}, {"name": "DEVDONE"}]}])
        if path.endswith("/myself"):
            return self._send({"displayName": "Demo User" if os.environ.get("DEMO_LANG") == "en" else "Demo Uživatel"})
        if path.endswith("/rest/agile/1.0/board"):
            return self._send({"values": [{"id": 1, "type": "simple", "location": {"projectKey": "APS"}}]})
        if path.endswith("/sprint"):
            return self._send({"values": [{"id": 1, "name": "Sprint 1", "state": "active"}, {"id": 2, "name": "Refinement", "state": "future"}]})
        if path.endswith("/field"):
            return self._send([])
        self._send({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        path = self.path.split("?")[0]
        WRITES.append((path, body))
        m = re.match(r"/rest/api/3/issue/(APS-\d+)/transitions", path)
        if m and m.group(1) in T:
            STATE[m.group(1)]["status"] = "REFINED"
            STATE[m.group(1)]["updated"] = "2026-11-22T09:30:00.000+0100"
            return self._send({}, 204)
        if path.endswith("/comment"):
            return self._send({"id": "1"}, 201)
        self._send({}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
