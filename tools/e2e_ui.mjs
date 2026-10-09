// End-to-end test of the local app in a real (headless) Chrome, driven over the
// DevTools protocol with no dependencies beyond Node 22.
//
//   python -m lookout ui --no-browser          # in another terminal
//   node tools/e2e_ui.mjs trips/synthetic-day  # files to upload through the UI
//
// What a person would do, step by step: create a day, add the files through the
// file picker, press Process (the real local model runs), wait for the result,
// then use the map, filters, evidence rows and the photo lightbox. Any console
// error or uncaught exception fails the run. Screenshots land in
// docs/screenshots/: desktop, phone width and dark mode.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const APP = process.env.LOOKOUT_URL ?? "http://127.0.0.1:8765";
const SRC = resolve(process.argv[2] ?? "trips/synthetic-day");
const SHOTS = resolve("docs/screenshots");
const DAY = `e2e-${Date.now()}`;
const PORT = 9333;
const CHROME = [
  process.env.CHROME,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find((p) => p && existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let fails = 0;
const check = (name, cond, detail = "") => {
  if (!cond) fails++;
  console.log(`  ${cond ? "ok  " : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
};

// ---- Chrome + CDP plumbing ------------------------------------------------
const profile = mkdtempSync(join(tmpdir(), "lookout-e2e-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, "--no-first-run", "--disable-gpu", "about:blank"],
  { stdio: "ignore" });

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error("Chrome did not start");
}

const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let nextId = 0;
const pending = new Map();
const problems = [];
ws.addEventListener("message", (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) {
    const { ok, err } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? err(new Error(msg.error.message)) : ok(msg.result);
  } else if (msg.method === "Runtime.exceptionThrown") {
    problems.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
  } else if (msg.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(msg.params.type)) {
    problems.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    problems.push(`${msg.params.entry.text} ${msg.params.entry.url ?? ""}`);
  }
});
const send = (method, params = {}) => new Promise((ok, err) => {
  const id = ++nextId;
  pending.set(id, { ok, err });
  ws.send(JSON.stringify({ id, method, params }));
});
const js = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
  return r.result.value;
};
const waitFor = async (expr, ms = 10000, step = 200) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await js(expr)) return true; await sleep(step); }
  return false;
};
// Full-page shots as JPEG (they are long); `screen` = just what is on screen.
const shot = async (name, screen = false) => {
  const jpg = name.endsWith(".jpg");
  const { data } = await send("Page.captureScreenshot", {
    format: jpg ? "jpeg" : "png", ...(jpg ? { quality: 82 } : {}), captureBeyondViewport: !screen });
  writeFileSync(join(SHOTS, name), Buffer.from(data, "base64"));
};
const viewport = (width, height, mobile = false) =>
  send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });

mkdirSync(SHOTS, { recursive: true });
await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable"); await send("DOM.enable");
await viewport(1360, 900);

// ---- 1. home ---------------------------------------------------------------
console.log(`app: ${APP}\nday: ${DAY}\nfiles from: ${SRC}`);
await send("Page.navigate", { url: APP });
check("home page renders", await waitFor(`!!document.querySelector(".hero h1")`));
check("model status shows the local model", await waitFor(`/ready|not running|No Gemma/.test(document.querySelector("#model-pill").textContent)`),
  await js(`document.querySelector("#model-pill").textContent`));
await shot("01-home.jpg");

// ---- 2. create a day through the form ---------------------------------------
await js(`document.querySelector('[data-action="new-day"]').click()`);
await js(`(() => { const i = document.querySelector("#new-day-name"); i.value = ${JSON.stringify(DAY)};
  document.querySelector("#new-day").requestSubmit(); })()`);
check("new day opens", await waitFor(`location.hash === "#/day/${DAY}" && !!document.querySelector("#drop")`));

// ---- 3. add files through the real file input --------------------------------
const files = readdirSync(SRC).filter((f) => /\.(jpe?g|png|heic|m4a|mp3|wav|ogg)$/i.test(f)).map((f) => join(SRC, f));
const { root } = await send("DOM.getDocument");
const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: "#pick" });
await send("DOM.setFileInputFiles", { nodeId, files });
const expectStops = await (await fetch(`${APP}/api/days/${encodeURIComponent(SRC.split(/[\\/]/).pop())}`)).json()
  .then((d) => d.plan.length).catch(() => null);
check(`files upload and group into stops`, await waitFor(`document.querySelectorAll(".plan .pc").length > 0`, 60000),
  `${files.length} files`);
const planStops = await js(`document.querySelectorAll(".plan .pc").length`);
if (expectStops != null) check("same grouping as the command line", planStops === expectStops, `${planStops} stops`);
await shot("02-plan.jpg");

// ---- 4. process with the real model -------------------------------------------
const started = Date.now();
await js(`document.querySelector('[data-action="process"]').click()`);
check("progress panel appears", await waitFor(`!!document.querySelector(".progress .meter")`, 15000));
await waitFor(`document.querySelectorAll(".plist .st.done, .plist .st.err").length >= 1`, 180000);
await shot("03-progress.jpg");
const finished = await waitFor(`document.querySelectorAll(".card").length >= ${planStops}`, 600000, 500);
check("processing finishes and every stop gets a card", finished, `${((Date.now() - started) / 1000).toFixed(1)} s`);

// ---- 5. results ----------------------------------------------------------------
const r = await js(`(() => ({
  cards: document.querySelectorAll(".card").length,
  pins: document.querySelectorAll(".pin").length,
  located: [...document.querySelectorAll(".card .meta")].filter((m) => !m.textContent.includes("no GPS")).length,
  chips: document.querySelectorAll(".chip-row").length,
  stats: [...document.querySelectorAll(".stat")].map((s) => s.textContent.trim().replace(/\\s+/g, " ")),
  links: [...document.querySelectorAll(".actions a")].map((a) => a.textContent),
}))()`);
check("one map pin per stop with GPS", r.pins === r.located, `${r.pins} pins, ${r.located} located`);
check("checklist rows rendered", r.chips > 0, `${r.chips} rows`);
check("downloads offered", ["Open trip page", "CSV", "GeoJSON"].every((l) => r.links.includes(l)), r.links.join(", "));
console.log(`        stats: ${r.stats.join(" | ")}`);
await shot("04-result.jpg");

// every stop's photo actually decodes (not just an <img> tag)
check("every card photo loads", await waitFor(`[...document.querySelectorAll(".card img.main")].every((i) => i.complete && i.naturalWidth > 0)`, 20000),
  `${await js(`document.querySelectorAll(".card img.main").length`)} photos`);

// the folded "unclear" items open and close
if (await js(`!!document.querySelector(".fold-btn")`)) {
  await js(`document.querySelector(".fold-btn").click()`);
  check("unclear items unfold", await js(`!document.querySelector(".fold-body").hidden`));
  await js(`document.querySelector(".fold-btn").click()`);
}

// evidence row expands
await js(`document.querySelector(".chip-row").click()`);
check("evidence row expands", await js(`document.querySelector(".chip-row").getAttribute("aria-expanded") === "true"`));

// map pin selects its card
if (r.pins) {
  await js(`document.querySelector(".pin").dispatchEvent(new MouseEvent("click", {bubbles: true}))`);
  check("clicking a pin selects its stop", await waitFor(`!!document.querySelector(".card.sel")`));
}

// filters
for (const f of ["yes", "conflict", "down", "failed", "all"]) {
  await js(`document.querySelector('[data-filter="${f}"]').click()`);
  const n = await js(`document.querySelectorAll(".card").length`);
  check(`filter "${f}" applies`, await js(`document.querySelector('[data-filter="${f}"]').getAttribute("aria-pressed") === "true"`), `${n} card(s)`);
}

// lightbox
const hasPhoto = await js(`!!document.querySelector('.card img.main')`);
if (hasPhoto) {
  await js(`document.querySelector('.card img.main').click()`);
  check("photo opens in the lightbox", await waitFor(`!document.querySelector("#lightbox").hidden && document.querySelector("#lightbox img").complete && document.querySelector("#lightbox img").naturalWidth > 0`));
  await shot("05-lightbox.jpg", true);
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
  check("Escape closes the lightbox", await waitFor(`document.querySelector("#lightbox").hidden`));
}

// trip page download link serves the self-contained page
const tripOk = await fetch(`${APP}/api/days/${encodeURIComponent(DAY)}/out/trip.html`).then((x) => x.ok);
check("trip page is served", tripOk);

// ---- 6. other layouts ----------------------------------------------------------
await viewport(390, 844, true);
await sleep(300);
await shot("06-phone.jpg");
const wide = await js(`[...document.querySelectorAll("body *")]
  .filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
  .slice(0, 3).map((el) => el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(" ")[0] : "")).join(", ")`);
check("no horizontal scroll at phone width", await js(`document.documentElement.scrollWidth <= 392`),
  `${await js("document.documentElement.scrollWidth")} px${wide && (await js("document.documentElement.scrollWidth")) > 392 ? "; too wide: " + wide : ""}`);
await viewport(1360, 900);
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
await sleep(300);
await shot("07-dark.jpg");

// ---- the README picture: a named, processed test day, light theme, top of page
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
const showcase = process.env.SHOWCASE_DAY ?? "test-hunza";
const days = await (await fetch(`${APP}/api/days`)).json();
if (days.some((d) => d.name === showcase && d.processed)) {
  if (!process.env.KEEP_DAY) rmSync(resolve("trips", DAY), { recursive: true, force: true });
  // A fresh load (new query string), so the day list no longer has the test day.
  await send("Page.navigate", { url: `${APP}/?shot=1#/day/${encodeURIComponent(showcase)}` });
  check("switching days shows the new day", await waitFor(
    `(document.querySelector(".day-head h1") || {}).textContent === ${JSON.stringify(showcase)}
     && [...document.querySelectorAll(".card img.main")].every((i) => i.complete && i.naturalWidth > 0)`, 20000));
  await js(`scrollTo(0, 0)`);
  await sleep(300);
  await shot("app.png", true);
}

// ---- 7. console ------------------------------------------------------------------
check("no console errors or uncaught exceptions", problems.length === 0, problems.slice(0, 3).join(" | "));

ws.close();
chrome.kill();
await sleep(300);
try { rmSync(profile, { recursive: true, force: true }); } catch { /* Chrome may hold a lock */ }
if (!process.env.KEEP_DAY) {
  try { rmSync(resolve("trips", DAY), { recursive: true, force: true }); } catch { /* ignore */ }
}
console.log(`\n${fails ? "FAIL" : "PASS"} (${fails} failed) · screenshots in ${SHOTS}`);
process.exit(fails ? 1 : 0);
