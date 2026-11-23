
import { t } from "./i18n.js";

const lazy = (prefix, ids) => { const o = {}; ids.forEach(id => Object.defineProperty(o, id, { get: () => t(prefix + "." + id), enumerable: true })); return o; };
const tx = (base, prefix, fields, withWho) => {
  const o = { ...base };
  fields.forEach(f => Object.defineProperty(o, f, { get: () => t(prefix + "." + base.id + "." + f), enumerable: true }));
  if (withWho) Object.defineProperty(o, "who", { get: () => (base.whoId ? t("domain.who." + base.whoId) : ""), enumerable: true });
  return o;
};

export const LABEL = lazy("state", ["waiting", "suspect", "running", "idle", "closed", "unknown"]);
export const GATE_SHORT = lazy("gate", ["approved", "draft", "changed", "none", "legacy", "unknown"]);
export const GATE_TIP = lazy("gtip", ["approved", "draft", "changed", "none", "legacy", "unknown"]);
export const WORKMODE = lazy("wm", ["AgentWorking", "WaitingForHuman", "HumanWorking", "Paused"]);

export function colOf(j) {
  const s = j.status, g = (j.ac || {}).gate;
  if (s === "TO DO" || s === "Backlog") return g === "draft" || g === "changed" ? "ac-review" : "ac-missing";
  if (s === "REFINED") return "refined";
  if (s === "In Progress" || s === "WAITING") return "progress";
  if (s === "DEVDONE") return "devdone";
  if (s === "Accepting") return "accepting";
  if (s === "ACCEPTED") return "accepted";
  if (["RELEASE-CANDIDATE", "ready-for-release", "RELEASE-BLOCKED"].includes(s)) return "release";
  if (s === "Done") return "done";
  if (s === "DECLINED") return null;
  return "other";
}

export function nextStep(j, sess) {
  const act = (sess || []).filter(x => x.state !== "closed");
  if (act.some(x => x.state === "waiting")) return { text: t("next.waiting"), hot: true };
  if (act.some(x => x.state === "suspect")) return { text: t("next.suspect"), hot: true };
  const g = (j.ac || {}).gate, s = j.status;
  if (s === "TO DO" || s === "Backlog") {
    if (g === "draft") return { text: t("next.draft") };
    if (g === "changed") return { text: t("next.changed") };
    return { text: t("next.missing") };
  }
  if (s === "REFINED") return { text: act.length ? t("next.refined_act") : t("next.refined") };
  if (s === "In Progress") return { text: act.some(x => x.state === "running") ? t("next.prog_run") : act.length ? t("next.prog_idle") : t("next.prog_none") };
  if (s === "WAITING") return { text: t("next.waiting_jira") };
  if (s === "DEVDONE") return { text: t("next.devdone") };
  if (s === "Accepting") return { text: t("next.accepting") };
  if (s === "ACCEPTED") return { text: t("next.accepted") };
  if (s === "RELEASE-CANDIDATE" || s === "ready-for-release") return { text: t("next.release") };
  if (s === "RELEASE-BLOCKED") return { text: t("next.blocked"), hot: true };
  if (s === "Done") return { text: t("next.done") };
  return { text: "" };
}

export function minutesSince(iso, now = Date.now()) {
  const t = iso ? Date.parse(iso) : NaN;
  return isNaN(t) ? null : Math.max(0, (now - t) / 60000);
}
export function ageText(min) {
  if (min == null) return "";
  if (min < 1) return t("time.now");
  if (min < 60) return t("time.min", { n: Math.round(min) });
  if (min < 1440) return t("time.h", { n: Math.round(min / 60) });
  return t("time.d", { n: Math.round(min / 1440) });
}
export const waitText = min => (min == null ? "" : t("time.waiting", { age: ageText(min) }));

export const plainSummary = s => (s || "").replace(/^\s*(?:\[[^\]]+\])+\s*/, "");
export function specLevel(sp) { return sp.block ? "error" : sp.score < sp.total ? "warning" : "success"; }

export const EFFECT = lazy("effect", ["ticket-refine", "deliver", "check", "bp-update", "ac-check"]);
export function repoOf(summary) {
  const tags = [...(summary || "").matchAll(/\[([^\]]+)\]/g)].map(m => m[1].toLowerCase());
  const fe = tags.includes("tris"), be = tags.some(x => ["aps.api", "aps", "driver.api"].includes(x));
  return fe && !be ? "tris" : be && !fe ? "aps_team_git" : "";
}
export function actionFor(key, j, sess, colId) {
  const active = (sess || []).some(s => s.state !== "closed"), where = repoOf(j.summary);
  const A = (action, w, why) => ({ action, key, cmd: "/" + action + " " + key, where: w, why, effect: EFFECT[action] });
  switch (colId) {
    case "ac-missing": return A("ticket-refine", "", t("why.ac-missing"));
    case "ac-review": return A("deliver", where, t("why.ac-review"));
    case "refined": return A("deliver", where, t("why.refined"));
    case "progress": return active ? null : A("deliver", where, t("why.progress"));
    case "devdone": return A("check", where, t("why.devdone"));
    case "accepted": return A("bp-update", "", t("why.accepted"));
    default: return null;
  }
}

export const INBOX_TYPES = [
  tx({ id: "session-waiting", color: "orange", cat: "now" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "session-suspect", color: "red", cat: "now" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "refine-questions", color: "orange", cat: "now" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "refine-draft", color: "orange", cat: "decide" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "refine-continue", color: "blue", cat: "now" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "agent-asks", color: "orange", cat: "now" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "ac-review", color: "orange", cat: "decide" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "release-blocked", color: "red", cat: "decide" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "accepted", color: "green", cat: "decide" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "refined", color: "blue", cat: "next" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "devdone", color: "green", cat: "next" }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "ac-missing", color: "blue", cat: "spec", bulk: true }, "inbox", ["title", "verb", "tip"]),
  tx({ id: "waiting-jira", color: "default", cat: "others" }, "inbox", ["title", "verb", "tip"]),
];
export const INBOX_BY_ID = Object.fromEntries(INBOX_TYPES.map(t => [t.id, t]));
export const INBOX_CATS = [
  tx({ id: "now", danger: true }, "cat", ["title", "tip"]),
  tx({ id: "decide", warn: true }, "cat", ["title", "tip"]),
  tx({ id: "next" }, "cat", ["title", "tip"]),
  tx({ id: "spec", folded: true }, "cat", ["title", "tip"]),
  tx({ id: "others" }, "cat", ["title", "tip"]),
];

export function assigneeOk(tickets, key, assignee, me) {
  if (assignee === "*") return true;
  const j = tickets[key];
  if (!j) return false;
  const a = j.assignee || null;
  if (assignee === "@none") return !a;
  if (assignee === "@me") return me ? a === me : true;
  return a === assignee;
}

export function inboxItems({ sessions, tickets, refine = {}, sprint = [], assignee = "*", me = null, useSprint = true, now = Date.now() }) {
  const items = [], bySess = {};
  sessions.forEach(s => { if (s.ticket) (bySess[s.ticket] ||= []).push(s); });
  sessions.forEach(s => {
    if (s.state !== "waiting" && s.state !== "suspect") return;
    items.push({ id: "session-" + s.state + ":" + s.session_id + ":" + (s.last_ts || ""), type: "session-" + s.state, key: s.ticket || null,
      j: s.ticket ? tickets[s.ticket] || null : null, sess: s.ticket ? bySess[s.ticket] : [s], session: s, sinceMin: s.age_min });
  });
  Object.entries(refine).forEach(([k, s]) => {
    const type = s.stage === "questions" && s.pending ? "refine-questions" : s.stage === "draft" ? "refine-draft" : s.waiting_agent ? "refine-continue" : null;
    if (type) items.push({ id: type + ":" + k + ":" + s.updated_at, type, key: k, j: tickets[k] || { status: null, summary: null, ac: null },
      sess: bySess[k] || [], sinceMin: minutesSince(s.updated_at, now) });
  });
  const keys = new Set(Object.keys(bySess));
  if (useSprint) sprint.forEach(k => keys.add(k));
  keys.forEach(k => {
    const j = tickets[k];
    if (!j || !assigneeOk(tickets, k, assignee, me)) return;
    const colId = colOf(j);
    if (!colId || colId === "done") return;
    const sess = bySess[k] || [], live = sess.filter(x => x.state !== "closed");
    const sinceMin = minutesSince((j.ac || {}).status_since || j.updated, now);
    const push = type => items.push({ id: type + ":" + k + ":" + j.status, type, key: k, j, sess, colId, sinceMin });
    const rf = refine[k];
    if ((j.labels || []).includes("agent-ceka") && !(rf && (rf.open || rf.waiting_agent))) { push("agent-asks"); return; }
    switch (colId) {
      case "ac-review": push("ac-review"); break;
      case "ac-missing": if (!live.some(x => x.state === "running")) push("ac-missing"); break;
      case "refined": if (!live.length) push("refined"); break;
      case "progress": if (j.status === "WAITING") push("waiting-jira"); break;
      case "devdone": push("devdone"); break;
      case "accepted": push("accepted"); break;
      case "release": if (j.status === "RELEASE-BLOCKED") push("release-blocked"); break;
    }
  });
  const order = t => INBOX_TYPES.findIndex(x => x.id === t);
  items.sort((a, b) => order(a.type) - order(b.type) || (b.sinceMin == null ? -1 : b.sinceMin) - (a.sinceMin == null ? -1 : a.sinceMin));
  return items;
}
export const catOf = it => INBOX_CATS.find(c => c.id === (INBOX_BY_ID[it.type] || {}).cat) || INBOX_CATS[INBOX_CATS.length - 1];

export function inboxSession(it) {
  if (it.session) return it.session;
  const linked = (it.sess || []).filter(s => s.app_link && s.app_link.startsWith("claude://claude.ai/epitaxy/")).sort((a, b) => a.age_min - b.age_min);
  return linked.find(s => s.state !== "closed") || linked[0] || null;
}
export const urgentCount = items => items.filter(i => !INBOX_BY_ID[i.type].bulk).length;

export const STATE_TIP = lazy("stip", ["waiting", "suspect", "running", "idle", "closed", "unknown"]);
export const STATE_COLOR = { waiting: "orange", suspect: "red", running: "blue", idle: "green", closed: "default", unknown: "default" };
export const STATE_ORDER = ["waiting", "suspect", "running", "idle", "closed", "unknown"];
export const NO_TICKET = "Bez tiketu";

export function listModel({ sessions, tickets, assignee = "*", me = null }) {
  const all = sessions.filter(s => assignee === "*" || (s.ticket && assigneeOk(tickets, s.ticket, assignee, me)));
  const counts = {};
  all.forEach(s => { counts[s.state] = (counts[s.state] || 0) + 1; });
  const group = list => {
    const by = {};
    list.forEach(s => (by[s.ticket || NO_TICKET] ||= []).push(s));
    return Object.keys(by).sort((a, b) => a === NO_TICKET ? 1 : b === NO_TICKET ? -1 : a.localeCompare(b))
      .map(name => ({ name, ticket: tickets[name] || null, sessions: by[name] }));
  };
  return {
    attn: all.filter(s => s.state === "waiting" || s.state === "suspect"),
    active: group(all.filter(s => s.state === "running" || s.state === "idle")),
    closed: group(all.filter(s => s.state === "closed")),
    counts,
  };
}
export const sessionTitle = s => s.title || (s.cwd || "").split("/").pop() || t("domain.untitled");
export const hasAppLink = s => !!(s.app_link && s.app_link.startsWith("claude://claude.ai/epitaxy/"));

export const COLS = [
  tx({ id: "ac-missing", whoId: "agent" }, "col", ["title", "tip"], true),
  tx({ id: "ac-review", whoId: "human" }, "col", ["title", "tip"], true),
  tx({ id: "refined", whoId: "agent" }, "col", ["title", "tip"], true),
  tx({ id: "progress", whoId: "agent" }, "col", ["title", "tip"], true),
  tx({ id: "devdone", whoId: "human" }, "col", ["title", "tip"], true),
  tx({ id: "accepting", whoId: "tester" }, "col", ["title", "tip"], true),
  tx({ id: "accepted", whoId: "human" }, "col", ["title", "tip"], true),
  tx({ id: "release", whoId: "human" }, "col", ["title", "tip"], true),
  tx({ id: "done", whoId: "" }, "col", ["title", "tip"], true),
];
export const OTHER_COL = tx({ id: "other", whoId: "" }, "col", ["title", "tip"], true);

export const BALL = lazy("ball", ["you", "agent", "other", "done"]);
export const BALL_TIP = lazy("btip", ["you", "agent", "other", "done"]);
export function ballOf(sess, colId) {
  const act = (sess || []).filter(x => x.state !== "closed");
  if (act.some(x => x.state === "waiting" || x.state === "suspect")) return "you";
  if (act.some(x => x.state === "running")) return "agent";
  if (colId === "done") return "done";
  const who = (COLS.find(c => c.id === colId) || {}).whoId;
  return who === "human" ? "you" : who === "agent" ? "agent" : "other";
}
export const COL_SKILL = { "ac-missing": "ticket-refine", "ac-review": "deliver", refined: "deliver", progress: "deliver", devdone: "check", accepted: "bp-update" };
export const SPEC_COLS = ["ac-missing", "ac-review", "refined"];
export const tagsOf = summary => {
  const m = (summary || "").match(/^\s*((?:\[[^\]]+\])+)/);
  return m ? [...m[1].matchAll(/\[([^\]]+)\]/g)].map(x => x[1]) : [];
};

export function boardMatch(k, j, sess, f) {
  if (!f) return true;
  const q = (f.q || "").trim().toLowerCase();
  if (q) {
    const hay = [k, j.summary, j.assignee, (j.labels || []).join(" "), j.parent && j.parent.key, j.parent && j.parent.summary, ...(sess || []).map(sessionTitle)].join(" ").toLowerCase();
    if (!q.split(/\s+/).every(w => hay.includes(w))) return false;
  }
  if (f.types && f.types.length && !f.types.includes(j.type)) return false;
  if (f.epics && f.epics.length && !f.epics.includes(j.parent ? j.parent.key : "-")) return false;
  if (f.labels && f.labels.length && !(j.labels || []).some(l => f.labels.includes(l))) return false;
  return true;
}
export function boardModel({ sessions, tickets, sprint = [], assignee = "*", me = null, useSprint = true, filters = null }) {
  const bySess = {};
  sessions.forEach(s => { if (s.ticket) (bySess[s.ticket] ||= []).push(s); });
  const cols = {};
  COLS.concat([OTHER_COL]).forEach(c => { cols[c.id] = []; });
  let declined = 0;
  const keys = new Set([...Object.keys(bySess), ...(useSprint ? sprint : [])]);
  keys.forEach(k => {
    if (!assigneeOk(tickets, k, assignee, me)) return;
    const j = tickets[k], sess = bySess[k] || [];
    if (!j) { if (!filters || boardMatch(k, { summary: "" }, sess, { q: filters.q })) cols.other.push({ k, j: { status: null }, sess }); return; }
    if (!boardMatch(k, j, sess, filters)) return;
    const id = colOf(j);
    if (!id) { declined++; return; }
    cols[id].push({ k, j, sess });
  });
  const rank = t => t.sess.some(x => x.state === "waiting" || x.state === "suspect") ? 0 : t.sess.some(x => x.state !== "closed") ? 1 : 2;
  Object.values(cols).forEach(list => list.sort((a, b) => rank(a) - rank(b) || String(b.j.updated || "").localeCompare(String(a.j.updated || ""))));
  const free = sessions.filter(s => !s.ticket);
  const freeAct = free.filter(s => s.state !== "closed").sort((a, b) => a.age_min - b.age_min);
  const nTickets = Object.values(cols).reduce((a, l) => a + l.length, 0);
  return { cols, free, freeAct, declined, nTickets, withSessions: Object.keys(bySess).length };
}
export const boardCols = model => COLS.concat(model.cols.other.length ? [OTHER_COL] : []);

const PRE = ["ac-missing", "ac-review", "refined"], DEV = ["progress", "devdone", "accepting"];
export function laneModel(model) {
  const defs = boardCols(model), lanes = new Map();
  defs.forEach(col => model.cols[col.id].forEach(t => {
    const p = t.j.parent, pk = p ? p.key : "";
    if (!lanes.has(pk)) lanes.set(pk, { key: pk, parent: p || null, byCol: {} });
    (lanes.get(pk).byCol[col.id] ||= []).push(t);
  }));
  return [...lanes.keys()].sort((a, b) => a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)).map(pk => {
    const L = lanes.get(pk), n = id => (L.byCol[id] || []).length;
    const total = defs.reduce((a, c) => a + n(c.id), 0), pre = PRE.reduce((a, id) => a + n(id), 0), dev = DEV.reduce((a, id) => a + n(id), 0);
    return { ...L, total, pre, dev, after: total - pre - dev };
  });
}
export const ticketWord = n => t("domain.ticket_word", { n });
