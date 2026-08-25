import {
  DrawingUtils,
  FaceLandmarker,
  FilesetResolver,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/vision_bundle.mjs";

import { normalizeBlendshapes, smoothBlendshapes } from "./blendshape-utils.js";

const WASM_ROOT = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const SMOOTHING_ALPHA = 0.35;

const elements = {
  video: document.querySelector("#webcam"),
  canvas: document.querySelector("#overlay"),
  placeholder: document.querySelector("#cameraPlaceholder"),
  start: document.querySelector("#startButton"),
  stop: document.querySelector("#stopButton"),
  meshToggle: document.querySelector("#meshToggle"),
  statusBadge: document.querySelector("#statusBadge"),
  statusMessage: document.querySelector("#statusMessage"),
  fps: document.querySelector("#fpsValue"),
  latency: document.querySelector("#latencyValue"),
  landmarks: document.querySelector("#landmarkValue"),
  delegate: document.querySelector("#delegateValue"),
  count: document.querySelector("#coefficientCount"),
  topName: document.querySelector("#topSignalName"),
  topScore: document.querySelector("#topSignalScore"),
  list: document.querySelector("#blendshapeList"),
};

let faceLandmarker = null;
let drawingUtils = null;
let stream = null;
let animationFrame = 0;
let lastVideoTime = -1;
let lastFrameAt = 0;
let smoothedScores = new Map();
let running = false;

function setStatus(state, label, message) {
  elements.statusBadge.dataset.state = state;
  elements.statusBadge.textContent = label;
  elements.statusMessage.textContent = message;
}

async function createLandmarker() {
  if (faceLandmarker) {
    return;
  }

  setStatus("loading", "로딩", "MediaPipe WASM과 Blendshape V2 모델을 불러오는 중입니다…");
  const vision = await FilesetResolver.forVisionTasks(WASM_ROOT);
  const sharedOptions = {
    runningMode: "VIDEO",
    numFaces: 1,
    minFaceDetectionConfidence: 0.5,
    minFacePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: false,
  };

  try {
    faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
      ...sharedOptions,
      baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
    });
    elements.delegate.textContent = "GPU";
  } catch (gpuError) {
    console.info("GPU delegate unavailable; falling back to CPU.", gpuError);
    faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
      ...sharedOptions,
      baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" },
    });
    elements.delegate.textContent = "CPU";
  }
  drawingUtils = new DrawingUtils(elements.canvas.getContext("2d"));
}

function sizeCanvas() {
  const width = elements.video.videoWidth || 640;
  const height = elements.video.videoHeight || 480;
  if (elements.canvas.width !== width || elements.canvas.height !== height) {
    elements.canvas.width = width;
    elements.canvas.height = height;
  }
}

function clearCanvas() {
  const context = elements.canvas.getContext("2d");
  context.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
}

function drawLandmarks(landmarks) {
  clearCanvas();
  if (!elements.meshToggle.checked || !landmarks?.length) {
    return;
  }
  drawingUtils.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_TESSELATION, {
    color: "rgba(99, 230, 190, 0.28)",
    lineWidth: 1,
  });
  drawingUtils.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_CONTOURS, {
    color: "#d8ff64",
    lineWidth: 2,
  });
  drawingUtils.drawLandmarks(landmarks, {
    color: "rgba(255, 255, 255, 0.72)",
    radius: 0.7,
  });
}

function renderBlendshapes(values) {
  elements.list.replaceChildren();
  for (const { name, score } of values) {
    const row = document.createElement("div");
    row.className = "signal-row";

    const label = document.createElement("span");
    label.className = "signal-name";
    label.textContent = name;

    const track = document.createElement("span");
    track.className = "signal-track";
    const fill = document.createElement("i");
    fill.style.width = `${(score * 100).toFixed(1)}%`;
    track.appendChild(fill);

    const output = document.createElement("output");
    output.textContent = score.toFixed(2);
    row.append(label, track, output);
    elements.list.appendChild(row);
  }

  elements.count.textContent = `${values.length} / 52`;
  const top = values[0];
  elements.topName.textContent = top?.name || "No face";
  elements.topScore.textContent = top ? top.score.toFixed(2) : "0.00";
}

function renderEmptyResult() {
  renderBlendshapes([]);
  elements.landmarks.textContent = "0";
  clearCanvas();
}

function updateRuntimeMetrics(startedAt, now) {
  elements.latency.textContent = `${(performance.now() - startedAt).toFixed(1)} ms`;
  if (lastFrameAt) {
    const instantFps = 1000 / Math.max(1, now - lastFrameAt);
    const oldFps = Number.parseFloat(elements.fps.textContent) || instantFps;
    elements.fps.textContent = (oldFps * 0.8 + instantFps * 0.2).toFixed(1);
  }
  lastFrameAt = now;
}

function predict() {
  if (!running) {
    return;
  }

  sizeCanvas();
  const now = performance.now();
  if (elements.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && elements.video.currentTime !== lastVideoTime) {
    const startedAt = performance.now();
    const result = faceLandmarker.detectForVideo(elements.video, now);
    lastVideoTime = elements.video.currentTime;

    const landmarks = result.faceLandmarks?.[0] || [];
    const categories = result.faceBlendshapes?.[0]?.categories || [];
    const normalized = normalizeBlendshapes(categories);
    const smoothed = smoothBlendshapes(normalized, smoothedScores, SMOOTHING_ALPHA).sort(
      (left, right) => right.score - left.score,
    );
    smoothedScores = new Map(smoothed.map(({ name, score }) => [name, score]));

    drawLandmarks(landmarks);
    renderBlendshapes(smoothed);
    elements.landmarks.textContent = String(landmarks.length);
    updateRuntimeMetrics(startedAt, now);
    setStatus(
      landmarks.length ? "running" : "searching",
      landmarks.length ? "실행 중" : "탐색 중",
      landmarks.length
        ? "얼굴 영상은 브라우저 안에서만 처리됩니다."
        : "얼굴을 정면으로 비추고 조명을 확인하세요.",
    );
  }
  animationFrame = requestAnimationFrame(predict);
}

async function startCamera() {
  elements.start.disabled = true;
  try {
    if (!window.isSecureContext && location.hostname !== "localhost") {
      throw new Error("카메라는 HTTPS 또는 localhost에서만 사용할 수 있습니다.");
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("이 브라우저는 웹캠 API를 지원하지 않습니다.");
    }

    await createLandmarker();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: "user",
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    elements.video.srcObject = stream;
    await elements.video.play();

    running = true;
    lastVideoTime = -1;
    lastFrameAt = 0;
    smoothedScores = new Map();
    elements.placeholder.hidden = true;
    elements.stop.disabled = false;
    setStatus("searching", "탐색 중", "얼굴을 정면으로 비추고 조명을 확인하세요.");
    predict();
  } catch (error) {
    console.error(error);
    setStatus("error", "오류", error.message || "카메라를 시작하지 못했습니다.");
    elements.start.disabled = false;
    stopCamera({ preserveStatus: true });
  }
}

function stopCamera({ preserveStatus = false } = {}) {
  running = false;
  cancelAnimationFrame(animationFrame);
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  elements.video.srcObject = null;
  elements.placeholder.hidden = false;
  elements.start.disabled = false;
  elements.stop.disabled = true;
  elements.fps.textContent = "—";
  elements.latency.textContent = "—";
  elements.landmarks.textContent = "—";
  smoothedScores = new Map();
  renderEmptyResult();
  if (!preserveStatus) {
    setStatus("idle", "대기", "카메라가 중지되었습니다. 모델은 다음 실행에 재사용됩니다.");
  }
}

elements.start.addEventListener("click", startCamera);
elements.stop.addEventListener("click", () => stopCamera());
elements.meshToggle.addEventListener("change", () => {
  if (!elements.meshToggle.checked) {
    clearCanvas();
  }
});
window.addEventListener("pagehide", () => stopCamera({ preserveStatus: true }));

renderEmptyResult();
