import { getState, subscribe } from "./api.js";
import { inboxItems, catOf, INBOX_BY_ID } from "./domain.js";

const { reactive, computed } = Vue;
const ls = {
  get: (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} },
};
let snooze = {};
try { snooze = JSON.parse(ls.get("flow.snooze", "{}")) || {}; } catch (e) { snooze = {}; }

export const store = reactive({
  data: null, error: null, loading: false, live: false, updated: null,
  ideas: [],
  collapsed: ls.get("flow.collapsed", "0") === "1",
  hours: Number(ls.get("flow.hours", "48")) || 48,
  sprint: ls.get("flow.sprint", "1") !== "0",
  assignee: ls.get("flow.assignee", "@me"),
  scope: ls.get("flow.scope", "open"),
  bq: "", ftypes: [], fepics: [], flabels: [],
  q: "", selId: null, showSnoozed: false, snooze,
  foldedCats: { spec: true },
  lanes: ls.get("flow.lanes", "0") === "1", foldedLanes: {},
  view: ["list", "board", "cleanup", "ideas"].includes(ls.get("flow.view", "inbox")) ? ls.get("flow.view", "inbox") : "inbox",
  legend: false, tips: false, narrow: false, detailOpen: false,
});

export const tickets = computed(() => (store.data && store.data.jira && store.data.jira.tickets) || {});
export const me = computed(() => (store.data && store.data.me) || null);
export const allItems = computed(() => !store.data ? [] : inboxItems({
  sessions: store.data.sessions, tickets: tickets.value, refine: store.data.refine || {}, sprint: store.data.sprint || [],
  assignee: store.assignee, me: me.value, useSprint: store.sprint }));
const isSnoozed = id => (store.snooze[id] || 0) > Date.now();
export const openItems = computed(() => allItems.value.filter(i => !isSnoozed(i.id)));
export const snoozedItems = computed(() => allItems.value.filter(i => isSnoozed(i.id)));
export const shownItems = computed(() => {
  const q = store.q.trim().toLowerCase();
  if (!q) return openItems.value;
  return openItems.value.filter(i => ((i.key || "") + " " + ((i.j && i.j.summary) || "") + " " + ((i.session && i.session.title) || "")).toLowerCase().includes(q));
});
export const selected = computed(() => {
  const list = shownItems.value, s = store.selId;
  return list.find(i => i.id === s) || (s && list.find(i => i.key && s.split(":")[1] === i.key)) || list[0] || null;
});
export const urgent = computed(() => openItems.value.filter(i => !INBOX_BY_ID[i.type].bulk).length);
export const assignees = computed(() => [...new Set(Object.values(tickets.value).map(t => t.assignee).filter(Boolean))].sort());

export function select(it) { store.selId = it.id; store.detailOpen = true; }
export async function loadIdeas() { try { const r = await fetch("/api/ideas", { cache: "no-store" }); if (r.ok) store.ideas = (await r.json()).ideas || []; } catch (e) {  } }
export function toggleSide() { store.collapsed = !store.collapsed; ls.set("flow.collapsed", store.collapsed ? "1" : "0"); }
export function setView(v) { const was = store.view; store.view = v; ls.set("flow.view", v); if (store.scope !== "open" && (v === "board") !== (was === "board")) refresh(true); }
export function setScope(v) { store.scope = v; ls.set("flow.scope", v); refresh(true); }
export function clearBoardFilters() { store.bq = ""; store.ftypes = []; store.fepics = []; store.flabels = []; }
export function setSnooze(id, until) { store.snooze[id] = until; ls.set("flow.snooze", JSON.stringify(store.snooze)); }
export function clearSnooze(id) { delete store.snooze[id]; ls.set("flow.snooze", JSON.stringify(store.snooze)); }
export function setAssignee(v) { store.assignee = v; ls.set("flow.assignee", v); }
export function setSprint(v) { store.sprint = v; ls.set("flow.sprint", v ? "1" : "0"); refresh(true); }
export function setLanes(v) { store.lanes = v; ls.set("flow.lanes", v ? "1" : "0"); }
export function setHours(v) { store.hours = v; ls.set("flow.hours", String(v)); refresh(true); }

let busy = false, again = false;
export async function refresh(force = false) {
  if (busy) { again = true; return; }
  busy = true; store.loading = true;
  try {
    store.data = await getState({ hours: store.hours, sprint: store.sprint, scope: store.view === "board" ? store.scope : "open", refresh: force === true });
    store.error = null; store.updated = new Date();
  } catch (e) { store.error = String(e.message || e); }
  store.loading = false; busy = false;
  if (again) { again = false; refresh(); }
}
const mq = window.matchMedia("(max-width: 959px)");
store.narrow = mq.matches; mq.addEventListener("change", e => { store.narrow = e.matches; });
let started = false;
export function start() {
  loadIdeas();
  if (started) return; started = true;
  refresh();
  subscribe(() => refresh(), v => { store.live = v; });
  setInterval(() => refresh(), 60000);
}
export { catOf, isSnoozed };
