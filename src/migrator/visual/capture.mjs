// The visual check's screenshot step. Runs inside the sandbox image (Node + Debian's
// Chromium) with the network off. Serves a built site on 127.0.0.1, opens each page,
// follows its clicks and takes a full-page screenshot.
//
//   node capture.mjs <input.json>
//
// input.json: { site, out, pages: [{ name, path, click, wait_for }], viewport: [w, h],
//               hide: [css selectors], settle_ms }
// Writes <out>/<name>.png per page and <out>/capture.json with what happened.
// Everything that could make two captures of the same site differ is pinned: the
// clock, the time zone, the locale, animations, the caret and the device scale.

import { createServer } from "node:http";
import { readFile, stat, writeFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { chromium } from "playwright-core";

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript",
  ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
  ".webp": "image/webp", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
  ".ttf": "font/ttf", ".map": "application/json",
};
const FIXED_TIME = new Date("2026-01-15T10:00:00Z");

async function serve(root) {
  const base = resolve(root);
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    let file = normalize(join(base, decodeURIComponent(url.pathname)));
    if (!file.startsWith(base)) { res.writeHead(403).end(); return; }
    try {
      if ((await stat(file)).isDirectory()) file = join(file, "index.html");
    } catch {
      // A single-page app's route: serve its index.html.
      file = extname(file) ? file : join(base, "index.html");
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  return server;
}

const input = JSON.parse(await readFile(process.argv[2], "utf8"));
await mkdir(input.out, { recursive: true });
const server = await serve(input.site);
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN || "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none",
         "--disable-gpu", "--force-color-profile=srgb"],
});
const [width, height] = input.viewport ?? [1280, 800];
const hide = (input.hide ?? []).map((s) => `${s}{visibility:hidden!important}`).join("");
const calm = "*,*::before,*::after{animation:none!important;transition:none!important;" +
  "caret-color:transparent!important;scroll-behavior:auto!important}" + hide;
const report = { origin, pages: [] };

for (const page of input.pages) {
  const context = await browser.newContext({
    viewport: { width, height }, deviceScaleFactor: 1, locale: "en-US",
    timezoneId: "UTC", reducedMotion: "reduce", colorScheme: "light",
  });
  await context.clock.setFixedTime(FIXED_TIME);
  const blocked = [];
  const errors = [];
  await context.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith(origin) || url.startsWith("data:")) return route.continue();
    blocked.push(url);
    return route.abort();
  });
  const tab = await context.newPage();
  tab.on("pageerror", (e) => errors.push(String(e)));
  tab.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const entry = { name: page.name, path: page.path ?? "/", ok: false, blocked, errors };
  try {
    await tab.goto(origin + (page.path ?? "/"), { waitUntil: "networkidle", timeout: 30000 });
    await tab.addStyleTag({ content: calm });
    for (const selector of page.click ?? []) {
      await tab.locator(selector).first().click({ timeout: 10000 });
      await tab.mouse.move(0, 0);
    }
    if (page.wait_for) await tab.locator(page.wait_for).first().waitFor({ timeout: 10000 });
    await tab.evaluate(() => document.fonts.ready);
    await tab.waitForTimeout(input.settle_ms ?? 300);
    await tab.screenshot({ path: join(input.out, `${page.name}.png`), fullPage: true });
    entry.ok = true;
  } catch (e) {
    entry.error = String(e).split("\n")[0];
  }
  report.pages.push(entry);
  await context.close();
}

await browser.close();
server.close();
await writeFile(join(input.out, "capture.json"), JSON.stringify(report, null, 2));
