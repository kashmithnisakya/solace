"use strict";

/* ---------- storage (never required: private mode must still work) ---------- */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* ignore */ } },
};

const $ = (id) => document.getElementById(id);
const thread = $("thread");
const input = $("input");
const sendBtn = $("send");
const statusEl = $("status");

const state = {
  sessionId: store.get("solace.session"),
  faith: store.get("solace.faith") || "",
  graph: { nodes: [], edges: [], domains: {} },
  resources: [],
  shownCare: false,
  busy: false,
};

const FAITHS = [["", "None"], ["buddhism", "Buddhism"], ["hinduism", "Hinduism"], ["islam", "Islam"], ["christianity", "Christianity"]];
const NODE_COLORS = { issue: "--red", emotion: "--orange", trigger: "--pink", person: "--accent", support: "--green", strength: "--teal" };
const NODE_NAMES = { issue: "Issue", emotion: "Feeling", trigger: "Trigger", person: "Person", support: "Support", strength: "Strength" };

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* ---------- thread rendering ---------- */
function scrollToEnd(smooth = true) {
  thread.scrollTo({ top: thread.scrollHeight, behavior: smooth ? "smooth" : "auto" });
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function addBubble(role, text) {
  const b = el("div", `bubble ${role === "user" ? "me" : "them"}`, text);
  thread.appendChild(b);
  scrollToEnd();
  return b;
}

function addStamp() {
  const now = new Date();
  const s = el("div", "stamp");
  const b = el("b", null, "Today ");
  s.append(b, document.createTextNode(now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })));
  thread.appendChild(s);
}

function typingBubble() {
  const b = el("div", "bubble them");
  b.setAttribute("aria-label", "Solace is typing");
  const dots = el("span", "typing-dots");
  dots.append(el("i"), el("i"), el("i"));
  b.appendChild(dots);
  thread.appendChild(b);
  scrollToEnd();
  return b;
}

function setTyping(on) {
  statusEl.textContent = on ? "typing…" : "Here for you";
  statusEl.classList.toggle("typing", on);
}

function telHref(contact) {
  const digits = contact.replace(/[^\d+]/g, "");
  return digits.length >= 3 ? `tel:${digits}` : null;
}

function addCareCard(resources, urgent) {
  const card = el("section", "care");
  card.setAttribute("aria-label", "Support lines");
  card.append(
    el("h3", null, urgent ? "You deserve support right now" : "You don't have to carry this alone"),
    el("p", null, "Free and confidential. Real people who want to help."),
  );
  for (const r of resources) {
    const row = el("div", "care-row");
    const info = el("div");
    info.append(el("strong", null, r.name), el("span", null, r.hours ? `${r.contact} · ${r.hours}` : r.contact));
    const href = telHref(r.contact) || r.url;
    if (href) {
      const a = el("a", `pill${href.startsWith("tel:") ? "" : " link"}`, href.startsWith("tel:") ? "Call" : "Open");
      a.href = href;
      if (!href.startsWith("tel:")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
      a.setAttribute("aria-label", `${a.textContent} ${r.name}`);
      row.append(info, a);
    } else {
      row.append(info);
    }
    card.appendChild(row);
  }
  thread.appendChild(card);
  scrollToEnd();
}

function greeting() {
  const h = new Date().getHours();
  const part = h < 5 ? "It's late, and I'm still here" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return `${part}. I'm Solace. Whatever's on your mind, big or small, I'm here to listen. How are you doing today?`;
}

function startFresh() {
  thread.replaceChildren();
  addStamp();
  addBubble("assistant", greeting());
}

/* ---------- conversation ---------- */
async function restore() {
  if (!state.sessionId) return startFresh();
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/messages`);
    const msgs = res.ok ? await res.json() : [];
    if (!msgs.length) return startFresh();
    thread.replaceChildren();
    addStamp();
    for (const m of msgs) addBubble(m.role, m.text);
    const g = await fetch(`/api/sessions/${state.sessionId}/graph`);
    if (g.ok) state.graph = (await g.json()).graph;
    scrollToEnd(false);
  } catch {
    startFresh();
  }
}

async function send(message) {
  state.busy = true;
  updateSendState();
  addBubble("user", message);
  setTyping(true);
  const typing = typingBubble();
  let bubble = null;
  let crisis = false;

  const write = (text) => {
    if (!bubble) { typing.remove(); bubble = addBubble("assistant", ""); }
    bubble.textContent += text;
    scrollToEnd(false);
  };

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: state.sessionId, faith: state.faith || null }),
    });
    if (res.status === 429) {
      const body = await res.json();
      write(body.message);
      addCareCard(body.resources, false);
      return;
    }
    if (!res.ok || !res.body) throw new Error(String(res.status));

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5));
        if (ev.type === "start") {
          state.sessionId = ev.session_id;
          store.set("solace.session", ev.session_id);
          state.resources = ev.resources;
          crisis = ev.risk_level === "high" || ev.risk_level === "imminent";
        } else if (ev.type === "delta") {
          write(ev.text);
        } else if (ev.type === "resources") {
          state.resources = ev.resources;
        } else if (ev.type === "done") {
          state.graph = ev.graph;
        }
      }
    }
    if (!bubble) write("I'm here.");
    if (state.resources.length && (crisis || !state.shownCare)) {
      addCareCard(state.resources, crisis);
      state.shownCare = true;
    }
  } catch {
    if (!bubble) typing.remove();
    addBubble("assistant", "I couldn't connect just now. Please try again in a moment. If you need someone right away, you can call 1926 any time.");
  } finally {
    setTyping(false);
    state.busy = false;
    updateSendState();
    input.focus();
  }
}

/* ---------- composer ---------- */
function autoGrow() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
}
function updateSendState() {
  sendBtn.disabled = state.busy || !input.value.trim();
}
input.addEventListener("input", () => { autoGrow(); updateSendState(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("composer").requestSubmit();
  }
});
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message || state.busy) return;
  input.value = "";
  autoGrow();
  send(message);
});

/* ---------- sheets ---------- */
function openSheet(d) { d.showModal(); }
document.querySelectorAll("dialog").forEach((d) => {
  d.addEventListener("click", (e) => { if (e.target === d && d.id !== "welcome") d.close(); }); // tap outside
  d.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => d.close()));
});

/* Welcome */
if (!store.get("solace.welcomed")) openSheet($("welcome"));
$("welcomeContinue").addEventListener("click", () => {
  store.set("solace.welcomed", "1");
  $("welcome").close();
  input.focus();
});
$("welcome").addEventListener("cancel", (e) => e.preventDefault());

/* Settings */
function renderSettings() {
  const support = $("supportList");
  support.replaceChildren();
  for (const r of state.allResources || []) {
    const li = el("li");
    const href = telHref(r.contact) || r.url;
    const row = el(href ? "a" : "div", "row");
    if (href) {
      row.href = href;
      if (!href.startsWith("tel:")) { row.target = "_blank"; row.rel = "noopener noreferrer"; }
    }
    const grow = el("div", "grow");
    grow.append(document.createTextNode(r.name), el("small", null, r.hours ? `${r.contact} · ${r.hours}` : r.contact));
    row.append(grow);
    if (href) row.append(el("span", "call", href.startsWith("tel:") ? "Call" : "Open"));
    li.appendChild(row);
    support.appendChild(li);
  }

  const list = $("faithList");
  list.replaceChildren();
  for (const [value, label] of FAITHS) {
    const li = el("li");
    const row = el("button", "row");
    row.type = "button";
    row.setAttribute("role", "radio");
    row.setAttribute("aria-checked", String(state.faith === value));
    row.append(el("span", "grow", label), el("span", "check", "✓"));
    row.addEventListener("click", () => {
      state.faith = value;
      store.set("solace.faith", value || null);
      renderSettings();
    });
    li.appendChild(row);
    list.appendChild(li);
  }
}
$("moreBtn").addEventListener("click", () => { renderSettings(); openSheet($("settingsSheet")); });

/* Delete */
$("deleteBtn").addEventListener("click", () => $("confirmDelete").showModal());
$("cancelDelete").addEventListener("click", () => $("confirmDelete").close());
$("confirmDeleteBtn").addEventListener("click", async () => {
  if (state.sessionId) {
    try { await fetch(`/api/sessions/${state.sessionId}`, { method: "DELETE" }); } catch { /* still clear locally */ }
  }
  state.sessionId = null;
  state.graph = { nodes: [], edges: [], domains: {} };
  state.shownCare = false;
  store.set("solace.session", null);
  $("confirmDelete").close();
  $("settingsSheet").close();
  startFresh();
});

/* Map */
let cy = null;
function renderLegend() {
  const legend = $("legend");
  legend.replaceChildren();
  for (const [type, name] of Object.entries(NODE_NAMES)) {
    const s = el("span");
    const dot = el("i");
    dot.style.background = cssVar(NODE_COLORS[type]);
    s.append(dot, document.createTextNode(name));
    legend.appendChild(s);
  }
}
function drawMap() {
  const box = $("map");
  const g = state.graph;
  const pct = Math.round((Object.keys(g.domains || {}).length / 11) * 100);
  $("progressFill").style.width = `${pct}%`;
  $("progress").setAttribute("aria-valuenow", String(pct));
  renderLegend();
  if (cy) { cy.destroy(); cy = null; }
  if (!g.nodes.length || typeof cytoscape === "undefined") {
    box.replaceChildren(el("div", "empty-map",
      g.nodes.length ? g.nodes.map((n) => n.label).join(" · ") : "Your map will grow as you share. Only you can see it."));
    return;
  }
  box.replaceChildren();
  const label = cssVar("--label");
  const line = cssVar("--label-3");
  cy = cytoscape({
    container: box,
    elements: [
      ...g.nodes.map((n) => ({ data: { id: n.id, label: n.label, color: cssVar(NODE_COLORS[n.type] || "--accent"),
        size: 22 + Math.min(n.mentions, 5) * 5 + n.severity * 6 } })),
      ...g.edges.map((e) => ({ data: { id: `${e.source}>${e.target}>${e.relation}`, source: e.source, target: e.target,
        label: e.relation.replace("_", " ") } })),
    ],
    style: [
      { selector: "node", style: { "background-color": "data(color)", width: "data(size)", height: "data(size)",
          label: "data(label)", color: label, "font-size": 12, "font-family": "-apple-system, system-ui, sans-serif",
          "text-valign": "bottom", "text-margin-y": 5, "text-wrap": "wrap", "text-max-width": 100,
          "border-width": 3, "border-color": "data(color)", "border-opacity": 0.25 } },
      { selector: "edge", style: { width: 1.5, "line-color": line, "target-arrow-color": line, "target-arrow-shape": "triangle",
          "curve-style": "bezier", label: "data(label)", "font-size": 10, color: line, "text-rotation": "autorotate",
          "text-background-color": cssVar("--grouped"), "text-background-opacity": 1, "text-background-padding": 2 } },
    ],
    layout: { name: "cose", animate: false, padding: 28, nodeRepulsion: 12000, idealEdgeLength: 90 },
    wheelSensitivity: 0.2,
  });
}
$("mapBtn").addEventListener("click", () => {
  openSheet($("mapSheet"));
  requestAnimationFrame(drawMap);
});

/* ---------- boot ---------- */
fetch("/api/resources").then((r) => r.json()).then((r) => { state.allResources = r; }).catch(() => {});
restore();
updateSendState();
