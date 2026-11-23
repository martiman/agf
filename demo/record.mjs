import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const SC = process.argv[2] || "approve", EN = process.argv[3] === "en";
const MUTE = EN && process.argv[4] === "mute", CC = EN && (process.argv[4] === "cc" || MUTE);
const NAME = (SC === "launch" ? "agf-spusteni-agenta" : "agf-schvaleni-ac") + (EN ? "-en" : "") + (MUTE ? "-cc-silent" : CC ? "-cc" : "");
const EN_HEAD = {
  approve: [
    "In this video: approve a ticket's acceptance criteria in AGF",
    "Step 1 · Open the Inbox: only what waits for you",
    "Step 2 · Open a ticket whose AC wait for approval",
    "Step 3 · Find the one main action: Approve AC",
    "Step 4 · Click Approve AC and review what you approve",
    "Step 5 · Confirm that you have read the criteria",
    "Done · The ticket is REFINED; one Jira transition written",
    "Next · Board: the same tickets by status",
    "Search the board by title and choose the sprint scope",
    "Backlog: only my tickets, one click shows all",
    "Open a card as a window",
    "Launch agent: choose the project, check the exact prompt",
    "Close without launching: nothing starts by itself",
  ],
  launch: [
    "In this video: launch an agent straight from a ticket",
    "Step 1 · Open a ticket ready for development and click Launch agent",
    "Step 2 · Check the folder and the exact prompt",
    "Step 3 · The project comes from the ticket tag; change it if needed",
    "Session names are always: ticket key · action · project",
    "Step 4 · Choose how to start: in the app or in the terminal",
    "Step 5 · Open in the app, the safer way",
    "Result · The session appears in Claude and on the Sessions tab",
  ],
};
const EN_TEXT = {
  approve: [
    "This is AGF, an overview of the work of your agents and tickets. On the left are three tabs: Inbox, Sessions and Board.",
    "The Inbox shows only what waits for you. It is ordered by urgency: what needs an answer or an approval is at the top.",
    "I open a ticket whose acceptance criteria wait for approval. On the right is the whole ticket: the title, the status and one box that says what the agent needs from you.",
    "Under the title there is just a grey line of information. What you can click is blue. The main step is the only filled button: Approve AC.",
    "I click Approve AC. The app shows exactly what you approve: the ticket, the transition in Jira and all numbered criteria.",
    "The spec check blocks nothing. I tick that I have read the criteria and confirm.",
    "The ticket moved to REFINED and development can start. Only this one transition was written to Jira.",
    "The Board tab shows the same tickets in columns by status. At the top are search and filters, like in Jira.",
    "I type part of a title and the board narrows down. On the right you choose the scope: the active sprint, single sprints, or the backlog.",
    "In the backlog I see only my tickets; the assignee filter hides the others. One click shows them all.",
    "I open a card as a window in the middle. For a ticket that is ready for development the app offers to launch an agent.",
    "Launch agent opens a dialog. I choose the project where the session should run and I see the exact prompt. Nothing starts until I click myself.",
    "I close the dialog without launching. That is the whole path: from the ticket through the approval to a controlled launch of an agent.",
  ],
  launch: [
    "You launch an agent straight from a ticket. I open the board and the card of a ticket that is ready for development.",
    "The app proposes the next step from the ticket status. For this one it is delivery: an agent implements it. I click Launch agent.",
    "A confirmation opens. Nothing starts until you click yourself. At the top you see the folder and the exact prompt the agent receives.",
    "The project is pre-filled from the tag in the ticket title, here TRIS, which means the frontend. I can change it: I try the whole workspace and the folder is rewritten at once. Then I go back to tris.",
    "The session name is always the same: ticket key, action and project. That makes sessions easy to find in the list and in the dashboard.",
    "There are two ways to start. In the app, the session opens with a pre-filled prompt and you send it yourself. In the terminal it starts right away, which is why that button is red.",
    "I choose the safer variant: open in the app.",
    "In this recording the session does not really open; the demo only pretends. In real life it would appear in the Claude app and, once you send the prompt, on the Sessions tab.",
  ],
};
let stepNo = 0, headNo = 0;
const BASE = "http://127.0.0.1:8799/v2/", OUT = path.resolve("out"), W = 1280, H = 720, PAD = 700;
for (const d of ["audio", "frames"]) fs.rmSync(OUT + "/" + d, { recursive: true, force: true }); fs.mkdirSync(OUT + "/audio", { recursive: true });
const FF = "/opt/homebrew/bin/ffmpeg", FP = "/opt/homebrew/bin/ffprobe";
const sleep = ms => new Promise(r => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, locale: EN ? "en-GB" : "cs-CZ" });
const page = await ctx.newPage();
await page.addInitScript(L => localStorage.setItem("flow.lang", L), EN ? "en" : "cs");
await page.route("**/api/launch", async route => {
  const body = route.request().postDataJSON() || {};
  if (body.dry) return route.continue();
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, method: body.method || "app" }) });
});
fs.mkdirSync(OUT + "/frames", { recursive: true });
const frames = [];
const cdp = await ctx.newCDPSession(page);
cdp.on("Page.screencastFrame", async f => {
  const file = `${OUT}/frames/${String(frames.length).padStart(6, "0")}.jpg`;
  fs.writeFileSync(file, Buffer.from(f.data, "base64")); frames.push({ file, ts: f.metadata.timestamp * 1000 });
  cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
await sleep(500);
const t00 = Date.now();
await page.addInitScript(() => {
  addEventListener("DOMContentLoaded", () => {
    const scrub = () => {   // no personal path in the recording
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) if (n.nodeValue.includes("/Users/")) n.nodeValue = n.nodeValue.replace(/\/Users\/[^/\s]+\/dev\/trafinoil/g, "~/work/workspace");
    };
    new MutationObserver(scrub).observe(document.body, { subtree: true, childList: true, characterData: true }); scrub();
    const st = document.createElement("style");   // tooltips would sit between the cursor and the target
    st.textContent = ".ant-tooltip { display: none !important }"; document.head.appendChild(st);
    const c = document.createElement("div");
    c.style.cssText = "position:fixed;z-index:99999;width:18px;height:18px;border-radius:50%;background:rgba(22,119,255,.55);border:2px solid #1677ff;pointer-events:none;left:-40px;top:-40px;transform:translate(-50%,-50%);transition:transform .08s";
    document.body.appendChild(c);
    addEventListener("mousemove", e => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", e => {
      c.style.transform = "translate(-50%,-50%) scale(.7)";
      const r = document.createElement("div");
      r.style.cssText = `position:fixed;z-index:99998;left:${e.clientX}px;top:${e.clientY}px;width:10px;height:10px;border-radius:50%;border:2px solid #1677ff;pointer-events:none;transform:translate(-50%,-50%);transition:all .5s ease-out;opacity:.9`;
      document.body.appendChild(r); requestAnimationFrame(() => { r.style.width = "56px"; r.style.height = "56px"; r.style.opacity = "0"; }); setTimeout(() => r.remove(), 600);
    }, true);
    addEventListener("mouseup", () => { c.style.transform = "translate(-50%,-50%)"; }, true);
    window.__cap = () => {
      let el = document.getElementById("agf-cap");
      const v = JSON.parse(localStorage.getItem("agf.cap") || "null");
      if (!v) return el && el.remove();
      if (!el) {
        el = document.createElement("div"); el.id = "agf-cap";
        el.style.cssText = "position:fixed;z-index:99990;left:0;right:0;bottom:0;padding:14px 40px 16px;background:rgba(10,18,32,.9);color:#fff;text-align:center;pointer-events:none;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif";
        document.body.appendChild(el);
      }
      el.innerHTML = "";
      const h = document.createElement("div"); h.textContent = v.head; h.style.cssText = "font-size:22px;font-weight:700;color:#69b1ff;margin-bottom:4px";
      const t = document.createElement("div"); t.textContent = v.say; t.style.cssText = "font-size:15px;line-height:1.35;color:#e6eefc";
      el.append(h, t);
    };
    window.__cap();
  });
});
const setCap = async s => { if (!CC) return; await page.evaluate(v => { localStorage.setItem("agf.cap", JSON.stringify(v)); window.__cap && window.__cap(); }, { head: s.head, say: s.say }).catch(() => {}); };
if (CC) await page.goto(BASE).catch(() => {});
let mx = 100, my = 100;
async function move(x, y) { await page.mouse.move(x, y, { steps: 28 }); mx = x; my = y; }
async function click(loc) {
  const l = typeof loc === "string" ? page.locator(loc).first() : loc.first();
  await l.scrollIntoViewIfNeeded(); const b = await l.boundingBox();
  await move(b.x + b.width / 2, b.y + b.height / 2); await sleep(250); await page.mouse.click(mx, my); await sleep(500);
}

const steps = [];
const step = (say, act) => steps.push({ say: EN ? EN_TEXT[SC][stepNo++] : say, head: EN ? EN_HEAD[SC][headNo++] : "", act });
if (SC === "approve") {

step("Tohle je AGF, přehled práce agentů a tiketů. Vlevo jsou tři záložky: Inbox, Sessions a Board.", async () => {
  await page.goto(BASE); await page.waitForSelector(".lrow"); await move(120, 80); await sleep(400); await move(110, 140);
});
step("Inbox ukazuje jen to, co čeká na vás. Je seřazený podle naléhavosti, nahoře je to, co potřebuje odpověď nebo schválení.", async () => {
  await move(430, 160); await sleep(600); await move(430, 330);
});
step("Otevřu tiket, jehož akceptační kritéria čekají na schválení. Vpravo je celý tiket: nadpis, stav a jedno pole, které říká, co od vás agent potřebuje.", async () => {
  await click(page.locator(".lrow", { hasText: "APS-9002" }));
  await page.locator(".lrow", { hasText: "APS-9002" }).first().click();   // the slow mouse path sometimes loses the selection to a refresh: make sure
  await page.getByRole("button", { name: /Schválit AC|Approve AC/ }).first().waitFor();
});
step("Pod nadpisem je jen šedý řádek s informacemi. Co jde kliknout, je modré. Hlavní krok je jediné plné tlačítko: Schválit AC.", async () => {
  await move(900, 160); await sleep(500); await move(900, 300);
});
step("Kliknu na Schválit AC. Aplikace ukáže, co přesně schvalujete: tiket, přechod v Jiře a všechna číslovaná kritéria.", async () => {
  await click(page.getByRole("button", { name: /Schválit AC|Approve AC/ }));
  await page.waitForSelector(".ant-modal");
});
step("Kontrola zadání nic neblokuje. Zaškrtnu, že jsem kritéria přečetl, a potvrdím.", async () => {
  await click(page.locator(".ant-modal .ant-checkbox-wrapper"));
});
step("Tiket se přesunul do stavu REFINED, vývoj může začít. Do Jiry se zapsal jen tento přechod.", async () => {
  await click(page.locator(".ant-modal .ant-btn-primary", { hasText: /Schválit AC|Approve AC/ }));
  await page.waitForSelector(".ant-message", { timeout: 8000 }).catch(() => {});
  await sleep(800);
});
step("Na záložce Board jsou stejné tikety ve sloupcích podle stavu. Nahoře je vyhledávání a filtry jako v Jiře.", async () => {
  await click(page.locator(".nav-item", { hasText: "Board" })); await page.waitForSelector(".board");
});
step("Napíšu část názvu a board se zúží. Vpravo je výběr rozsahu: aktivní sprint, jednotlivé sprinty nebo backlog.", async () => {
  await click(page.getByPlaceholder(/Hledat: klíč|Search: key/)); await page.keyboard.type("limit", { delay: 140 }); await sleep(700);
  await page.getByPlaceholder(/Hledat: klíč|Search: key/).fill(""); await sleep(300);
  await click(page.locator(".ant-select", { hasText: /sprint|Backlog|Refinement/i }).first());
  await click(page.locator(".ant-select-item-option", { hasText: "Backlog" }));
});
step("V backlogu vidím jen svoje tikety, ostatní skrývá filtr řešitele. Jedním klikem zobrazím všechny.", async () => {
  await sleep(600); const a = page.locator("button.hidden-hint");
  if (await a.count()) await click(a);
});
step("Kartu otevřu jako okno uprostřed. U tiketu, který je připravený k vývoji, nabídne aplikace spuštění agenta.", async () => {
  await click(page.locator(".ant-select", { hasText: /sprint|Backlog|Refinement/i }).first());
  await click(page.locator(".ant-select-item-option", { hasText: /Aktivní sprint|Active sprint/ })); await sleep(900);
  await click(page.locator(".card", { hasText: "APS-9004" }).locator(".csum"));
  await page.waitForSelector(".ticket-modal .dt");
});
step("Spustit agenta otevře dialog. Vyberu projekt, ve kterém má session běžet, a vidím přesný prompt. Nic se nespustí, dokud sám nekliknu.", async () => {
  await click(page.locator(".ticket-modal button", { hasText: /Spustit agenta|Launch agent/ }));
  await page.waitForSelector(".ant-modal .ant-select");
  await click(page.locator(".ant-modal .ant-select").last()); await sleep(500);
});
step("Dialog zavřu bez spuštění. To je celé: od zadání přes schválení k řízenému spuštění agenta.", async () => {
  await page.keyboard.press("Escape"); await sleep(400); await page.keyboard.press("Escape"); await sleep(400); await page.keyboard.press("Escape");
});
}
if (SC === "launch") {
  const modalSelect = () => page.locator(".ant-modal .ant-select").last();
  const pick = async txt => { await click(modalSelect()); await click(page.locator(".ant-select-item-option", { hasText: txt })); };
  step("Agenta spouštíte přímo z tiketu. Otevřu board a kartu tiketu, který je připravený k vývoji.", async () => {
    await page.goto(BASE); await page.waitForSelector(".lrow"); await move(120, 80);
    await click(page.locator(".nav-item", { hasText: "Board" })); await page.waitForSelector(".board");
    await click(page.locator(".card", { hasText: "APS-9004" }).locator(".csum"));
    await page.waitForSelector(".ticket-modal .dt");
  });
  step("Aplikace sama navrhne další krok podle stavu tiketu. U tohoto je to dodání: agent ho naprogramuje. Kliknu na Spustit agenta.", async () => {
    await move(700, 250); await sleep(500);
    await click(page.locator(".ticket-modal button", { hasText: /Spustit agenta|Launch agent/ }));
    await page.waitForSelector(".ant-modal .ant-select");
  });
  step("Otevře se potvrzení. Nic se nespustí, dokud sami nekliknete. Nahoře vidíte složku a přesný prompt, který agent dostane.", async () => {
    await move(640, 330); await sleep(700); await move(640, 420);
  });
  step("Projekt se předvyplní podle značky v názvu tiketu, tady TRIS, tedy frontend. Můžu ho změnit: zkusím celý workspace a složka se okamžitě přepíše. Pak se vrátím k tris.", async () => {
    await pick("Workspace"); await sleep(1500); await pick("tris"); await sleep(900);
  });
  step("Název session je vždy stejný: klíč tiketu, akce a projekt. Díky tomu se session snadno najdou v seznamu i v dashboardu.", async () => {
    await move(640, 440); await sleep(600); await move(640, 500);
  });
  step("Jsou dva způsoby spuštění. V aplikaci se session otevře s předvyplněným promptem a odešlete ho sami. V terminálu začne hned, proto je tlačítko červené.", async () => {
    await move(560, 600); await sleep(900); await move(720, 600);
  });
  step("Zvolím bezpečnější variantu: otevřít v aplikaci.", async () => {
    await click(page.locator(".ant-modal .ant-btn-primary", { hasText: /Otevřít v aplikaci|Open in the app/ }));
    await page.waitForSelector(".ant-message", { timeout: 8000 }).catch(() => {});
    await sleep(1200);
  });
  step("V záznamu se session neotevřela doopravdy, ukázka ji jen předstírá. Ve skutečnosti by se objevila v aplikaci Claude a po odeslání promptu i na záložce Sessions.", async () => {
    await click(page.locator(".nav-item", { hasText: "Sessions" })); await sleep(800);
  });
}

const dur = f => parseFloat(execFileSync(FP, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString());
steps.forEach((s, i) => {
  s.file = `${OUT}/audio/${String(i).padStart(2, "0")}.aiff`;
  execFileSync("/usr/bin/say", ["-v", EN ? "Samantha" : "Zuzana", "-r", EN ? "175" : "165", "-o", s.file, s.say]);
  s.dur = dur(s.file) * 1000;
});
for (const s of steps) {
  const t0 = Date.now(); s.start = t0 - t00;
  await setCap(s);
  try { await s.act(); } catch (e) { console.error("step failed:", s.say.slice(0, 40), String(e).split("\n").slice(0, process.env.DEBUG ? 12 : 1).join(" | ")); }
  const left = s.dur + PAD - (Date.now() - t0); if (left > 0) await sleep(left);
  s.end = Date.now() - t00;
}
await sleep(800); await cdp.send("Page.stopScreencast").catch(() => {});
await ctx.close(); await browser.close();
const cutAbs = t00 + steps[0].start - 300;
const endAbs = t00 + steps.at(-1).end + 500;
steps.forEach(s => { s.start = s.start + t00 - cutAbs; s.end = s.end + t00 - cutAbs; });
let list = "", last = null;
frames.forEach((f, i) => {
  const next = i + 1 < frames.length ? frames[i + 1].ts : endAbs;
  if (next <= cutAbs) return;
  list += `file '${f.file}'\nduration ${Math.max(0.02, (next - Math.max(f.ts, cutAbs)) / 1000).toFixed(3)}\n`; last = f;
});
list += `file '${last.file}'\n`;
fs.writeFileSync(OUT + "/frames.txt", list);
execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", OUT + "/frames.txt", "-vf", "scale=1280:720,fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "20", OUT + "/silent.mp4"], { stdio: "ignore" });

const ts = ms => { const d = new Date(ms).toISOString(); return d.slice(11, 23).replace(".", ","); };
fs.writeFileSync(OUT + "/" + NAME + ".srt", steps.map((s, i) => `${i + 1}\n${ts(s.start)} --> ${ts(s.end - 200)}\n${s.say}\n`).join("\n"));
const video = OUT + "/silent.mp4";
const args = ["-y", "-i", video, ...steps.flatMap(s => ["-i", s.file])];
const filt = steps.map((s, i) => `[${i + 1}:a]adelay=${Math.round(s.start)}|${Math.round(s.start)}[a${i}]`).join(";") + ";" + steps.map((_, i) => `[a${i}]`).join("") + `amix=inputs=${steps.length}:normalize=0[a]`;
if (MUTE) execFileSync(FF, ["-y", "-i", video, "-i", OUT + "/" + NAME + ".srt", "-map", "0:v", "-map", "1:s", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:s", "mov_text", OUT + "/" + NAME + ".mp4"], { stdio: "ignore" });
else execFileSync(FF, [...args, "-i", OUT + "/" + NAME + ".srt", "-filter_complex", filt, "-map", "0:v", "-map", "[a]", "-map", `${steps.length + 1}:s`,
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-c:s", "mov_text", "-shortest", OUT + "/" + NAME + ".mp4"], { stdio: "inherit" });
console.log("hotovo:", OUT + "/" + NAME + ".mp4", Math.round(steps.at(-1).end / 1000) + " s");
