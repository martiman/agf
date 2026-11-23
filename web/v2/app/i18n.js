import cs from "./i18n/cs.js";
import en from "./i18n/en.js";

const { reactive } = Vue;
export const DICTS = { cs, en };
export const LANGS = [{ id: "cs", label: "CS", locale: "cs-CZ" }, { id: "en", label: "EN", locale: "en-GB" }];

const read = () => { try { return localStorage.getItem("flow.lang"); } catch (e) { return null; } };
const first = read();
export const i18n = reactive({ lang: first in DICTS ? first : "en" });
if (typeof document !== "undefined") document.documentElement.lang = i18n.lang;

export function setLang(id) {
  if (!(id in DICTS)) return;
  i18n.lang = id;
  try { localStorage.setItem("flow.lang", id); } catch (e) {}
  if (typeof document !== "undefined") document.documentElement.lang = id;
}

const fill = (s, p) => s.replace(/\{(\w+)\}/g, (m, k) => (p && p[k] != null ? String(p[k]) : m));

export function translate(lang, key, params) {
  let v = DICTS[lang] && DICTS[lang][key];
  if (v === undefined) v = cs[key];
  if (v === undefined) return key;
  if (typeof v === "object") {
    const form = new Intl.PluralRules(lang).select(Number((params && params.n) || 0));
    v = v[form] !== undefined ? v[form] : v.other;
  }
  return fill(v, params);
}
export const t = (key, params) => translate(i18n.lang, key, params);

export const locale = () => (LANGS.find(l => l.id === i18n.lang) || LANGS[0]).locale;

export const antLocale = () => ({ locale: i18n.lang, Modal: { okText: t("ant.ok"), cancelText: t("ant.cancel"), justOkText: t("ant.ok") }, Empty: { description: t("ant.empty") } });

export const srv = (pair, fallback) => (Array.isArray(pair) && typeof pair[0] === "string" ? t(pair[0], pair[1] || {}) : (fallback == null ? "" : fallback));
