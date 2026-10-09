// Check a processed day's trip.html against its own field_log.csv, without a browser.
//
//   node tools/check_trip_page.mjs trips/synthetic-day/lookout_out
//
// The page is meant to be opened with no network, so the first checks are that
// nothing in it reaches out. The rest confirm the page and the CSV describe the
// same day: same stops, same answers, failures shown as failures.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2] ?? "trips/synthetic-day/lookout_out";
const html = readFileSync(join(dir, "trip.html"), "utf8");
const csvText = readFileSync(join(dir, "field_log.csv"), "utf8");
const geo = JSON.parse(readFileSync(join(dir, "field_log.geojson"), "utf8"));

let fails = 0, checks = 0;
const ok = (name, cond, detail = "") => {
  checks++;
  if (!cond) fails++;
  console.log(`  ${cond ? "ok  " : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
};

// Minimal RFC 4180 parser: quoted fields may contain commas, quotes and newlines.
function parseCsv(text) {
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') q = false;
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows.filter(r => r.length > 1);
  return body.map(r => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}
const rows = parseCsv(csvText);

// 1. Nothing leaves the page.
ok("no <script> elements", !/<script/i.test(html));
ok("no external src/href", !/(src|href)\s*=\s*"(https?:)?\/\//i.test(html));
ok("no url() to the network in CSS", !/url\(\s*['"]?(https?:)?\/\//i.test(html));
ok("no web fonts", !/@import|@font-face/i.test(html));

// 2. Page and CSV describe the same stops.
const cards = [...html.matchAll(/<article class="stop" id="([^"]+)"/g)].map(m => m[1]);
ok("one card per CSV row", cards.length === rows.length, `${cards.length} cards, ${rows.length} rows`);
ok("same stops in the same order", cards.join() === rows.map(r => r.stop).join());

// 3. Answers on the page match the CSV, stop by stop.
const header = Object.keys(rows[0] ?? {});
const answerCols = header.filter(k => header.includes(`${k}_evidence`));
let mismatch = [];
for (const r of rows) {
  const block = html.split(`<article class="stop" id="${r.stop}"`)[1]?.split("</article>")[0] ?? "";
  if (r.error) continue;
  const chips = [...block.matchAll(/<span class="chip (\w+)">/g)].map(m => m[1]);
  const want = answerCols.map(k => r[k]);
  if (chips.join() !== want.join()) mismatch.push(r.stop);
}
ok("every chip matches the CSV answer", mismatch.length === 0, mismatch.join(" "));

// 4. Failures are shown, not hidden.
const failed = rows.filter(r => r.error);
ok("every failed stop says so on the page",
   failed.every(r => html.includes(`Not processed: `)), `${failed.length} failed`);

// 5. GeoJSON has exactly the located stops.
const located = rows.filter(r => r.lat && r.lon).map(r => r.stop);
ok("GeoJSON holds every located stop and nothing else",
   geo.features.map(f => f.properties.stop).join() === located.join(),
   `${geo.features.length} features`);

console.log(`\n${fails ? "FAIL" : "PASS"}: ${checks - fails}/${checks} checks`);
process.exit(fails ? 1 : 0);
