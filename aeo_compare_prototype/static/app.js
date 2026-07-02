const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const splitList = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);
const yn = (b) => (b ? '<span class="yes">Yes</span>' : '<span class="no">No</span>');
const fmt = (v) => (v === null || v === undefined || v === "" ? "&mdash;" : esc(v));

// ---------- init ----------
async function init() {
  const res = await fetch("/api/providers").then((r) => r.json());
  const box = $("#providers");
  res.providers.forEach((p) => {
    const lab = el("label");
    const cb = el("input");
    cb.type = "checkbox";
    cb.value = p;
    cb.checked = true; // all 5 providers on by default (matches real flow)
    lab.append(cb, document.createTextNode(p));
    box.append(lab);
  });
  const DEFAULT_PROMPTS = [
    "What are the best all-in-one workspace tools for startups?",
    "Best note-taking and documentation apps for remote teams",
    "Notion vs Confluence: which is better for team wikis?",
    "What tools can replace Google Docs for collaborative documentation?",
  ];
  DEFAULT_PROMPTS.forEach((p) => addPrompt(p));

  // If the user previously saved a business, restore it (overrides the prefilled
  // defaults). Otherwise the prefilled Notion values in the HTML stay as-is. We
  // intentionally do NOT auto-load a DB profile, so an empty database shows no
  // error — use the "Load business by ID" button if you want a real profile.
  restoreBusiness();
  loadSessions();
}

// ---------- business save/restore (localStorage) ----------
const BIZ_FIELDS = [
  "business_name", "website_url", "brand_names", "industry",
  "products_services", "business_id", "business_overview",
];
const BIZ_KEY = "aeo_compare_business";

function saveBusiness() {
  const data = {};
  BIZ_FIELDS.forEach((id) => (data[id] = $("#" + id).value));
  localStorage.setItem(BIZ_KEY, JSON.stringify(data));
  const s = $("#bizStatus");
  s.textContent = "Saved ✓";
  s.style.color = "var(--green)";
}

function restoreBusiness() {
  const raw = localStorage.getItem(BIZ_KEY);
  if (!raw) return false;
  try {
    const data = JSON.parse(raw);
    BIZ_FIELDS.forEach((id) => {
      if (data[id] !== undefined) $("#" + id).value = data[id];
    });
    const s = $("#bizStatus");
    s.textContent = "Restored saved business";
    s.style.color = "var(--muted)";
    return true;
  } catch {
    return false;
  }
}

function clearBusiness() {
  localStorage.removeItem(BIZ_KEY);
  BIZ_FIELDS.forEach((id) => ($("#" + id).value = ""));
  const s = $("#bizStatus");
  s.textContent = "Cleared (placeholders shown)";
  s.style.color = "var(--muted)";
}

async function loadBusiness() {
  const id = $("#business_id").value.trim();
  const status = $("#bizStatus");
  if (!id) return;
  status.textContent = "Loading…";
  status.style.color = "var(--muted)";
  try {
    const b = await fetch(`/api/business/${encodeURIComponent(id)}`).then(async (r) => {
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      return r.json();
    });
    $("#business_name").value = b.business_name || "";
    $("#website_url").value = b.website_url || "";
    $("#brand_names").value = (b.brand_names || []).join(", ");
    $("#industry").value = (b.industry || []).join(", ");
    $("#products_services").value = (b.products_services || []).join(", ");
    $("#business_overview").value = b.business_overview || "";
    status.textContent = `Loaded "${b.business_name}"`;
    status.style.color = "var(--green)";
  } catch (e) {
    status.textContent = "Error: " + e.message;
    status.style.color = "var(--red)";
  }
}

function addPrompt(value = "") {
  const row = el("div", "prompt-row");
  const ta = el("textarea");
  ta.rows = 2;
  ta.placeholder = "e.g. what is the best note-taking app for startups";
  ta.value = value;
  const rm = el("button", "btn-ghost small rm", "&times;");
  rm.onclick = () => row.remove();
  row.append(ta, rm);
  $("#prompts").append(row);
}

function collect() {
  const providers = [...document.querySelectorAll("#providers input:checked")].map((c) => c.value);
  const prompts = [...document.querySelectorAll("#prompts textarea")].map((t) => t.value).filter((v) => v.trim());
  return {
    business: {
      business_id: $("#business_id").value.trim() || null,
      business_name: $("#business_name").value.trim(),
      website_url: $("#website_url").value.trim(),
      brand_names: splitList($("#brand_names").value),
      industry: splitList($("#industry").value),
      products_services: splitList($("#products_services").value),
      business_overview: $("#business_overview").value.trim() || null,
    },
    providers,
    prompts,
  };
}

// ---------- run ----------
async function run() {
  const payload = collect();
  if (!payload.prompts.length) return setStatus("Add at least one prompt.", true);
  if (!payload.providers.length) return setStatus("Pick at least one provider.", true);

  setStatus("Fetching responses + running both parses… (this can take a while)");
  $("#runBtn").disabled = true;
  try {
    const session = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      return r.json();
    });
    renderSession(session);
    setStatus("Done.");
    loadSessions();
  } catch (e) {
    setStatus("Error: " + e.message, true);
  } finally {
    $("#runBtn").disabled = false;
  }
}

const setStatus = (msg, isErr) => {
  const s = $("#status");
  s.textContent = msg;
  s.style.color = isErr ? "var(--red)" : "var(--muted)";
};

// ---------- sessions ----------
async function loadSessions() {
  const { sessions } = await fetch("/api/sessions").then((r) => r.json());
  const list = $("#sessionList");
  list.innerHTML = "";
  sessions.forEach((s) => {
    const li = el("li");
    const reparse = s.reparse_of ? ' <span class="tag-reparse">(reparse)</span>' : "";
    li.innerHTML = `<strong>${esc(s.business_name || "—")}</strong>${reparse}
      <span class="when">${s.prompt_count} prompt(s) · ${(s.providers || []).join(", ")}<br>${esc(s.created_at || "")}</span>`;
    li.onclick = () => openSession(s.id);
    list.append(li);
  });
}

async function openSession(id) {
  setStatus("Loading session…");
  const session = await fetch(`/api/sessions/${id}`).then((r) => r.json());
  renderSession(session);
  setStatus("");
}

// ---------- render ----------
function renderSession(session) {
  const root = $("#results");
  root.innerHTML = "";

  const header = el("div", "panel");
  const reparseBtn = el("button", "btn-ghost small", "↻ Re-parse (reuse responses)");
  reparseBtn.onclick = async () => {
    setStatus("Re-parsing with stored responses…");
    const s = await fetch(`/api/sessions/${session.id}/reparse`, { method: "POST" }).then((r) => r.json());
    renderSession(s);
    setStatus("Re-parsed.");
    loadSessions();
  };
  const left = el("div");
  left.innerHTML = `<h2>Results — ${esc(session.business_name || "")}</h2>
    <p class="sub">${(session.prompts || []).length} prompt(s) · ${session.reparse_of ? "reparse" : esc(session.id)}</p>
    <div class="brand-chips">${(session.target_brand_names || []).map((b) => `<span class="brand-chip">${esc(b)}</span>`).join("")}</div>`;
  const head = el("div", "results-head");
  head.append(left, reparseBtn);
  header.append(head);
  root.append(header);

  (session.prompts || []).forEach((block) => {
    root.append(renderPromptCard(block));
  });
}

// One card per prompt; all providers live inside as tabs.
function renderPromptCard(block) {
  const wrap = el("div", "prompt-block");
  wrap.append(el("p", "prompt-title", esc(block.prompt_text)));

  const providers = block.providers || [];
  const tabs = el("div", "ptabs");
  const body = el("div", "ptab-body");

  const show = (idx) => {
    [...tabs.children].forEach((b, i) => b.classList.toggle("active", i === idx));
    body.innerHTML = "";
    body.append(renderProviderBody(providers[idx]));
  };

  providers.forEach((pr, i) => {
    const failed = pr.error || pr.current_design?.error || pr.proposed_design?.error;
    const btn = el("button", "ptab", `${esc(pr.provider)}${failed ? " ⚠️" : ""}`);
    btn.onclick = () => show(i);
    tabs.append(btn);
  });

  wrap.append(tabs, body);
  if (providers.length) show(0);
  return wrap;
}

function renderProviderBody(pr) {
  const wrap = el("div");
  if (pr.error) {
    wrap.append(el("p", "err", esc(pr.error)));
    return wrap;
  }

  // at-a-glance comparison strip
  const strip = compareStrip(pr.current_design, pr.proposed_design);
  if (strip) wrap.append(strip);

  // shared raw response (same for both designs)
  const raw = el("details", "raw");
  raw.innerHTML = `<summary>Raw ${esc(pr.provider)} response (${(pr.raw_response || "").length} chars · shared by both)</summary>
    <div class="raw-body">${esc(pr.raw_response || "")}</div>`;
  wrap.append(raw);

  const cols = el("div", "cols");
  cols.append(renderCurrent(pr.current_design));
  cols.append(renderProposed(pr.proposed_design));
  wrap.append(cols);
  return wrap;
}

function metricCard(k, v) {
  return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function sovCard(pct) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return `<div class="metric"><div class="k">Share of voice</div><div class="v">${fmt(pct)}%</div>
    <div class="sov-bar"><i style="width:${p}%"></i></div></div>`;
}

// Compact agreement/difference strip between the two designs.
function compareStrip(cd, pd) {
  if (!cd || cd.error || !pd || pd.error) return null;
  const m = cd.metrics || {};
  const a = pd.analytics || {};
  const t = a.target || {};
  const jr = cd.sentiment_join_report || {};
  const strip = el("div", "cmp-strip");

  const cmp = (label, oldV, newV, fmtFn = (x) => x) => {
    const same = String(oldV) === String(newV);
    const cls = same ? "chip ok" : "chip diff";
    const val = same ? `<b>${fmtFn(oldV)}</b>` : `<b>${fmtFn(oldV)}</b> → <b>${fmtFn(newV)}</b>`;
    return `<span class="${cls}">${same ? "✓" : "≠"} ${label} ${val}</span>`;
  };

  let html = "";
  html += cmp("Mentioned", !!m.target_brand_mentioned, !!t.mentioned, (b) => (b ? "yes" : "no"));
  html += cmp("SOV", m.share_of_voice, a.share_of_voice, (x) => x + "%");
  html += cmp("Brands", (cd.unique_brands_count ?? (m.competitor_mentions || []).length),
    (a.brand_cards || []).length);

  const avoided = jr.needs_fuzzy_join || 0;
  if (avoided > 0) {
    html += `<span class="chip win">★ ${avoided} fuzzy join(s) avoided by proposed design</span>`;
  } else {
    html += `<span class="chip win">★ 0 name-joins needed in proposed design</span>`;
  }
  strip.innerHTML = html;
  return strip;
}

function sourceBadge(t) {
  const map = { owned_media: "b-owned", earned_media: "b-earned", competitor: "b-competitor" };
  return `<span class="badge ${map[t] || "b-other"}">${esc(t || "?")}</span>`;
}

// ----- CURRENT (4-list) -----
function renderCurrent(cd) {
  const col = el("div", "col current");
  col.innerHTML = `<h4><span class="dot"></span>Current (4 separate lists)</h4>`;
  if (!cd || cd.error) {
    col.append(el("p", "err", esc(cd?.error || "No data")));
    return col;
  }
  const m = cd.metrics;
  col.insertAdjacentHTML(
    "beforeend",
    `<div class="metrics">
      ${metricCard("Mentioned", yn(m.target_brand_mentioned))}
      ${metricCard("Position", fmt(m.target_brand_position))}
      ${metricCard("Your mentions", fmt(m.target_brand_mention_count))}
      ${metricCard("Total mentions", fmt(m.total_mentions_count))}
      ${sovCard(m.share_of_voice)}
      ${metricCard("Cited", yn(m.target_brand_cited))}
    </div>`
  );

  // brands (competitor_mentions)
  let rows = (m.competitor_mentions || [])
    .map(
      (b) => `<tr class="${b.is_target_brand ? "target-row" : ""}">
        <td>${esc(b.brand_name)}${b.is_target_brand ? " ★" : ""}</td>
        <td>${fmt(b.position)}</td><td>${fmt(b.mention_count)}</td><td>${yn(b.is_cited)}</td></tr>`
    )
    .join("");
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Brands (mentions list)</div>
    <table class="t"><tr><th>Brand</th><th>Pos</th><th>Mentions</th><th>Cited</th></tr>${rows}</table>`);

  // sentiment (separate list)
  let sRows = (m.brand_sentiments || [])
    .map(
      (s) => `<tr><td>${esc(s.brand_name)}</td><td>${fmt(s.sentiment_score)}</td><td>${fmt(s.sentiment_rating)}</td>
        <td class="descriptors">${(s.sentiment_descriptors || []).map((d) => esc(d.phrase || d)).join(", ")}</td></tr>`
    )
    .join("");
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Sentiment (separate list — keyed by name)</div>
    <table class="t"><tr><th>Brand</th><th>Score</th><th>Rating</th><th>Descriptors</th></tr>${sRows}</table>`);

  // citations
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Citations</div>${renderCitationsFromList(m.citations || [])}`);

  // topics
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Key topics</div>${renderTopics(m.key_topics || [])}`);

  // join fragility
  const jr = cd.sentiment_join_report || {};
  if (jr.fragile) {
    col.insertAdjacentHTML(
      "beforeend",
      `<div class="join-note join-warn">⚠️ ${jr.needs_fuzzy_join}/${jr.sentiment_entries} sentiment entries don't exact-match a mention &rarr; need fuzzy join: ${(jr.unmatched_sentiment_brands || []).map(esc).join(", ")}</div>`
    );
  } else {
    col.insertAdjacentHTML(
      "beforeend",
      `<div class="join-note join-ok">✓ ${jr.exact_matched_to_mention || 0}/${jr.sentiment_entries || 0} sentiment entries exact-matched (still required a name join though)</div>`
    );
  }
  return col;
}

// ----- PROPOSED (brand-centric) -----
function renderProposed(pd) {
  const col = el("div", "col proposed");
  col.innerHTML = `<h4><span class="dot"></span>Proposed (one brand = one object)</h4>`;
  if (!pd || pd.error) {
    col.append(el("p", "err", esc(pd?.error || "No data")));
    return col;
  }
  const a = pd.analytics;
  const t = a.target || {};
  col.insertAdjacentHTML(
    "beforeend",
    `<div class="metrics">
      ${metricCard("Mentioned", yn(t.mentioned))}
      ${metricCard("Position", fmt(t.position))}
      ${metricCard("Your mentions", fmt(t.mention_count))}
      ${metricCard("Total mentions", fmt(a.total_mentions_count))}
      ${sovCard(a.share_of_voice)}
      ${metricCard("Cited", yn(t.cited))}
    </div>`
  );

  // brand cards — everything in one row
  let rows = (a.brand_cards || [])
    .map(
      (b) => `<tr class="${b.is_target ? "target-row" : ""}">
        <td>${esc(b.brand_name)}${b.is_target ? " ★" : ""}</td>
        <td>${fmt(b.position)}</td><td>${fmt(b.mention_count)}</td>
        <td>${fmt(b.citation_count)}</td><td>${fmt(b.sentiment_rating)}</td></tr>`
    )
    .join("");
  col.insertAdjacentHTML(
    "beforeend",
    `<div class="subhead">Brands (mentions + citations + sentiment together)</div>
    <table class="t"><tr><th>Brand</th><th>Pos</th><th>Mentions</th><th>Cites</th><th>Sentiment</th></tr>${rows}</table>`
  );

  // citations from the brand objects directly
  const brands = (pd.parsed && pd.parsed.brands) || [];
  const citeList = brands
    .filter((b) => (b.citation_urls || []).length)
    .map((b) => ({ brand_name: b.brand_name, is_target_brand: b.is_target, citation_urls: b.citation_urls }));
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Citations</div>${renderCitationsFromList(citeList)}`);

  // topics
  col.insertAdjacentHTML("beforeend", `<div class="subhead">Key topics</div>${renderTopics(a.key_topics || [])}`);

  col.insertAdjacentHTML(
    "beforeend",
    `<div class="win-note">No name-join needed — each row's sentiment &amp; citations come from the same brand object.</div>`
  );
  return col;
}

function renderCitationsFromList(citations) {
  if (!citations.length) return '<p class="descriptors">None</p>';
  return citations
    .map((c) => {
      const urls = (c.citation_urls || [])
        .map((u) => {
          const url = typeof u === "string" ? u : u.url;
          const st = typeof u === "string" ? null : u.source_type;
          return `<li>${sourceBadge(st)} ${esc(url)}</li>`;
        })
        .join("");
      return `<div class="topic"><strong>${esc(c.brand_name)}</strong>${c.is_target_brand ? " ★" : ""}
        <ul class="cite-list">${urls}</ul></div>`;
    })
    .join("");
}

function renderTopics(topics) {
  if (!topics.length) return '<p class="descriptors">None</p>';
  return topics
    .map(
      (t) => `<div class="topic">${esc(t.topic)} <span class="brands">— ${(t.brands || []).map(esc).join(", ") || "general"}</span></div>`
    )
    .join("");
}

// ---------- wire ----------
$("#addPrompt").onclick = () => addPrompt();
$("#runBtn").onclick = run;
$("#refreshSessions").onclick = loadSessions;
$("#loadBiz").onclick = loadBusiness;
$("#saveBiz").onclick = saveBusiness;
$("#clearBiz").onclick = clearBusiness;
init();
