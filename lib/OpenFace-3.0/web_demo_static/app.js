const video = document.getElementById("camera");
const canvas = document.getElementById("captureCanvas");
const resultFrame = document.querySelector(".result-frame");
const resultImage = document.getElementById("resultImage");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const deviceBadge = document.getElementById("deviceBadge");
const headerFps = document.getElementById("headerFps");
const resolutionText = document.getElementById("resolutionText");
const uptimeText = document.getElementById("uptimeText");
const inputFps = document.getElementById("inputFps");
const analysisStatus = document.getElementById("analysisStatus");
const emotionList = document.getElementById("emotionList");
const auList = document.getElementById("auList");
const resolutionSelect = document.getElementById("resolutionSelect");
const flipSelect = document.getElementById("flipSelect");
const intervalInput = document.getElementById("intervalInput");
const cameraSelect = document.getElementById("cameraSelect");
const downloadBtn = document.getElementById("downloadBtn");
const DEFAULT_CAMERA_INDEX = 1;

const emotionDefaults = [
  { label: "Happy", label_ko: "행복", value: 0 },
  { label: "Neutral", label_ko: "중립", value: 0 },
  { label: "Sad", label_ko: "슬픔", value: 0 },
  { label: "Surprise", label_ko: "놀람", value: 0 },
  { label: "Fear", label_ko: "두려움", value: 0 },
  { label: "Disgust", label_ko: "혐오", value: 0 },
  { label: "Anger", label_ko: "분노", value: 0 },
  { label: "Contempt", label_ko: "경멸", value: 0 },
];

let stream = null;
let running = false;
let inFlight = false;
let lastRequestAt = 0;
let startedAt = 0;
let frameCounter = 0;
let lastInputFpsAt = 0;
let avgFps = 0;
let uptimeTimer = null;

function parseResolution(value) {
  const [width, height] = value.split("x").map((part) => Number(part));
  return { width, height };
}

function setDevice(text) {
  deviceBadge.innerHTML = `<i></i> ${text || "auto"}`;
}

function formatUptime(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

function renderBarList(container, items, options = {}) {
  container.innerHTML = "";
  for (const item of items || []) {
    const value = Math.max(0, Math.min(1, Number(item.value || 0)));
    const row = document.createElement("div");
    row.className = options.rowClass || "metric-row";
    const name = options.formatName ? options.formatName(item) : `${item.label} (${item.label_ko})`;
    row.innerHTML = `
      <div class="${options.lineClass || "metric-line"}">
        <span class="${options.nameClass || "metric-name"}">${name}</span>
        <div class="bar-track"><div class="bar-fill" style="width: ${(value * 100).toFixed(1)}%"></div></div>
        <span class="${options.valueClass || "metric-value"}">${value.toFixed(2)}</span>
      </div>
    `;
    container.appendChild(row);
  }
}

function renderAUs(items) {
  renderBarList(auList, items, {
    rowClass: "au-row",
    lineClass: "au-title",
    nameClass: "au-name",
    valueClass: "au-value",
    formatName: (item) => `${item.code} - ${item.name_en} <span class="au-ko">/ ${item.name_ko}</span>`,
  });
}

function renderEmotions(items) {
  const sorted = [...(items || emotionDefaults)].sort((a, b) => Number(b.value || 0) - Number(a.value || 0));
  renderBarList(emotionList, sorted);
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    setDevice(status.device || "auto");
    renderAUs((status.aus || []).map((item) => ({ ...item, value: 0 })));
    renderEmotions(emotionDefaults);
  } catch {
    setDevice("unavailable");
  }
}

async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return;
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cameras = devices.filter((device) => device.kind === "videoinput");
  if (!cameras.length) {
    return;
  }
  const previousCameraId = cameraSelect.value;
  cameraSelect.innerHTML = "";
  for (const [index, camera] of cameras.entries()) {
    const option = document.createElement("option");
    option.value = camera.deviceId;
    option.textContent = camera.label || `Camera ${index + 1}`;
    cameraSelect.appendChild(option);
  }
  const preferredCamera = cameras[DEFAULT_CAMERA_INDEX] || cameras[0];
  const hasPreviousCamera = cameras.some((camera) => camera.deviceId === previousCameraId);
  cameraSelect.value = hasPreviousCamera ? previousCameraId : preferredCamera.deviceId;
}

function setRunning(next) {
  running = next;
  startBtn.disabled = next;
  stopBtn.disabled = !next;
  if (next) {
    startedAt = Date.now();
    uptimeTimer = window.setInterval(() => {
      uptimeText.textContent = formatUptime(Date.now() - startedAt);
    }, 500);
  } else {
    window.clearInterval(uptimeTimer);
    uptimeTimer = null;
    uptimeText.textContent = "00:00:00";
  }
}

function stopStream() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
  }
  stream = null;
  video.srcObject = null;
  setRunning(false);
}

function captureFrame() {
  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;
  const targetWidth = 480;
  const scale = Math.min(1, targetWidth / width);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (flipSelect.value === "on") {
    context.translate(canvas.width, 0);
    context.scale(-1, 1);
  }
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.82);
}

function updateInputFps() {
  frameCounter += 1;
  const now = performance.now();
  if (!lastInputFpsAt) {
    lastInputFpsAt = now;
    return;
  }
  const elapsed = now - lastInputFpsAt;
  if (elapsed >= 1000) {
    inputFps.textContent = ((frameCounter * 1000) / elapsed).toFixed(1);
    frameCounter = 0;
    lastInputFpsAt = now;
  }
}

function renderAnalysis(body) {
  resultImage.src = body.image;
  resultFrame.classList.add("has-image");
  setDevice(body.device || "auto");

  const analysis = body.analysis || {};
  const fps = Number(analysis.fps || 0);
  avgFps = avgFps ? avgFps * 0.82 + fps * 0.18 : fps;
  headerFps.textContent = avgFps.toFixed(1);
  analysisStatus.textContent = `FPS: ${fps.toFixed(1)}`;

  renderEmotions(analysis.emotions || emotionDefaults);
  renderAUs(analysis.aus || []);
}

async function analyzeOnce() {
  if (!running || inFlight || !video.videoWidth) {
    return;
  }
  const now = performance.now();
  const intervalMs = Math.max(120, Number(intervalInput.value || 260));
  if (now - lastRequestAt < intervalMs) {
    return;
  }
  lastRequestAt = now;
  inFlight = true;
  analysisStatus.textContent = "Analyzing...";
  try {
    const image = captureFrame();
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || "analysis failed");
    }
    renderAnalysis(body);
  } catch (error) {
    analysisStatus.textContent = error.message;
  } finally {
    inFlight = false;
  }
}

function loop() {
  updateInputFps();
  analyzeOnce();
  if (running) {
    requestAnimationFrame(loop);
  }
}

async function startCamera() {
  stopStream();
  const selected = parseResolution(resolutionSelect.value);
  resolutionText.textContent = `${selected.width} x ${selected.height}`;
  document.body.classList.toggle("flip-video", flipSelect.value === "on");
  const constraints = {
    video: {
      width: { ideal: selected.width },
      height: { ideal: selected.height },
      facingMode: "user",
    },
    audio: false,
  };
  if (cameraSelect.value) {
    constraints.video.deviceId = { ideal: cameraSelect.value };
  }
  stream = await navigator.mediaDevices.getUserMedia(constraints);
  video.srcObject = stream;
  await video.play();
  await listCameras();
  frameCounter = 0;
  lastInputFpsAt = 0;
  avgFps = 0;
  headerFps.textContent = "0.0";
  setRunning(true);
  loop();
}

startBtn.addEventListener("click", async () => {
  try {
    await startCamera();
  } catch (error) {
    analysisStatus.textContent = error.message;
  }
});

stopBtn.addEventListener("click", stopStream);
flipSelect.addEventListener("change", () => {
  document.body.classList.toggle("flip-video", flipSelect.value === "on");
});
downloadBtn.addEventListener("click", () => {
  if (!resultImage.src) {
    return;
  }
  const link = document.createElement("a");
  link.href = resultImage.src;
  link.download = "openface-frame.jpg";
  link.click();
});
window.addEventListener("beforeunload", stopStream);

loadStatus();
listCameras();
