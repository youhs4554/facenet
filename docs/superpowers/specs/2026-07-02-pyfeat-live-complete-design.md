# Py-Feat.Live Complete Web Demo Design

Date: 2026-07-02

## Goal

Rework `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/` from a single webcam demo into a Py-Feat.Live-inspired web application that follows the official `cosanlab/pyfeat-live` product shape while remaining lightweight enough for this local workspace.

The final app should provide a functional `Live`, `Viewer`, and `Analyze` workflow using official `py-feat` models and data structures where practical. It should not merely mimic the screenshot; it should use the same Py-Feat outputs and comparable workflows.

## Sources

- Official Py-Feat.Live repository: https://github.com/cosanlab/pyfeat-live
- Official Py-Feat repository: https://github.com/cosanlab/py-feat
- Official Py-Feat docs home: https://py-feat.org/
- Official Py-Feat model docs: https://py-feat.org/pages/models/
- Official Py-Feat plotting docs: https://py-feat.org/basic_tutorials/03_plotting.html
- Local reference clone used for design extraction: `/tmp/pyfeat-live-reference`
- Existing local demo to evolve: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/`

Key source facts:

- Py-Feat.Live has `Live`, `Viewer`, and `Analyze` pages.
- Official Live supports detector/model/compute/camera sidebar controls, detection-size presets, landmark style, overlay chips, Start/Pause/Stop, recording, and saved sessions.
- Official Viewer loads recorded sessions, replays video, draws overlays from saved Fex CSV, supports scrub/annotations/identity assignment, and shows per-frame AU/emotion data.
- Official Analyze batch-processes image/video files with presets and progress, then exposes completed results as sessions.
- Official `Detectorv2` predicts 20 AUs, 7 emotions, valence/arousal, gaze, 6-DoF pose, a 478-point 3D MediaPipe FaceMesh, 52 MediaPipe/ARKit blendshapes, and optional identity embeddings.

## Product Scope

### In Scope

Build a local web app with these pages:

1. `Live`
   - Camera stream.
   - Detector configuration.
   - Compute selection: `cpu`, `mps`, `cuda` when available.
   - Detection-size preset.
   - Overlay chips for faceboxes, landmarks, pose, gaze, AUs, emotions, valence/arousal, and blendshapes when the active detector supports them.
   - Landmark style: points, lines, mesh.
   - Start, Pause, Stop, Capture Frame, Record, Stop Record.
   - Per-frame metrics: FPS, latency, frame id, face count, device, detector state.
   - Client-side overlay rendering from normalized face coordinates.
   - Optional recording to a session directory.

2. `Viewer`
   - Session list from the local session directory.
   - Load a saved session.
   - Play/pause video if video exists.
   - Scrub through frame index/time.
   - Draw overlays from saved Fex/JSON frame data.
   - Show frame-level AU, emotion, valence/arousal, pose, and gaze panels.
   - Add simple annotations: event, exclude range, custom text marker.
   - Export annotations as JSON in the session directory.

3. `Analyze`
   - Upload image or video files.
   - Choose preset and compute device.
   - Queue items.
   - Run/pause/stop queue.
   - Show per-item status and progress.
   - Write completed outputs as sessions usable in Viewer.

4. `Presets / Settings`
   - Built-in presets:
     - `Detectorv2 · standard`
     - `Detectorv2 · fast`
     - `Detectorv1 · retinaface`
     - `Detectorv1 · img2pose`
   - Persist custom presets in a JSON file under the user config directory when possible.
   - Overlay settings: landmark style, point size, line opacity, AU display mode.

5. `System`
   - Health/status endpoint.
   - Compute capability endpoint.
   - Detector capability endpoint.
   - Logs endpoint for recent backend errors.

### Deferred Scope

These are official Py-Feat.Live-adjacent but not required for the first complete local web implementation:

- Tauri desktop shell.
- Auto-updater.
- Native file picker integration.
- Full identity clustering/merge UX.
- Keyboard shortcuts parity.
- Full WebSocket progress if polling is sufficient for local use.
- `Generate` page powered by `pyfeat-generator`.
- Exact visual parity with official Tailwind/Svelte implementation.

## Architecture

Keep the existing local app directory but split it into clearer modules:

```text
lib/py-feat-demo/
  pyfeat_web_demo.py
  pyfeat_analyzer.py
  pyfeat_live_core/
    __init__.py
    capabilities.py
    presets.py
    sessions.py
    recorder.py
    analysis_queue.py
    serialization.py
    overlay_geometry.py
  static/
    index.html
    styles.css
    app.js
  tests/
    test_pyfeat_analyzer.py
    test_pyfeat_web_demo.py
    test_pyfeat_live_api.py
    test_pyfeat_sessions.py
    test_pyfeat_analyze_queue.py
```

Use Flask for this local implementation instead of importing FastAPI/Svelte/Tauri. The goal is faithful feature behavior, not framework parity. Plain JS remains acceptable because the current app is already plain JS and the repo has no package-managed frontend build.

## Data Model

### Face Payload

Live and Viewer should share one face payload:

```json
{
  "face_idx": 0,
  "rect": [10, 20, 120, 140],
  "lm": [x0, y0, x1, y1],
  "landmark_count": 478,
  "pose": [pitch, roll, yaw],
  "gaze": [x, y, z],
  "emotions": {"neutral": 0.61, "happiness": 0.36},
  "aus": {"AU24": 0.76, "AU02": 0.53},
  "blendshapes": {"browInnerUp": 0.12},
  "valence_arousal": {"valence": 0.1, "arousal": -0.2}
}
```

`lm` should prefer `mesh_x_<i>/mesh_y_<i>` for `Detectorv2` when available and fall back to `x_<i>/y_<i>` for classic 68-point outputs.

### Session Directory

Use:

```text
~/Documents/pyfeat-live/sessions/<timestamp>/
  metadata.json
  frames.jsonl
  fex.csv
  video.mp4
  annotations.json
  thumbnails/
```

Minimum required for a session:

- `metadata.json`
- `frames.jsonl` or `fex.csv`

`video.mp4` is required only for sessions created with video recording or video Analyze items.

## API Design

### Existing Compatibility

Keep current routes:

- `GET /`
- `GET /api/status`
- `POST /api/analyze`

These remain for smoke tests and backward compatibility.

### New Live API

- `GET /api/system/health`
- `GET /api/system/compute`
- `GET /api/system/detector-capabilities`
- `GET /api/system/logs`
- `GET /api/presets`
- `POST /api/presets`
- `DELETE /api/presets/<id>`
- `POST /api/live/configure`
- `POST /api/live/hints`
- `POST /api/live/frame`
- `POST /api/live/recording/start`
- `POST /api/live/recording/stop`

`POST /api/live/frame` accepts a JPEG body and returns latest normalized JSON:

```json
{
  "id": 42,
  "generation": 12,
  "frame": [640, 480],
  "faces": []
}
```

The implementation may initially run detection synchronously per frame, but the API should be shaped so it can later move to decoupled detection like official Py-Feat.Live.

### Viewer API

- `GET /api/sessions`
- `GET /api/sessions/<session_id>`
- `GET /api/sessions/<session_id>/frames`
- `GET /api/sessions/<session_id>/frame/<frame_index>`
- `GET /api/sessions/<session_id>/video`
- `GET /api/sessions/<session_id>/annotations`
- `POST /api/sessions/<session_id>/annotations`

### Analyze API

- `GET /api/analyze/queue`
- `POST /api/analyze/queue`
- `PATCH /api/analyze/queue/<item_id>`
- `DELETE /api/analyze/queue/<item_id>`
- `POST /api/analyze/run`
- `POST /api/analyze/pause`
- `POST /api/analyze/stop`
- `POST /api/analyze/queue/clear-done`

Use polling for progress in the first implementation. WebSocket progress can be added after the queue is stable.

## UI Design

Do not build a landing page. The app opens into the usable product shell.

Shell:

- Top navigation: `Live`, `Viewer`, `Analyze`, `Settings`.
- Left sidebar on Live: Camera, Detector, Models, Compute, Detection Size.
- Main Live stage: black video/canvas surface, overlay canvas, status badges.
- Bottom Live control bar: overlay chips and stream/recording controls.
- Right inspector: Emotion bars, AU bars, valence/arousal, pose, gaze, blendshape summary.

Viewer:

- Left: session list and annotation tools.
- Center: video/canvas stage and scrub bar.
- Right: selected frame inspector.

Analyze:

- Dropzone/upload button.
- Queue table/list.
- Per-item preset/settings summary.
- Run controls.
- Completed item action: open in Viewer.

Settings:

- Presets list.
- Overlay style controls.
- Session directory path.
- Runtime notes for macOS `libomp` and FFmpeg dependencies.

## Error Handling

- Detector load failures surface in UI and `/api/system/logs`.
- Invalid image/file uploads return `400`.
- Missing sessions or queue items return `404`.
- Queue mutation of running items returns `409`.
- Model/pipeline errors mark the item/session failed without crashing the server.
- Camera permission errors remain client-side and visible near stream controls.

## Performance

- Default live detection upload budget: longest edge around 640 px.
- Default Live target: one detection in flight at a time.
- Client should cache the last frame and avoid stale async responses after Stop.
- Detector instances should be reused until configuration changes.
- `Detectorv2` should be the default Live preset.
- Identity should default off for speed unless the user enables it.

## Testing And Verification

Automated tests:

- Analyzer normalization tests for Detectorv1/Detectorv2-like rows.
- Capability and preset tests.
- Live configure/frame route tests with fake analyzer.
- Session IO tests for metadata, frames, annotations.
- Analyze queue lifecycle tests.
- Existing backward-compatible `/api/status` and `/api/analyze` tests.

Runtime smoke:

- Start server at `http://127.0.0.1:7861`.
- Confirm `/api/system/health`, `/api/presets`, `/api/live/configure`, `/api/live/frame`, `/api/sessions`, and `/api/analyze/queue`.
- Confirm real `Detectorv2` ready state on local Mac with `DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib`.
- Confirm sample image analysis returns 478 landmarks, 20 AUs, and nonzero emotions when a face is present.
- Verify rendered UI in Brave/Playwright: desktop and mobile no horizontal overflow, no console errors, page navigation works.

Manual/browser verification:

- Live loads and shows ready detector.
- Overlay chips toggle visible overlay categories.
- Analyze can process at least an image file into a session.
- Viewer can open that session and show frame-level data.

## Non-Goals

- Do not modify `/Users/hossay/workspace/main/facenet/lib/OpenFace-3.0/`.
- Do not require Tauri or Svelte for this local Flask demo.
- Do not mark the goal complete until Live, Viewer, Analyze, Presets/Settings, and verification are all implemented.
- Do not claim visual parity with official Py-Feat.Live unless side-by-side screenshots prove it.

## Implementation Strategy

Implement in milestones:

1. Core contracts: capabilities, presets, serialization, sessions.
2. Live API: configure, frame, hints, recording stubs, status.
3. Live UI shell and overlay renderer.
4. Session writing and Viewer page.
5. Analyze queue and file processing.
6. Settings/presets polish.
7. Full tests and browser verification.

This sequence ensures every milestone has testable behavior and moves toward the full Py-Feat.Live shape without requiring a framework rewrite.
