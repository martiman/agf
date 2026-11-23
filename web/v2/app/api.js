const TOKEN = (document.querySelector('meta[name="flow-token"]') || {}).content || "";

export async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
export const getState = ({ hours = 48, sprint = true, scope = "open", refresh = false } = {}) =>
  getJSON("/api/state?hours=" + hours + (sprint ? "&sprint=1&scope=" + encodeURIComponent(scope) : "") + (refresh ? "&refresh=1" : ""));

export const getDescription = (key, refresh) => getJSON("/api/description?key=" + encodeURIComponent(key) + (refresh ? "&refresh=1" : ""));

export async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Flow-Launch": TOKEN }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  return Object.assign({ ok: r.ok, status: r.status }, j);
}
export const refineApi = (action, body) => post("/api/refine/" + action, body);
export const ideasApi = body => post("/api/ideas", body);
export const approveApi = body => post("/api/approve", body);
export const launchApi = (act, dry, method, where) => post("/api/launch", { action: act.action, key: act.key, where: (where == null ? act.where : where) || "", dry, ...(method ? { method } : {}) });

export function subscribe(onTick, onLive) {
  const es = new EventSource("/events");
  es.onopen = () => onLive(true);
  es.onerror = () => onLive(false);
  es.onmessage = e => { if (e.data === "tick") onTick(); };
  return () => es.close();
}
export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) { return false; }
}
