const ui = {
  start: document.querySelector("#start"),
  stop: document.querySelector("#stop"),
  submit: document.querySelector("#submit"),
  typed: document.querySelector("#typed"),
  language: document.querySelector("#language"),
  status: document.querySelector("#status"),
  dot: document.querySelector("#dot"),
  meter: document.querySelector("#meter"),
  final: document.querySelector("#final"),
  partial: document.querySelector("#partial"),
  question: document.querySelector("#question"),
  state: document.querySelector("#state"),
  events: document.querySelector("#events"),
  alert: document.querySelector("#alert"),
  flowStage: document.querySelector("#flowStage"),
  flowHeadline: document.querySelector("#flowHeadline"),
  flowChoices: document.querySelector("#flowChoices"),
  engine: document.querySelector("#engine"),
};

let socket;
let connecting;
let reconnectTimer;
let stopped = false;
let sessionId = null;
let mediaStream;
let audioContext;
let captureNode;
let captureSource;
let pendingPcm = new Int16Array(0);
let aiSpeaking = false;
let speechFrames = 0;
let bargeInSent = false;
let playbackTime = 0;
const playbackSources = new Set();

function event(message) {
  const row = document.createElement("div");
  row.className = "event";
  row.textContent = `${new Date().toLocaleTimeString()} — ${message}`;
  ui.events.prepend(row);
}

function setStatus(text, live = false) {
  ui.status.textContent = text;
  ui.dot.classList.toggle("live", live);
}

function websocketUrl() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/ws/session`;
}

async function connectSocket() {
  if (socket?.readyState === WebSocket.OPEN) return;
  if (connecting) return connecting;
  stopped = false;
  clearTimeout(reconnectTimer);
  const current = new WebSocket(websocketUrl() + (sessionId ? `?resume=${encodeURIComponent(sessionId)}` : ""));
  socket = current;
  current.binaryType = "arraybuffer";
  current.addEventListener("message", handleMessage);
  current.addEventListener("close", () => {
    if (socket !== current) return;
    setStatus(stopped ? "Stopped" : "Disconnected");
    if (!stopped) reconnectTimer = setTimeout(() => connectSocket().catch(() => {}), 2000);
  });
  connecting = new Promise((resolve, reject) => {
    current.addEventListener("open", () => { setStatus("Connected", true); resolve(); }, { once: true });
    current.addEventListener("error", reject, { once: true });
    current.addEventListener("close", reject, { once: true });
  });
  try { await connecting; } finally { connecting = null; }
}

async function start() {
  if (mediaStream?.active) return;
  try {
    await connectSocket();
    audioContext = audioContext || new AudioContext({ latencyHint: "interactive" });
    await audioContext.resume();
    await audioContext.audioWorklet.addModule("/static/pcm-worklet.js");
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    captureSource = audioContext.createMediaStreamSource(mediaStream);
    captureNode = new AudioWorkletNode(audioContext, "pcm-capture");
    captureNode.port.onmessage = captureAudio;
    captureSource.connect(captureNode);
    const silent = audioContext.createGain();
    silent.gain.value = 0;
    captureNode.connect(silent).connect(audioContext.destination);
    ui.start.disabled = true;
    ui.stop.disabled = false;
    setStatus("Listening", true);
    event("Microphone started with browser WebRTC AEC and noise suppression");
  } catch (error) {
    event(`Microphone start failed: ${error.message}`);
    setStatus("Microphone unavailable");
  }
}

function captureAudio({ data: { pcm, rms } }) {
  ui.meter.style.width = `${Math.min(100, rms * 900)}%`;
  if (rms > 0.025) {
    speechFrames += 1;
    if (speechFrames >= 2 && aiSpeaking && !bargeInSent) {
      bargeInSent = true;
      stopPlayback();
      sendJson({ type: "barge_in" });
      event("Local VAD detected barge-in; TTS stopped immediately");
    }
  } else {
    speechFrames = 0;
    if (!aiSpeaking) bargeInSent = false;
  }

  const combined = new Int16Array(pendingPcm.length + pcm.length);
  combined.set(pendingPcm);
  combined.set(pcm, pendingPcm.length);
  pendingPcm = combined;
  while (pendingPcm.length >= 1600) {
    const chunk = pendingPcm.slice(0, 1600);
    pendingPcm = pendingPcm.slice(1600);
    if (socket?.readyState === WebSocket.OPEN) socket.send(chunk.buffer);
  }
}

async function stop() {
  stopped = true;
  clearTimeout(reconnectTimer);
  pendingPcm = new Int16Array(0);
  mediaStream?.getTracks().forEach((track) => track.stop());
  captureSource?.disconnect();
  captureNode?.disconnect();
  stopPlayback();
  sendJson({ type: "session.stop" });
  socket?.close();
  ui.start.disabled = false;
  ui.stop.disabled = true;
  ui.meter.style.width = "0%";
  setStatus("Stopped");
}

function sendJson(payload) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
}

async function submitTyped() {
  await connectSocket();
  sendJson({
    type: "transcript.submit",
    text: ui.typed.value,
    language: ui.language.value === "auto" ? "en-IN" : ui.language.value,
  });
  event("Submitted typed transcript for pipeline testing");
}

function handleMessage({ data }) {
  const message = JSON.parse(data);
  switch (message.type) {
    case "session.id":
      sessionId = message.session_id;
      break;
    case "clinical.question":
      ui.question.textContent = message.text;
      break;
    case "session.ready":
      setStatus("Connected", true);
      const engine = message.providers.local
        ? "on-device (whisper.cpp STT + Piper/Flite TTS)"
        : message.providers.sarvam ? "Sarvam cloud" : "typed only";
      event(`Session ready — speech: ${engine}`);
      ui.engine.textContent = engine;
      break;
    case "configuration.required":
      event(message.message);
      break;
    case "transcript.partial":
      ui.partial.textContent = message.text;
      break;
    case "transcript.final":
      ui.final.textContent += `${message.text}\n`;
      ui.partial.textContent = "";
      break;
    case "clinical.processing":
      ui.question.textContent = "Processing clinical state…";
      break;
    case "clinical.turn":
      renderTurn(message.data);
      break;
    case "staff.alert":
      ui.alert.style.display = "block";
      ui.alert.textContent = `ALERT STAFF: ${message.alerts.map((a) => a.message).join(" ")}`;
      event("Deterministic red-flag rule requested a staff alert");
      break;
    case "vad":
      event(`${message.source} VAD: ${message.state}`);
      break;
    case "tts.start":
      aiSpeaking = true;
      bargeInSent = false;
      event("Speech playback started");
      break;
    case "tts.audio":
      playPcm(base64Bytes(message.audio), message.sample_rate);
      break;
    case "tts.end":
      aiSpeaking = playbackSources.size > 0;
      event("Speech audio received");
      break;
    case "tts.cancelled":
      stopPlayback();
      event(`TTS cancelled: ${message.reason}`);
      break;
    case "flow.screen":
      renderFlowScreen(message.data);
      break;
    case "flow.report":
      renderReport(message.data);
      break;
    case "error":
      event(`${message.stage} error: ${message.message}`);
      break;
  }
}

// The eight-step workflow. The server decides which stage is current and what input it takes;
// this only draws the choices and reports which one was pressed - no clinical logic here.
let flowStage = null;
let flowQuestionId = null;

function renderFlowScreen(screen) {
  if (screen.stage === "language") {
    ui.alert.style.display = "none";
    ui.final.textContent = "";
    ui.partial.textContent = "";
    ui.question.textContent = "";
    ui.state.textContent = "";
  }
  flowStage = screen.stage;
  flowQuestionId = screen.question_id || null;
  ui.flowStage.textContent = screen.stage;
  ui.flowHeadline.textContent = screen.headline || "";
  ui.flowHeadline.classList.toggle("alert", Boolean(screen.alert));
  ui.flowChoices.replaceChildren();

  for (const option of screen.options || []) {
    const button = document.createElement("button");
    button.className = "choice";
    button.textContent = option.label;
    button.addEventListener("click", () => chooseFlowOption(option.value));
    ui.flowChoices.appendChild(button);
  }

  // Stages with no fixed choices still need a way forward: skip ABHA, finish scanning documents.
  if (!(screen.options || []).length && ["abha", "documents"].includes(screen.stage)) {
    if (screen.stage === "abha") {
      const field = document.createElement("input");
      field.className = "choice-input";
      field.placeholder = "ABHA number (optional)";
      ui.flowChoices.appendChild(field);
      addFlowButton("Continue", () => sendJson({ type: "flow.abha", value: field.value.trim() }));
    } else {
      addFlowButton(screen.scan_label || "Scan", scanDocument);
      addFlowButton(screen.skip_label || "Done", () => sendJson({ type: "flow.next" }));
    }
  }
  event(`Stage: ${screen.stage} (${screen.input})`);
}

function addFlowButton(label, handler) {
  const button = document.createElement("button");
  button.className = "choice";
  button.textContent = label;
  button.addEventListener("click", handler);
  ui.flowChoices.appendChild(button);
}

function chooseFlowOption(value) {
  if (flowStage === "language") sendJson({ type: "flow.language", value });
  else if (flowStage === "who") sendJson({ type: "flow.who", value });
  else if (flowStage === "ayurveda") {
    sendJson({ type: "flow.ayurveda", question_id: flowQuestionId, value });
  }
}

async function scanDocument() {
  // Reuses the same /api/ocr endpoint the camera panel uses, then hands the lines to the flow.
  const video = document.querySelector("#camVideo");
  if (!video?.videoWidth) {
    event("Start the camera first, then press Scan");
    return;
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
  const body = new FormData();
  body.append("image", blob, "scan.jpg");
  try {
    const response = await fetch("/api/ocr", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Scan failed");
    if (flowStage !== "documents") return;
    sendJson({ type: "flow.document", lines: data.lines, seconds: data.seconds });
    event(`Scanned ${data.lines.length} lines in ${data.seconds}s`);
  } catch (error) {
    event(`Scan failed: ${error}`);
  }
}

function renderReport(report) {
  ui.flowHeadline.textContent =
    `${report.routing.queue} — ${report.routing.priority}`;
  ui.state.textContent = JSON.stringify(report, null, 2);
  event(`Report ready: ${report.routing.queue} (${report.routing.reason})`);
}

function renderTurn(turn) {
  ui.final.textContent += `${turn.transcript}\n`;
  ui.state.textContent = JSON.stringify(turn.state, null, 2);
  ui.question.textContent = turn.next_question || "Intake fields complete; hand over to staff.";
  if (!turn.should_alert_staff) ui.alert.style.display = "none";
  event(`Clinical state updated; next=${turn.next_question_id || "none"}`);
}

function base64Bytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function playPcm(bytes, sampleRate = 24000) {
  if (!audioContext) audioContext = new AudioContext({ latencyHint: "interactive" });
  const sampleCount = Math.floor(bytes.byteLength / 2);
  const samples = new Float32Array(sampleCount);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i < sampleCount; i += 1) samples[i] = view.getInt16(i * 2, true) / 32768;
  const buffer = audioContext.createBuffer(1, sampleCount, sampleRate);
  buffer.copyToChannel(samples, 0);
  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);
  const now = audioContext.currentTime;
  playbackTime = Math.max(playbackTime, now + 0.02);
  source.start(playbackTime);
  playbackTime += buffer.duration;
  playbackSources.add(source);
  source.onended = () => { playbackSources.delete(source); aiSpeaking = playbackSources.size > 0; };
}

function stopPlayback() {
  for (const source of playbackSources) {
    try { source.stop(); } catch (_) { /* already stopped */ }
  }
  playbackSources.clear();
  playbackTime = audioContext?.currentTime || 0;
  aiSpeaking = false;
}

ui.start.addEventListener("click", start);
ui.stop.addEventListener("click", stop);
ui.submit.addEventListener("click", submitTyped);

// Connect as soon as the page loads, not when the microphone starts. The workflow is touch-driven
// for its first three stages, so waiting for a mic click left the kiosk sitting on "connecting…"
// with no way to pick a language.
connectSocket().catch((error) => event(`Connect failed: ${error.message ?? error}`));

