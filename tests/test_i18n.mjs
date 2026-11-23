import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, "../web/v2/app");
globalThis.Vue = { reactive: o => o };
const { DICTS, translate, i18n } = await import(path.join(APP, "i18n.js"));
const cs = DICTS.cs, en = DICTS.en;
const CZ = /[áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]/;
const KEEP_CZECH = {   // Czech that must stay in the code: commands and prompts for the agent, names of Jira sections
  "components/RefinePanel.js": ["pokračuj", "Otevřené otázky", "Přijmout návrh"],
  "components/TicketDetail.js": ["Proveď nezávislou kontrolu"],
};
const CONVERTED = ["domain.js", ...fs.readdirSync(path.join(APP, "components")).filter(f => f.endsWith(".js")).map(f => "components/" + f)];
let fails = 0, checks = 0;
const ok = (c, msg) => { checks++; if (!c) { fails++; console.error("FAIL:", msg); } };
const params = v => [...new Set((typeof v === "object" ? Object.values(v).join(" ") : v).match(/\{\w+\}/g) || [])].sort().join(",");
const forms = v => typeof v === "object" ? Object.keys(v).sort().join(",") : "text";

for (const k of Object.keys(cs)) {
  ok(k in en, `missing in en.js: ${k}`);
  if (!(k in en)) continue;
  ok(params(cs[k]) === params(en[k]), `parameters differ for ${k}: ${params(cs[k])} vs ${params(en[k])}`);
  ok((typeof cs[k] === "object") === (typeof en[k] === "object"), `plural/text mismatch for ${k}`);
  ok(!CZ.test(typeof en[k] === "object" ? Object.values(en[k]).join(" ") : en[k]), `Czech diacritics in en.js: ${k}`);
}
for (const k of Object.keys(en)) ok(k in cs, `key only in en.js: ${k}`);
for (const [lang, d] of Object.entries(DICTS)) for (const [k, v] of Object.entries(d))
  if (typeof v === "object") ok(v.other !== undefined, `${lang}: plural without "other": ${k}`);

ok(translate("cs", "filter.days", { n: 1 }) === "1 den", "cs one");
ok(translate("cs", "filter.days", { n: 3 }) === "3 dny", "cs few");
ok(translate("cs", "filter.days", { n: 7 }) === "7 dní", "cs other");
ok(translate("en", "filter.days", { n: 1 }) === "1 day" && translate("en", "filter.days", { n: 7 }) === "7 days", "en plurals");
ok(translate("en", "shell.jira_off", { reason: "x" }).startsWith("Jira: x"), "parameter filled");
ok(translate("en", "nonexistent.key") === "nonexistent.key", "unknown key is visible");
ok(translate("cs", "shell.server_down", {}) === "Server neodpovídá: {error}", "missing parameter stays visible");

const saved = en["__only_cs"]; cs["__only_cs"] = "jen česky";
ok(translate("en", "__only_cs") === "jen česky", "fallback to Czech"); delete cs["__only_cs"];

for (const f of CONVERTED) {
  const src = fs.readFileSync(path.join(APP, f), "utf8");
  const used = [...src.matchAll(/\bt\(\s*['"]([\w.]+)['"]|\$t\(\s*['"]([\w.]+)['"]/g)].map(m => m[1] || m[2]);
  for (const k of used.filter(k => !/[._]$/.test(k))) ok(k in cs, `${f}: unknown key ${k}`);
  const code = src.split("\n").filter(l => !l.trim().startsWith("//") && !(KEEP_CZECH[f] || []).some(w => l.includes(w))).join("\n");
  ok(!CZ.test(code), `${f}: Czech text left in the component`);
}
if (fails) { console.error(`${fails} of ${checks} checks failed`); process.exit(1); }
console.log(`${checks} checks ok (${Object.keys(cs).length} keys, ${Object.keys(DICTS).length} languages)`);
