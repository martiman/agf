import { chromium } from "playwright";
const LANG = process.argv[2] === "cs" ? "cs" : "en";
const BASE = "http://127.0.0.1:8799/v2/", OUT = "../assets/screenshots/";
const b = await chromium.launch({ channel: "chrome", headless: true });
const open = async (w, h, scale = 2) => {
  const p = await (await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: scale, locale: LANG === "cs" ? "cs-CZ" : "en-GB" })).newPage();
  await p.addInitScript(L => localStorage.setItem("flow.lang", L), LANG);
  await p.goto(BASE); await p.waitForSelector(".lrow"); return p;
};
let p = await open(1440, 860);
await p.locator(".lrow", { hasText: "APS-9002" }).first().click(); await p.waitForTimeout(800);
await p.screenshot({ path: OUT + "inbox.png" });
await p.getByRole("button", { name: /Schválit AC|Approve AC/ }).first().click(); await p.waitForSelector(".ant-modal"); await p.waitForTimeout(600);
await p.screenshot({ path: OUT + "approve.png" });
await p.close();

p = await open(2920, 620, 1.5);
await p.locator(".nav-item", { hasText: "Board" }).click(); await p.waitForSelector(".board"); await p.waitForTimeout(900);
await p.screenshot({ path: OUT + "board.png" });
await p.locator(".card", { hasText: "APS-9004" }).locator(".csum").click(); await p.waitForSelector(".ticket-modal .dt"); await p.waitForTimeout(600);
await p.setViewportSize({ width: 1440, height: 960 }); await p.waitForTimeout(500);
await p.screenshot({ path: OUT + "board-card.png" });
await p.close();

p = await open(1440, 760);
await p.locator(".nav-item", { hasText: "Sessions" }).click(); await p.waitForTimeout(900);
await p.screenshot({ path: OUT + "sessions.png" });
await b.close();
