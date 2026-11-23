# agenticflow

Lokální přehled sessions Claude Code a stavu tiketů APS: dashboard (Seznam / Board / Inbox), brána AC se stavem REFINED, kontrola zadání, schvalování AC, dialog s agentem a čtecí MCP server. Jen standardní knihovna Pythonu 3.

## Struktura

```
agenticflow/
  bin/flow            příkaz flow (start, stop, restart, status, open, logs, notify, launch, approve)
  src/                kód (Python, bez závislostí)
    hook.py             hook Claude Code → events.jsonl + ping na dashboard
    status.py           stavy sessions z událostí (running / waiting / idle / closed / suspect)
    jira.py             čtení a zápis do Jiry (REST), cache
    ac.py               brána AC (none / draft / approved / changed / legacy / closed)
    spec.py             kontrola připravenosti zadání (8 kontrol)
    approve.py          schválení AC = přechod do REFINED (plán, otisk, audit)
    workmode.py         pole WorkMode / NextAction v Jiře podle stavu sessions (vypnuto; flow workmode on)
    refine.py           schránka dialogu agent ↔ člověk (soubory v ~/.flow/refine)
    dashboard.py        HTTP server 127.0.0.1:8765 (stránka, API, SSE)
    mcp_server.py       MCP server pro čtení stavu (+ mcp_refine.py: nástroje dialogu)
  web/                statické soubory stránky
    v2/                 stránka (/ přesměruje na /v2/), bez buildu: Vue 3 + Ant Design Vue jako globální knihovny, vlastní kód jako ES moduly
      app/domain.js       čistá logika (Inbox, kategorie, pravidla), testovaná v Node
      app/store.js, api.js  stav a komunikace se serverem (stejné API jako první stránka)
      app/components/     App, MasterList, ListView, BoardView, TicketDetail, ApproveModal, LaunchModal, RefinePanel (dialog, návrh, AC), SpecChecks, Legend, Tips
      assets/branding/    finální logo AGF v barvách Trafinoil: SVG, průhledné PNG, JPG, ikona a favicon
    vendor/             Vue, Ant Design Vue a dayjs zkopírované z tris/node_modules (nic se nenačítá z internetu)
  tests/              test_*.py a run_all.sh (bez sítě; e2e používá mock Jiry)
  prototype/          HTML prototyp UI z videa agentury (index.html, screenshots/), reference UX
  docs/               návrhy (navrh-*.md), předání sessions (handoff-*.md), docs/pr/ popisy PR ke skills
```

## Kód × data

Kód je v tomto adresáři. Běhová data a tajemství jsou **mimo repo** v `~/.flow/` (přepíše `FLOW_HOME`):
`events.jsonl`, `titles.json`, `config.json`, `secret`, `page.token`, `jira.env`, `refine/`, `approve.log`, `launch.log`, `dashboard.log`.

## Napojení

| Co | Kam ukazuje |
|---|---|
| příkaz `flow` | symlink `~/.local/bin/flow` → `agenticflow/bin/flow` |
| hooks | `~/.claude/settings.json` → `agenticflow/src/hook.py` |
| MCP `flow` | `~/.claude.json` (user scope) → `agenticflow/src/mcp_server.py` |

## Testy

```bash
agenticflow/tests/run_all.sh
```

`test_mcp.py` potřebuje běžící dashboard (`flow start`).
