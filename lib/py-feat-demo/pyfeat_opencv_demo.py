from __future__ import annotations

import argparse
import statistics
import threading
import time
from collections import deque

import cv2
import numpy as np

from pyfeat_analyzer import AnalyzerState, AU_DESCRIPTIONS
from pyfeat_live_core.overlay_geometry import overlay_geometry
from pyfeat_live_core.serialization import serialize_faces


WINDOW_NAME = "Py-Feat OpenCV Live"
EMOTION_COLORS = {
    "neutral": (210, 210, 210),
    "happiness": (70, 210, 120),
    "sadness": (255, 170, 70),
    "anger": (70, 70, 230),
    "surprise": (80, 220, 255),
    "fear": (210, 120, 255),
    "disgust": (140, 210, 120),
}


class LatestFrameWorker:
    def __init__(self, analyzer: AnalyzerState):
        self.analyzer = analyzer
        self.condition = threading.Condition()
        self.latest_frame: np.ndarray | None = None
        self.latest_seq = 0
        self.processed_seq = 0
        self.result: dict | None = None
        self.latencies = deque(maxlen=240)
        self.result_times = deque(maxlen=240)
        self.errors = deque(maxlen=5)
        self.running = False
        self.thread: threading.Thread | None = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        with self.condition:
            self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=2.0)

    def submit(self, frame: np.ndarray):
        with self.condition:
            self.latest_seq += 1
            self.latest_frame = frame.copy()
            self.condition.notify()

    def snapshot(self) -> dict | None:
        return self.result

    def _run(self):
        while self.running:
            with self.condition:
                self.condition.wait_for(
                    lambda: not self.running or self.latest_seq != self.processed_seq,
                    timeout=0.5,
                )
                if not self.running:
                    break
                seq = self.latest_seq
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
                self.processed_seq = seq
            if frame is None:
                continue
            try:
                self.result = analyze_frame(self.analyzer, frame)
                self.latencies.append(self.result["latency_ms"])
                self.result_times.append(time.perf_counter())
            except Exception as exc:
                self.errors.append(str(exc))


def load_analyzer(device: str, detector_type: str) -> AnalyzerState:
    analyzer = AnalyzerState(device_name=device, detector_type=detector_type)
    analyzer.start_loading()
    print("Loading Py-Feat model...")
    while True:
        status = analyzer.snapshot()
        if status["ready"]:
            print(f"Model ready: detector={status['detector_type']} device={status['device']}")
            return analyzer
        if status["state"] == "error":
            raise RuntimeError(status["error"])
        time.sleep(0.2)


def resize_for_detection(frame: np.ndarray, longest_side: int) -> np.ndarray:
    if longest_side <= 0:
        return frame
    height, width = frame.shape[:2]
    longest = max(width, height)
    if longest <= longest_side:
        return frame
    scale = longest_side / float(longest)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def analyze_frame(analyzer: AnalyzerState, frame: np.ndarray) -> dict:
    start = time.perf_counter()
    result = analyzer.analyze_fex(frame)
    faces = serialize_faces(result, mp_landmarks=True)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return {
        "faces": faces,
        "latency_ms": latency_ms,
        "fps": 1000.0 / latency_ms if latency_ms > 0 else 0.0,
        "live_mode": analyzer.snapshot().get("live_mode", ""),
        "timestamp": time.time(),
    }


def draw_result(frame: np.ndarray, result: dict | None, geometry: dict, stats: dict):
    output = frame.copy()
    if result:
        for face in result.get("faces", []):
            draw_face_overlay(output, face, geometry)
        draw_side_panel(output, result)
    draw_status(output, result, stats)
    return output


def draw_face_overlay(frame: np.ndarray, face: dict, geometry: dict):
    rect = face.get("rect") or [0, 0, 0, 0]
    x, y, width, height = [int(round(v)) for v in rect]
    if width > 0 and height > 0:
        cv2.rectangle(frame, (x, y), (x + width, y + height), (30, 220, 95), 2)

    points = points_from_face(face)
    if points.size == 0:
        return

    draw_au_shade(frame, points, face.get("aus", {}), geometry)
    if len(points) >= 478:
        draw_edges(frame, points, geometry["edges"].get("mp_tess", []), (245, 245, 245), 1)
        draw_edges(frame, points, geometry["edges"].get("mp_contours", []), (255, 255, 255), 2)
    else:
        draw_edges(frame, points, geometry["edges"].get("dlib_mesh", []), (245, 245, 245), 1)
        for point in points:
            cv2.circle(frame, tuple(point.astype(int)), 1, (255, 255, 255), -1, lineType=cv2.LINE_AA)


def points_from_face(face: dict) -> np.ndarray:
    flat = face.get("lm") or []
    if len(flat) < 2:
        return np.empty((0, 2), dtype=np.float32)
    return np.asarray(flat, dtype=np.float32).reshape(-1, 2)


def draw_edges(frame: np.ndarray, points: np.ndarray, edges: list[list[int]], color, thickness: int):
    count = len(points)
    for a, b in edges:
        if a >= count or b >= count:
            continue
        p1 = tuple(np.round(points[a]).astype(int))
        p2 = tuple(np.round(points[b]).astype(int))
        cv2.line(frame, p1, p2, color, thickness, lineType=cv2.LINE_AA)


def draw_au_shade(frame: np.ndarray, points: np.ndarray, aus: dict, geometry: dict):
    if len(points) < 478 or not aus:
        return
    au_mesh = geometry.get("auMesh", {})
    triangles_by_au = au_mesh.get("regionToTriangles", {})
    overlay = frame.copy()
    active = [
        (code, float(value))
        for code, value in aus.items()
        if float(value) >= 0.08 and code in triangles_by_au
    ]
    for code, value in sorted(active, key=lambda item: item[1], reverse=True)[:8]:
        alpha = min(0.42, 0.10 + value * 0.35)
        color = (35, 55, 230)
        for triangle in triangles_by_au.get(code, []):
            if max(triangle) >= len(points):
                continue
            poly = np.round(points[np.asarray(triangle, dtype=int)]).astype(np.int32)
            cv2.fillConvexPoly(overlay, poly, color, lineType=cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_side_panel(frame: np.ndarray, result: dict):
    face = (result.get("faces") or [{}])[0]
    emotions = sorted(
        (face.get("emotions") or {}).items(),
        key=lambda item: item[1],
        reverse=True,
    )
    aus = sorted(
        (face.get("aus") or {}).items(),
        key=lambda item: item[1],
        reverse=True,
    )
    panel_w = 250
    panel_h = min(frame.shape[0] - 24, 340)
    x, y = 12, 48
    cv2.rectangle(frame, (x, y), (x + panel_w, y + panel_h), (15, 15, 15), -1)
    cv2.addWeighted(frame, 0.72, frame, 0.28, 0, frame)
    draw_text(frame, "Emotions", x + 14, y + 28, 0.58, (245, 245, 245), 1)
    yy = y + 56
    for label, value in emotions[:7]:
        draw_bar(frame, x + 14, yy, 150, label, value, EMOTION_COLORS.get(label, (180, 180, 180)))
        yy += 28
    yy += 8
    draw_text(frame, "Top AUs", x + 14, yy, 0.58, (245, 245, 245), 1)
    yy += 26
    for code, value in aus[:5]:
        label = AU_DESCRIPTIONS.get(code, code).split(" / ", 1)[0]
        draw_bar(frame, x + 14, yy, 150, f"{code} {label[:17]}", value, (60, 210, 110))
        yy += 28


def draw_bar(frame: np.ndarray, x: int, y: int, width: int, label: str, value: float, color):
    value = max(0.0, min(1.0, float(value)))
    draw_text(frame, label, x, y, 0.42, (225, 225, 225), 1)
    bx = x + 92
    by = y - 10
    cv2.rectangle(frame, (bx, by), (bx + width, by + 8), (85, 85, 85), -1)
    cv2.rectangle(frame, (bx, by), (bx + int(width * value), by + 8), color, -1)
    draw_text(frame, f"{value:.2f}", bx + width + 8, y, 0.38, (220, 220, 220), 1)


def draw_status(frame: np.ndarray, result: dict | None, stats: dict):
    inference_fps = rolling_fps(stats.get("result_times", []))
    capture_fps = rolling_fps(stats.get("capture_times", []))
    latency = result.get("latency_ms", 0.0) if result else 0.0
    mode = result.get("live_mode", "-") if result else "-"
    text = (
        f"capture {capture_fps:4.1f} fps | inference {inference_fps:4.1f} fps | "
        f"latency {latency:5.1f} ms | {mode}"
    )
    cv2.rectangle(frame, (8, 8), (min(frame.shape[1] - 8, 610), 36), (10, 10, 10), -1)
    draw_text(frame, text, 18, 28, 0.52, (230, 255, 230), 1)


def draw_text(frame: np.ndarray, text: str, x: int, y: int, scale: float, color, thickness: int):
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def rolling_fps(times) -> float:
    if len(times) < 2:
        return 0.0
    elapsed = times[-1] - times[0]
    if elapsed <= 0:
        return 0.0
    return (len(times) - 1) / elapsed


def benchmark_image(args, analyzer: AnalyzerState):
    frame = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Could not read image: {args.image}")
    frame = resize_for_detection(frame, args.detection_size)
    geometry = overlay_geometry()
    print(f"Benchmark image: {frame.shape[1]}x{frame.shape[0]}")
    for _ in range(args.warmup):
        analyze_frame(analyzer, frame)

    latencies = []
    started = time.perf_counter()
    deadline = started + args.duration
    iterations = 0
    last_result = None
    while time.perf_counter() < deadline:
        last_result = analyze_frame(analyzer, frame)
        latencies.append(last_result["latency_ms"])
        iterations += 1
    elapsed = time.perf_counter() - started
    if last_result and not args.no_window:
        rendered = draw_result(frame, last_result, geometry, {"capture_times": [], "result_times": []})
        cv2.imshow(WINDOW_NAME, rendered)
        cv2.waitKey(0)
    print_report("OpenCV image benchmark", elapsed, iterations, latencies, last_result)


def live_camera(args, analyzer: AnalyzerState):
    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera index {args.camera}")
    if args.width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    if args.height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    geometry = overlay_geometry()
    worker = LatestFrameWorker(analyzer)
    worker.start()
    capture_times = deque(maxlen=240)
    started = time.perf_counter()
    frames = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Camera frame read failed")
            frame = resize_for_detection(frame, args.detection_size)
            capture_times.append(time.perf_counter())
            frames += 1
            worker.submit(frame)
            result = worker.snapshot()
            stats = {"capture_times": capture_times, "result_times": worker.result_times}
            if not args.no_window:
                rendered = draw_result(frame, result, geometry, stats)
                cv2.imshow(WINDOW_NAME, rendered)
                key = cv2.waitKey(1) & 0xFF
                if key in {27, ord("q")}:
                    break
            if args.duration and time.perf_counter() - started >= args.duration:
                break
    finally:
        worker.stop()
        capture.release()
        if not args.no_window:
            cv2.destroyAllWindows()
    elapsed = time.perf_counter() - started
    print_report("OpenCV camera live", elapsed, len(worker.latencies), list(worker.latencies), worker.snapshot(), frames)
    if worker.errors:
        print("Recent worker errors:")
        for error in worker.errors:
            print(f"  - {error}")


def print_report(name: str, elapsed: float, iterations: int, latencies: list[float], result: dict | None, frames: int | None = None):
    mean_latency = statistics.mean(latencies) if latencies else 0.0
    median_latency = statistics.median(latencies) if latencies else 0.0
    p90_latency = percentile(latencies, 90) if latencies else 0.0
    inference_fps = iterations / elapsed if elapsed > 0 else 0.0
    print("")
    print(name)
    print("-" * len(name))
    if frames is not None:
        print(f"capture_frames: {frames}")
        print(f"capture_fps: {frames / elapsed if elapsed > 0 else 0.0:.2f}")
    print(f"elapsed_sec: {elapsed:.2f}")
    print(f"new_results: {iterations}")
    print(f"inference_fps: {inference_fps:.2f}")
    print(f"latency_ms_mean: {mean_latency:.2f}")
    print(f"latency_ms_median: {median_latency:.2f}")
    print(f"latency_ms_p90: {p90_latency:.2f}")
    if result:
        print(f"face_count: {len(result.get('faces', []))}")
        print(f"live_mode: {result.get('live_mode', '')}")


def percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percent / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def parse_args():
    parser = argparse.ArgumentParser(description="Run Py-Feat.Live-style inference directly in OpenCV.")
    parser.add_argument("--device", default="auto", help="auto, cpu, mps, or cuda")
    parser.add_argument("--detector-type", default="Detectorv2", choices=["Detectorv1", "Detectorv2"])
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--image", help="Benchmark or display a single image instead of camera input")
    parser.add_argument("--benchmark", action="store_true", help="Run a timed benchmark")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--detection-size", type=int, default=640)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--no-window", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    analyzer = load_analyzer(args.device, args.detector_type)
    if args.image:
        benchmark_image(args, analyzer)
    else:
        live_camera(args, analyzer)


if __name__ == "__main__":
    main()
