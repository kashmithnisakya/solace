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

function addCounsellorBubble(name, text) {
  const last = thread.lastElementChild;
  if (!(last && last.classList.contains("human"))) thread.appendChild(el("div", "sender", `${name} · Counsellor`));
  const b = el("div", "bubble them human", text);
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
  statusEl.textContent = on ? "typing…" : handoff.status === "active" ? "With a counsellor" : "Here for you";
  statusEl.classList.toggle("typing", on);
}

function telHref(contact) {
  const digits = contact.replace(/[^\d+]/g, "");
  return digits.length >= 3 ? `tel:${digits}` : null;
}

/* Citations: replies mark ideas from the knowledge base like [1]. We hide the markers and show
   the sources the reply actually used, as small links under the bubble. */
const MARKER = /\s?\[(\d+(?:\s*,\s*\d+)*)\]/g;
const PARTIAL_MARKER = /\s?\[[\d,\s]*$/; // a marker still arriving mid-stream

function cleanReply(raw, streaming = false) {
  const text = raw.replace(MARKER, "");
  return streaming ? text.replace(PARTIAL_MARKER, "") : text;
}

function citedSources(raw, sources) {
  const cited = new Set();
  for (const m of raw.matchAll(MARKER)) m[1].split(",").forEach((n) => cited.add(Number(n)));
  const seen = new Set();
  return sources.filter((s) => cited.has(s.n) && !seen.has(s.url) && seen.add(s.url));
}

function addSources(sources) {
  if (!sources.length) return;
  const box = el("div", "sources");
  box.appendChild(el("span", "sources-label", "Sources"));
  for (const s of sources) {
    const a = el("a", "source", s.title);
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = s.source;
    box.appendChild(a);
  }
  thread.appendChild(box);
  requestAnimationFrame(() => scrollToEnd(false)); // keep the sources in view once the reply settles
}

function addCareCard(resources, urgent) {
  const card = el("section", "care");
  card.setAttribute("aria-label", "Support lines");
  card.append(
    el("h3", null, urgent ? "You deserve support right now" : "You don't have to carry this alone"),
    el("p", null, "Free and confidential. Real people who want to help."),
  );
  if (!handoff.status) {
    const ask = el("button", "care-ask", "Chat with a counsellor here");
    ask.type = "button";
    ask.addEventListener("click", openHandoffSheet);
    card.appendChild(ask);
  }
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
    for (const m of msgs) {
      if (m.role === "counsellor") addCounsellorBubble(m.name, m.text); else addBubble(m.role, m.text);
    }
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
  const withPerson = handoff.status === "active"; // a counsellor replies in their own time
  if (!withPerson) setTyping(true);
  const typing = withPerson ? el("div") : typingBubble();
  let bubble = null;
  let crisis = false;
  let raw = "";
  let sources = [];

  const write = (text) => {
    if (!bubble) { typing.remove(); bubble = addBubble("assistant", ""); }
    raw += text;
    bubble.textContent = cleanReply(raw, true);
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
          if (ev.human) { typing.remove(); bubble = typing; } // a counsellor is here; Solace stays quiet
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
          sources = ev.sources || [];
        }
      }
    }
    if (!bubble) write("I'm here.");
    bubble.textContent = cleanReply(raw);
    addSources(citedSources(raw, sources));
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
  const hasText = Boolean(input.value.trim());
  sendBtn.disabled = state.busy || !hasText;
  // Like Messages: the voice button sits where Send goes until you start typing.
  sendBtn.hidden = !hasText;
  $("voiceBtn").hidden = hasText;
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
  d.addEventListener("click", (e) => { if (e.target === d && d.id !== "welcome" && d.id !== "callSheet") d.close(); }); // tap outside
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
$("settingsHandoff").addEventListener("click", () => { $("settingsSheet").close(); openHandoffSheet(); });

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
  setHandoff(null);
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

/* ---------- voice call ---------- */
/*
 * The browser talks to OpenAI's Realtime API directly over WebRTC (audio never passes through our
 * server). Our server hands out a short-lived key, then screens every finished transcript for risk
 * and tells us when to switch Solace into crisis mode mid-call.
 */
const call = {
  pc: null, dc: null, mic: null, audio: null, ctx: null, raf: 0, tick: 0,
  startedAt: 0, crisis: false, muted: false, active: false,
  pending: new Map(), // user item_id -> { bubble, done: Promise, resolve }
  replies: new Map(), // response_id -> assistant bubble
  caption: "",
};

const callStatus = (text) => { $("callStatus").textContent = text; };
// Live captions follow the latest words, starting at a sentence when the reply gets long.
function setCaption(text) {
  let shown = text.replace(/\s+/g, " ").trim();
  if (shown.length > 150) {
    const tail = shown.slice(-150);
    const start = tail.search(/[.!?]\s+\S/);
    shown = start >= 0 ? tail.slice(start + 1).trim() : `…${tail.trim()}`;
  }
  $("captions").textContent = shown;
}

function addNotice(text) {
  thread.appendChild(el("div", "notice", text));
  scrollToEnd();
}

function fmtTime(ms) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function showCallCare(resources) {
  if (!resources?.length) return;
  const list = $("callCareList");
  list.replaceChildren();
  for (const r of resources.slice(0, 3)) {
    const href = telHref(r.contact);
    if (!href) continue;
    const a = el("a", "pill", `Call ${r.name.split(" (")[0]}`);
    a.href = href;
    a.setAttribute("aria-label", `Call ${r.name}, ${r.contact}`);
    list.appendChild(a);
  }
  $("callCare").hidden = !list.children.length;
  $("callSheet").classList.toggle("care-on", !$("callCare").hidden);
}

function sendEvent(ev) {
  if (call.dc?.readyState === "open") call.dc.send(JSON.stringify(ev));
}

async function postTurn(role, text) {
  const res = await fetch("/api/voice/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, role, text, faith: state.faith || null }),
  });
  return res.status === 200 ? res.json() : null;
}

async function onUserTranscript(itemId, text) {
  const p = call.pending.get(itemId);
  const words = (text || "").trim();
  if (p) {
    if (words) p.bubble.textContent = words; else p.bubble.remove();
  } else if (words) {
    addBubble("user", words);
  }
  try {
    if (!words) return;
    const turn = await postTurn("user", words);
    if (!turn || !call.active) return;
    state.resources = turn.resources;
    sendEvent({ type: "session.update", session: { type: "realtime", instructions: turn.instructions } });
    if (turn.in_crisis && !call.crisis) {
      // Risk found: stop whatever ordinary reply is playing and answer again in crisis mode.
      sendEvent({ type: "response.cancel" });
      sendEvent({ type: "output_audio_buffer.clear" });
      sendEvent({ type: "response.create" });
      addCareCard(turn.resources, true);
      state.shownCare = true;
    }
    call.crisis = turn.in_crisis;
    if (turn.resources.length) showCallCare(turn.resources);
  } catch { /* the call carries on; the transcript just isn't saved */ } finally {
    p?.resolve();
    call.pending.delete(itemId);
  }
}

async function onAssistantTranscript(text, responseId) {
  const words = (text || "").trim();
  if (!words) return;
  call.replies.set(responseId, addBubble("assistant", words));
  // Save in order: wait until what the person said before this has been saved.
  await Promise.all([...call.pending.values()].map((p) => p.done));
  try { await postTurn("assistant", words); } catch { /* ignore */ }
}

function onRealtimeEvent(msg) {
  let ev;
  try { ev = JSON.parse(msg.data); } catch { return; }
  switch (ev.type) {
    case "input_audio_buffer.speech_started":
      callStatus(call.muted ? "Muted" : "Listening…");
      break;
    case "input_audio_buffer.committed": {
      // Hold this message's place in the thread, so the order stays right if transcription is slow.
      const bubble = addBubble("user", "…");
      let resolve;
      const done = new Promise((r) => { resolve = r; });
      call.pending.set(ev.item_id, { bubble, done, resolve });
      break;
    }
    case "conversation.item.input_audio_transcription.completed":
      onUserTranscript(ev.item_id, ev.transcript);
      break;
    case "conversation.item.input_audio_transcription.failed":
      onUserTranscript(ev.item_id, "");
      break;
    case "response.created":
      call.caption = "";
      break;
    case "response.output_audio_transcript.delta":
      call.caption += ev.delta || "";
      callStatus("Speaking");
      setCaption(call.caption);
      break;
    case "response.output_audio_transcript.done":
      onAssistantTranscript(ev.transcript, ev.response_id);
      break;
    case "response.done": {
      // Interrupted replies (the person spoke over Solace, or a crisis switch) show where they stopped.
      const bubble = call.replies.get(ev.response?.id);
      if (bubble && ev.response.status !== "completed") bubble.textContent += "…";
      call.replies.delete(ev.response?.id);
      callStatus(call.muted ? "Muted" : "Listening");
      break;
    }
    case "error":
      if (ev.error?.code !== "response_cancel_not_active") console.warn("voice:", ev.error?.message);
      break;
    default:
  }
}

function level(analyser, buf) {
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
  return Math.min(1, Math.sqrt(sum / buf.length) * 4);
}

function animateLevels(remote) {
  try {
    call.ctx = new AudioContext();
    const make = (stream) => {
      const a = call.ctx.createAnalyser();
      a.fftSize = 512;
      call.ctx.createMediaStreamSource(stream).connect(a);
      return [a, new Uint8Array(a.fftSize)];
    };
    const [out, outBuf] = make(remote);
    const [mic, micBuf] = make(call.mic);
    const orb = $("orb");
    const halo = $("orbHalo");
    const frame = () => {
      orb.style.setProperty("--level", level(out, outBuf).toFixed(3));
      halo.style.setProperty("--mic", call.muted ? "0" : level(mic, micBuf).toFixed(3));
      call.raf = requestAnimationFrame(frame);
    };
    frame();
  } catch { /* the orb just stays still */ }
}

async function startCall() {
  if (call.active) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
    addNotice("Voice isn't supported in this browser. You can keep typing, I'm here.");
    return;
  }
  Object.assign(call, { active: true, crisis: false, muted: false, caption: "", pending: new Map(), replies: new Map() });
  $("muteBtn").setAttribute("aria-pressed", "false");
  $("callCare").hidden = true;
  $("callSheet").classList.remove("care-on");
  $("callTimer").textContent = "0:00";
  callStatus("Connecting…");
  setCaption("Speak whenever you're ready.");
  $("callSheet").showModal();

  try {
    call.mic = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    endCall(false);
    addNotice("Solace needs microphone access for voice. You can allow it in your browser settings, or keep typing.");
    return;
  }

  try {
    const res = await fetch("/api/voice/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, faith: state.faith || null }),
    });
    if (res.status === 409) {
      endCall(false);
      addNotice("Voice is paused while you're chatting with a counsellor.");
      return;
    }
    if (res.status === 429) {
      const body = await res.json();
      endCall(false);
      addBubble("assistant", body.message);
      addCareCard(body.resources, false);
      return;
    }
    if (!res.ok) throw new Error(String(res.status));
    const session = await res.json();
    if (!call.active) return;
    state.sessionId = session.session_id;
    store.set("solace.session", session.session_id);

    const pc = new RTCPeerConnection();
    call.pc = pc;
    call.audio = new Audio();
    call.audio.autoplay = true;
    pc.ontrack = (e) => {
      call.audio.srcObject = e.streams[0];
      animateLevels(e.streams[0]);
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
        if (call.active) { endCall(); addNotice("The call dropped. You can start it again, or keep typing."); }
      }
    };
    pc.addTrack(call.mic.getAudioTracks()[0], call.mic);

    call.dc = pc.createDataChannel("oai-events");
    call.dc.onmessage = onRealtimeEvent;
    call.dc.onopen = () => {
      call.startedAt = Date.now();
      call.tick = setInterval(() => { $("callTimer").textContent = fmtTime(Date.now() - call.startedAt); }, 500);
      callStatus("Listening");
      addStamp();
      // Solace picks up like a friend answering the phone.
      sendEvent({ type: "response.create" });
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const answer = await fetch("https://api.openai.com/v1/realtime/calls", {
      method: "POST",
      body: offer.sdp,
      headers: { Authorization: `Bearer ${session.client_secret}`, "Content-Type": "application/sdp" },
    });
    if (!answer.ok) throw new Error(String(answer.status));
    if (!call.active) return;
    await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });
  } catch {
    endCall(false);
    addNotice("I couldn't start a voice call just now. You can keep typing, or try again in a moment.");
  }
}

function endCall(summary = true) {
  if (!call.active) return;
  call.active = false;
  const duration = call.startedAt ? Date.now() - call.startedAt : 0;
  clearInterval(call.tick);
  cancelAnimationFrame(call.raf);
  try { call.dc?.close(); } catch { /* ignore */ }
  try { call.pc?.close(); } catch { /* ignore */ }
  call.mic?.getTracks().forEach((t) => t.stop());
  call.ctx?.close().catch(() => {});
  if (call.audio) call.audio.srcObject = null;
  for (const p of call.pending.values()) { if (p.bubble.textContent === "…") p.bubble.remove(); p.resolve(); }
  Object.assign(call, { pc: null, dc: null, mic: null, audio: null, ctx: null, startedAt: 0 });
  if ($("callSheet").open) $("callSheet").close();
  if (summary && duration > 0) addNotice(`Voice call · ${fmtTime(duration)}`);
}

function toggleMute() {
  call.muted = !call.muted;
  call.mic?.getAudioTracks().forEach((t) => { t.enabled = !call.muted; });
  $("muteBtn").setAttribute("aria-pressed", String(call.muted));
  $("muteBtn").setAttribute("aria-label", call.muted ? "Unmute" : "Mute");
  callStatus(call.muted ? "Muted" : "Listening");
}

$("voiceBtn").addEventListener("click", startCall);
$("endBtn").addEventListener("click", () => endCall());
$("muteBtn").addEventListener("click", toggleMute);
$("callSheet").addEventListener("cancel", (e) => { e.preventDefault(); endCall(); });
window.addEventListener("pagehide", () => endCall(false));

/* ---------- talking to a real person ---------- */
const handoff = { status: null, name: null, live: null };

function newSessionId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function setHandoff(status, name = null) {
  handoff.status = status;
  handoff.name = name || handoff.name;
  const bar = $("handoffBar");
  bar.hidden = !status;
  bar.classList.toggle("active", status === "active");
  if (status === "requested") {
    $("handoffText").textContent = "Waiting for a counsellor. Solace is here meanwhile.";
    $("handoffEnd").textContent = "Cancel";
  } else if (status === "active") {
    $("handoffText").textContent = `${handoff.name} is here with you`;
    $("handoffEnd").textContent = "End Chat";
  }
  statusEl.textContent = status === "active" ? "With a counsellor" : "Here for you";
  if (status) listen(); else stopListening();
}

function listen() {
  if (handoff.live || !state.sessionId) return;
  handoff.live = new EventSource(`/api/sessions/${state.sessionId}/live`);
  handoff.live.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch { return; }
    if (ev.type === "message" && ev.role === "counsellor") {
      addCounsellorBubble(ev.name, ev.text);
    } else if (ev.type === "handoff" && ev.status === "active") {
      setHandoff("active", ev.name);
      addNotice(`${ev.name}, a counsellor, joined the chat`);
    } else if (ev.type === "handoff" && ev.status === "closed") {
      const who = handoff.name;
      setHandoff(null);
      addNotice(ev.by === "person" ? "You ended the chat." : `${who || "The counsellor"} left the chat. Solace is here with you again.`);
    }
  };
}

function stopListening() {
  handoff.live?.close();
  handoff.live = null;
}

async function openHandoffSheet() {
  const avail = $("handoffAvail");
  avail.textContent = "";
  avail.classList.remove("online");
  openSheet($("handoffSheet"));
  try {
    const { online } = await (await fetch("/api/handoff/availability")).json();
    avail.classList.toggle("online", online > 0);
    avail.textContent = online > 0
      ? "A counsellor is online now."
      : "No counsellors are online right now. Your request will wait for the next one. If you need someone now, the free lines in Settings are open.";
  } catch { /* still allow asking */ }
}

$("handoffConfirm").addEventListener("click", async () => {
  if (!state.sessionId) {
    state.sessionId = newSessionId();
    store.set("solace.session", state.sessionId);
  }
  $("handoffSheet").close();
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/handoff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: true }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const body = await res.json();
    setHandoff(body.status, body.counsellor);
    addNotice("You asked for a counsellor. They'll see this conversation when they join.");
  } catch {
    addNotice("I couldn't reach a counsellor just now. Please try again, or call 1926 to talk to someone.");
  }
});

$("handoffEnd").addEventListener("click", async () => {
  if (!state.sessionId) return;
  const was = handoff.status;
  try { await fetch(`/api/sessions/${state.sessionId}/handoff`, { method: "DELETE" }); } catch { /* ignore */ }
  setHandoff(null);
  addNotice(was === "active" ? "You ended the chat with the counsellor. Solace is here with you." : "Request cancelled.");
});

async function restoreHandoff() {
  if (!state.sessionId) return;
  try {
    const h = await (await fetch(`/api/sessions/${state.sessionId}/handoff`)).json();
    if (h.status) setHandoff(h.status, h.counsellor);
  } catch { /* ignore */ }
}

/* ---------- boot ---------- */
fetch("/api/resources").then((r) => r.json()).then((r) => { state.allResources = r; }).catch(() => {});
restore().then(restoreHandoff);
updateSendState();
