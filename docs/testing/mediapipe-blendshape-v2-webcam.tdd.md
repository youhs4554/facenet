# MediaPipe Blendshape V2 Webcam Demo - TDD Evidence

## Source and user journey

No plan file was supplied. The journey was derived from the requested feature:
as a researcher, I can start a webcam and inspect MediaPipe Blendshape V2
coefficients and face landmarks locally, so that I can evaluate expression
signals without uploading video.

## RED and GREEN evidence

| Stage | Command | Result | Evidence |
|---|---|---|---|
| RED | `node --test lib/mediapipe-blendshape-demo/tests/blendshape-utils.test.js` | Expected failure | `ERR_MODULE_NOT_FOUND` for the not-yet-created processing module |
| GREEN | Same command after implementation | PASS | 4 tests passed, 0 failed |
| Coverage | `node --test --experimental-test-coverage lib/mediapipe-blendshape-demo/tests/blendshape-utils.test.js` | PASS | Utility: 93.94% lines, 92.31% branches, 100% functions |

## Test specification

| # | Guaranteed behavior | Test | Type | Result |
|---|---|---|---|---|
| 1 | Neutral is omitted, scores are clamped to `[0, 1]`, and results are sorted descending | `normalizeBlendshapes removes neutral, clamps scores, and sorts descending` | Unit | PASS |
| 2 | Missing, malformed, and non-finite categories are ignored | `normalizeBlendshapes ignores malformed categories` | Unit | PASS |
| 3 | Existing scores are temporally interpolated without changing input order | `smoothBlendshapes interpolates previous values without changing order` | Unit | PASS |
| 4 | New names retain current scores and smoothing alpha is bounded | `smoothBlendshapes uses current values for unseen names and bounds alpha` | Unit | PASS |

## Browser smoke test

A local HTTP server and a headless Chromium session with a synthetic camera
verified that the page loads, MediaPipe initializes, the GPU delegate is
selected, the camera reaches `readyState = 4`, and the UI transitions from
idle to searching. The synthetic source contains no face, so the 52 live
coefficients and landmark overlay still require an ordinary webcam/manual face
for visual confirmation.

## Known gaps

The model and WASM are loaded from pinned third-party URLs and require network
access on first use. The browser test covers initialization and the no-face
camera path; it does not assert model accuracy or expression semantics.
