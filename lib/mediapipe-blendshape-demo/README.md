# MediaPipe Blendshape V2 Webcam Demo

A standalone browser demo for MediaPipe Face Landmarker and its Blendshape V2
output. It displays the 478 face landmarks and all 52 blendshape coefficients
without sending webcam frames to a server.

## Run

Serve this directory from `localhost` (camera access does not work from a plain
`file://` URL):

```sh
cd lib/mediapipe-blendshape-demo
python3 -m http.server 8080
```

Open <http://localhost:8080>, select **카메라 시작**, and grant camera access.
The first run downloads MediaPipe Tasks Vision WASM and the 3.6 MB Face
Landmarker model. Both dependency URLs are pinned in `app.js`.

## Test

```sh
node --test --experimental-test-coverage tests/*.test.js
```

## Configuration and interpretation

- `runningMode: "VIDEO"` is used for webcam frames.
- `numFaces: 1` enables the task's temporal smoothing and matches the model's
  front-facing, single-person use case.
- `outputFaceBlendshapes: true` returns 52 coefficients in the `[0, 1]` range.
- Detection, presence, and tracking confidence thresholds use the documented
  default of `0.5`.
- A small exponential moving average (`alpha = 0.35`) reduces display jitter;
  it does not change the model output or assign semantic thresholds.
- GPU execution is attempted first, with an automatic CPU fallback.

The model card describes an MLP-Mixer that consumes 146 landmarks selected from
the 478 FaceMesh landmarks. It is intended for real-time AR expression control,
not identity recognition, medical decisions, or other life-critical uses.
Performance can degrade with poor lighting, motion, occlusion, a distant face,
or large out-of-plane rotation.

## Official references

- [MediaPipe Blendshape V2 model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf)
- [Face Landmarker guide for Web](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/web_js)
- [MediaPipe Tasks Vision package](https://www.npmjs.com/package/@mediapipe/tasks-vision)
- [Face Landmarker model bundle](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)
