let DATA = null;
let ACTIVE_FILE = null;
let SELECTED_IDX = null;
let SORT_STATE = { key: "risk_pct", type: "number", dir: "descending" };
let OUTCOMES_CACHE = { by_patient: {} };
const CONSENT_STATE = new Map();

const MAX_RENDER_ROWS = 500;
const MAX_UPLOAD_BYTES = 64 * 1024 * 1024;
const SCORE_TIMEOUT_MS = 300_000;
const TIER_RANK = {
  "Urgent Clinical Review": 7,
  High: 6,
  Elevated: 5,
  "Routine - overdue": 4,
  Routine: 3,
  Low: 2,
  Excluded: 1,
  "Insufficient data": 0,
};

const COLLATOR = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

const $ = (id) => document.getElementById(id);

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));

// Coerce to a finite number, or null. Prevents "NaN%"/"undefined%" rendering
// and keeps every numeric interpolation going through esc().
const toFinite = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const fmtNum = (v, suffix = "", digits = null) => {
  const n = toFinite(v);
  if (n == null) return "—";
  return `${esc(digits == null ? n : n.toFixed(digits))}${suffix}`;
};

const clampPct = (v) => {
  const n = toFinite(v);
  return n == null ? 0 : Math.min(100, Math.max(0, n));
};

const shortTier = (t) =>
  ({
    "Urgent Clinical Review": "Urgent",
    "Routine - overdue": "Routine overdue",
    "Insufficient data": "Insufficient",
  }[t] || t);

// Translate internal upload warnings into plain language for the screen.
const humanizeWarning = (w) => {
  const s = String(w);
  if (s.startsWith("Model features not supplied")) {
    return "Some optional health details were not supplied. The screening order still works, but it is less complete.";
  }
  if (s.includes("sex column auto-detected as 1=male")) {
    return "Sex column detected: 1 = male and 2 = female.";
  }
  if (s.includes("sex column contains only 1s")) {
    return "The sex column contains only 1. It was read as female. If your file uses 1 = male and 2 = female, rename the column to riagendr and upload again.";
  }
  if (s.includes("out-of-range")) {
    return "Some values were outside the possible range and were treated as missing.";
  }
  if (s.includes("missing/invalid age")) {
    return "Some ages were missing or invalid. Those rows were marked Not enough information.";
  }
  if (s.includes("missing sex")) {
    return "Some sex values were missing. Those rows were marked Not enough information.";
  }
  if (s.includes("pregnant=yes with male sex")) {
    return "Pregnancy was marked for a male record. The pregnancy flag was ignored.";
  }
  return s;
};

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function setActiveFile(file) {
  ACTIVE_FILE = file || null;
  $("dl-flagged").hidden = true;
  if (ACTIVE_FILE) {
    $("file-meta").textContent = `${ACTIVE_FILE.name} · ${formatBytes(ACTIVE_FILE.size)}`;
  } else {
    $("file-meta").textContent = "No file selected · max 200,000 rows";
  }
}

function showNotices(items, tone = "warn") {
  const box = $("msg");
  if (!items || !items.length) {
    box.hidden = true;
    box.innerHTML = "";
    box.removeAttribute("data-tone");
    return;
  }
  box.dataset.tone = tone;
  box.innerHTML = items.map((item) => `<div>${esc(item)}</div>`).join("");
  box.hidden = false;
}

let SCORE_SEQ = 0;
let SCORE_CONTROLLER = null;
let SCORE_DEBOUNCE = null;

function setScoring(on) {
  const dz = $("dropzone");
  if (dz) dz.dataset.scoring = on ? "true" : "false";
  const overlay = $("scoring-overlay");
  if (overlay) overlay.hidden = !on;
  const meta = $("file-meta");
  if (!meta) return;
  if (on) {
    meta.textContent = "Scoring cohort…";
  } else if (ACTIVE_FILE) {
    meta.textContent = `${ACTIVE_FILE.name} · ${formatBytes(ACTIVE_FILE.size)}`;
  } else {
    meta.textContent = "No file selected · max 200,000 rows";
  }
}

function scrollToResults() {
  const el = $("results");
  if (!el || el.hidden) return;
  requestAnimationFrame(() => {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function scheduleScore(file) {
  clearTimeout(SCORE_DEBOUNCE);
  SCORE_DEBOUNCE = setTimeout(() => scoreFile(file), 30);
}

async function scoreFile(file) {
  if (!file) {
    showNotices(["Please select a CSV file first."], "error");
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    showNotices(
      [`File is ${formatBytes(file.size)}; the upload limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`],
      "error"
    );
    return;
  }

  // A newer upload supersedes any in-flight request.
  if (SCORE_CONTROLLER) SCORE_CONTROLLER.abort();
  const seq = ++SCORE_SEQ;
  const controller = new AbortController();
  SCORE_CONTROLLER = controller;
  const timer = setTimeout(() => controller.abort(), SCORE_TIMEOUT_MS);

  setScoring(true);
  showNotices(["Scoring cohort and running safeguard checks…"], "info");

  // Let the overlay paint before the fetch + render work starts.
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/score", {
      method: "POST",
      body: fd,
      signal: controller.signal,
    });
    const text = await res.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      /* non-JSON error page (proxy, gateway, etc.) */
    }
    if (!res.ok) {
      throw new Error(payload?.detail || text.slice(0, 200) || `HTTP ${res.status}`);
    }
    if (!payload) {
      throw new Error("Server returned an empty or non-JSON response.");
    }
    if (seq !== SCORE_SEQ) return; // superseded by a newer upload

    DATA = payload;
    CONSENT_STATE.clear();
    SELECTED_IDX = null;
    showNotices(
      payload.warnings && payload.warnings.length
        ? payload.warnings.map((w) => `Warning: ${humanizeWarning(w)}`)
        : [],
      "warn"
    );
    renderDashboard();
    if (seq === SCORE_SEQ) {
      setScoring(false);
      scrollToResults();
    }
  } catch (e) {
    if (seq !== SCORE_SEQ) return; // superseded; the newer request reports
    const message =
      e.name === "AbortError" ? "Scoring timed out; try a smaller cohort." : e.message;
    showNotices([`Scoring failed: ${message}`], "error");
  } finally {
    clearTimeout(timer);
    if (seq === SCORE_SEQ) {
      SCORE_CONTROLLER = null;
      setScoring(false);
    }
  }
}

function renderDashboard() {
  const s = DATA.summary;
  $("dl-flagged").hidden = false;
  $("results").hidden = false;
  $("seg-card").hidden = false;
  $("variant-badge").textContent = "Screening priority";

  $("tier-urgent").textContent = s.urgent ?? 0;
  $("tier-high").textContent = s.high ?? 0;
  $("tier-elevated").textContent = s.elevated ?? 0;
  $("tier-hero").hidden = false;

  const stats = [
    ["Rows uploaded", s.rows, ""],
    ["Adults with a score", s.adults_screenable, ""],
    ["Missed by age-40 rule", s.missed_by_age_rules, "accent"],
    ["Estimated undiagnosed diabetes cases", s.expected_undiagnosed_diabetes_cases, ""],
    ["Results not checked", s.observations_unit_suspect ?? 0, "warn"],
    ["Results checked", s.observations_captured ?? 0, ""],
  ];
  $("cards").innerHTML = stats
    .map(
      ([label, value, tone]) =>
        `<div class="stat"${tone ? ` data-tone="${esc(tone)}"` : ""}><span class="stat-val">${esc(value)}</span><span class="stat-label">${esc(label)}</span></div>`
    )
    .join("");

  renderTierDistribution(DATA.results);
  refreshOutcomes();
  renderSegments();
  $("disclaimer").textContent = s.disclaimer;

  renderRows();
  autoSelectFirstVisibleRow();
}

function renderTierDistribution(results) {
  const wrap = $("tier-mix");
  if (!results || !results.length) {
    wrap.hidden = true;
    return;
  }
  const order = [
    "Urgent Clinical Review",
    "High",
    "Elevated",
    "Routine - overdue",
    "Routine",
    "Low",
    "Excluded",
    "Insufficient data",
  ];
  const counts = new Map(order.map((t) => [t, 0]));
  for (const r of results) {
    counts.set(r.tier, (counts.get(r.tier) || 0) + 1);
  }
  const total = results.length;
  const active = order.filter((t) => counts.get(t) > 0);
  const flaggedTotal =
    (counts.get("Urgent Clinical Review") || 0) +
    (counts.get("High") || 0) +
    (counts.get("Elevated") || 0);
  $("tier-mix-caption").textContent =
    `${flaggedTotal} of ${total} (${((100 * flaggedTotal) / total).toFixed(1)}%) flagged Urgent, High, or Elevated`;

  $("tier-bar").innerHTML = active
    .map((t) => {
      const pct = (100 * counts.get(t)) / total;
      return `<span class="tier-seg" data-tier="${esc(t)}" style="inline-size:${pct.toFixed(2)}%"></span>`;
    })
    .join("");

  const colorMap = {
    "Urgent Clinical Review": "var(--accent-rose)",
    High: "var(--accent-coral)",
    Elevated: "var(--accent-amber)",
    "Routine - overdue": "var(--accent-teal)",
    Routine: "var(--seg-routine)",
    Low: "var(--seg-low)",
    Excluded: "var(--seg-excl-b)",
    "Insufficient data": "var(--accent-slate)",
  };
  $("tier-legend").innerHTML = active
    .map(
      (t) =>
        `<li><span class="dot" style="background:${esc(colorMap[t] ?? "var(--accent-slate)")}"></span>${esc(t)}: <b>${esc(counts.get(t) ?? 0)}</b></li>`
    )
    .join("");
  wrap.hidden = false;
}

function getFilteredSortedRows() {
  const tierVal = $("tier-filter").value;
  const popVal = $("pop-filter").value;
  const q = $("search-q").value.trim().toLowerCase();

  const indexed = DATA.results.map((r, idx) => ({ r, idx }));
  const filtered = indexed.filter(({ r }) => {
    if (tierVal === "flagged" && !["Urgent Clinical Review", "High", "Elevated"].includes(r.tier)) {
      return false;
    }
    if (tierVal !== "all" && tierVal !== "flagged" && r.tier !== tierVal) return false;
    if (popVal !== "all" && r.population !== popVal) return false;
    if (q) {
      const hay = [r.id, r.district, r.language, r.tier, ...(r.flags || [])]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const factor = SORT_STATE.dir === "ascending" ? 1 : -1;
  filtered.sort((a, b) => {
    const va = a.r[SORT_STATE.key];
    const vb = b.r[SORT_STATE.key];
    if (SORT_STATE.type === "number") {
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return factor * (Number(va) - Number(vb));
    }
    if (SORT_STATE.type === "tier") {
      return factor * ((TIER_RANK[va] ?? -1) - (TIER_RANK[vb] ?? -1));
    }
    return factor * COLLATOR.compare(String(va ?? ""), String(vb ?? ""));
  });
  return filtered;
}

function renderRows() {
  if (!DATA) return;
  const filtered = getFilteredSortedRows();
  const shown = filtered.slice(0, MAX_RENDER_ROWS);

  if (filtered.length > MAX_RENDER_ROWS) {
    $("count").textContent = `Top ${MAX_RENDER_ROWS} of ${filtered.length} matching`;
    $("queue-footnote").textContent =
      `Showing the first ${MAX_RENDER_ROWS} of ${filtered.length} matching rows. Use filters or Download CSV to inspect all records.`;
    $("queue-footnote").hidden = false;
  } else {
    $("count").textContent = `${filtered.length} of ${DATA.results.length} patients`;
    $("queue-footnote").hidden = true;
  }

  if (!shown.length) {
    $("rows").innerHTML =
      '<tr><td colspan="6" class="muted">No patients match the current filters.</td></tr>';
    return;
  }

  $("rows").innerHTML = shown
    .map(({ r, idx }) => {
      const selected = idx === SELECTED_IDX;
      return (
        `<tr data-i="${idx}" data-selected="${selected ? "true" : "false"}">` +
        `<td data-label="Patient ID"><button type="button" class="row-btn" data-select="${idx}" aria-pressed="${selected ? "true" : "false"}">${esc(r.id)}</button></td>` +
        `<td data-label="Age" class="tabular">${fmtNum(r.age)}</td>` +
        `<td data-label="Tier"><span class="pill tier-pill" data-tier="${esc(r.tier)}" title="${esc(r.tier)}">${esc(shortTier(r.tier))}</span></td>` +
        `<td data-label="DM Priority %" class="tabular">${fmtNum(r.risk_pct, "%")}</td>` +
        `<td data-label="Dysgly Priority %" class="tabular">${fmtNum(r.dysglycaemia_pct, "%")}</td>` +
        `<td data-label="Timing">${esc(r.timing)}</td>` +
        "</tr>"
      );
    })
    .join("");
}

function autoSelectFirstVisibleRow() {
  const firstBtn = $("rows").querySelector("button[data-select]");
  if (firstBtn) {
    showDetail(Number(firstBtn.dataset.select), false);
  } else {
    SELECTED_IDX = null;
    $("detail").hidden = true;
    $("detail-empty").hidden = false;
  }
}

function reasonDirection(text) {
  const lower = String(text).toLowerCase();
  if (lower.includes("raises")) return ["up", "+"];
  if (lower.includes("lowers")) return ["down", "−"];
  return ["note", "•"];
}

function setSelectedRow(idx) {
  const rows = $("rows").querySelectorAll("tr[data-i]");
  for (const tr of rows) {
    const on = Number(tr.dataset.i) === idx;
    tr.dataset.selected = on ? "true" : "false";
    const btn = tr.querySelector("button[data-select]");
    if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
  }
}

function showDetail(idx, moveFocus = true) {
  const r = DATA.results[idx];
  if (!r) return;
  SELECTED_IDX = idx;
  setSelectedRow(idx);

  $("detail-empty").hidden = true;
  const d = $("detail");
  d.hidden = false;

  const metaChips = [
    r.population ? `<span class="pill pill-neutral">${esc(r.population)}</span>` : "",
    r.age != null ? `<span class="pill pill-neutral">Age ${esc(r.age)}</span>` : "",
    r.district ? `<span class="pill pill-neutral">${esc(r.district)}</span>` : "",
    r.language ? `<span class="pill pill-neutral">Lang: ${esc(r.language)}</span>` : "",
  ].filter(Boolean);

  const dmPct = clampPct(r.risk_pct);
  const dysPct = clampPct(r.dysglycaemia_pct);
  const completeness = toFinite(r.completeness);

  const metersHtml =
    r.risk_pct != null
      ? `<div class="risk-meters">
          <div class="meter-box">
            <span class="meter-label">Undiagnosed DM Priority</span>
            <span class="meter-value">${fmtNum(r.risk_pct, "%")}</span>
            <div class="meter-track"><div class="meter-fill" style="--pct:${dmPct}%;--meter-color:var(--accent-coral)"></div></div>
          </div>
          <div class="meter-box">
            <span class="meter-label">Dysglycaemia Priority</span>
            <span class="meter-value">${fmtNum(r.dysglycaemia_pct, "%")}</span>
            <div class="meter-track"><div class="meter-fill" style="--pct:${dysPct}%;--meter-color:var(--accent-amber)"></div></div>
          </div>
        </div>
        <p class="muted meter-note">This is a screening priority score, not a diagnosis or a personal risk percentage. Lab results and vital signs change the flags and urgency, not this ranking.</p>`
      : `<div class="meter-box">
          <span class="meter-label">Scoring Method</span>
          <span>${esc(r.population === "child/adolescent" ? "WHO BMI-for-age z-score rule (<20y)" : "Rule-based exclusion / insufficient data")}</span>
        </div>`;

  const reasonsHtml = (r.reasons || [])
    .map((txt) => {
      const [dir, sym] = reasonDirection(txt);
      return `<li class="reason-item"><span class="dir-badge" data-dir="${dir}" aria-hidden="true">${sym}</span><span>${esc(txt)}</span></li>`;
    })
    .join("");

  const urgentHtml =
    r.urgent_alerts && r.urgent_alerts.length
      ? `<div class="detail-section urgent-box">
          <h4>Urgent Clinical Alerts (Clinician Sign-off Required)</h4>
          <ul class="flag-list">${r.urgent_alerts
            .map(
              (a) =>
                `<li class="flag-chip flag-chip-urgent"><b>${esc(a.rule_id)}</b> · ${esc(a.test)}: ${esc(a.value)} ${esc(a.unit || "")} (${esc(a.threshold)}) — ${esc(a.action)} <span class="muted">[${esc(a.citation)}]</span></li>`
            )
            .join("")}</ul>
        </div>`
      : "";

  const unevaluated = (r.observations || []).filter(
    (o) => o.quality === "unit_suspect" || o.quality === "out_of_plausible_range"
  );
  const unevaluatedHtml = unevaluated.length
    ? `<div class="detail-section warn-box">
        <h4>Not Checked — Please Confirm the Unit</h4>
        <p class="muted">These values were captured but deliberately excluded from clinical rules because the unit or magnitude is ambiguous. Add the correct unit and re-upload; do not treat this row as cleared.</p>
        <ul class="flag-list">${unevaluated
          .map(
            (o) =>
              `<li class="flag-chip flag-chip-warn">${esc(o.canonical || o.name_raw)}: ${esc(o.value ?? o.raw_text ?? "—")} ${esc(o.unit || "")} <span class="muted">(${esc(o.quality)})</span></li>`
          )
          .join("")}</ul>
      </div>`
    : "";

  const obsHtml =
    r.observations && r.observations.length
      ? `<div class="detail-section">
          <h4>Other Test Results</h4>
          <ul class="flag-list">${r.observations
            .map((o) => {
              const provenance =
                o.raw_value != null && o.raw_unit
                  ? ` <span class="muted">(converted from ${esc(o.raw_value)} ${esc(o.raw_unit)})</span>`
                  : "";
              return `<li class="flag-chip">${esc(o.canonical || o.name_raw)}: ${esc(o.value ?? o.raw_text ?? "—")} ${esc(o.unit || "")} <span class="muted">(${esc(o.quality)})</span>${provenance}</li>`;
            })
            .join("")}</ul>
        </div>`
      : "";

  const flagsHtml =
    r.flags && r.flags.length
      ? `<div class="detail-section">
          <h4>Screening Flags</h4>
          <ul class="flag-list">${r.flags.map((f) => `<li class="flag-chip">${esc(f)}</li>`).join("")}</ul>
        </div>`
      : "";

  let outreachHtml = "";
  if (r.outreach_preview) {
    const op = r.outreach_preview;
    const isAr = op.language === "AR";
    const saved = OUTCOMES_CACHE.by_patient?.[String(r.id)] || {};
    const chosen = CONSENT_STATE.get(idx) || saved.outreach_choice || null;
    const completed = Boolean(saved.completed_screening);
    const choicesBtns = op.choices
      .map(
        (ch) =>
          `<button type="button" class="btn btn-outline btn-sm choice-btn" data-choice="${esc(ch)}" aria-pressed="${chosen === ch ? "true" : "false"}">${esc(ch)}</button>`
      )
      .join("");
    outreachHtml = `
      <div class="detail-section">
        <h4>Culturally Tailored Outreach (${esc(op.language)})</h4>
        <div class="outreach-box">
          <p class="outreach-msg" lang="${isAr ? "ar" : "en"}" dir="${isAr ? "rtl" : "ltr"}">${esc(op.message)}</p>
          <div class="choice-row" role="group" aria-label="Resident consent and completion action">
            ${choicesBtns}
            <button type="button" class="btn btn-outline btn-sm choice-btn" data-complete="${completed ? "false" : "true"}" aria-pressed="${completed ? "true" : "false"}">${completed ? "Completed ✓" : "Mark screening completed"}</button>
          </div>
          <p class="muted" id="consent-note">
            ${chosen ? `Recorded response: <b>${esc(chosen)}</b>${completed ? " · Screening completed" : ""}` : completed ? "Screening completed recorded." : "Select a response to persist to the outcome tracker."}
          </p>
        </div>
      </div>`;
  }

  d.innerHTML = `
    <div class="stack-sm">
      <div class="detail-head">
        <div class="detail-title-row">
          <h3>${esc(r.id)}</h3>
          <span class="pill tier-pill" data-tier="${esc(r.tier)}">${esc(r.tier)}</span>
        </div>
        <div class="meta-chips">${metaChips.join("")}</div>
      </div>

      ${metersHtml}

      <div class="pathway-box">
        <div><b>Pathway:</b> ${esc(r.pathway)}</div>
        <div><b>Recommended timing:</b> ${esc(r.timing)} · <b>Data completeness:</b> ${completeness == null ? "—" : `${Math.round(completeness * 100)}%`}</div>
      </div>

      <div class="detail-section">
        <h4>Why Flagged</h4>
        <ul class="reason-list">${reasonsHtml}</ul>
      </div>

      ${urgentHtml}
      ${unevaluatedHtml}
      ${obsHtml}
      ${flagsHtml}
      ${outreachHtml}

      <p class="muted">Screening priority only. A clinician must review and sign off. The individual may decline.</p>
    </div>`;

  if (moveFocus) {
    d.focus({ preventScroll: false });
  }
}

function renderSegments() {
  if (!DATA) return;
  const dim = $("seg-filter").value;
  const segs = DATA.summary.segments.filter((g) => (dim === "all" ? true : g.dimension === dim));
  if (!segs.length) {
    $("segs").innerHTML = '<tr><td colspan="5" class="muted">No segment breakdowns available.</td></tr>';
    return;
  }
  $("segs").innerHTML = segs
    .map((g) => {
      if (g.suppressed) {
        return (
          `<tr><td>${esc(g.dimension)}</td><td>${esc(g.segment)}</td>` +
          `<td><span class="supp-badge">${esc(g.n)}</span></td>` +
          '<td colspan="2" class="muted">Suppressed for small-cell privacy</td></tr>'
        );
      }
      return (
        `<tr><td>${esc(g.dimension)}</td><td>${esc(g.segment)}</td><td class="tabular">${esc(g.n)}</td>` +
        `<td class="tabular">${esc(g.flagged_pct)}%</td><td class="tabular">${esc(g.mean_risk_pct)}%</td></tr>`
      );
    })
    .join("");
}

async function downloadFlaggedCsv() {
  if (!ACTIVE_FILE || !DATA) {
    showNotices(["Score a cohort before exporting flagged rows."], "error");
    return;
  }
  try {
    const fd = new FormData();
    fd.append("file", ACTIVE_FILE);
    fd.append("min_tier", "flagged");
    const res = await fetch("/api/score.csv", { method: "POST", body: fd });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        detail = err.detail || detail;
      } catch {
        detail = await res.text();
      }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nabdh_screening_flagged.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    showNotices([`CSV export failed: ${e.message}`], "error");
  }
}

function wireSorting() {
  const table = $("queue-table");
  table.tHead.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-sort]");
    if (!btn || !DATA) return;
    const th = btn.closest("th");
    const key = th.dataset.key;
    const type = th.dataset.type || "text";
    const nextDir =
      SORT_STATE.key === key && SORT_STATE.dir === "ascending" ? "descending" : "ascending";

    SORT_STATE = { key, type, dir: nextDir };
    for (const cell of table.tHead.rows[0].cells) cell.removeAttribute("aria-sort");
    th.setAttribute("aria-sort", nextDir);

    renderRows();
    const shownCount = $("rows").querySelectorAll("tr[data-i]").length;
    $("sort-status").textContent = `Sorted by ${btn.textContent.trim()}, ${nextDir}, ${shownCount} rows shown`;
  });
}

async function loadDemoCohort() {
  const btn = $("btn-demo");
  if (btn) btn.disabled = true;
  try {
    showNotices(["Loading the 206-record demo cohort…"], "info");
    const res = await fetch("/demo-master.csv", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const file = new File([text], "00_master_all_cases.csv", { type: "text/csv" });
    setActiveFile(file);
    await scoreFile(file);
  } catch (e) {
    showNotices([`Could not load the demo cohort: ${e.message}`], "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function wireDropzone() {
  const dz = $("dropzone");
  const input = $("csv-file");

  input.addEventListener("change", () => {
    const f = input.files && input.files[0];
    setActiveFile(f);
    if (f) scheduleScore(f);
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.dataset.dragover = "true";
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      delete dz.dataset.dragover;
    })
  );
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    const dt = new DataTransfer();
    dt.items.add(f);
    input.files = dt.files;
    setActiveFile(f);
    scheduleScore(f);
  });
}

function wireThemeToggle() {
  const meta = document.querySelector('meta[name="color-scheme"]');
  const btn = $("theme-toggle");
  if (!meta || !btn) return;

  const getSystemScheme = () =>
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

  const readStored = () => {
    try {
      const val = localStorage.getItem("color-scheme");
      return val === "light" || val === "dark" ? val : null;
    } catch {
      return null;
    }
  };

  btn.addEventListener("click", () => {
    const rendered = readStored() ?? getSystemScheme();
    const target = rendered === "dark" ? "light" : "dark";
    const system = getSystemScheme();
    try {
      if (target === system) {
        localStorage.removeItem("color-scheme");
        meta.content = "light dark";
      } else {
        localStorage.setItem("color-scheme", target);
        meta.content = target;
      }
    } catch {
      meta.content = target === system ? "light dark" : target;
    }
  });

  window.addEventListener("storage", (e) => {
    if (e.key !== "color-scheme") return;
    meta.content = e.newValue === "light" || e.newValue === "dark" ? e.newValue : "light dark";
  });
}

function renderOutcomeStrip(summary) {
  OUTCOMES_CACHE = summary || { by_patient: {} };
  const strip = $("outcome-strip");
  if (!strip) return;
  const total = summary.total_recorded || 0;
  $("outcome-caption").textContent =
    total > 0
      ? `${summary.completed_screenings} completed · ${summary.attendance_rate_pct}% attendance of booked`
      : "No responses recorded yet — click a patient's outreach action below";
  $("outcome-metrics").innerHTML = [
    ["Confirmed", summary.confirmed || 0],
    ["Rescheduled", summary.rescheduled || 0],
    ["Opted out", summary.opted_out || 0],
    ["Completed", summary.completed_screenings || 0],
  ]
    .map(([lbl, val]) => `<span>${esc(lbl)}: <b>${esc(val)}</b></span>`)
    .join(" · ");
  strip.hidden = false;
}

async function refreshOutcomes() {
  try {
    const res = await fetch("/api/outcomes");
    if (res.ok) renderOutcomeStrip(await res.json());
  } catch {
    /* ignore offline preview */
  }
}

async function saveOutcome(payload) {
  try {
    const res = await fetch("/api/outcomes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) renderOutcomeStrip(await res.json());
  } catch {
    /* ignore */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  wireThemeToggle();
  wireDropzone();
  wireSorting();

  const demoBtn = $("btn-demo");
  if (demoBtn) demoBtn.addEventListener("click", loadDemoCohort);

  $("score-form").addEventListener("submit", (e) => {
    e.preventDefault();
    scoreFile(ACTIVE_FILE || $("csv-file").files[0]);
  });

  $("tier-filter").addEventListener("change", () => DATA && renderRows());
  $("pop-filter").addEventListener("change", () => DATA && renderRows());
  let searchTimer = null;
  $("search-q").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => DATA && renderRows(), 120);
  });
  $("filter-form").addEventListener("submit", (e) => e.preventDefault());
  $("seg-filter").addEventListener("change", () => DATA && renderSegments());

  $("rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-i]");
    if (!tr) return;
    const idx = Number(tr.dataset.i);
    const viaButton = Boolean(e.target.closest("button[data-select]"));
    showDetail(idx, viaButton);
  });

  $("detail").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-choice], button[data-complete]");
    if (!btn || SELECTED_IDX == null || !DATA) return;
    const row = DATA.results[SELECTED_IDX];
    if (!row) return;
    const payload = {
      patient_id: String(row.id),
      tier: row.tier,
      pathway: row.pathway,
      population: row.population,
    };
    if (btn.dataset.choice) {
      CONSENT_STATE.set(SELECTED_IDX, btn.dataset.choice);
      payload.outreach_choice = btn.dataset.choice;
    }
    if (btn.dataset.complete) {
      payload.completed_screening = btn.dataset.complete === "true";
    }
    await saveOutcome(payload);
    showDetail(SELECTED_IDX, false);
  });

  $("dl-flagged").addEventListener("click", downloadFlaggedCsv);

  const dialog = $("how-dialog");
  $("open-how").addEventListener("click", () => dialog.showModal());
});
