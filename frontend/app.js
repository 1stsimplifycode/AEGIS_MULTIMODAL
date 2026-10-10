/* Did That Trade Really Happen? - investigation UI (desktop). Every number shown comes from the API; every stage shown was executed. */
"use strict";
const $app = document.getElementById("app");
const state = { health: null, samples: null, selected: null, results: {} };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
};
const PFA = { PASS: ["pass", "PASS", "constraint satisfied"], FAIL: ["fail", "FAIL", "contradiction shown"], ABSTAIN: ["abstain", "ABSTAIN", "no reliable conclusion"] };
const pfa = (v) => { const x = PFA[v] || ["abstain", v, ""]; return `<span class="pfa pfa-${x[0]}" title="${esc(x[2])}">${esc(x[1])}</span>`; };
const plainOf = (v) => ({ "Consistent with available records": "consistent", "Contradicted by available records": "contradicted",
  "Not enough evidence": "insufficient", "Not a checkable claim": "not_checkable" }[v] || (String(v).startsWith("Contradicted") ? "contradicted" :
  String(v).startsWith("Consistent") ? "consistent" : "other"));
const badge = (verdict) => `<span class="verdict v-${plainOf(verdict)}">${esc(verdict)}</span>`;
const TYPE = { QUOTE: "Current price", CALL: "Trading call", TARGET: "Price target / level", HISTORICAL: "Past price",
  PERSONAL_TRADE: "Claimed execution", HYPOTHETICAL: "Conditional", UNCLASSIFIED: "Unclear statement" };
const fmtP = (x, sym) => (x == null ? "–" : (String(sym || "").startsWith("^") ? `${Number(x).toLocaleString("en-IN", { maximumFractionDigits: 2 })} points`
  : `₹${Number(x).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`));
const mmss = (s) => { s = Math.max(0, Math.round(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const thumbURL = (res, name) => (name ? `/media/${esc(res.meta.id)}/frames/${esc(name)}` : "");

function setNav(key) { document.querySelectorAll("nav.main a").forEach((a) => a.setAttribute("aria-current", a.dataset.nav === key ? "page" : "false")); }
function render(html) { $app.innerHTML = html; $app.focus({ preventScroll: true }); window.scrollTo(0, 0); }

async function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [a, b, c, d] = h.split("/");
  try {
    if (!state.health) { state.health = await api("/api/health"); document.getElementById("version").textContent = "· " + state.health.version; }
    if (!a) return home();
    if (a === "check") return checkPage();
    if (a === "how") return howPage();
    if (a === "analysis") return progressPage(b);
    if (a === "result") return resultPage(b, c || "investigation", d ? decodeURIComponent(d) : null);
    home();
  } catch (e) { render(`<div class="error">Something went wrong: ${esc(e.message)}</div><p><a href="#/">Back to start</a></p>`); }
}
window.addEventListener("hashchange", route);

/* ============================================================ LANDING */
async function home() {
  setNav("home");
  if (!state.samples) state.samples = await api("/api/samples");
  const up = state.health.upload_enabled;
  render(`
  <h1>Did That Trade Really Happen?</h1>
  <p class="lead">Upload a stock-market video. See what was claimed, what the market records show, and what can actually be verified.</p>
  ${archSVG(null, true)}
  <div class="grid g2" style="margin-top:18px">
    <section class="card" aria-labelledby="pick">
      <h2 id="pick" style="margin-top:0">1. Choose a recorded video</h2>
      <p class="small muted">Short excerpts of real Indian business-TV broadcasts that we recorded ourselves, plus one clearly labelled set of made-up test claims.</p>
      <div class="grid" role="group" aria-label="Recorded videos">
        ${state.samples.map((x) => `
          <button class="sample" data-id="${esc(x.id)}" aria-pressed="false">
            ${x.thumbnail ? `<img src="/media/${esc(x.id)}/${esc(x.thumbnail)}" alt="">` : `<span class="ph novideo">No video<br>typed claims</span>`}
            <span><span class="tag ${x.synthetic ? "synthetic" : "real"}">${x.synthetic ? "Synthetic test claims" : "Real broadcast"}</span>
              <strong style="display:block;margin-top:6px">${esc(x.title)}</strong>
              <span class="small muted">${esc(x.channel_name || "")}${x.recorded_ist ? " · recorded " + esc(x.recorded_ist) : ""}${x.duration_s ? " · " + mmss(x.duration_s) + " min" : ""}</span>
              <span class="small" style="display:block;margin-top:4px">${esc(x.description || "")}</span></span>
          </button>`).join("")}
      </div>
      <p style="margin-top:16px"><button class="btn" id="start" disabled>Start investigation</button>
        <span id="pickhint" class="small muted" style="margin-left:8px">Select a video first.</span></p>
    </section>
    <section class="card" aria-labelledby="upl">
      <h2 id="upl" style="margin-top:0">…or analyse your own video</h2>
      ${up ? `<form id="upform" class="grid">
          <label>Video file (.mp4, .mkv, .webm, .mov)<input type="file" name="file" accept="video/*" required></label>
          <label>Recorded on (optional)<input type="date" name="recorded_date"></label>
          <label>Recording started at, IST (optional)<input type="time" name="recorded_time"></label>
          <p class="small muted">A date and time you type cannot be independently checked: results will say "user-supplied". If the video shows an index chart, the time is read from the chart instead.</p>
          <button class="btn" type="submit">Upload and investigate</button></form>`
        : `<div class="callout warn"><strong>Not available on this online demo.</strong> Analysing a new video means running speech recognition and text recognition on every frame, which this free server cannot do. Run the project on your own computer to analyse your own video (README).</div>`}
      <h2>Three checks, three possible answers</h2>
      <dl class="kv"><dt>${pfa("PASS")}</dt><dd>the tested rule was satisfied by the records. It never proves who traded, that the video is authentic, or compliance.</dd>
        <dt>${pfa("FAIL")}</dt><dd>a contradiction was shown, under assumptions that are listed.</dd>
        <dt>${pfa("ABSTAIN")}</dt><dd>something essential is missing, so no conclusion is given.</dd></dl>
      <ol class="small"><li><b>Fill conservation</b>: could the claimed number of shares really have been bought at that price and time?</li>
        <li><b>Knowability</b>: was the price someone "saw" actually visible in the market at that moment?</li>
        <li><b>Data age</b>: was the market data old enough for SEBI's 30-day educational rule, where that rule applies?</li></ol>
    </section>
  </div>
  <div class="callout" style="margin-top:20px"><strong>What this tool cannot do.</strong> Public market records show that a price traded, not who traded it. We use 1-minute price ranges for NSE instruments as published by a data vendor (Yahoo Finance) - not NSE's own trade-by-trade record. "ABSTAIN" is common and honest. Nothing here is an accusation.</div>`);
  const btn = document.getElementById("start");
  document.querySelectorAll(".sample").forEach((el) => el.addEventListener("click", () => {
    document.querySelectorAll(".sample").forEach((e) => e.setAttribute("aria-pressed", "false"));
    el.setAttribute("aria-pressed", "true"); state.selected = el.dataset.id; btn.disabled = false; document.getElementById("pickhint").textContent = "Ready.";
  }));
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const r = await api("/api/analyses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample_id: state.selected }) });
    location.hash = `#/analysis/${r.job_id}`;
  });
  const f = document.getElementById("upform");
  if (f) f.addEventListener("submit", async (ev) => {
    ev.preventDefault(); f.querySelector("button").disabled = true;
    try { const r = await api("/api/upload", { method: "POST", body: new FormData(f) }); location.hash = `#/analysis/${r.job_id}`; }
    catch (e) { f.insertAdjacentHTML("beforeend", `<div class="error">${esc(e.message)}</div>`); f.querySelector("button").disabled = false; }
  });
}

/* ============================================================ ARCHITECTURE DIAGRAM (shared by landing, progress, investigation) */
const NODES = [
  ["visual_frame", "Visual frame encoder", "chart ratchets → video-to-market time τ(t)", 20, 20],
  ["visual_text", "Visual text encoder", "on-screen fills, prices, names, clocks, P&L", 20, 110],
  ["audio", "Audio encoder", "spoken trades, prices, quantities, times", 20, 200],
  ["claim_set", "Claim set with market time", "who said / showed what, when", 300, 110],
  ["tape", "Anonymous exchange tape", "NSE 1-min price & volume", 300, 220],
  ["fill", "Fill conservation", "quantity vs traded volume", 580, 20],
  ["knowability", "Knowability", "was it observable then?", 580, 110],
  ["data_age", "Data age", "SEBI 30-day rule", 580, 200],
  ["certificate", "Impossibility certificate", "PASS / FAIL / ABSTAIN", 860, 110]];
function archSVG(stages, staticOnly, sel) {
  const W = 1080, H = 290, w = 220, h = 66;
  const pos = Object.fromEntries(NODES.map((n) => [n[0], n]));
  const edges = [["visual_frame", "claim_set"], ["visual_text", "claim_set"], ["audio", "claim_set"], ["claim_set", "fill"], ["claim_set", "knowability"],
    ["claim_set", "data_age"], ["tape", "fill"], ["tape", "knowability"], ["fill", "certificate"], ["knowability", "certificate"], ["data_age", "certificate"],
    ["visual_frame", "data_age"]];
  const line = ([a, b]) => { const A = pos[a], B = pos[b]; return `<path d="M${A[3] + w},${A[4] + h / 2} C${A[3] + w + 40},${A[4] + h / 2} ${B[3] - 40},${B[4] + h / 2} ${B[3]},${B[4] + h / 2}" class="edge"/>`; };
  const node = (n) => {
    const st = stages ? stages.find((s) => s.key === n[0]) : null;
    const status = st ? st.status : "idle";
    const verdict = st && st.verdict ? `<text x="${n[3] + w - 10}" y="${n[4] + 22}" text-anchor="end" class="nv nv-${st.verdict.toLowerCase()}">${st.verdict}</text>` : "";
    const stTxt = { pending: "waiting", running: "working…", done: "done", done_offline: "done earlier", not_available: "not available", idle: "" }[status] || status;
    return `<g class="node st-${status} ${sel === n[0] ? "sel" : ""}" ${staticOnly ? "" : `data-stage="${n[0]}" tabindex="0" role="button" aria-label="${esc(n[1])}: ${esc(stTxt)}"`}>
      <rect x="${n[3]}" y="${n[4]}" width="${w}" height="${h}" rx="9"/>
      <text x="${n[3] + 12}" y="${n[4] + 24}" class="nt">${esc(n[1])}</text>
      <text x="${n[3] + 12}" y="${n[4] + 44}" class="ns">${esc(n[2])}</text>
      ${stTxt ? `<text x="${n[3] + 12}" y="${n[4] + 60}" class="nst">${esc(stTxt)}${st && st.seconds != null ? " · " + st.seconds + " s" : ""}</text>` : ""}${verdict}</g>`;
  };
  return `<svg class="arch" viewBox="0 0 ${W} ${H}" role="img" aria-label="Architecture: three encoders feed a claim set with market time; with the exchange tape it feeds three parallel checks that produce an impossibility certificate">
    <defs><marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="ah"/></marker></defs>
    ${edges.map(line).join("")}${NODES.map(node).join("")}</svg>`;
}

/* ============================================================ PROGRESS */
async function progressPage(jid) {
  setNav("home");
  render(`<h1>Investigation in progress</h1><p class="lead" id="plabel"></p><div id="diag"></div>
    <ol class="stages card" id="stages" aria-label="Analysis steps"></ol>
    <p class="small muted">Statuses are real. Text and speech recognition of the recorded samples were run earlier on our computer (too heavy for the online server); their recorded time is shown inside each stage. Everything else runs now.</p><div id="perr"></div>`);
  const tick = async () => {
    let s;
    try { s = await api(`/api/analyses/${jid}`); } catch (e) { document.getElementById("perr").innerHTML = `<div class="error">${esc(e.message)} <a href="#/">Start again</a></div>`; return; }
    document.getElementById("plabel").textContent = s.label;
    document.getElementById("diag").innerHTML = archSVG(s.stages, true);
    document.getElementById("stages").innerHTML = s.stages.map((x) => {
      const st = { pending: "Waiting", running: "Working…", done: "Done", done_offline: "Done earlier", not_available: "Not available" }[x.status] || x.status;
      const cls = x.status === "done_offline" ? "done" : x.status;
      const icon = (x.status === "done" || x.status === "done_offline") ? "✓" : x.status === "not_available" ? "–" : "";
      return `<li class="${cls}"><span class="icon" aria-hidden="true">${icon}</span><span><strong>${esc(x.label)}</strong><br><span class="small muted">${esc(x.detail || "")}</span></span>
        <span class="small">${esc(st)}${x.seconds != null ? ` · ${x.seconds} s` : ""}</span></li>`;
    }).join("");
    if (s.status === "done") { setTimeout(() => (location.hash = `#/result/${jid}/investigation`), 900); return; }
    if (s.status === "error") { document.getElementById("perr").innerHTML = `<div class="error">The analysis failed: ${esc(s.error)}</div>`; return; }
    setTimeout(tick, 500);
  };
  tick();
}

/* ============================================================ RESULT SHELL */
async function getResult(jid) {
  if (!state.results[jid]) {
    const [res, st] = await Promise.all([api(`/api/analyses/${jid}/result`), api(`/api/analyses/${jid}`)]);
    res.__stages = st.stages; state.results[jid] = res;
  }
  return state.results[jid];
}
function stageList(res) {
  return res.__stages.map((s) => {
    const b = res.branches[s.key];
    return { ...s, verdict: b ? b.verdict : s.key === "certificate" ? null : null };
  });
}
function shell(res, jid, tab, inner) {
  const m = res.meta;
  return `<p class="small"><a href="#/">← Choose another video</a></p>
  <span class="tag ${m.synthetic ? "synthetic" : "real"}">${m.synthetic ? "Synthetic test claims (made up for testing)" : "Real broadcast recording"}</span>
  <h1 style="margin-top:8px">${esc(m.title)}</h1>
  <p class="muted small">${esc(m.channel_name || "")}${m.recorded_ist ? " · recorded " + esc(m.recorded_ist) : ""} · ${esc(m.source || "")}</p>
  <nav class="tabs" aria-label="Result sections">
    ${[["investigation", "Investigation flow"], ["claims", "Claims & traces"], ["timeline", "Video timeline"], ["certificate", "Impossibility certificate"]]
      .map(([k, l]) => `<a href="#/result/${jid}/${k}" ${tab === k ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>${inner}`;
}
async function resultPage(jid, tab, arg) {
  setNav("home");
  let res;
  try { res = await getResult(jid); } catch (e) {
    return render(`<div class="error">This result is no longer available (${esc(e.message)}). The server keeps results only while it is running.</div><p><a href="#/">Start again</a></p>`);
  }
  if (tab === "investigation") { render(shell(res, jid, tab, investigation(res, jid, arg))); return wireInvestigation(res, jid); }
  if (tab === "claims") return render(shell(res, jid, tab, claimsList(res, jid)));
  if (tab === "trace") return render(shell(res, jid, "claims", trace(res, jid, arg)));
  if (tab === "timeline") { render(shell(res, jid, tab, timelineView(res, jid))); return wireTimeline(res, jid, arg); }
  if (tab === "certificate") return render(shell(res, jid, tab, certView(res, jid)));
}

/* ============================================================ INVESTIGATION FLOW */
function investigation(res, jid, sel) {
  sel = sel || "certificate";
  const c = res.certificate;
  return `
  <div class="certbar">${c.checks.map((k) => `<div><span class="small muted">${esc(k.name)}</span><br>${pfa(k.verdict)}</div>`).join("")}
    <div class="small muted" style="align-self:center">Certificate <span class="mono">${esc(c.certificate_id)}</span> · click any box below to see what it received, did and produced</div></div>
  <div id="archwrap">${archSVG(stageList(res), false, sel)}</div>
  <section class="card" id="stagedetail">${stageDetail(res, jid, sel)}</section>`;
}
function wireInvestigation(res, jid) {
  const go = (k) => { history.replaceState(null, "", `#/result/${jid}/investigation/${k}`); document.getElementById("archwrap").innerHTML = archSVG(stageList(res), false, k);
    document.getElementById("stagedetail").innerHTML = stageDetail(res, jid, k); bind(); };
  const bind = () => document.querySelectorAll(".arch .node[data-stage]").forEach((n) => {
    n.addEventListener("click", () => go(n.dataset.stage));
    n.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(n.dataset.stage); } });
  });
  bind();
}
function itemsTable(res, jid, items) {
  if (!items.length) return `<p class="muted">No items.</p>`;
  return `<table class="cmp"><tr><th>Item</th><th>Verdict</th><th>Why</th><th></th></tr>${items.map((i) => `
    <tr><td>${esc(i.kind || i.source || "")}<br><span class="small muted">${esc(i.claim_id)}${i.value != null ? " · " + esc(i.value) : ""}</span></td><td>${pfa(i.verdict)}</td>
    <td class="small">${esc(i.reason || "")}${(i.assumptions || []).length ? `<br><span class="muted">Assumes: ${esc(i.assumptions.join("; "))}</span>` : ""}</td>
    <td>${i.claim_id && !String(i.claim_id).startsWith("screen") && i.claim_id !== "segment" ? `<a href="#/result/${jid}/trace/${encodeURIComponent(i.claim_id)}">Trace →</a>` : ""}</td></tr>`).join("")}</table>`;
}
function stageDetail(res, jid, key) {
  const S = res.stages[key];
  const st = res.__stages.find((s) => s.key === key) || {};
  const head = `<h2 style="margin-top:0">${esc((NODES.find((n) => n[0] === key) || [0, key])[1])}</h2>
    <dl class="kv"><dt>Input</dt><dd>${esc(S.input)}</dd><dt>Processing</dt><dd>${esc(S.processing)}</dd>
    <dt>Status</dt><dd>${esc({ done: "done (run now)", done_offline: "done earlier on our computer", not_available: "not available for this input" }[st.status] || st.status)}${st.seconds != null ? ` · ${st.seconds} s` : ""}</dd>
    <dt>Output</dt><dd><strong>${esc(S.output)}</strong></dd></dl><h3 class="evh">Evidence</h3>`;
  if (key === "visual_frame") {
    const vf = S.result || {}; const t = vf.tau || {};
    const frames = (vf.frames || []).filter((f) => f.price);
    const show = frames.filter((_, i) => i % Math.max(1, Math.floor(frames.length / 6)) === 0).slice(0, 6);
    return head + (t.status === "IDENTIFIED" ? `<p>The chart panel shows the index price, and its top axis label is the <b>day's high so far</b> (a "ratchet": it can only go up).
      Matching every frame's price and day-high against the exchange's 1-minute record, only <b>${esc(t.day)}</b> fits (${t.days_searched.length} trading days searched),
      and the video-to-market time offset is known to <b>±${Math.round(t.tau_radius)} s</b>. No clock or file metadata was used.</p>
      ${vf.agreement_with_capture_clock ? `<p class="small">Independent check: our own recording clock says this aired at ${esc(vf.agreement_with_capture_clock.capture_air_time)};
      the chart says the data shown is from ${esc(vf.agreement_with_capture_clock.market_time_from_ratchets)} — the channel shows market data about
      <b>${esc(vf.agreement_with_capture_clock.air_minus_market_s)} s late</b>, which is normal broadcast delay.</p>` : ""}`
      : `<div class="callout warn"><b>Ratchet extraction was not possible:</b> ${esc(t.reason || "")}. The claim set therefore uses ${res.claim_set[0] ? esc(res.claim_set[0].time_source) : "no time source"} — shown on every claim.</div>`)
      + (vf.ratchet_events && vf.ratchet_events.length ? `<p class="small">Day-high extensions seen: ${vf.ratchet_events.map((e) => `${mmss(e.t_media - res.meta.clip[0])} ${esc(e.symbol)} ${e.from}→${e.to}`).join("; ")}</p>`
        : `<p class="small muted">No day-high extension happened during this excerpt; the day-high value itself (a ratchet state) still constrains the time.</p>`)
      + `<div class="frames">${show.map((f) => `<figure><img src="${thumbURL(res, f.thumb)}" alt="video frame at ${mmss(f.t_media - res.meta.clip[0])}">
        <figcaption class="small"><b>${mmss(f.t_media - res.meta.clip[0])}</b> · ${esc(f.name_text)} price ${esc(f.price)}${f.axis_top ? ` · day-high label ${esc(f.axis_top)}` : ""}${f.axis_bottom ? ` · prev close ${esc(f.axis_bottom)}` : ""}${f.screen_clock ? ` · clock ${esc(f.screen_clock)}` : ""}</figcaption></figure>`).join("")}</div>`;
  }
  if (key === "visual_text") {
    const vt = S.result; if (!vt) return head + `<p class="muted">No frames.</p>`;
    const ck = vt.screen_clock_frames.slice(0, 3);
    return head + `<p>${esc(vt.summary)}.</p><ul class="small"><li>Trading-panel frames: ${vt.trading_panel_frames.length}</li><li>Fill quantities read: ${vt.quantity_frames.length}</li>
      <li>P&L figures read: ${vt.pnl_frames.length}</li><li>On-screen clock readings: ${vt.screen_clock_frames.length}</li><li>Name–price pairs: ${vt.n_name_price_pairs}</li></ul>
      <div class="frames">${ck.map((c) => `<figure><img src="${thumbURL(res, c.thumb)}" alt=""><figcaption class="small">${mmss(c.t_media - res.meta.clip[0])} · on-screen clock ${esc(c.clock)}</figcaption></figure>`).join("")}</div>`;
  }
  if (key === "audio") {
    return head + `<div class="transcript" style="max-height:300px">${res.sentences.map((s) => `<button onclick="location.hash='#/result/${jid}/timeline'"><span class="t">${mmss(s.start - res.meta.clip[0])}</span>${esc(s.text)}</button>`).join("") || "<p class='muted' style='padding:8px'>No speech.</p>"}</div>`;
  }
  if (key === "claim_set") {
    return head + `<table class="cmp"><tr><th>Who</th><th>What</th><th>Kind</th><th>Market time</th><th></th></tr>${res.claim_set.map((c) => `
      <tr><td class="small">${esc(c.who)}</td><td class="small">${esc(c.what)}</td><td class="small">${esc(c.kind)}${c.quantity ? `<br>qty ${Number(c.quantity).toLocaleString("en-IN")}` : ""}</td>
      <td class="small">${esc(c.market_time || "–")}<br><span class="muted">${esc(c.time_source)}${c.uncertainty_s != null ? ` ±${Math.round(c.uncertainty_s)} s` : ""}</span></td>
      <td><a href="#/result/${jid}/trace/${encodeURIComponent(c.id)}">Trace →</a></td></tr>`).join("")}</table>`;
  }
  if (key === "tape") {
    const t = S.result; return head + `<dl class="kv small">${Object.entries(t.files).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">sha256 ${esc(v)}</dd>`).join("")}
      <dt>Instruments used</dt><dd>${esc(t.symbols.join(", ") || "–")}</dd><dt>Resolution</dt><dd>1 minute: lowest/highest price and NSE volume per minute. Not individual trades. Anonymous: no names of buyers or sellers.</dd></dl>`;
  }
  if (["fill", "knowability", "data_age"].includes(key)) {
    const b = res.branches[key];
    return head + `<p>Branch verdict: ${pfa(b.verdict)} <span class="small muted">${esc((PFA[b.verdict] || [])[2] || "")}</span></p>${b.note ? `<div class="callout">${esc(b.note)}</div>` : ""}
      ${key === "data_age" && b.items[0] ? `<dl class="kv small">${Object.entries(b.items[0].facts || {}).map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(v ?? "unknown")}</dd>`).join("")}
        <dt>rule</dt><dd>${esc(b.rule || "")} (<a href="${esc(b.source_url)}" target="_blank" rel="noopener">source</a>)</dd></dl>` : ""}${itemsTable(res, jid, b.items)}`;
  }
  if (key === "certificate") {
    return head + certSummary(res, jid);
  }
  return head;
}
function certSummary(res, jid) {
  const c = res.certificate;
  return `<table class="cmp"><tr><th>Check</th><th>Question</th><th>Verdict</th><th>Items</th></tr>${c.checks.map((k) => `<tr><td><b>${esc(k.name)}</b></td><td class="small">${esc(k.question)}</td>
    <td>${pfa(k.verdict)}</td><td class="small">${k.items.length ? ["PASS", "FAIL", "ABSTAIN"].map((v) => `${v} ${k.items.filter((i) => i.verdict === v).length}`).join(" · ") : esc(k.note || "none")}</td></tr>`).join("")}</table>
    <p class="small">${Object.entries(c.verdict_meanings).map(([k, v]) => `${pfa(k)} ${esc(v)}`).join("<br>")}</p>
    <p><a href="#/result/${jid}/certificate">Open the full certificate →</a></p>`;
}

/* ============================================================ CLAIMS & TRACE */
function claimsList(res, jid) {
  const rows = res.claim_set.map((c) => {
    const r = res.claims.find((x) => x.claim.id === c.id);
    const its = Object.values(res.branches).flatMap((b) => b.items.filter((i) => i.claim_id === c.id).map((i) => ({ b: b.name, v: i.verdict })));
    return `<a class="claimrow" href="#/result/${jid}/trace/${encodeURIComponent(c.id)}"><span class="small muted">${c.t_media != null ? mmss(c.t_media - res.meta.clip[0]) : "typed"}<br>${esc(c.kind)}</span>
      <span><span class="quote">“${esc(c.what)}”</span><br><span class="small muted">${esc(r ? r.finding : "")}</span></span>
      <span>${its.length ? its.map((x) => `<span class="small muted">${esc(x.b)}</span> ${pfa(x.v)}`).join("<br>") : `<span class="small muted">not a claim to test</span>`}</span></a>`;
  });
  return `<p>Every claim in the claim set. Click one to trace its verdict back to the video frame, the words and the market minutes.</p><div class="grid">${rows.join("") || "<p class='muted'>No claims.</p>"}</div>`;
}
function trace(res, jid, cid) {
  const r = res.claims.find((x) => x.claim.id === cid);
  const c = res.claim_set.find((x) => x.id === cid);
  if (!r || !c) return `<p>Claim not found.</p>`;
  const its = Object.values(res.branches).flatMap((b) => b.items.filter((i) => i.claim_id === cid).map((i) => ({ ...i, branch: b.name })));
  const sent = res.sentences.find((s) => s.id === r.claim.sentence_id);
  const fr = r.frame;
  return `<p class="small"><a href="#/result/${jid}/claims">← All claims</a>${r.claim.t_media != null ? ` · <a href="#/result/${jid}/timeline/${encodeURIComponent(cid)}">Play this moment</a>` : ""}</p>
  <h2 style="margin-top:0">Trace of one claim, from certificate back to the evidence</h2>
  <ol class="tracechain">
   <li><h3>1 · Certificate</h3>${its.length ? its.map((i) => `<p><b>${esc(i.branch)}</b> ${pfa(i.verdict)} — ${esc(i.reason || "")}</p>${(i.assumptions || []).length ? `<p class="small muted">Assumptions: ${esc(i.assumptions.join("; "))}</p>` : ""}`).join("")
      : `<p class="muted">This statement is not tested by any check (${esc(c.kind)}): ${esc(r.finding)}</p>`}</li>
   <li><h3>2 · Claim set entry</h3><dl class="kv small"><dt>Who</dt><dd>${esc(c.who)}</dd><dt>What</dt><dd>“${esc(c.what)}”</dd><dt>Kind</dt><dd>${esc(c.kind)}</dd>
      <dt>Stock / index</dt><dd>“${esc(c.instrument_span || "")}” → ${(c.candidates || []).map((s) => `${esc((r.instrument_names || {})[s] || s)} (${esc(s)})`).join(", ") || "none"}</dd>
      <dt>Number</dt><dd>${esc(c.number)}${c.quantity ? ` · quantity ${Number(c.quantity).toLocaleString("en-IN")}` : ""}</dd>
      <dt>Market time</dt><dd>${esc(c.market_time || "–")} <span class="muted">(${esc(c.time_source)}${c.uncertainty_s != null ? `, ±${Math.round(c.uncertainty_s)} s` : ""})</span></dd></dl></li>
   <li><h3>3 · Encoders</h3><div class="grid g2">
      <div><b>Audio encoder</b><br>${sent ? `<p class="quote">“${esc(sent.text)}”</p><p class="small muted">Spoken at ${mmss(sent.start - res.meta.clip[0])} of the excerpt${r.claim.asr_word_conf != null ? ` · recognition confidence of the number ${Math.round(r.claim.asr_word_conf * 100)} %` : ""}</p>` : `<p class="muted small">${c.source === "typed" ? "Typed claim: no audio." : "–"}</p>`}</div>
      <div><b>Visual encoders</b><br>${fr && fr.thumb ? `<img class="tframe" src="${thumbURL(res, fr.thumb)}" alt="video frame at the moment of the claim"><p class="small muted">Frame at ${mmss(fr.t_media - res.meta.clip[0])}${res.tau && res.tau.status === "IDENTIFIED" ? ` · its market time comes from the chart's ratchet (τ ±${Math.round(res.tau.tau_radius)} s)` : ""}</p>` : `<p class="muted small">No video frame for this claim.</p>`}</div></div></li>
   <li><h3>4 · Exchange tape</h3>${comparisonTable(r)}${chartSVG(r)}${certTable(r)}</li></ol>`;
}
function certTable(r) {
  const bars = (r.quantity && r.quantity.certificate && r.quantity.certificate.length ? r.quantity.certificate : r.certificate) || [];
  if (!bars.length) return "";
  const sym = r.instrument || r.context_symbol;
  return `<table class="cmp" style="margin-top:10px"><tr><th>Deciding minute</th><th>Traded range</th><th>NSE volume</th><th>Source</th></tr>${bars.map((b) => `<tr><td class="mono">${esc(b.time_ist)} IST</td>
    <td class="mono">${fmtP(b.low, sym)} – ${fmtP(b.high, sym)}</td><td class="mono">${b.volume != null && !String(sym).startsWith("^") ? Number(b.volume).toLocaleString("en-IN") : "–"}</td><td class="small">NSE 1-min</td></tr>`).join("")}</table>`;
}
function comparisonTable(r) {
  const c = r.claim, sym = r.instrument || r.context_symbol || (c.candidates || [])[0];
  const p0 = (r.per_instrument || {})[sym] || {};
  return `<table class="cmp"><tr><th></th><th>${c.source === "typed" ? "What was claimed" : "What the video claimed"}</th><th>What the exchange record shows</th></tr>
    <tr><td>Price</td><td>${fmtP(c.value, sym)} <span class="small muted">(${esc(c.tolerance_why || "")})</span></td>
      <td>${p0.day_range ? `Day range ${fmtP(p0.day_range[0], sym)} – ${fmtP(p0.day_range[1], sym)}` : "–"}${p0.coverage != null ? `<br><span class="small muted">${Math.round(p0.coverage * 100)} % of minutes in the checked window have data</span>` : ""}</td></tr>
    <tr><td>Quantity</td><td>${c.quantity ? Number(c.quantity).toLocaleString("en-IN") + " shares" : "not stated"}</td><td>${r.quantity ? esc(r.quantity.finding) : c.quantity ? "–" : "not applicable"}</td></tr>
    <tr><td>Time</td><td>${r.t_air_ist ? esc(r.t_air_ist) : esc(c.stated_time_text || r.day || "not stated")}</td><td>${r.window ? `Checked ${esc(r.window[0].slice(11, 16))}–${esc(r.window[1].slice(11, 16))} IST on ${esc(r.day)}` : esc(r.day_status || "–")}</td></tr>
    <tr><td>Who traded</td><td>${c.type === "PERSONAL_TRADE" ? "the speaker, as claimed" : "no trade claimed"}</td><td>The exchange record is anonymous: it cannot show who traded.</td></tr></table>
    <p style="margin-top:10px">${badge(r.verdict)} ${esc(r.finding)}</p><p class="small">${esc(r.why || "")}</p>
    ${r.timing ? `<p class="small"><b>Timing:</b> ${esc(r.timing.finding)}</p>` : ""}${r.outcome_after ? `<p class="small"><b>Afterwards (information only, not cause and effect):</b> ${esc(r.outcome_after.finding)}</p>` : ""}`;
}
function chartSVG(r) {
  const bars = r.context_bars || [];
  if (!bars.length) return "";
  const sym = r.context_symbol, P = r.claim.value, W = 900, H = 230, pl = 70, pr = 12, pt = 14, pb = 28;
  const tolv = r.claim.inequality ? 0 : Number(r.claim.tolerance || 0);
  const lo = Math.min(P - tolv, ...bars.map((b) => b.low)), hi = Math.max(P + tolv, ...bars.map((b) => b.high));
  const pad = (hi - lo) * 0.08 || 1;
  const y = (v) => pt + (H - pt - pb) * (1 - (v - (lo - pad)) / ((hi + pad) - (lo - pad)));
  const t0 = bars[0].t, t1 = bars[bars.length - 1].t + 60, x = (t) => pl + (W - pl - pr) * ((t - t0) / (t1 - t0));
  const toEpoch = (s) => { const m = (s || "").match(/(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})/); return m ? Date.parse(`${m[1]}T${m[2]}:${m[3]}:${m[4]}+05:30`) / 1000 : null; };
  let win = "";
  if (r.window) { const a = toEpoch(r.window[0]), b = toEpoch(r.window[1]); if (a && b) win = `<rect x="${Math.max(pl, x(a))}" y="${pt}" width="${Math.max(0, Math.min(W - pr, x(b)) - Math.max(pl, x(a)))}" height="${H - pt - pb}" fill="var(--accent)" opacity=".10"/>`; }
  const band = r.claim.inequality ? "" : (tolv > 0 ? `<rect x="${pl}" y="${y(P + tolv)}" width="${W - pl - pr}" height="${Math.max(1, y(P - tolv) - y(P + tolv))}" fill="var(--bad)" opacity=".10"/>` : "");
  const cw = Math.max(1.5, (W - pl - pr) / bars.length * 0.6);
  const candles = bars.map((b) => `<rect x="${x(b.t + 30) - cw / 2}" y="${y(b.high)}" width="${cw}" height="${Math.max(1, y(b.low) - y(b.high))}" fill="var(--ink-2)"><title>${b.time_ist} IST: ${fmtP(b.low, sym)} – ${fmtP(b.high, sym)}</title></rect>`).join("");
  const said = r.t_air_epoch ? `<line x1="${x(r.t_air_epoch)}" x2="${x(r.t_air_epoch)}" y1="${pt}" y2="${H - pb}" stroke="var(--accent)" stroke-width="2"/><text x="${x(r.t_air_epoch) + 4}" y="${pt + 10}">said</text>` : "";
  const ticks = [lo, (lo + hi) / 2, hi].map((v) => `<text x="4" y="${y(v) + 4}">${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</text>`).join("");
  return `<figure style="margin:10px 0 0"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="1-minute price ranges around the claim">${win}${band}${candles}
    <line x1="${pl}" x2="${W - pr}" y1="${y(P)}" y2="${y(P)}" stroke="var(--bad)" stroke-dasharray="6 4" stroke-width="2"/>
    <rect x="${pl + 2}" y="${y(P) - 17}" width="122" height="15" fill="var(--surface)" opacity=".85"/><text x="${pl + 6}" y="${y(P) - 5}">claimed ${Number(P).toLocaleString("en-IN")}</text>${said}${ticks}
    <text x="${pl}" y="${H - 8}">${esc(bars[0].time_ist)} IST</text><text x="${W - pr}" y="${H - 8}" text-anchor="end">${esc(bars[bars.length - 1].time_ist)} IST</text></svg>
    <figcaption class="small muted">Grey bars: lowest-to-highest value in each minute (NSE prices, 1-minute data via Yahoo Finance; for an index this is the index level, not a trade). Dashed red line: the claimed price; light red band: what a spoken round number can mean. Shaded: the time window the claim can refer to. Blue line: when it was said (in market time).</figcaption></figure>`;
}

/* ============================================================ TIMELINE */
function timelineView(res, jid) {
  const m = res.meta;
  if (!m.media) return `<p class="muted">No video is attached to this result (typed or synthetic claims).</p>`;
  return `<p>Play the video, or click any marker to jump there. Circles: spoken claims. Squares: prices read from the on-screen ticker. Diamonds: the chart's day-high going up (ratchet).
     Colours show the finding. No arrows of cause and effect are drawn: timing alone does not show causation.</p>
  <div class="legend"><span class="l-c">PASS / consistent</span><span class="l-x">FAIL / contradicted</span><span class="l-i">ABSTAIN / not enough evidence</span><span class="l-n">not tested</span></div>
  <div class="track" id="track" aria-label="Evidence timeline"></div>
  <p class="small muted">Market time: ${esc(res.claim_set[0] ? res.claim_set[0].time_source : "-")}${res.tau && res.tau.status === "IDENTIFIED" ? ` (±${Math.round(res.tau.tau_radius)} s)` : ""}.</p>
  <div class="player"><div>${m.media_available === false
    ? `<div class="callout warn">The video excerpt is not included in this deployment (broadcast rights). All findings below are unaffected.</div><video id="vid" hidden></video>`
    : `<video id="vid" controls preload="metadata" poster="/media/${esc(m.id)}/${esc(m.media.poster)}" src="/media/${esc(m.id)}/${esc(m.media.video)}"></video>`}
    <div id="evinfo" class="card flat" style="margin-top:12px"><span class="muted">Select a marker to see what it is.</span></div></div>
    <div><h3>Transcript (speech recognition)</h3><div class="transcript" id="tx"></div></div></div>`;
}
function wireTimeline(res, jid, cid) {
  const m = res.meta; if (!m.media) return;
  const off = m.media.offset_s, dur = m.duration_s, v = document.getElementById("vid"), track = document.getElementById("track");
  const lanes = { speech: 24, screen: 54, ratchet: 82 };
  track.style.height = "104px";
  track.innerHTML = Object.entries(lanes).map(([k, yv]) => `<div class="lane" style="top:${yv}px"></div><div class="lane-label" style="top:${yv}px">${{ speech: "Speech", screen: "On-screen ticker", ratchet: "Chart day-high" }[k]}</div>`).join("") + `<div class="playhead" id="ph"></div>`;
  const evs = res.timeline;
  if (!evs.some((e) => e.kind === "screen")) {
    const why = (res.screen.find((s) => s.unusable_reason) || {}).unusable_reason;
    track.insertAdjacentHTML("beforeend", `<div class="small muted" style="position:absolute;left:140px;top:${lanes.screen - 9}px">${res.screen.length ? `Ticker readings not used here (${esc(why || "not reliable enough")}).` : "No ticker prices read."}</div>`);
  }
  if (!evs.some((e) => e.kind === "ratchet")) track.insertAdjacentHTML("beforeend", `<div class="small muted" style="position:absolute;left:140px;top:${lanes.ratchet - 9}px">No day-high extension in this excerpt${res.tau && res.tau.status === "IDENTIFIED" ? " (the day-high level itself was still used to set market time)" : ""}.</div>`);
  const col = (e) => (e.kind === "ratchet" ? "ratchet" : e.plain);
  evs.forEach((e, i) => {
    const b = document.createElement("button");
    b.className = `ev ${e.kind} c-${col(e)}`; b.style.left = `${(100 * (e.t_media - off)) / dur}%`; b.style.top = `${lanes[e.kind]}px`;
    b.title = `${mmss(e.t_media - off)}${e.t_air_ist ? " (market time " + e.t_air_ist + ")" : ""}: ${e.label}`;
    b.setAttribute("aria-label", `${e.kind} at ${mmss(e.t_media - off)}: ${e.label}`);
    b.addEventListener("click", () => select(i, true));
    track.appendChild(b);
  });
  const tx = document.getElementById("tx");
  tx.innerHTML = res.sentences.map((s) => `<button data-t="${s.start}"><span class="t">${mmss(s.start - off)}</span>${esc(s.text)}</button>`).join("");
  tx.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { v.currentTime = Math.max(0, b.dataset.t - off); if (!v.hidden) v.play(); }));
  function select(i, seek) {
    track.querySelectorAll(".ev").forEach((x, k) => x.classList.toggle("sel", k === i));
    const e = evs[i]; if (seek) v.currentTime = Math.max(0, e.t_media - off - 1);
    const info = document.getElementById("evinfo");
    if (e.kind === "speech") {
      const r = res.claims.find((x) => x.claim.id === e.claim_id);
      info.innerHTML = `<p class="small muted">Spoken at ${mmss(e.t_media - off)} · market time ${esc(e.t_air_ist || "?")}</p><p class="quote">“${esc(r.claim.sentence)}”</p>
        <p>${badge(r.verdict)} ${esc(r.finding)}</p><p><a href="#/result/${jid}/trace/${encodeURIComponent(r.claim.id)}">Trace this claim →</a></p>`;
    } else if (e.kind === "ratchet") {
      info.innerHTML = `<p class="small muted">${mmss(e.t_media - off)}</p><p><b>${esc(e.label)}</b></p>${e.thumb ? `<img class="tframe" src="${thumbURL(res, e.thumb)}" alt="">` : ""}`;
    } else {
      info.innerHTML = `<p class="small muted">Shown on screen at ${mmss(e.t_media - off)} · market time ${esc(e.t_air_ist || "?")}</p><p><strong>${esc(e.label)}</strong> → ${esc(e.symbol)}</p>`;
    }
  }
  const ph = document.getElementById("ph");
  v.addEventListener("timeupdate", () => {
    const t = v.currentTime + off; ph.style.left = `${(100 * v.currentTime) / dur}%`;
    let cur = null;
    tx.querySelectorAll("button").forEach((b) => { if (Number(b.dataset.t) <= t + 0.2) cur = b; b.classList.remove("now"); });
    if (cur) { cur.classList.add("now"); const top = cur.offsetTop - tx.offsetTop; if (top < tx.scrollTop || top + cur.offsetHeight > tx.scrollTop + tx.clientHeight) tx.scrollTop = Math.max(0, top - 40); }
  });
  if (cid) { const i = evs.findIndex((e) => e.claim_id === cid); if (i >= 0) select(i, true); }
}

/* ============================================================ CERTIFICATE */
function certView(res, jid) {
  const c = res.certificate, t = c.time_mapping || {};
  return `<p><a class="btn secondary" href="/api/analyses/${jid}/report.html" download>Download certificate (HTML)</a>
     <a class="btn secondary" href="/api/analyses/${jid}/report.json" download>Download certificate (JSON)</a></p>
  <div class="card flat"><h2 style="margin-top:0">Final Impossibility Certificate <span class="mono">${esc(c.certificate_id)}</span></h2>
    <dl class="kv"><dt>Video</dt><dd>${esc(c.video.title)} · ${esc(c.video.source)}</dd><dt>Excerpt</dt><dd>video seconds ${esc(c.video.clip[0])}–${esc(c.video.clip[1])}</dd>
      <dt>Video→market time</dt><dd>${t.status === "IDENTIFIED" ? `identified from chart ratchets: ${esc(t.day)}, ±${Math.round(t.tau_radius)} s (${esc(t.method)})` : `not identified from the video: ${esc(t.reason || "")}`}</dd>
      <dt>Algorithm</dt><dd>${esc(c.algorithm_version)} · generated ${esc(c.generated_utc)}</dd></dl>
    ${certSummary(res, jid).replace(/<p><a href="#\/result\/[^"]+\/certificate">Open the full certificate →<\/a><\/p>/, "")}
    ${c.checks.map((k) => `<h3 style="margin-top:18px">${esc(k.name)} ${pfa(k.verdict)}</h3>${k.note ? `<p class="small">${esc(k.note)}</p>` : ""}${itemsTable(res, jid, k.items)}`).join("")}
    <h3 style="margin-top:18px">Sources</h3><dl class="kv small">${Object.entries(c.sources.files).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v)}</dd>`).join("")}
      <dt>granularity</dt><dd>${esc(c.sources.granularity)}</dd><dt>provider</dt><dd>${esc(c.sources.provider)}</dd></dl>
    <h3>Reproduce</h3><ol class="small mono">${c.reproduce.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    <div class="callout"><b>${esc(c.disclaimer)}</b></div></div>`;
}

/* ============================================================ CHECK A CLAIM YOURSELF */
function checkPage() {
  setNav("check");
  render(`<h1>Check a claim yourself</h1>
  <p class="lead">Type a claimed trade, e.g. "I bought 1,800 shares of ITC at ₹265.50 at 10:31 on 6 October 2026". It runs the Fill-conservation check against NSE 1-minute records (29 Sep – 8 Oct 2026).</p>
  <div class="callout warn" style="margin-bottom:16px">Whatever the result, this cannot show that a particular person made the trade.</div>
  <form class="claim card" id="cf">
    <label>Stock (name or NSE symbol)<input name="instrument" required value="ITC" autocomplete="off"></label>
    <label>Action<select name="action"><option>bought</option><option>sold</option></select></label>
    <label>Price (₹)<input name="price" type="number" step="0.05" min="0.05" required value="265.50"></label>
    <label>Quantity (shares)<input name="quantity" type="number" min="1" step="1" value="1800"></label>
    <label>Date<input name="date" type="date" required value="2026-10-06" min="2026-09-10" max="2026-10-08"></label>
    <label>Time, IST (optional)<input name="time" type="time" value="10:31"></label>
    <button class="btn" type="submit">Check this claim</button></form>
  <p class="small muted" style="margin-top:14px">Or load a made-up test case (synthetic):</p><div class="examples" id="ex"></div><div id="cres"></div>`);
  const ex = [
    ["Market holiday (2 Oct)", { instrument: "Reliance", action: "bought", price: 1180, quantity: 100, date: "2026-10-02", time: "11:00" }],
    ["Huge quantity", { instrument: "Grasim", action: "bought", price: 2955.5, quantity: 5000000, date: "2026-10-06", time: "14:20" }],
    ["Price far away", { instrument: "TCS", action: "sold", price: 9999, quantity: 10, date: "2026-10-06", time: "11:15" }],
    ["Ambiguous name", { instrument: "HDFC", action: "bought", price: 712.7, quantity: 100, date: "2026-10-06", time: "13:00" }],
    ["No time given", { instrument: "Infosys", action: "bought", price: 1030, quantity: 100, date: "2026-10-05", time: "" }]];
  const f = document.getElementById("cf");
  document.getElementById("ex").innerHTML = ex.map(([l], i) => `<button type="button" data-i="${i}">${esc(l)}</button>`).join("");
  document.querySelectorAll("#ex button").forEach((b) => b.addEventListener("click", () => { Object.entries(ex[b.dataset.i][1]).forEach(([k, val]) => { if (f.elements[k]) f.elements[k].value = val; }); f.requestSubmit(); }));
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = Object.fromEntries(new FormData(f));
    const body = { instrument: fd.instrument, action: fd.action, price: Number(fd.price), date: fd.date, time: fd.time || null, quantity: fd.quantity ? Number(fd.quantity) : null };
    const out = document.getElementById("cres"); out.innerHTML = `<p class="muted">Checking…</p>`;
    try {
      const r = await api("/api/check-claim", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      r.claim.source = "typed"; r.claim.stated_time_text = fd.time ? `${fd.date} ${fd.time} IST (as typed)` : `${fd.date} (no time)`;
      const fb = r.fill_branch;
      out.innerHTML = `<h2>Fill conservation: ${pfa(fb.verdict)}</h2><p class="small">${esc(fb.meaning[fb.verdict])}</p>${fb.note ? `<p class="small">${esc(fb.note)}</p>` : ""}
        ${fb.item ? `<p>${esc(fb.item.reason || "")}</p><p class="small muted">Assumes: ${esc((fb.item.assumptions || []).join("; "))}</p>` : ""}
        <p>${r.identity ? `<b>Who traded:</b> ${esc(r.identity.verdict)} — ${esc(r.identity.finding)}` : ""}</p>
        <h3>Claim vs exchange record</h3>${comparisonTable(r)}${chartSVG(r)}${certTable(r)}`;
    } catch (e) { out.innerHTML = `<div class="error">${esc(e.message)}</div>`; }
  });
}

/* ============================================================ HOW IT WORKS */
async function howPage() {
  setNav("how");
  const reg = await api("/api/regulation");
  render(`<h1>How it works, and what it cannot do</h1>${archSVG(null, true)}
  <div class="grid g2" style="margin-top:16px"><section class="card"><h2 style="margin-top:0">In plain words</h2><ol>
    <li><b>Visual frame encoder.</b> Business channels show an index chart whose top label is the day's highest price so far. That number only ever goes up, like a ratchet. Matching it, frame by frame, against the exchange's minute-by-minute record tells us which day and which moment the screen is showing, to within a few seconds, without trusting any clock or file date.</li>
    <li><b>Visual text encoder.</b> Reads every number and name on screen: trading panels, quantities, P&L, the on-screen clock.</li>
    <li><b>Audio encoder.</b> Writes down what is said, with the time of every word, and finds prices, quantities and trades in it.</li>
    <li><b>Claim set.</b> Puts it together: who said or showed what, and when in market time.</li>
    <li><b>Three checks.</b> Fill conservation (could that many shares trade then?), knowability (was that price visible then?), data age (SEBI's 30-day rule).</li>
    <li><b>Certificate.</b> PASS, FAIL or ABSTAIN for each, with the evidence and assumptions.</li></ol></section>
  <section class="card"><h2 style="margin-top:0">Limits you should know</h2><ul>
    <li>We cannot tell <b>who</b> traded: the exchange record is anonymous.</li><li>We have <b>1-minute price ranges and NSE volume</b>, not individual trades, and no BSE.</li>
    <li>PASS never proves ownership, authenticity or compliance; FAIL always lists its assumptions.</li><li>Speech and text recognition make mistakes; confidence is shown.</li>
    <li>Timing is never cause.</li><li>Results are not accusations and not regulatory findings.</li></ul></section></div>
  <section class="card" style="margin-top:16px"><h2 style="margin-top:0">SEBI's 30-day rule (primary source)</h2>
    <p>Circular <span class="mono">${esc(reg.circular)}</span>, dated ${esc(reg.date)}, applicable from <b>${esc(reg.effective)}</b>. <a href="${esc(reg.url)}" target="_blank" rel="noopener">Read it on sebi.gov.in</a>.</p>
    <p>Exchanges and intermediaries may share price data for investor education only with a 30-day lag. A person <em>engaged solely in education</em> should not use the last 30 days' prices to name a security while indicating its future price, advice or a recommendation. A video alone rarely shows whether a presenter is in that category, so the Data-age check usually ABSTAINs and lists the facts.</p>
    <details><summary>Full text of the circular</summary><pre class="json">${esc(reg.text)}</pre></details></section>`);
}

route();
