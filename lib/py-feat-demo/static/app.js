const state = {
  labels: { emotions: [], aus: [], au_descriptions: {} },
  stream: null,
  modelReady: false,
  running: false,
  paused: false,
  recording: false,
  inFlight: false,
  sessionId: 0,
  lastRequestAt: 0,
  latestFrame: null,
  vaTrail: [],
  sessions: [],
  viewerFrames: [],
  selectedSessionId: "",
  analyzePayload: null,
  overlayGeometry: { edges: {}, auMesh: { triangles: [], vertexAUs: {} } },
};

const LIVE_JPEG_QUALITY = 0.78;
const BLOB_FALLBACK_MS = 80;
const MAX_LIVE_AU_SHADE_REGIONS = 6;

const el = (id) => document.getElementById(id);
const video = el("camera");
const mirror = el("mirror");
const captureCanvas = el("captureCanvas");
const overlayCanvas = el("overlayCanvas");
const resultFrame = document.querySelector(".result-frame");

function setText(id, text) {
  const target = el(id);
  if (target) {
    target.textContent = text;
  }
}

function clamp(value, min, max) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : min;
}

function numberText(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function parseResolution(value) {
  const [width, height] = String(value || "640x480").split("x").map(Number);
  return { width: width || 640, height: height || 480 };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function setStatus(text) {
  if (text === "Analyzing..." || text === "Waiting" || String(text).startsWith("Frame ")) {
    return;
  }
  setText("cameraStatus", text);
}

function updateRunButtons() {
  if (el("startBtn")) el("startBtn").disabled = state.running;
  if (el("pauseBtn")) el("pauseBtn").disabled = !state.running;
  if (el("stopBtn")) el("stopBtn").disabled = !state.running;
  if (el("recordBtn")) el("recordBtn").disabled = !state.running;
  setText("pauseBtn", state.paused ? "Resume" : "Pause");
  setText("recordBtn", state.recording ? "Stop Record" : "Record");
}

function switchView(viewName) {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === viewName);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.viewPanel === viewName);
  });
  if (viewName === "viewer") {
    loadSessions();
  }
  if (viewName === "analyze") {
    loadQueue();
  }
  if (viewName === "settings") {
    loadSystemPanels();
  }
}

function sortedEntries(values) {
  const entries = Array.isArray(values)
    ? values.map((item) => [item.label || item.code || item.name, item.value])
    : Object.entries(values || {});
  return entries
    .filter(([name]) => name)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
}

function renderBars(container, values, options = {}) {
  const descriptions = options.descriptions || {};
  const sorted = sortedEntries(values).slice(0, options.limit || Infinity);

  container.innerHTML = "";
  for (const [name, rawValue] of sorted) {
    const value = clamp(rawValue, 0, 1);
    const row = document.createElement("div");
    const line = document.createElement("div");
    const label = document.createElement("span");
    const track = document.createElement("div");
    const fill = document.createElement("div");
    const score = document.createElement("span");

    row.className = "metric-row";
    line.className = "metric-line";
    label.className = "metric-name";
    track.className = "bar-track";
    fill.className = "bar-fill";
    score.className = "metric-value";

    const description = descriptions[name] || "";
    label.textContent = description ? `${name} - ${description}` : name;
    if (description) {
      row.classList.add("with-description");
    }
    fill.style.width = `${(value * 100).toFixed(1)}%`;
    score.textContent = value.toFixed(2);

    track.appendChild(fill);
    line.append(label, track, score);
    row.appendChild(line);
    container.appendChild(row);
  }
}

function renderPrimaryEmotion(values) {
  const [name, rawValue] = sortedEntries(values)[0] || ["neutral", 0];
  const value = clamp(rawValue, 0, 1);
  setText("primaryEmotion", `${value > 0 ? name : "neutral"} ${value.toFixed(2)}`);
}

function renderActiveAUs(values) {
  const descriptions = state.labels.au_descriptions || {};
  const entries = sortedEntries(values);
  const active = entries.filter(([, value]) => Number(value || 0) >= 0.08).slice(0, 4);
  const list = el("activeAuList");
  if (!list) {
    return;
  }
  list.innerHTML = "";
  setText("activeAuCount", String(active.length));
  const [topName, topValue] = entries[0] || ["none", 0];
  setText("topAuText", topName === "none" ? "none" : `${topName} ${clamp(topValue, 0, 1).toFixed(2)}`);
  if (!active.length) {
    list.innerHTML = '<div class="empty-row compact-empty">No active AU above threshold.</div>';
    return;
  }
  for (const [name, rawValue] of active) {
    const value = clamp(rawValue, 0, 1);
    const row = document.createElement("div");
    row.className = "active-au-row";
    row.innerHTML = `
      <div>
        <strong>${name}</strong>
        <span>${descriptions[name] || "No description available"}</span>
      </div>
      <em>${value.toFixed(2)}</em>
    `;
    list.appendChild(row);
  }
}

function renderEmptyMetrics() {
  const emptyEmotions = Object.fromEntries((state.labels.emotions || []).map((label) => [label, 0]));
  renderPrimaryEmotion(emptyEmotions);
  renderBars(el("emotionList"), emptyEmotions, { limit: 3 });
  renderActiveAUs({});
  renderBars(
    el("auList"),
    Object.fromEntries((state.labels.aus || []).map((code) => [code, 0])),
    { descriptions: state.labels.au_descriptions || {} },
  );
  renderBars(el("blendshapeList"), {});
  setText("faceCountText", "0");
  setText("posePitch", "0.00");
  setText("poseRoll", "0.00");
  setText("poseYaw", "0.00");
  setText("gazeText", "0.00, 0.00, 1.00");
  setText("landmarkCount", "0");
  setText("landmarkToggleCount", "0");
}

async function loadStatus() {
  try {
    const body = await fetchJson("/api/status?autoload=0");
    state.labels = body.labels || state.labels;
    state.modelReady = Boolean(body.ready) && body.state !== "error";
    setText("modelState", body.state || "unknown");
    setText("deviceBadge", body.device || "auto");
    setText("cameraStatus", body.error || (body.ready ? "Model ready." : "Ready to start model."));
    updateRunButtons();
    renderEmptyMetrics();
    if (body.state === "loading") {
      window.setTimeout(loadStatus, 1500);
    }
  } catch (error) {
    state.modelReady = false;
    setText("modelState", "error");
    setText("cameraStatus", error.message || "Status check failed.");
    updateRunButtons();
  }
}

async function loadPresets() {
  const payload = await fetchJson("/api/presets");
  const presetSelect = el("presetSelect");
  presetSelect.innerHTML = "";
  for (const preset of payload.presets || []) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.name;
    option.dataset.detectorType = preset.detector_type;
    option.dataset.detectionSize = preset.detection_size;
    option.dataset.maxFps = preset.max_fps || "";
    presetSelect.appendChild(option);
  }
  renderPresetList(payload.presets || []);
}

async function loadOverlayGeometry() {
  state.overlayGeometry = await fetchJson("/api/system/overlay-geometry");
  drawOverlay();
}

async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return;
  }
  try {
    const previous = el("cameraSelect").value;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === "videoinput");
    el("cameraSelect").innerHTML = "";
    for (const [index, camera] of cameras.entries()) {
      const option = document.createElement("option");
      option.value = camera.deviceId;
      option.textContent = camera.label || `Camera ${index + 1}`;
      el("cameraSelect").appendChild(option);
    }
    if (cameras.some((camera) => camera.deviceId === previous)) {
      el("cameraSelect").value = previous;
    }
  } catch (error) {
    setText("cameraStatus", error.message || "Could not list cameras.");
  }
}

async function configureLive() {
  const presetOption = el("presetSelect").selectedOptions[0];
  if (presetOption?.dataset.maxFps) {
    const interval = Math.max(16, Math.round(1000 / Number(presetOption.dataset.maxFps || 30)));
    el("intervalInput").value = String(interval);
  }
  const payload = {
    preset_id: el("presetSelect").value || "v2-standard",
    detector_type: presetOption?.dataset.detectorType || "Detectorv2",
    device: el("deviceSelect").value || "auto",
    detection_size: Number(el("detectionSizeInput").value || presetOption?.dataset.detectionSize || 640),
  };
  const configured = await fetchJson("/api/live/configure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  setText("deviceBadge", configured.analyzer?.device || payload.device);
  await syncLiveHints();
  return configured;
}

async function syncLiveHints() {
  return fetchJson("/api/live/hints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      blendshapes: Boolean(el("blendshapeToggle")?.checked),
    }),
  }).catch(() => null);
}

async function waitForAnalyzerReady(timeoutMs = 180000) {
  const started = performance.now();
  while (performance.now() - started < timeoutMs) {
    const snapshot = await fetchJson("/api/status?autoload=0");
    state.modelReady = Boolean(snapshot.ready) && snapshot.state !== "error";
    setText("modelState", snapshot.state || "unknown");
    setText("deviceBadge", snapshot.device || "auto");
    setText("cameraStatus", snapshot.error || (snapshot.ready ? "Model ready." : "Loading model..."));
    updateRunButtons();
    if (snapshot.ready) {
      return snapshot;
    }
    if (snapshot.state === "error") {
      throw new Error(snapshot.error || "model loading failed");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
  }
  throw new Error("model loading timed out");
}

function drawCaptureFrame() {
  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;
  const targetWidth = clamp(Number(el("detectionSizeInput").value || 640), 160, 1280);
  const scale = Math.min(1, targetWidth / width);
  captureCanvas.width = Math.round(width * scale);
  captureCanvas.height = Math.round(height * scale);
  const context = captureCanvas.getContext("2d");
  context.save();
  if (el("flipSelect").value === "on") {
    context.translate(captureCanvas.width, 0);
    context.scale(-1, 1);
  }
  context.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
  context.restore();
  return captureCanvas;
}

function captureFrame() {
  drawCaptureFrame();
  return captureCanvas.toDataURL("image/jpeg", 0.82);
}

function dataUrlToBlob(dataUrl) {
  const commaIndex = dataUrl.indexOf(",");
  if (commaIndex < 0) {
    throw new Error("Could not encode frame");
  }
  const binary = atob(dataUrl.slice(commaIndex + 1));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: "image/jpeg" });
}

function canvasToJpegBlob(canvas, quality = LIVE_JPEG_QUALITY) {
  if (!canvas.toBlob) {
    return Promise.resolve(dataUrlToBlob(canvas.toDataURL("image/jpeg", quality)));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (blob) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(fallbackTimer);
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error("Could not encode frame"));
      }
    };
    const fallbackTimer = window.setTimeout(() => {
      try {
        finish(dataUrlToBlob(canvas.toDataURL("image/jpeg", quality)));
      } catch (error) {
        reject(error);
      }
    }, BLOB_FALLBACK_MS);
    canvas.toBlob((blob) => finish(blob), "image/jpeg", quality);
  });
}

function captureFrameBlob() {
  drawCaptureFrame();
  return canvasToJpegBlob(captureCanvas);
}

function clearOverlay() {
  const context = overlayCanvas.getContext("2d");
  overlayCanvas.width = overlayCanvas.clientWidth || 0;
  overlayCanvas.height = overlayCanvas.clientHeight || 0;
  context.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function overlayMapping(canvas = overlayCanvas, frame = state.latestFrame) {
  const source = frame?.frame || [captureCanvas.width || 640, captureCanvas.height || 480];
  const sourceWidth = source[0] || 640;
  const sourceHeight = source[1] || 480;
  const scale = Math.min(canvas.width / sourceWidth, canvas.height / sourceHeight);
  const drawnWidth = sourceWidth * scale;
  const drawnHeight = sourceHeight * scale;
  return {
    scale,
    offsetX: (canvas.width - drawnWidth) / 2,
    offsetY: (canvas.height - drawnHeight) / 2,
  };
}

function drawFacePayload(canvas, framePayload, options = {}) {
  const context = canvas.getContext("2d");
  canvas.width = options.width || canvas.clientWidth || canvas.width;
  canvas.height = options.height || canvas.clientHeight || canvas.height;
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (options.background) {
    context.fillStyle = "#101416";
    context.fillRect(0, 0, canvas.width, canvas.height);
  }
  const mapping = overlayMapping(canvas, framePayload);
  const faces = framePayload?.faces || [];
  for (const face of faces) {
    const rect = face.rect || [0, 0, 0, 0];
    const x = mapping.offsetX + numberText(rect[0]) * mapping.scale;
    const y = mapping.offsetY + numberText(rect[1]) * mapping.scale;
    const width = numberText(rect[2]) * mapping.scale;
    const height = numberText(rect[3]) * mapping.scale;

    if (options.aus !== false) {
      drawAuMeshHeatmap(context, face, mapping);
    }

    if (options.landmarks !== false) {
      drawLandmarks(context, face, mapping, options.landmarkStyle || el("landmarkStyleSelect")?.value || "mesh");
    }

    if (options.gaze !== false) {
      const gaze = face.gaze || [0, 0, 1];
      const originX = x + width / 2;
      const originY = y + height * 0.42;
      const length = Math.max(32, Math.min(84, Math.max(width, height) * 0.24 || 48));
      context.strokeStyle = "#d99b13";
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(originX, originY);
      context.lineTo(originX + numberText(gaze[0]) * length, originY - numberText(gaze[1]) * length);
      context.stroke();
    }

    if (options.pose !== false) {
      const pose = face.pose || [0, 0, 0];
      context.font = "12px system-ui, sans-serif";
      context.fillStyle = "rgba(16,20,22,0.78)";
      context.fillRect(Math.max(4, x), Math.max(4, y - 30), 120, 24);
      context.fillStyle = "#ffffff";
      context.fillText(`yaw ${numberText(pose[2]).toFixed(2)}`, Math.max(12, x + 8), Math.max(20, y - 14));
    }

    if (options.boxes !== false && width > 0 && height > 0) {
      context.save();
      context.strokeStyle = "#22c55e";
      context.lineWidth = Math.max(2, Math.min(4, mapping.scale * 1.6));
      context.shadowBlur = 3;
      context.shadowColor = "rgba(0,0,0,0.45)";
      context.strokeRect(x, y, width, height);
      context.restore();
    }
  }
}

function drawLandmarks(context, face, mapping, style) {
  const points = face.lm || [];
  const landmarkCount = Math.floor(points.length / 2);
  const isMpMesh = landmarkCount >= 478;
  const edgeKey = isMpMesh
    ? style === "lines" ? "mp_contours" : "mp_tess"
    : style === "lines" ? "dlib_parts" : "dlib_mesh";
  const edges = style === "points" ? [] : state.overlayGeometry.edges?.[edgeKey] || [];

  context.save();
  context.lineCap = "round";
  context.lineJoin = "round";
  context.fillStyle = isMpMesh ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.92)";
  context.strokeStyle = isMpMesh ? "rgba(255,255,255,0.86)" : "rgba(255,255,255,0.86)";
  context.lineWidth = style === "mesh" ? Math.max(0.75, Math.min(1.3, mapping.scale * 0.58)) : 1.25;
  context.shadowBlur = style === "mesh" ? 1.6 : 0;
  context.shadowColor = "rgba(0,0,0,0.38)";

  if (edges.length) {
    context.beginPath();
    for (const [a, b] of edges) {
      const ax = pointX(points, a, mapping);
      const ay = pointY(points, a, mapping);
      const bx = pointX(points, b, mapping);
      const by = pointY(points, b, mapping);
      if (!Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(bx) || !Number.isFinite(by)) {
        continue;
      }
      context.moveTo(ax, ay);
      context.lineTo(bx, by);
    }
    context.stroke();
  } else {
    const radius = isMpMesh ? 1.05 : 2.1;
    for (let index = 0; index < landmarkCount; index += 1) {
      const px = pointX(points, index, mapping);
      const py = pointY(points, index, mapping);
      if (!Number.isFinite(px) || !Number.isFinite(py)) {
        continue;
      }
      context.beginPath();
      context.arc(px, py, radius, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.restore();
}

function drawAuMeshHeatmap(context, face, mapping) {
  const points = face.lm || [];
  if (points.length < 956 || !face.aus) {
    return;
  }
  const regionToTriangles = state.overlayGeometry.auMesh?.regionToTriangles || {};
  const fallbackTriangles = state.overlayGeometry.auMesh?.triangles || [];
  const vertexAUs = state.overlayGeometry.auMesh?.vertexAUs || {};
  if (!Object.keys(regionToTriangles).length && (!fallbackTriangles.length || !Object.keys(vertexAUs).length)) {
    return;
  }

  context.save();
  if (Object.keys(regionToTriangles).length) {
    const activeRegions = Object.entries(regionToTriangles)
      .map(([region, triangles]) => [region, triangles, clamp(face.aus[region] ?? 0, 0, 1)])
      .filter(([, , raw]) => raw >= 0.08)
      .sort((a, b) => b[2] - a[2])
      .slice(0, MAX_LIVE_AU_SHADE_REGIONS);
    for (const [, triangles, raw] of activeRegions) {
      const display = Math.pow(raw, 2.2);
      const alpha = Math.min(0.72, Math.max(0.08, display * 0.82));
      context.fillStyle = auHeatColor(display, alpha);
      context.beginPath();
      for (const [a, b, c] of triangles) {
        addTrianglePath(context, points, mapping, a, b, c);
      }
      context.fill();
    }
    context.restore();
    return;
  }

  const auCache = new Map();
  const vertexIntensity = new Map();
  for (const [vertex, aus] of Object.entries(vertexAUs)) {
    let maxValue = 0;
    for (const au of aus) {
      if (!auCache.has(au)) {
        auCache.set(au, clamp(face.aus[au] ?? 0, 0, 1));
      }
      maxValue = Math.max(maxValue, auCache.get(au));
    }
    if (maxValue > 0) {
      vertexIntensity.set(Number(vertex), maxValue);
    }
  }

  for (const [a, b, c] of fallbackTriangles) {
    const mean = ((vertexIntensity.get(a) || 0) + (vertexIntensity.get(b) || 0) + (vertexIntensity.get(c) || 0)) / 3;
    if (mean < 0.08) {
      continue;
    }
    const display = Math.pow(mean, 2.2);
    const alpha = Math.min(0.62, Math.max(0.06, display * 0.78));
    context.fillStyle = auHeatColor(display, alpha);
    context.beginPath();
    addTrianglePath(context, points, mapping, a, b, c);
    context.fill();
  }
  context.restore();
}

function addTrianglePath(context, points, mapping, a, b, c) {
  const ax = pointX(points, a, mapping);
  const ay = pointY(points, a, mapping);
  const bx = pointX(points, b, mapping);
  const by = pointY(points, b, mapping);
  const cx = pointX(points, c, mapping);
  const cy = pointY(points, c, mapping);
  if (![ax, ay, bx, by, cx, cy].every(Number.isFinite)) {
    return;
  }
  context.beginPath();
  context.moveTo(ax, ay);
  context.lineTo(bx, by);
  context.lineTo(cx, cy);
  context.closePath();
}

function auHeatColor(value, alpha) {
  const t = clamp(value, 0, 1);
  const red = Math.round(200 + 45 * t);
  const green = Math.round(50 + 45 * (1 - t));
  const blue = Math.round(38 + 30 * (1 - t));
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function pointX(points, index, mapping) {
  return mapping.offsetX + numberText(points[index * 2], NaN) * mapping.scale;
}

function pointY(points, index, mapping) {
  return mapping.offsetY + numberText(points[index * 2 + 1], NaN) * mapping.scale;
}

function drawOverlay() {
  clearOverlay();
  if (!state.latestFrame) {
    return;
  }
  drawFacePayload(overlayCanvas, state.latestFrame, {
    boxes: el("boxToggle").checked,
    landmarks: el("meshToggle").checked,
    aus: el("auToggle").checked,
    gaze: el("gazeToggle").checked,
    pose: el("poseToggle").checked,
    landmarkStyle: el("landmarkStyleSelect").value,
  });
}

function drawValenceArousal() {
  const canvas = el("vaCanvas");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.strokeStyle = "#dce3ea";
  context.beginPath();
  context.moveTo(width / 2, 10);
  context.lineTo(width / 2, height - 10);
  context.moveTo(10, height / 2);
  context.lineTo(width - 10, height / 2);
  context.stroke();
  for (const [index, point] of state.vaTrail.entries()) {
    const x = width / 2 + clamp(point.valence, -1, 1) * (width / 2 - 20);
    const y = height / 2 - clamp(point.arousal, -1, 1) * (height / 2 - 20);
    context.fillStyle = index === state.vaTrail.length - 1 ? "#208b8f" : "rgba(32,139,143,0.26)";
    context.beginPath();
    context.arc(x, y, index === state.vaTrail.length - 1 ? 6 : 3, 0, Math.PI * 2);
    context.fill();
  }
}

function updateLatencyText(payload = {}) {
  const total = numberText(payload.latency_ms);
  const inference = numberText(payload.inference_ms, NaN);
  const serialize = numberText(payload.serialize_ms, NaN);
  const latencyText = el("latencyText");
  setText("latencyText", `${total.toFixed(0)} ms`);
  if (latencyText && (Number.isFinite(inference) || Number.isFinite(serialize))) {
    latencyText.title = `inference ${numberText(inference).toFixed(1)} ms, serialize ${numberText(serialize).toFixed(
      1,
    )} ms`;
  }
}

function renderLiveFrame(payload) {
  updateLatencyText(payload);
  if (payload.unchanged) {
    setText("headerFps", numberText(payload.fps).toFixed(1));
    setText("deviceBadge", payload.device || el("deviceBadge")?.textContent || "auto");
    return;
  }
  state.latestFrame = payload;
  resultFrame.classList.add("has-stream");
  const face = payload.faces?.[0];
  setText("headerFps", numberText(payload.fps).toFixed(1));
  setText("deviceBadge", payload.device || el("deviceBadge")?.textContent || "auto");

  if (!face) {
    renderEmptyMetrics();
    setStatus("No face");
    drawOverlay();
    return;
  }

  renderPrimaryEmotion(face.emotions || {});
  renderBars(el("emotionList"), face.emotions || {}, { limit: 3 });
  renderActiveAUs(face.aus || {});
  renderBars(el("auList"), face.aus || {}, { descriptions: state.labels.au_descriptions || {} });
  renderBars(el("blendshapeList"), el("blendshapeToggle").checked ? face.blendshapes || {} : {});
  setText("faceCountText", String(payload.face_count || 0));
  setText("posePitch", numberText(face.pose?.[0]).toFixed(2));
  setText("poseRoll", numberText(face.pose?.[1]).toFixed(2));
  setText("poseYaw", numberText(face.pose?.[2]).toFixed(2));
  setText("gazeText", `${numberText(face.gaze?.[0]).toFixed(2)}, ${numberText(face.gaze?.[1]).toFixed(
    2,
  )}, ${numberText(face.gaze?.[2], 1).toFixed(2)}`);
  setText("landmarkCount", String(face.landmark_count || 0));
  setText("landmarkToggleCount", String(face.landmark_count || 0));
  const va = face.valence_arousal || {};
  if (el("vaToggle").checked) {
    state.vaTrail.push({ valence: numberText(va.valence), arousal: numberText(va.arousal) });
    state.vaTrail = state.vaTrail.slice(-24);
  }
  setStatus(`Frame ${payload.id} · Faces ${payload.face_count} · Landmarks ${face.landmark_count || 0}`);
  drawValenceArousal();
  drawOverlay();
}

async function analyzeOnce() {
  if (!state.running || state.paused || state.inFlight || !video.videoWidth) {
    return;
  }
  const now = performance.now();
  const intervalMs = Math.max(16, Number(el("intervalInput").value || 33));
  if (now - state.lastRequestAt < intervalMs) {
    return;
  }
  state.lastRequestAt = now;
  state.inFlight = true;
  const sessionId = state.sessionId;
  setStatus("Analyzing...");
  try {
    const blob = await captureFrameBlob();
    const payload = await fetchJson("/api/live/frame", {
      method: "POST",
      headers: {
        "Content-Type": "image/jpeg",
        "X-Last-Result-Id": state.latestFrame?.id ? String(state.latestFrame.id) : "",
      },
      body: blob,
    });
    if (state.running && sessionId === state.sessionId) {
      renderLiveFrame(payload);
    }
  } catch (error) {
    if (state.running && sessionId === state.sessionId) {
      setStatus(error.message || "Analysis failed.");
    }
  } finally {
    if (sessionId === state.sessionId) {
      state.inFlight = false;
    }
  }
}

function loop(sessionId) {
  if (!state.running || sessionId !== state.sessionId) {
    return;
  }
  analyzeOnce();
  requestAnimationFrame(() => loop(sessionId));
}

function stopStream(options = {}) {
  state.sessionId += 1;
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
  }
  state.stream = null;
  state.running = false;
  state.paused = false;
  state.inFlight = false;
  state.latestFrame = null;
  state.vaTrail = [];
  video.srcObject = null;
  mirror.srcObject = null;
  resultFrame.classList.remove("has-stream");
  updateRunButtons();
  clearOverlay();
  drawValenceArousal();
  if (!options.quiet) {
    setStatus("Stopped");
  }
}

async function startCamera() {
  if (state.running) {
    return;
  }
  await configureLive();
  await waitForAnalyzerReady();
  stopStream({ quiet: true });
  state.sessionId += 1;
  const sessionId = state.sessionId;
  const selected = parseResolution(el("resolutionSelect").value);
  const constraints = {
    video: { width: { ideal: selected.width }, height: { ideal: selected.height }, facingMode: "user" },
    audio: false,
  };
  if (el("cameraSelect").value) {
    constraints.video.deviceId = { ideal: el("cameraSelect").value };
  }
  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  if (sessionId !== state.sessionId) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  state.stream = stream;
  video.srcObject = stream;
  mirror.srcObject = stream;
  await video.play();
  await mirror.play();
  await listCameras();
  document.body.classList.toggle("flip-video", el("flipSelect").value === "on");
  state.running = true;
  state.paused = false;
  state.recording = false;
  state.lastRequestAt = 0;
  resultFrame.classList.add("has-stream");
  setText("cameraStatus", "Camera running.");
  updateRunButtons();
  setStatus("Waiting");
  loop(sessionId);
}

async function toggleRecording() {
  if (!state.running) {
    return;
  }
  if (state.recording) {
    await fetchJson("/api/live/recording/stop", { method: "POST" });
    state.recording = false;
    setText("cameraStatus", "Recording stopped.");
    await loadSessions();
  } else {
    const payload = await fetchJson("/api/live/recording/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "Live recording" }),
    });
    state.recording = true;
    setText("cameraStatus", `Recording ${payload.recording.id}`);
  }
  updateRunButtons();
}

async function loadSessions() {
  const payload = await fetchJson("/api/sessions");
  state.sessions = payload.sessions || [];
  const list = el("sessionList");
  list.innerHTML = "";
  if (!state.sessions.length) {
    list.innerHTML = '<div class="empty-row">No sessions yet.</div>';
    return;
  }
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "list-item";
    button.innerHTML = `<strong>${session.label || session.id}</strong><span>${session.source || "session"} · ${
      session.frame_count || 0
    } frames</span>`;
    button.addEventListener("click", () => loadSession(session.id));
    list.appendChild(button);
  }
}

async function loadSession(sessionId) {
  state.selectedSessionId = sessionId;
  const payload = await fetchJson(`/api/sessions/${sessionId}/frames`);
  state.viewerFrames = payload.frames || [];
  el("viewerFrameInput").max = String(Math.max(0, state.viewerFrames.length - 1));
  el("viewerFrameInput").value = "0";
  renderViewerFrame(0);
}

function renderViewerFrame(index) {
  const frame = state.viewerFrames[index];
  const canvas = el("viewerCanvas");
  drawFacePayload(canvas, frame || { frame: [640, 480], faces: [] }, {
    background: true,
    width: canvas.clientWidth || 720,
    height: canvas.clientHeight || 540,
    aus: true,
    landmarkStyle: "mesh",
  });
  setText("viewerFrameLabel", `${state.viewerFrames.length ? index + 1 : 0} / ${state.viewerFrames.length}`);
  if (!frame) {
    setText("viewerDetails", "No frame selected.");
    return;
  }
  const face = frame.faces?.[0] || {};
  el("viewerDetails").innerHTML = `
    <div><strong>Session</strong> ${state.selectedSessionId}</div>
    <div><strong>Frame</strong> ${frame.id || index + 1}</div>
    <div><strong>Faces</strong> ${frame.face_count || 0}</div>
    <div><strong>Landmarks</strong> ${face.landmark_count || 0}</div>
    <div><strong>Top AU</strong> ${topEntry(face.aus)}</div>
    <div><strong>Top Emotion</strong> ${topEntry(face.emotions)}</div>
  `;
}

function topEntry(values) {
  const entries = Object.entries(values || {}).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
  return entries[0] ? `${entries[0][0]} ${Number(entries[0][1]).toFixed(2)}` : "none";
}

async function loadQueue() {
  const payload = await fetchJson("/api/analyze/queue");
  const list = el("queueList");
  list.innerHTML = "";
  for (const item of payload.items || []) {
    const row = document.createElement("div");
    row.className = "queue-row";
    row.innerHTML = `<strong>${item.label || item.id}</strong><span>${item.status} · ${Math.round(
      (item.progress || 0) * 100,
    )}%</span><span>${item.session_id || item.error || ""}</span>`;
    list.appendChild(row);
  }
  if (!list.children.length) {
    list.innerHTML = '<div class="empty-row">Queue is empty.</div>';
  }
}

async function addAnalyzeImage() {
  if (!state.analyzePayload) {
    return;
  }
  const payload = {
    label: el("analyzeLabelInput").value,
    [state.analyzePayload.kind]: state.analyzePayload.data,
  };
  await fetchJson("/api/analyze/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadQueue();
}

async function runQueue() {
  await fetchJson("/api/analyze/queue/run", { method: "POST" });
  await loadQueue();
  await loadSessions();
}

async function loadSystemPanels() {
  const [compute, caps, logs, presets] = await Promise.all([
    fetchJson("/api/system/compute"),
    fetchJson("/api/system/detector-capabilities"),
    fetchJson("/api/system/logs"),
    fetchJson("/api/presets"),
  ]);
  renderPresetList(presets.presets || []);
  el("computeInfo").innerHTML = Object.entries(compute)
    .map(([key, value]) => `<div><strong>${key}</strong> ${value.available ? "available" : "unavailable"}</div>`)
    .join("");
  el("capabilityInfo").innerHTML = Object.entries(caps)
    .map(([name, cap]) => `<div><strong>${name}</strong> ${cap.landmark_space} · gaze ${String(cap.has_gaze)}</div>`)
    .join("");
  el("logList").innerHTML = (logs.logs || [])
    .map((log) => `<div><strong>${new Date(log.time * 1000).toLocaleTimeString()}</strong> ${log.message}</div>`)
    .join("") || '<div class="empty-row">No backend logs.</div>';
}

function renderPresetList(presets) {
  const list = el("presetList");
  if (!list) {
    return;
  }
  list.innerHTML = "";
  for (const preset of presets) {
    const row = document.createElement("div");
    row.className = "queue-row";
    row.innerHTML = `<strong>${preset.name}</strong><span>${preset.detector_type} · ${preset.detection_size}px</span>`;
    list.appendChild(row);
  }
}

document.querySelectorAll(".nav-tab").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

el("startBtn").addEventListener("click", async () => {
  try {
    await startCamera();
  } catch (error) {
    setText("cameraStatus", error.message || "Could not start camera.");
    stopStream({ quiet: true });
  }
});
el("pauseBtn").addEventListener("click", () => {
  state.paused = !state.paused;
  setStatus(state.paused ? "Paused" : "Waiting");
  updateRunButtons();
});
el("stopBtn").addEventListener("click", () => stopStream());
el("recordBtn").addEventListener("click", () => toggleRecording().catch((error) => setStatus(error.message)));
el("downloadBtn").addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = state.running ? captureFrame() : captureCanvas.toDataURL("image/jpeg", 0.86);
  link.download = "py-feat-frame.jpg";
  link.click();
});
el("presetSelect").addEventListener("change", () => {
  const option = el("presetSelect").selectedOptions[0];
  if (option?.dataset.detectionSize) {
    el("detectionSizeInput").value = option.dataset.detectionSize;
  }
  if (option?.dataset.maxFps) {
    el("intervalInput").value = String(Math.max(16, Math.round(1000 / Number(option.dataset.maxFps || 30))));
  }
});
el("flipSelect").addEventListener("change", () => {
  document.body.classList.toggle("flip-video", el("flipSelect").value === "on");
});
for (const id of ["boxToggle", "meshToggle", "auToggle", "gazeToggle", "poseToggle", "landmarkStyleSelect"]) {
  el(id).addEventListener("change", drawOverlay);
}
el("blendshapeToggle").addEventListener("change", () => {
  syncLiveHints();
  if (state.latestFrame) {
    renderBars(el("blendshapeList"), el("blendshapeToggle").checked ? state.latestFrame.faces?.[0]?.blendshapes || {} : {});
  }
});
el("refreshSessionsBtn").addEventListener("click", loadSessions);
el("viewerFrameInput").addEventListener("input", (event) => renderViewerFrame(Number(event.target.value)));
el("analyzeFileInput").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const data = String(reader.result || "");
    state.analyzePayload = { kind: file.type.startsWith("video/") ? "video" : "image", data };
    if (state.analyzePayload.kind === "image") {
      el("analyzePreview").src = data;
    } else {
      el("analyzePreview").removeAttribute("src");
    }
  };
  reader.readAsDataURL(file);
});
el("queueImageBtn").addEventListener("click", () => addAnalyzeImage().catch((error) => alert(error.message)));
el("runQueueBtn").addEventListener("click", () => runQueue().catch((error) => alert(error.message)));
el("pauseQueueBtn").addEventListener("click", () => fetchJson("/api/analyze/queue/pause", { method: "POST" }).then(loadQueue));
el("stopQueueBtn").addEventListener("click", () => fetchJson("/api/analyze/queue/stop", { method: "POST" }).then(loadQueue));

window.addEventListener("beforeunload", () => stopStream({ quiet: true }));
window.addEventListener("resize", () => {
  drawOverlay();
  drawValenceArousal();
  if (state.viewerFrames.length) {
    renderViewerFrame(Number(el("viewerFrameInput").value || 0));
  }
});

loadStatus();
loadPresets().catch((error) => {
  setText("cameraStatus", error.message || "Could not load presets.");
});
loadOverlayGeometry().catch((error) => {
  setText("cameraStatus", error.message || "Could not load overlay geometry.");
});
listCameras();
loadSessions().catch(() => {});
loadQueue().catch(() => {});
drawValenceArousal();

if (new URLSearchParams(window.location.search).has("debug_overlay")) {
  window.pyFeatDemoDebug = {
    state,
    drawOverlay,
    drawFacePayload,
  };
}
