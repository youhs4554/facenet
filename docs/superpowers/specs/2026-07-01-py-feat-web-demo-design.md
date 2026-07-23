# Py-Feat Web Demo Design

Date: 2026-07-01

## Goal

Build a demonstration web app for `cosanlab/py-feat` that follows the interaction pattern of the existing OpenFace 3.0 web demo in `/Users/hossay/workspace/main/facenet/lib/OpenFace-3.0/`, while adapting the UI and API contract to Py-Feat `Detectorv2` outputs.

The first version is a live webcam demo. It should make Py-Feat's multi-output analysis visible in a single screen without adding session management, recording, or batch workflows.

## Sources

- Existing reference app: `/Users/hossay/workspace/main/facenet/lib/OpenFace-3.0/web_demo.py`
- Existing reference static UI: `/Users/hossay/workspace/main/facenet/lib/OpenFace-3.0/web_demo_static/`
- Py-Feat project: https://github.com/cosanlab/py-feat
- Py-Feat docs: https://py-feat.org/

Py-Feat `Detectorv2` is the target analyzer because it provides a single multi-task pipeline for Action Units, emotions, valence/arousal, gaze, head pose, 478-point FaceMesh, and blendshapes.

## Scope

### In Scope

- Browser webcam input with Start and Stop controls.
- Camera selection, resolution selection, horizontal flip, and analysis interval controls.
- Flask server with static HTML/CSS/JS frontend, mirroring the existing OpenFace demo shape.
- Lazy-loaded Py-Feat analyzer using `Detectorv2`.
- Device option exposed by the server CLI: `auto`, `cpu`, `mps`, or `cuda`.
- `/api/status` endpoint for model readiness, device, supported metric labels, and any load error.
- `/api/analyze` endpoint that accepts a browser JPEG data URL and returns normalized JSON.
- One-screen dashboard showing:
  - Live camera input.
  - Analysis output with overlays.
  - Runtime stats: device, readiness, FPS, latency, face count.
  - Emotion bars.
  - Action Unit bars.
  - Valence/arousal 2D plot.
  - Head pose readout.
  - Gaze readout and arrow overlay.
  - Face box and FaceMesh or landmark overlay.
- Download of the current analyzed frame or current visible result.
- Unit tests for API helpers, analyzer injection, and result normalization.

### Out of Scope

- Video recording.
- Session history.
- CSV or JSON export of time series.
- Batch image or video analysis.
- Identity tracking or clustering.
- Full replication of Py-Feat Live.
- Reworking the OpenFace demo files.

## Product Shape

The app opens directly into the demo surface, not a landing page.

The layout follows the existing OpenFace dashboard pattern:

- Left column: camera input, camera settings, Start/Stop controls.
- Center column: analyzed frame and overlay controls.
- Right column: live analysis metrics.

The OpenFace UI's Gaze-heavy emphasis changes to a Py-Feat expression-analysis emphasis. The most prominent panels are Emotion, Action Units, and Valence/Arousal. Pose, gaze, and mesh are visible but secondary.

## User Workflow

1. The user opens the app.
2. The app calls `/api/status`.
3. The first status request starts model loading in the background if it has not started yet.
4. If the model is loading, the app shows a loading state and disables Start until status is ready.
5. The user selects a camera/resolution if desired.
6. The user presses Start.
7. The browser captures frames at the configured interval and sends one frame at a time to `/api/analyze`.
8. The app renders the latest result and skips additional frames while a request is in flight.
9. The user can toggle overlays without re-running analysis.
10. The user presses Stop to end the camera stream.

## Architecture

Create the Py-Feat demo as an isolated app directory under the workspace, for example:

```text
lib/py-feat-demo/
  pyfeat_web_demo.py
  pyfeat_analyzer.py
  static/
    index.html
    styles.css
    app.js
  tests/
    test_pyfeat_web_demo.py
    test_pyfeat_normalization.py
  README.md
```

This keeps Py-Feat demo code separate from the OpenFace repository while still allowing the OpenFace demo to be used as a design and API reference.

### Server

The Flask app owns routing, image decoding, response encoding, analyzer state, and analyzer lifecycle.

The analyzer wrapper owns Py-Feat imports, `Detectorv2` construction, device selection, temporary frame handling, and conversion from Fex-like outputs into a stable JSON contract. Model construction is started from `/api/status` so process startup stays responsive while the UI can still block Start until the model is ready.

The analyzer is injectable so tests can use a fake analyzer without loading Py-Feat models.

### Frontend

The frontend is plain HTML/CSS/JS, matching the existing OpenFace demo's low-dependency style.

The frontend owns webcam access, request pacing, overlay toggles, and rendering of normalized metrics. It should not know Py-Feat DataFrame column names directly. It should only consume the normalized API response.

## API Contract

### GET `/api/status`

Returns:

```json
{
  "ready": true,
  "state": "ready",
  "device": "mps",
  "error": "",
  "labels": {
    "emotions": ["anger", "disgust", "fear", "happiness", "sadness", "surprise", "neutral"],
    "aus": ["AU01", "AU02", "AU04"]
  }
}
```

`state` is one of `idle`, `loading`, `ready`, or `error`.

### POST `/api/analyze`

Request:

```json
{
  "image": "data:image/jpeg;base64,..."
}
```

Response:

```json
{
  "analysis": {
    "face_count": 1,
    "faces": [
      {
        "box": {"x": 10, "y": 20, "width": 120, "height": 140, "confidence": 0.98},
        "emotions": [{"label": "happiness", "value": 0.72}],
        "aus": [{"code": "AU12", "value": 0.63}],
        "valence": 0.34,
        "arousal": 0.12,
        "pose": {"pitch": 0.1, "roll": -0.02, "yaw": 0.2},
        "gaze": {"x": 0.0, "y": 0.0, "z": 1.0},
        "mesh": [{"x": 0.42, "y": 0.31, "z": -0.02}]
      }
    ],
    "primary_face": 0,
    "fps": 4.7,
    "latency_ms": 212.5
  },
  "device": "mps"
}
```

The response should remain valid when no face is detected:

```json
{
  "analysis": {
    "face_count": 0,
    "faces": [],
    "primary_face": null,
    "fps": 0.0,
    "latency_ms": 0.0
  },
  "device": "mps"
}
```

## UI Requirements

- The app must be usable on a laptop viewport without scrolling away from the main analysis surface.
- Cards should be shallow and functional, with compact headings and no nested card layout.
- Overlay controls should be toggles or icon buttons, not explanatory text blocks.
- The main overlay supports:
  - Face box.
  - FaceMesh or reduced landmark points.
  - Gaze arrow.
  - Pose axes or numeric pose badge.
- Emotion and AU panels use sorted bars, with values clamped to a display range.
- Valence/arousal uses a 2D quadrant plot with the current point and a short trail of recent points.
- No-face state should clear stale face overlays while preserving the latest runtime status.
- Loading and error states should be visible in the header/status area and near the Start control.

## Error Handling

- Missing `image` in `/api/analyze` returns HTTP 400.
- Invalid image payload returns HTTP 400 with a concise error.
- Analyzer/model errors return HTTP 500 with a concise error string.
- `/api/status` exposes persistent model load failure without crashing the server.
- The frontend displays analysis errors in the output status area and continues running unless the camera stream fails.
- Camera permission errors should be shown near the Start button.

## Performance Constraints

- Only one analysis request may be in flight per browser session.
- Default analysis interval should be conservative, around 300-500 ms.
- Frames should be downscaled before sending to the server, targeting about 480 px width by default.
- The server should lazy-load the model to keep process startup responsive.
- The UI should show latency separately from input frame rate so slow model inference is obvious.

## Testing

Unit tests:

- Data URL decode accepts browser JPEG payloads.
- App factory uses an injected fake analyzer.
- `/api/status` returns readiness and labels.
- `/api/analyze` returns normalized JSON for a fake analyzer.
- Normalization handles no-face results.
- Normalization clamps or defaults missing numeric values safely.

Manual verification:

- Start the dev server.
- Load the app in a browser.
- Confirm status transitions from loading to ready or displays a load error.
- Start the webcam.
- Confirm frames are analyzed without overlapping requests.
- Toggle overlays and confirm the layout does not shift.
- Stop the webcam and confirm camera tracks end.

## Acceptance Criteria

- A user can run a local Flask web demo for Py-Feat.
- The UI follows the OpenFace demo's live-camera structure but reflects Py-Feat outputs.
- Py-Feat `Detectorv2` is the intended real analyzer.
- Tests pass with fake analyzer injection without downloading model weights.
- The implementation does not modify or revert the existing OpenFace demo.
- README instructions explain setup, run command, model download/cache behavior, device options, and known first-run latency.
