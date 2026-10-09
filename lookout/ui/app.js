/* Lake Lookout: the local app. No libraries, no network beyond this computer. */
"use strict";

const PHOTO_EXT = [".jpg", ".jpeg", ".png", ".heic", ".heif"];
const AUDIO_EXT = [".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".amr", ".3gp", ".webm", ".flac"];

const state = {
  health: null, days: [], day: null, data: null,
  filter: "all", selected: null, open: new Set(),
  poll: null, jobNext: 0, events: [], uploading: null,
};

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const ext = (name) => name.slice(name.lastIndexOf(".")).toLowerCase();

/* Where everything lives. The local app asks its own server; an exported,
   read-only demo (python -m lookout export) reads pre-built files instead.
   Static paths are relative so the demo works under any sub-path. */
const STATIC = window.LOOKOUT_STATIC || null;
const URLS = STATIC ? {
  health: () => "data/health.json",
  days: () => "data/days.json",
  day: (d) => `data/days/${enc(d)}.json`,
  thumb: (d, name, s) => `data/thumbs/${enc(d)}/${enc(name)}.${s <= 360 ? 360 : s <= 640 ? 640 : 1600}.jpg`,
  file: (d, name) => `data/files/${enc(d)}/${enc(name)}`,
  // Voice notes are re-encoded to AAC in .mp4 on export: plays in every browser and host.
  audio: (d, name) => `data/audio/${enc(d)}/${enc(name)}.mp4`,
  out: (d, f) => `data/out/${enc(d)}/${f}`,
} : {
  health: () => "/api/health",
  days: () => "/api/days",
  day: (d) => `/api/days/${enc(d)}`,
  thumb: (d, name, s) => `/api/days/${enc(d)}/thumb/${enc(name)}?s=${s}`,
  file: (d, name) => `/api/days/${enc(d)}/file/${enc(name)}`,
  audio: (d, name) => `/api/days/${enc(d)}/file/${enc(name)}`,
  out: (d, f) => `/api/days/${enc(d)}/out/${f}`,
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", onKey);
  window.addEventListener("hashchange", route);
  if (STATIC) {
    document.body.classList.add("static");
    const offline = $(".pill.ok");
    offline.title = "The days shown here were processed offline on a laptop. Nothing is processed on this website.";
    offline.innerHTML = "<i></i>Read-only demo · processed offline on a laptop";
  } else {
    $("#new-day").addEventListener("submit", onNewDay);
    wireDrop();
  }
  await Promise.all([loadHealth(), loadDays()]);
  route();
}

async function loadHealth() {
  try { state.health = await api(URLS.health()); }
  catch { state.health = { ollama: false, models: [], checklist: [] }; }
  const pill = $("#model-pill");
  const h = state.health;
  if (STATIC) {
    pill.className = "pill ok";
    pill.innerHTML = `<i></i>Results from ${esc(STATIC.model || h.default_model)}, run locally`;
  } else if (!h.ollama) {
    pill.className = "pill bad";
    pill.innerHTML = "<i></i>Ollama is not running: start it to process a day";
  } else if (!h.models.length) {
    pill.className = "pill bad";
    pill.innerHTML = `<i></i>No Gemma model: run <code>ollama pull ${esc(h.default_model)}</code>`;
  } else {
    pill.className = "pill ok";
    pill.innerHTML = `<i></i>Local model ready · ${esc(h.models.join(", "))}`;
  }
}

async function loadDays() {
  state.days = await api(URLS.days());
  renderDays();
}

function route() {
  const m = location.hash.match(/^#\/day\/(.+)$/);
  if (m) openDay(decodeURIComponent(m[1]));
  else { state.day = null; state.data = null; stopPolling(); renderDays(); renderHome(); }
}

/* ------------------------------------------------------------- sidebar */
function renderDays() {
  const nav = $("#days");
  if (!state.days.length) {
    nav.innerHTML = `<p class="nogps">No days yet. Create one, then drop the day's photos and voice notes in.</p>`;
    return;
  }
  nav.innerHTML = state.days.map((d) => {
    const files = `${d.photos} photo${d.photos === 1 ? "" : "s"} · ${d.memos} voice note${d.memos === 1 ? "" : "s"}`;
    const tag = d.job === "running" ? `<span class="tag run">processing</span>`
      : d.processed ? `<span class="tag">done</span>` : "";
    return `<a class="day-link" href="#/day/${enc(d.name)}" ${d.name === state.day ? 'aria-current="page"' : ""}>
      ${tag}<b>${esc(d.name)}</b><small>${files}</small></a>`;
  }).join("");
}

/* ---------------------------------------------------------------- home */
function renderHome() {
  $("#main").innerHTML = `
  <section class="hero">
    <h1>Be the eyes the satellites lack.</h1>
    <p class="lede">Satellites lose glacial lakes under monsoon cloud. Hikers walk past them every day.
    Lake Lookout turns a day's photos and voice notes into a field log, on this computer, with no internet.</p>
    <div class="steps">
      <div class="step"><span class="n">1</span><b>On the trail</b><p>At each lake, take one wide photo and say what you see. The screen stays in your pocket.</p></div>
      <div class="step"><span class="n">2</span><b>In the evening</b><p>Drop the day's files here. Gemma runs locally and fills in a checklist for every stop, citing its evidence.</p></div>
      <div class="step"><span class="n">3</span><b>Share the log</b><p>One offline page, plus CSV and GeoJSON for researchers. Observations only: no risk scores, no alerts.</p></div>
    </div>
    ${STATIC ? staticIntro() : `<button class="btn primary" data-action="new-day">+ Start a new day</button>`}
  </section>`;
}

function staticDayNote(day) {
  const notes = (STATIC.notes || {})[day];
  return `<div class="notice warn">Read-only demo of a processed day.${notes ? " " + esc(notes) : ""}
    ${(STATIC.credits || {})[day] ? ` <a href="${URLS.file(day, STATIC.credits[day])}">Photo credits</a>.` : ""}</div>`;
}

function staticIntro() {
  const featured = STATIC.featured || (state.days[0] || {}).name;
  return `<div class="notice warn">This is a <b>read-only demo</b>. The days here were processed on a laptop,
      offline, by Gemma 4. Nothing is processed on this website, and by design Lake Lookout never uploads
      anyone's photos: to log your own hike, run it on your own computer${STATIC.repo ? ` (<a href="${esc(STATIC.repo)}">code and instructions</a>)` : ""}.</div>
    ${featured ? `<a class="btn primary" href="#/day/${enc(featured)}">Open the ${esc(featured)} day</a>` : ""}`;
}

/* ----------------------------------------------------------------- day */
async function openDay(name) {
  if (state.day !== name) {
    stopPolling();
    state.selected = null; state.open = new Set(); state.filter = "all";
    state.events = []; state.jobNext = 0;
  }
  state.day = name;
  renderDays();
  let data;
  try { data = await api(URLS.day(name)); }
  catch (e) { if (state.day === name) $("#main").innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  // A slower answer for a day the person has already left must not replace
  // the day they are looking at now.
  if (state.day !== name) return;
  state.data = data;
  if (state.data.job && state.data.job.status === "running") startPolling();
  renderDay();
}

function counts(plan) {
  const photos = plan.reduce((n, s) => n + s.photos.length, 0);
  const memos = plan.reduce((n, s) => n + s.memos.length, 0);
  return { stops: plan.length, photos, memos };
}

function renderDay() {
  const d = state.data;
  if (!d) return;
  const running = d.job && d.job.status === "running" || state.poll;
  const c = counts(d.plan);
  const res = d.result;
  const h = state.health || { models: [] };
  const modelOpts = (h.models.length ? h.models : [h.default_model || "gemma4:e4b"])
    .map((m) => `<option ${m === h.default_model ? "selected" : ""}>${esc(m)}</option>`).join("");
  const sub = c.stops
    ? `${c.stops} stop${c.stops === 1 ? "" : "s"} · ${c.photos} photo${c.photos === 1 ? "" : "s"} · ${c.memos} voice note${c.memos === 1 ? "" : "s"}`
    : "No files yet";
  const done = res ? ` · processed ${esc(res.meta.processed)} with ${esc(res.meta.model)} in ${esc(res.meta.seconds)} s` : "";
  const out = (f, label) => `<a class="btn small" href="${URLS.out(d.name, f)}" ${f.endsWith("html") ? 'target="_blank" rel="noopener"' : ""}>${label}</a>`;

  $("#main").innerHTML = `
    <div class="day-head">
      <div><h1>${esc(d.name)}</h1><div class="sub">${sub}${done}</div></div>
      <div class="actions">
        ${res ? out("trip.html", "Open trip page") + out("field_log.csv", "CSV") + out("field_log.geojson", "GeoJSON") : ""}
        <select id="model" aria-label="Model">${modelOpts}</select>
        <label class="cpu"><input type="checkbox" id="cpu"> CPU only</label>
        <button class="btn primary" data-action="process" ${!c.stops || running || !h.ollama ? "disabled" : ""}>
          ${running ? '<span class="spinner"></span> Processing…' : res ? "Process again" : "Process day"}</button>
      </div>
    </div>
    <div class="drop" id="drop">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
      <div class="grow"><b>Drop photos and voice notes here</b><br>
        <small>Copy them off the phone by cable so the GPS and times survive. JPEG, HEIC, m4a, mp3, ogg, wav.</small></div>
      <label class="btn small">Browse…<input type="file" id="pick" multiple hidden
        accept="${[...PHOTO_EXT, ...AUDIO_EXT].join(",")},image/*,audio/*"></label>
    </div>
    <div id="upload-note"></div>
    ${d.plan_error ? `<div class="notice err">Could not read some files: ${esc(d.plan_error)}</div>` : ""}
    ${!h.ollama && !STATIC ? `<div class="notice warn">Start Ollama to process this day. Everything else works without it.</div>` : ""}
    ${STATIC ? staticDayNote(d.name) : ""}
    <div id="progress"></div>
    ${res ? renderResult(res) : renderPlan(d.plan)}
    <p class="footer-note">These are field observations, not a hazard assessment, and nothing here is an alert.
      Items with a citation correspond to published glacial-lake hazard indicators; interpretation belongs to people qualified to make it.</p>`;

  $("#pick").addEventListener("change", (e) => upload([...e.target.files]));
  const cpu = $("#cpu"), model = $("#model");
  cpu.addEventListener("change", () => {
    const want = cpu.checked ? h.cpu_model : h.default_model;
    if ([...model.options].some((o) => o.value === want)) model.value = want;
  });
  renderProgress();
  if (res) wireMap();
}

function renderPlan(plan) {
  if (!plan.length) return `<p class="nogps">Drop the day's files above to see how they group into stops.</p>`;
  return `<h2 class="section-title">Stops found, not yet processed</h2>
    <div class="plan">${plan.map((s) => `
      <div class="pc panel">
        ${s.photos.length ? `<img loading="lazy" src="${thumb(s.photos[0], 420)}" alt="">` : `<div class="np">voice note only</div>`}
        <div><b>${esc(s.id)}</b> · ${esc(s.time_local.slice(11))}
          <small>${s.photos.length} photo(s) · ${s.memos.length} voice note(s) · ${s.lat != null ? "GPS" : "no GPS"}</small></div>
      </div>`).join("")}</div>`;
}

const thumb = (name, s) => URLS.thumb(state.day, name, s);
const item = (id) => (state.health.checklist || []).find((i) => i.id === id) || { id, label: id };
const isScope = (id) => (state.health.checklist || []).some((i) => i.needs === id);

/* -------------------------------------------------------------- result */
function tally(stops) {
  const t = { yes: 0, no: 0, unclear: 0, conflicts: 0, failed: 0 };
  for (const s of stops) {
    if (s.error) { t.failed++; continue; }
    t.conflicts += (s.conflicts || []).length;
    for (const it of state.health.checklist) {
      if (isScope(it.id)) continue;
      const a = (s.checklist[it.id] || {}).answer;
      if (a in t) t[a]++;
    }
  }
  return t;
}

function haversine(a, b) {
  const R = 6371000, r = Math.PI / 180;
  const dp = (b.lat - a.lat) * r, dl = (b.lon - a.lon) * r;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function renderResult(res) {
  const stops = res.stops;
  const t = tally(stops);
  const located = stops.filter((s) => s.lat != null);
  let km = 0;
  for (let i = 1; i < located.length; i++) km += haversine(located[i - 1], located[i]) / 1000;
  const stat = (v, l, cls = "") => `<div class="stat ${cls}"><b>${v}</b><span>${l}</span></div>`;
  const filters = [["all", "All stops"], ["yes", "Has a yes"], ["conflict", "Photo and voice disagree"],
    ["down", "Answers downgraded"], ["failed", "Not processed"]];
  return `
    <div class="stats">
      ${stat(stops.length, "stops")}
      ${located.length > 1 ? stat(km < 10 ? km.toFixed(1) : Math.round(km), "km between stops") : ""}
      ${stat(t.yes, "yes", "yes")}${stat(t.no, "no")}${stat(t.unclear, "unclear", "unc")}
      ${stat(t.conflicts, "disagreements", t.conflicts ? "unc" : "")}
      ${t.failed ? stat(t.failed, "not processed", "err") : ""}
    </div>
    <div class="map panel">${mapSvg(stops)}
      <div class="map-foot">
        <span><i style="background:var(--pin-glacial)"></i>glacial setting</span>
        <span><i style="background:var(--pin-not)"></i>not glacial</span>
        <span><i style="background:var(--pin-unclear)"></i>unclear</span>
        ${stops.length - located.length ? `<span>${stops.length - located.length} stop(s) without GPS are listed below but not on the map</span>` : ""}
      </div></div>
    <div class="filters" role="group" aria-label="Filter stops">
      ${filters.map(([k, l]) => `<button data-action="filter" data-filter="${k}" aria-pressed="${state.filter === k}">${l}</button>`).join("")}
    </div>
    <div class="stops">${stops.filter(keep).map(card).join("") || `<p class="nogps">No stops match this filter.</p>`}</div>`;
}

function keep(s) {
  switch (state.filter) {
    case "yes": return !s.error && state.health.checklist.some((i) => !isScope(i.id) && (s.checklist[i.id] || {}).answer === "yes");
    case "conflict": return (s.conflicts || []).length > 0;
    case "down": return (s.downgrades || []).length > 0;
    case "failed": return !!s.error;
    default: return true;
  }
}

function pinClass(s) {
  if (s.error) return "var(--err)";
  const a = (s.checklist && s.checklist.glacial_setting || {}).answer;
  return a === "yes" ? "var(--pin-glacial)" : a === "no" ? "var(--pin-not)" : "var(--pin-unclear)";
}

function niceStep(span, n) {
  const raw = span / n, p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
}

function mapSvg(stops) {
  const pts = stops.filter((s) => s.lat != null);
  if (!pts.length) return `<p class="nogps">No stop has a GPS position. Turn on location for the camera to see a map.</p>`;
  // Draw at the size it will be shown, so labels stay readable on a phone.
  const avail = Math.max(320, Math.min(900, (($("#main") || {}).clientWidth || 900) - 70));
  const W = Math.round(avail), H = Math.round(W < 600 ? W * 0.85 : 380), pad = W < 600 ? 34 : 46;
  const lat0 = pts.reduce((a, s) => a + s.lat, 0) / pts.length;
  const k = Math.cos(lat0 * Math.PI / 180);
  const minX = Math.min(...pts.map((s) => s.lon * k)), maxX = Math.max(...pts.map((s) => s.lon * k));
  const minY = Math.min(...pts.map((s) => s.lat)), maxY = Math.max(...pts.map((s) => s.lat));
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  // Fit every stop; never zoom in past ~2 km of ground across the frame.
  const MIN_SPAN_DEG = 0.02;
  const sc = Math.min((W - 2 * pad) / Math.max(maxX - minX, 1e-9),
                      (H - 2 * pad) / Math.max(maxY - minY, 1e-9),
                      (H - 2 * pad) / MIN_SPAN_DEG);
  const X = (lon) => W / 2 + (lon * k - cx) * sc;
  const Y = (lat) => H / 2 - (lat - cy) * sc;

  // graticule
  const latSpan = (H / sc), lonSpan = (W / sc) / k;
  const dLat = niceStep(latSpan, 4), dLon = niceStep(lonSpan, 5);
  const lat1 = cy - latSpan / 2, lon1 = (cx / k) - lonSpan / 2;
  const dec = (d) => Math.max(0, -Math.floor(Math.log10(d)));
  let grid = "";
  for (let la = Math.ceil(lat1 / dLat) * dLat; la < lat1 + latSpan; la += dLat)
    grid += `<line x1="0" x2="${W}" y1="${Y(la).toFixed(1)}" y2="${Y(la).toFixed(1)}"/><text x="4" y="${(Y(la) - 3).toFixed(1)}">${la.toFixed(dec(dLat))}°</text>`;
  for (let lo = Math.ceil(lon1 / dLon) * dLon; lo < lon1 + lonSpan; lo += dLon)
    grid += `<line y1="0" y2="${H}" x1="${X(lo).toFixed(1)}" x2="${X(lo).toFixed(1)}"/><text y="${H - 4}" x="${(X(lo) + 3).toFixed(1)}">${lo.toFixed(dec(dLon))}°</text>`;

  // scale bar: a round number of km close to a fifth of the width
  const kmPerPx = 111.32 / sc;
  const km = niceStep(kmPerPx * W / 5, 1);
  const px = km / kmPerPx;
  const label = km >= 1 ? `${km} km` : `${Math.round(km * 1000)} m`;

  const route = pts.map((s) => `${X(s.lon).toFixed(1)},${Y(s.lat).toFixed(1)}`).join(" ");
  // Stops a few hundred metres apart would hide each other's pins. Each pin
  // that lands on an earlier one steps outwards around a circle, and a thin
  // leader keeps a dot on its true position.
  const placed = [];
  const pins = pts.map((s) => {
    const tx = X(s.lon), ty = Y(s.lat);
    let px = tx, py = ty;
    for (let step = 0; placed.some(([x, y]) => Math.hypot(x - px, y - py) < 27) && step < 24; step++) {
      const ang = -Math.PI / 2 + step * (Math.PI / 4);
      const rad = 30 * (1 + Math.floor(step / 8));
      px = tx + rad * Math.cos(ang); py = ty + rad * Math.sin(ang);
    }
    placed.push([px, py]);
    const moved = px !== tx || py !== ty;
    return `<g class="pin ${state.selected === s.id ? "sel" : ""}" data-stop="${esc(s.id)}" tabindex="0" role="button" aria-label="Stop ${esc(s.id)}">
      ${moved ? `<line class="leader" x1="${tx.toFixed(1)}" y1="${ty.toFixed(1)}" x2="${px.toFixed(1)}" y2="${py.toFixed(1)}"/><circle class="dot" cx="${tx.toFixed(1)}" cy="${ty.toFixed(1)}" r="3"/>` : ""}
      <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="13" fill="${pinClass(s)}"/>
      <text x="${px.toFixed(1)}" y="${(py + 3.8).toFixed(1)}">${esc(s.id.replace(/^S0?/, ""))}</text>
    </g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of the day's stops">
    <g class="grid">${grid}</g>
    ${pts.length > 1 ? `<polyline class="route" points="${route}"/>` : ""}
    ${pins}
    <g class="scale"><line x1="${W - 24 - px}" x2="${W - 24}" y1="${H - 22}" y2="${H - 22}"/>
      <line x1="${W - 24 - px}" x2="${W - 24 - px}" y1="${H - 27}" y2="${H - 17}"/><line x1="${W - 24}" x2="${W - 24}" y1="${H - 27}" y2="${H - 17}"/>
      <text x="${W - 24 - px / 2}" y="${H - 30}" text-anchor="middle">${label}</text></g>
    <g class="north" transform="translate(${W - 30},28)"><path d="M0,-14 L6,6 L0,2 L-6,6 Z"/><text y="20" text-anchor="middle">N</text></g>
  </svg>`;
}

/** Shorten to the last whole word within n characters. */
function clip(text, n) {
  if (text.length <= n) return text;
  const cut = text.slice(0, n);
  return cut.slice(0, Math.max(cut.lastIndexOf(" "), n * 0.6)).replace(/[,.;:]$/, "") + "…";
}

function wireMap() {
  const tip = $("#tooltip");
  document.querySelectorAll(".pin").forEach((g) => {
    const s = state.data.result.stops.find((x) => x.id === g.dataset.stop);
    g.addEventListener("mouseenter", () => {
      tip.innerHTML = `${s.photos.length ? `<img src="${thumb(s.photos[0], 360)}" alt="">` : ""}
        <b>${esc(s.id)}</b> · ${esc(s.time_local.slice(11))}<br>${esc(clip(s.checklist && s.checklist.summary || s.error || "", 110))}`;
      tip.hidden = false;
    });
    g.addEventListener("mousemove", (e) => {
      tip.style.left = Math.min(e.clientX + 14, innerWidth - 210) + "px";
      tip.style.top = Math.min(e.clientY + 14, innerHeight - 220) + "px";
    });
    g.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

function card(s) {
  const day = state.day;
  const glacial = s.checklist && (s.checklist.glacial_setting || {}).answer === "yes";
  const media = s.photos.length
    ? `<img class="main" src="${thumb(s.photos[0], 640)}" alt="Photo from stop ${esc(s.id)}" data-action="zoom" data-photo="${esc(s.photos[0])}">
       ${s.photos.length > 1 ? `<div class="strip">${s.photos.slice(1).map((p) =>
         `<img loading="lazy" src="${thumb(p, 160)}" alt="" data-action="zoom" data-photo="${esc(p)}">`).join("")}</div>` : ""}`
    : `<div class="nophoto">No photo at this stop.<br>Observations come from the voice note.</div>`;
  const audio = s.memos.map((m) => `<audio controls preload="none" src="${URLS.audio(day, m.name)}" title="${esc(m.name)}"></audio>`).join("");
  const where = s.lat != null ? `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}${s.alt_m != null ? ` · ${Math.round(s.alt_m)} m` : ""}` : "no GPS";
  const conflicts = (s.conflicts || []).map((c) => c.item);
  const badges = [
    glacial ? `<span class="badge glacial">glacial setting</span>` : "",
    conflicts.length ? `<span class="badge conf">photo and voice disagree</span>` : "",
    s.error ? `<span class="badge err">not processed</span>` : "",
  ].join("");

  let body = "";
  if (s.error) {
    body = `<p class="err-text">Not processed: ${esc(s.error)}</p>`;
  } else {
    const row = (it) => {
      const a = s.checklist[it.id] || { answer: "unclear", evidence: "", source: "none" };
      const key = `${s.id}:${it.id}`;
      const open = state.open.has(key);
      const conflict = conflicts.includes(it.id);
      const ev = a.evidence ? `<em>${esc(a.evidence)}</em>${a.source && a.source !== "none" ? ` (${esc(a.source)})` : ""}` : "Not visible in the photo and not mentioned.";
      const gate = it.needs ? `<br>Judged from a photo only when “${esc(item(it.needs).label)}” is yes; your own words can always answer it.` : "";
      return `<div class="chip-row ${isScope(it.id) ? "scope" : ""}" role="button" tabindex="0" aria-expanded="${open}" data-action="toggle" data-key="${esc(key)}">
        <span class="lab">${esc(it.label)}${conflict ? ` <small>⚠ photo and voice disagree</small>` : ""}</span>
        <span class="chip ${esc(a.answer)}">${esc(a.answer)}</span>
        <span class="more">${ev}<br><small>${esc(it.source)}</small>${gate}</span>
      </div>`;
    };
    // Observations first; what could not be judged is folded into one line,
    // so a stop reads as what was seen rather than a wall of "unclear".
    const answer = (it) => (s.checklist[it.id] || {}).answer;
    const seen = state.health.checklist.filter((it) => answer(it) !== "unclear" || conflicts.includes(it.id));
    const notJudged = state.health.checklist.filter((it) => !seen.includes(it));
    const foldKey = `${s.id}:unclear`;
    const folded = notJudged.length ? `
      <div class="fold">
        <button class="fold-btn" data-action="fold" data-key="${esc(foldKey)}" aria-expanded="${state.open.has(foldKey)}">
          <span class="chip unclear">${notJudged.length} unclear</span>
          <span class="names">${esc(notJudged.map((it) => it.label).join(" · "))}</span></button>
        <div class="fold-body" ${state.open.has(foldKey) ? "" : "hidden"}>${notJudged.map(row).join("")}</div>
      </div>` : "";
    const down = (s.downgrades || []);
    body = `
      ${s.transcript ? `<blockquote class="quote">${esc(s.transcript)}</blockquote>` : ""}
      ${s.checklist.summary ? `<p class="summary">${esc(s.checklist.summary)}</p>` : ""}
      <div class="checks">${seen.map(row).join("") || `<p class="nogps">Nothing could be judged at this stop.</p>`}${folded}</div>
      ${down.length ? `<details class="down"><summary>${down.length} answer(s) from the model were not supported and were changed to unclear</summary>
        <ul>${down.map((x) => `<li>${esc(item(x.item).label)} (${esc(x.pass || "")}): the model said <b>${esc(x.model_answer ?? "nothing")}</b>; ${esc(x.reason)}</li>`).join("")}</ul></details>` : ""}`;
  }
  return `<article class="card panel ${state.selected === s.id ? "sel" : ""}" id="stop-${esc(s.id)}">
    <div class="media">${media}${audio}</div>
    <div class="body">
      <div class="top"><h3>${esc(s.id)}</h3><span class="meta">${esc(s.time_local)} · ${esc(where)}</span>${badges}</div>
      ${body}
    </div></article>`;
}

/* ----------------------------------------------------------- progress */
function renderProgress() {
  const el = $("#progress");
  if (!el || !state.events.length) { if (el) el.innerHTML = ""; return; }
  const plan = state.events.find((e) => e.type === "plan");
  const ids = plan ? plan.stops.map((s) => s.id) : [];
  const st = Object.fromEntries(ids.map((id) => [id, { state: "wait", text: "" }]));
  let total = ids.length, doneN = 0, finished = null, error = null;
  for (const e of state.events) {
    if (e.type === "stop") st[e.id] = { state: "now", text: "starting" };
    if (e.type === "step") st[e.id] = { state: "now", text: e.text };
    if (e.type === "stop_done") {
      doneN = e.index;
      st[e.id] = { state: e.error ? "err" : "done",
        text: e.error ? e.error : `${e.answered} answered${e.conflicts ? `, ${e.conflicts} disagreement(s)` : ""}` };
    }
    if (e.type === "done") finished = e;
    if (e.type === "error") error = e.text;
  }
  const pct = total ? Math.round(100 * doneN / total) : 0;
  const icon = { wait: "·", now: '<span class="spinner"></span>', done: "✓", err: "✕" };
  const last = state.events[state.events.length - 1];
  if (finished && state.data && state.data.result) {
    // Once the result is on screen, the per-stop list has done its job.
    const failed = Object.values(st).filter((x) => x.state === "err").length;
    el.innerHTML = `<div class="notice ${failed ? "err" : "done"}" role="status">✓ Processed ${total} stop(s) in ${finished.seconds} s on this computer${failed ? `; ${failed} could not be processed and are marked below` : ""}.</div>`;
    return;
  }
  el.innerHTML = `<section class="progress panel" aria-live="polite">
    <h3>${finished ? "Processed" : error ? "Stopped" : "Processing on this computer"}
      <span>${finished ? `${finished.seconds} s` : `${doneN} of ${total} stops · ${last ? last.t : 0} s`}</span></h3>
    <div class="meter"><i style="width:${finished ? 100 : pct}%"></i></div>
    ${error ? `<div class="notice err">${esc(error)}</div>` : ""}
    <ul class="plist">${ids.map((id) => `<li><span class="st ${st[id].state}">${icon[st[id].state]}</span>
      <b>${esc(id)}</b> <span class="txt ${st[id].state === "now" ? "now" : ""}">${esc(st[id].text)}</span></li>`).join("")}</ul>
  </section>`;
}

function startPolling() {
  if (state.poll) return;
  const day = state.day;
  const tick = async () => {
    try {
      const j = await api(`/api/days/${enc(day)}/job?since=${state.jobNext}`);
      if (state.day !== day) return stopPolling();
      state.events.push(...(j.events || []));
      state.jobNext = j.next ?? state.jobNext;
      renderProgress();
      if (j.status !== "running") {
        stopPolling();
        await loadDays();
        state.data = await api(URLS.day(day));
        renderDay();
        return;
      }
    } catch (e) { console.warn(e); }
    state.poll = setTimeout(tick, 700);
  };
  state.poll = setTimeout(tick, 100);
}

function stopPolling() { clearTimeout(state.poll); state.poll = null; }

async function process() {
  const model = $("#model").value, cpu = $("#cpu").checked;
  state.events = []; state.jobNext = 0;
  try {
    await api(`/api/days/${enc(state.day)}/process`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, cpu }) });
  } catch (e) { $("#progress").innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  startPolling();
  renderDay();
  loadDays();
}

/* -------------------------------------------------------------- upload */
function wireDrop() {
  let depth = 0;
  document.addEventListener("dragenter", (e) => { if (!state.day) return; depth++; e.preventDefault(); const d = $("#drop"); if (d) d.classList.add("over"); });
  document.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) { const d = $("#drop"); if (d) d.classList.remove("over"); } });
  document.addEventListener("dragover", (e) => { if (state.day) e.preventDefault(); });
  document.addEventListener("drop", (e) => {
    if (!state.day) return;
    e.preventDefault(); depth = 0;
    const d = $("#drop"); if (d) d.classList.remove("over");
    upload([...e.dataTransfer.files]);
  });
}

async function upload(files) {
  const ok = files.filter((f) => [...PHOTO_EXT, ...AUDIO_EXT].includes(ext(f.name)));
  const skipped = files.length - ok.length;
  const note = $("#upload-note");
  const day = state.day;
  let n = 0, failed = [];
  for (const f of ok) {
    note.innerHTML = `<div class="notice warn"><span class="spinner"></span> Adding ${++n} of ${ok.length}: ${esc(f.name)}</div>`;
    try {
      await api(`/api/days/${enc(day)}/files/${enc(f.name)}`, {
        method: "PUT", body: f, headers: { "X-Last-Modified": String(f.lastModified) } });
    } catch (e) { failed.push(`${f.name}: ${e.message}`); }
  }
  await loadDays();
  if (state.day === day) await openDay(day);
  const msg = [`Added ${ok.length - failed.length} file(s).`,
    skipped ? `${skipped} skipped (not a photo or voice note).` : "",
    failed.length ? `Failed: ${failed.join("; ")}` : ""].join(" ");
  $("#upload-note").innerHTML = `<div class="notice ${failed.length ? "err" : "warn"}">${esc(msg)}</div>`;
}

/* -------------------------------------------------------------- events */
async function onNewDay(e) {
  e.preventDefault();
  const name = $("#new-day-name").value.trim();
  try {
    await api("/api/days", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }) });
    $("#new-day").hidden = true;
    await loadDays();
    location.hash = `#/day/${enc(name)}`;
  } catch (err) { alertInline(err.message); }
}

function alertInline(text) {
  $("#new-day").insertAdjacentHTML("beforeend", `<div class="notice err">${esc(text)}</div>`);
}

function onClick(e) {
  const t = e.target.closest("[data-action],[data-stop]");
  if (!t) return;
  if (t.dataset.stop && !t.dataset.action) return selectStop(t.dataset.stop);
  switch (t.dataset.action) {
    case "home": e.preventDefault(); location.hash = ""; break;
    case "new-day": {
      const f = $("#new-day"); f.hidden = false;
      const inp = $("#new-day-name");
      inp.value = new Date().toISOString().slice(0, 10); inp.focus(); inp.select();
      break;
    }
    case "process": process(); break;
    case "filter": state.filter = t.dataset.filter; renderDay(); break;
    case "fold": {
      const k = t.dataset.key;
      state.open.has(k) ? state.open.delete(k) : state.open.add(k);
      t.setAttribute("aria-expanded", state.open.has(k));
      t.nextElementSibling.hidden = !state.open.has(k);
      break;
    }
    case "toggle": {
      const k = t.dataset.key;
      state.open.has(k) ? state.open.delete(k) : state.open.add(k);
      t.setAttribute("aria-expanded", state.open.has(k));
      break;
    }
    case "zoom": {
      const lb = $("#lightbox");
      $("img", lb).src = thumb(t.dataset.photo, 1600);
      $(".caption", lb).textContent = t.dataset.photo;
      lb.hidden = false;
      break;
    }
    case "close-lightbox": $("#lightbox").hidden = true; break;
  }
}

function onKey(e) {
  if (e.key === "Escape") $("#lightbox").hidden = true;
  if ((e.key === "Enter" || e.key === " ") && e.target.matches(".chip-row, .pin")) {
    e.preventDefault();
    e.target.matches(".pin") ? selectStop(e.target.dataset.stop) : e.target.click();
  }
}

function selectStop(id) {
  state.selected = id;
  if (state.filter !== "all" && !keep(state.data.result.stops.find((s) => s.id === id))) state.filter = "all";
  renderDay();
  const el = document.getElementById(`stop-${id}`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox") e.currentTarget.hidden = true; });
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.data && state.data.result) renderDay(); }, 250);
});
boot();
