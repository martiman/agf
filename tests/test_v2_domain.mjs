import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

globalThis.Vue = { reactive: o => o };
globalThis.localStorage = { getItem: () => "cs", setItem() {} };
const here = path.dirname(fileURLToPath(import.meta.url));
const D = await import(pathToFileURL(path.join(here, "..", "web", "v2", "app", "domain.js")).href);
let fails = 0;
const check = (name, fn) => { try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "  " + e.message.split("\n")[0]); } };

const NOW = Date.parse("2026-11-19T12:00:00+01:00");
const t = (over = {}) => ({ status: "TO DO", summary: "[TRIS] x", assignee: "Já", labels: [], updated: "2026-11-19T10:00:00+01:00", ac: { gate: "draft", total: 2, ticked: 0 }, ...over });

check("colOf: TO DO + draft AC -> ac-review, without AC -> ac-missing", () => {
  assert.equal(D.colOf(t()), "ac-review"); assert.equal(D.colOf(t({ ac: { gate: "none" } })), "ac-missing");
});
check("colOf: statuses map to the board columns, DECLINED is hidden", () => {
  assert.equal(D.colOf({ status: "REFINED" }), "refined"); assert.equal(D.colOf({ status: "DEVDONE" }), "devdone");
  assert.equal(D.colOf({ status: "DECLINED" }), null); assert.equal(D.colOf({ status: "Weird" }), "other");
});
check("the AC of a ticket in TO DO go to the 'decide' category and count as urgent", () => {
  const items = D.inboxItems({ sessions: [], tickets: { "APS-1": t() }, sprint: ["APS-1"], now: NOW });
  assert.deepEqual(items.map(i => i.type), ["ac-review"]); assert.equal(D.catOf(items[0]).id, "decide"); assert.equal(D.urgentCount(items), 1);
});
check("tickets without AC are in the bulk category 'spec' and are not urgent", () => {
  const items = D.inboxItems({ sessions: [], tickets: { "APS-1": t({ ac: { gate: "none" } }) }, sprint: ["APS-1"], now: NOW });
  assert.equal(D.catOf(items[0]).id, "spec"); assert.equal(D.urgentCount(items), 0);
});
check("a waiting session is an item of its own and comes first", () => {
  const s = { session_id: "abc", state: "waiting", ticket: "APS-1", last_ts: "2026-11-19T11:00:00+01:00", age_min: 60 };
  const items = D.inboxItems({ sessions: [s], tickets: { "APS-1": t() }, sprint: ["APS-1"], now: NOW });
  assert.deepEqual(items.map(i => i.type), ["session-waiting", "ac-review"]); assert.equal(D.catOf(items[0]).id, "now");
});
check("a session working on a ticket without AC hides the 'spec missing' item", () => {
  const s = { session_id: "abc", state: "running", ticket: "APS-1", last_ts: "x", age_min: 1 };
  assert.deepEqual(D.inboxItems({ sessions: [s], tickets: { "APS-1": t({ ac: { gate: "none" } }) }, now: NOW }), []);
});
check("the assignee filter: mine, nobody's, everybody's; without a known 'me' nothing is hidden", () => {
  const tk = { "APS-1": t(), "APS-2": t({ assignee: null }), "APS-3": t({ assignee: "Jiný" }) }, sp = ["APS-1", "APS-2", "APS-3"];
  const keys = a => D.inboxItems({ sessions: [], tickets: tk, sprint: sp, assignee: a, me: "Já", now: NOW }).map(i => i.key).sort();
  assert.deepEqual(keys("@me"), ["APS-1"]); assert.deepEqual(keys("@none"), ["APS-2"]); assert.deepEqual(keys("*"), ["APS-1", "APS-2", "APS-3"]);
  assert.equal(D.inboxItems({ sessions: [], tickets: tk, sprint: sp, assignee: "@me", me: null, now: NOW }).length, 3);
});
check("questions of the agent wait for the human whoever owns the ticket", () => {
  const items = D.inboxItems({ sessions: [], tickets: { "APS-3": t({ assignee: "Jiný" }) }, assignee: "@me", me: "Já",
    refine: { "APS-3": { stage: "questions", pending: 1, updated_at: "2026-11-19T11:00:00+01:00" } }, now: NOW });
  assert.deepEqual(items.map(i => i.type), ["refine-questions"]);
});
check("the label agent-ceka gives an item unless a dialog in the dashboard replaces it", () => {
  const tk = { "APS-1": t({ labels: ["agent-ceka"] }) };
  assert.deepEqual(D.inboxItems({ sessions: [], tickets: tk, sprint: ["APS-1"], now: NOW }).map(i => i.type), ["agent-asks"]);
  assert.deepEqual(D.inboxItems({ sessions: [], tickets: tk, sprint: ["APS-1"], refine: { "APS-1": { open: true, stage: "questions", pending: 1, updated_at: "x" } }, now: NOW }).map(i => i.type), ["refine-questions", "ac-review"]);
});
check("Done tickets and DECLINED tickets are not items", () => {
  assert.deepEqual(D.inboxItems({ sessions: [], tickets: { "A-1": t({ status: "Done" }), "A-2": t({ status: "DECLINED" }) }, sprint: ["A-1", "A-2"], now: NOW }), []);
});
check("every inbox type belongs to a known category", () => {
  D.INBOX_TYPES.forEach(x => assert.ok(D.INBOX_CATS.some(c => c.id === x.cat), x.id));
});
check("repoOf finds the repository from the tags in the title", () => {
  assert.equal(D.repoOf("[TRIS] a"), "tris"); assert.equal(D.repoOf("[APS.API] a"), "aps_team_git"); assert.equal(D.repoOf("[TRIS][APS.API] a"), ""); assert.equal(D.repoOf("a"), "");
});
check("actionFor: ac-review -> deliver in the right repo; progress with a live session -> nothing", () => {
  assert.equal(D.actionFor("APS-1", t(), [], "ac-review").cmd, "/deliver APS-1"); assert.equal(D.actionFor("APS-1", t(), [], "ac-review").where, "tris");
  assert.equal(D.actionFor("APS-1", t(), [{ state: "running" }], "progress"), null);
});
check("time text", () => {
  assert.equal(D.ageText(0.2), "právě teď"); assert.equal(D.ageText(30), "30 min"); assert.equal(D.ageText(180), "3 h"); assert.equal(D.ageText(2880), "2 d");
  assert.equal(D.waitText(null), ""); assert.equal(D.minutesSince("2026-11-19T11:00:00+01:00", NOW), 60);
});
check("plainSummary drops the leading tags", () => assert.equal(D.plainSummary("[TRIS][APS.API] Něco"), "Něco"));

const S = (id, state, ticket, over = {}) => ({ session_id: id, state, ticket, age_min: 5, last_ts: "2026-11-19T11:55:00+01:00", ...over });
check("listModel: attention = waiting + suspect, active = running + idle, closed apart; counts per state", () => {
  const m = D.listModel({ sessions: [S("a", "waiting", "APS-1"), S("b", "suspect", null), S("c", "running", "APS-1"), S("d", "idle", "APS-2"), S("e", "closed", "APS-2")], tickets: {} });
  assert.deepEqual(m.attn.map(s => s.session_id), ["a", "b"]); assert.deepEqual(m.active.flatMap(g => g.sessions.map(s => s.session_id)), ["c", "d"]);
  assert.deepEqual(m.closed.flatMap(g => g.sessions.map(s => s.session_id)), ["e"]); assert.deepEqual(m.counts, { waiting: 1, suspect: 1, running: 1, idle: 1, closed: 1 });
});
check("listModel: groups are sorted by key and 'Bez tiketu' comes last, the ticket data is attached", () => {
  const m = D.listModel({ sessions: [S("a", "idle", null), S("b", "idle", "APS-9"), S("c", "idle", "APS-10")], tickets: { "APS-9": { status: "TO DO" } } });
  assert.deepEqual(m.active.map(g => g.name), ["APS-10", "APS-9", D.NO_TICKET]); assert.equal(m.active[1].ticket.status, "TO DO"); assert.equal(m.active[2].ticket, null);
});
check("listModel: the assignee filter hides sessions without a ticket (as the first page does)", () => {
  const tk = { "APS-1": { assignee: "Já" }, "APS-2": { assignee: "Jiný" } };
  const m = D.listModel({ sessions: [S("a", "idle", "APS-1"), S("b", "idle", "APS-2"), S("c", "idle", null)], tickets: tk, assignee: "@me", me: "Já" });
  assert.deepEqual(m.active.flatMap(g => g.sessions.map(s => s.session_id)), ["a"]);
});
check("sessionTitle falls back to the folder name; app links are recognised", () => {
  assert.equal(D.sessionTitle({ title: "T" }), "T"); assert.equal(D.sessionTitle({ cwd: "/a/b/tris" }), "tris"); assert.equal(D.sessionTitle({}), "(bez názvu)");
  assert.equal(D.hasAppLink({ app_link: "claude://claude.ai/epitaxy/local_1" }), true); assert.equal(D.hasAppLink({ app_link: "https://x" }), false);
});

const TK = (status, over = {}) => ({ status, summary: "[TRIS] x", assignee: "Já", updated: "2026-11-19T10:00:00+01:00", ac: { gate: "none" }, parent: null, ...over });
check("boardModel: tickets land in the column of their step, DECLINED is counted and hidden, unknown data goes to 'other'", () => {
  const m = D.boardModel({ sessions: [S("a", "running", "APS-9")], tickets: { "APS-1": TK("REFINED"), "APS-2": TK("DECLINED"), "APS-3": TK("Done"), "APS-4": TK("In Progress") }, sprint: ["APS-1", "APS-2", "APS-3", "APS-4"] });
  assert.deepEqual(m.cols.refined.map(t => t.k), ["APS-1"]); assert.deepEqual(m.cols.done.map(t => t.k), ["APS-3"]); assert.deepEqual(m.cols.progress.map(t => t.k), ["APS-4"]);
  assert.equal(m.declined, 1); assert.deepEqual(m.cols.other.map(t => t.k), ["APS-9"]); assert.equal(m.nTickets, 4);
});
check("boardModel: a ticket with a waiting session comes first, then a live one, then the newest", () => {
  const tk = { "APS-1": TK("In Progress", { updated: "2026-11-19T09:00:00+01:00" }), "APS-2": TK("In Progress", { updated: "2026-11-19T11:00:00+01:00" }), "APS-3": TK("In Progress") };
  const m = D.boardModel({ sessions: [S("a", "waiting", "APS-1"), S("b", "running", "APS-3")], tickets: tk, sprint: ["APS-2"] });
  assert.deepEqual(m.cols.progress.map(t => t.k), ["APS-1", "APS-3", "APS-2"]);
});
check("boardModel: sessions without a ticket are listed apart, closed ones are only counted", () => {
  const m = D.boardModel({ sessions: [S("a", "idle", null), S("b", "closed", null)], tickets: {} });
  assert.deepEqual(m.freeAct.map(s => s.session_id), ["a"]); assert.equal(m.free.length, 2);
});
check("boardModel: without the sprint only tickets with your sessions are shown", () => {
  const m = D.boardModel({ sessions: [], tickets: { "APS-1": TK("REFINED") }, sprint: ["APS-1"], useSprint: false });
  assert.equal(m.nTickets, 0);
});
check("laneModel: one lane per parent, 'Bez epiku' last, counts before/in/after development", () => {
  const ep = { key: "APS-100", summary: "Epic", status: "In Progress" };
  const tk = { "APS-1": TK("TO DO", { parent: ep }), "APS-2": TK("In Progress", { parent: ep }), "APS-3": TK("ACCEPTED", { parent: ep }), "APS-4": TK("REFINED") };
  const L = D.laneModel(D.boardModel({ sessions: [], tickets: tk, sprint: Object.keys(tk) }));
  assert.deepEqual(L.map(l => l.key), ["APS-100", ""]);
  assert.deepEqual([L[0].total, L[0].pre, L[0].dev, L[0].after], [3, 1, 1, 1]); assert.equal(L[1].parent, null);
});
check("tagsOf and the czech plural of tickets", () => {
  assert.deepEqual(D.tagsOf("[TRIS][UX] a"), ["TRIS", "UX"]); assert.deepEqual(D.tagsOf("a [x]"), []);
  assert.deepEqual([1, 3, 7].map(D.ticketWord), ["tiket", "tikety", "tiketů"]);
});
check("board search and Jira-like filters (type, epic, label) narrow the tickets", () => {
  const ep = { key: "APS-100", summary: "Rekapitulace", status: "In Progress" };
  const tk = { "APS-1": TK("TO DO", { summary: "Poznámka svozu", type: "Story", parent: ep, labels: ["tris"] }),
               "APS-2": TK("TO DO", { summary: "Chyba exportu", type: "Bug", labels: ["api"] }) };
  const n = f => D.boardModel({ sessions: [], tickets: tk, sprint: Object.keys(tk), filters: f }).nTickets;
  assert.equal(n(null), 2); assert.equal(n({ q: "poznámka" }), 1); assert.equal(n({ q: "aps-2" }), 1); assert.equal(n({ q: "rekapitulace tris" }), 1);
  assert.equal(n({ types: ["Bug"] }), 1); assert.equal(n({ epics: ["APS-100"] }), 1); assert.equal(n({ epics: ["-"] }), 1);
  assert.equal(n({ labels: ["api", "tris"] }), 2); assert.equal(n({ q: "poznámka", types: ["Bug"] }), 0);
});

console.log("\n" + (fails ? fails + " FAILED" : "ALL PASSED"));
process.exit(fails ? 1 : 0);
