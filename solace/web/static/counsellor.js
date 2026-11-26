"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

const NODE_NAMES = { issue: "Issues", emotion: "Feelings", trigger: "Triggers", person: "People", support: "Supports", strength: "Strengths" };
const RISK_NOTES = {
  none: "No risk signs in recent messages.",
  low: "Some distress, no signs of danger.",
  moderate: "Signs of hopelessness. Check in on safety.",
  high: "Possible suicidal thoughts. Ask about safety directly.",
  imminent: "May be in immediate danger. Prioritise safety and emergency help.",
};

const state = { me: null, items: [], selected: null, view: null, live: null };

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (res.status === 401) { showLogin(); throw new Error("login"); }
  if (!res.ok) throw new Error(String(res.status));
  return res.status === 204 ? null : res.json();
}

const shortId = (sessionId) => sessionId.slice(0, 4).toUpperCase();
function ago(ts) {
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (mins < 1) return "now";
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  return h < 24 ? `${h} h` : `${Math.floor(h / 24)} d`;
}

/* ---------- sign in ---------- */
function showLogin() {
  state.live?.close();
  state.live = null;
  $("dashView").hidden = true;
  $("loginView").hidden = false;
  $("email").focus();
}

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("loginError").textContent = "";
  $("loginBtn").disabled = true;
  try {
    const res = await fetch("/api/counsellor/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value, password: $("password").value }),
    });
    if (res.status === 429) throw new Error("Too many attempts. Wait a few minutes and try again.");
    if (!res.ok) throw new Error("That email and password don't match.");
    $("password").value = "";
    start(await res.json());
  } catch (err) {
    $("loginError").textContent = err.message;
  } finally {
    $("loginBtn").disabled = false;
  }
});

$("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/counsellor/logout", { method: "POST" }); } catch { /* ignore */ }
  showLogin();
});

/* ---------- queue ---------- */
async function loadQueue() {
  state.items = await api("/api/counsellor/queue");
  renderQueue();
  const waiting = state.items.filter((i) => i.handoff.status === "requested").length;
  document.title = waiting ? `(${waiting}) Solace for Counsellors` : "Solace for Counsellors";
}

function renderQueue() {
  const box = $("queue");
  box.replaceChildren();
  const groups = [
    ["Waiting", (i) => i.handoff.status === "requested"],
    ["With you", (i) => i.handoff.status === "active" && i.mine],
    ["With others", (i) => i.handoff.status === "active" && !i.mine],
    ["Ended today", (i) => i.handoff.status === "closed"],
  ];
  let any = false;
  for (const [label, test] of groups) {
    const items = state.items.filter(test);
    if (!items.length) continue;
    any = true;
    box.appendChild(el("h3", "group-label", label));
    for (const item of items) box.appendChild(queueRow(item));
  }
  if (!any) box.appendChild(el("p", "empty-q", "No one is waiting right now. New requests appear here instantly."));
}

function queueRow(item) {
  const h = item.handoff;
  const row = el("button", "q-row");
  row.type = "button";
  row.setAttribute("aria-current", String(state.selected === h.id));
  const name = el("span", "q-name", `Person ${shortId(h.session_id)}`);
  if (h.status !== "closed" && (h.risk_level === "high" || h.risk_level === "imminent")) name.appendChild(el("span", "badge", "URGENT"));
  if (item.mine && h.status === "active") name.appendChild(el("span", "badge mine", "YOU"));
  const since = h.status === "requested" ? h.created_at : h.updated_at;
  row.append(el("span", `q-dot ${h.risk_level}`), name, el("span", "q-time", ago(since)),
    el("span", "q-preview", item.preview || "No messages yet"));
  row.setAttribute("aria-label", `Person ${shortId(h.session_id)}, risk ${h.risk_level}, ${h.status}`);
  row.addEventListener("click", () => select(h.id));
  return row;
}

/* ---------- conversation ---------- */
async function select(id) {
  state.selected = id;
  renderQueue();
  $("dashView").classList.add("open");
  await loadDetail();
}

async function loadDetail() {
  if (!state.selected) return;
  let view;
  try { view = await api(`/api/counsellor/handoffs/${state.selected}`); } catch { return; }
  state.view = view;
  const h = view.handoff;
  const mine = h.status === "active" && h.counsellor_id === state.me.id;
  $("placeholder").hidden = true;
  $("convo").hidden = false;
  $("convoTitle").textContent = `Person ${shortId(h.session_id)}`;
  const status = h.status === "requested" ? `Waiting ${ago(h.created_at)}`
    : h.status === "active" ? (mine ? "You're chatting" : `With ${h.counsellor_name}`) : "Ended";
  $("convoSub").textContent = `${status} · risk ${h.risk_level}`;
  $("acceptBtn").hidden = h.status !== "requested";
  $("closeBtn").hidden = !(mine || h.status === "requested");
  $("closeBtn").textContent = h.status === "requested" ? "Decline" : "End Chat";
  $("replyInput").disabled = !mine;
  $("replyInput").placeholder = mine ? "Reply as yourself"
    : h.status === "closed" ? "This chat has ended" : h.status === "active" ? "Another counsellor is chatting" : "Accept to reply";
  $("replyNote").textContent = mine
    ? "They see your name. Solace is paused while you chat."
    : h.status === "requested" ? "Solace is supporting them until someone accepts." : "";
  updateSend();
  renderThread(view.messages);
  renderInfo(view);
}

function renderThread(messages) {
  const t = $("convoThread");
  const atBottom = t.scrollHeight - t.scrollTop - t.clientHeight < 40;
  t.replaceChildren();
  let prev = null;
  for (const m of messages) {
    const kind = m.role === "user" ? "person" : m.role === "counsellor" ? (m.name === state.me.name ? "self" : "self other") : "ai";
    const label = m.role === "user" ? "Person" : m.role === "counsellor" ? `${m.name} · Counsellor` : "Solace · AI";
    if (label !== prev) t.appendChild(el("div", `who${m.role === "user" ? "" : " right"}`, label));
    t.appendChild(el("div", `bubble ${kind}`, m.text));
    prev = label;
  }
  if (!messages.length) t.appendChild(el("p", "empty-q", "They haven't written anything yet."));
  if (atBottom || !prev) t.scrollTop = t.scrollHeight;
}

function renderInfo(view) {
  const risk = view.handoff.risk_level;
  $("infoRisk").className = `risk ${risk}`;
  $("infoRisk").textContent = risk;
  $("infoRiskNote").textContent = RISK_NOTES[risk] || "";

  const map = $("infoMap");
  map.replaceChildren();
  const byType = {};
  for (const n of view.graph.nodes) (byType[n.type] ||= []).push(n.label);
  for (const [type, name] of Object.entries(NODE_NAMES)) {
    if (!byType[type]) continue;
    map.appendChild(el("div", "chip-type", name));
    const chips = el("div", "chips");
    for (const label of byType[type]) chips.appendChild(el("span", "chip", label));
    map.appendChild(chips);
  }
  if (!view.graph.nodes.length) map.appendChild(el("p", "small", "Nothing mapped yet."));
  map.appendChild(el("p", "small", `Understanding: ${Math.round(view.coverage * 100)}%`));

  const lines = $("infoLines");
  lines.replaceChildren();
  for (const r of view.resources) {
    const row = el("div", "line-row");
    row.append(el("span", null, r.name), el("strong", null, r.contact));
    lines.appendChild(row);
  }
}

$("backBtn").addEventListener("click", () => {
  $("dashView").classList.remove("open");
  state.selected = null;
  renderQueue();
});

$("acceptBtn").addEventListener("click", async () => {
  try {
    await api(`/api/counsellor/handoffs/${state.selected}/accept`, { method: "POST" });
  } catch {
    alert("Someone else already accepted this chat.");
  }
  await Promise.all([loadQueue(), loadDetail()]);
  $("replyInput").focus();
});

/* reply */
function updateSend() {
  $("replySend").disabled = $("replyInput").disabled || !$("replyInput").value.trim();
}
$("replyInput").addEventListener("input", () => {
  const i = $("replyInput");
  i.style.height = "auto";
  i.style.height = `${Math.min(i.scrollHeight, 160)}px`;
  updateSend();
});
$("replyInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("replyForm").requestSubmit(); }
});
$("replyForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("replyInput").value.trim();
  if (!text || $("replyInput").disabled) return;
  $("replyInput").value = "";
  updateSend();
  try {
    await api(`/api/counsellor/handoffs/${state.selected}/messages`, { method: "POST", body: JSON.stringify({ text }) });
  } catch {
    $("replyInput").value = text;
    $("replyNote").textContent = "Couldn't send. Check your connection and try again.";
  }
  await loadDetail();
});

/* end */
$("closeBtn").addEventListener("click", () => { $("closeNote").value = ""; $("closeDialog").showModal(); });
$("closeCancel").addEventListener("click", () => $("closeDialog").close());
$("closeConfirm").addEventListener("click", async () => {
  $("closeDialog").close();
  try {
    await api(`/api/counsellor/handoffs/${state.selected}/close`, { method: "POST", body: JSON.stringify({ note: $("closeNote").value }) });
  } catch { /* already closed */ }
  await Promise.all([loadQueue(), loadDetail()]);
});

/* ---------- live updates ---------- */
function connect() {
  state.live?.close();
  state.live = new EventSource("/api/counsellor/live");
  state.live.onmessage = async (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch { return; }
    if (ev.type !== "updated") return;
    await loadQueue().catch(() => {});
    if (ev.handoff_id === state.selected) await loadDetail();
  };
  state.live.onerror = async () => {
    // EventSource retries by itself; if the login expired, show the sign-in screen.
    try { await api("/api/counsellor/me"); } catch { /* handled in api() */ }
  };
}

async function start(me) {
  state.me = me;
  $("meLine").textContent = `Signed in as ${me.name}`;
  $("loginView").hidden = true;
  $("dashView").hidden = false;
  connect();
  await loadQueue();
  setInterval(() => loadQueue().catch(() => {}), 60000); // keeps waiting times fresh
}

/* ---------- boot ---------- */
fetch("/api/counsellor/me").then(async (res) => (res.ok ? start(await res.json()) : showLogin())).catch(showLogin);
