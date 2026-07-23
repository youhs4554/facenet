# Py-Feat Live Web Demo

This is a local browser implementation inspired by official [Py-Feat.Live](https://github.com/cosanlab/pyfeat-live) workflows and powered by [cosanlab/py-feat](https://github.com/cosanlab/py-feat). It uses a lightweight Flask backend with a static frontend.

The app includes:

- `Live`: webcam input, detector presets, overlays, emotions, AUs, pose, gaze, valence/arousal, blendshapes, and JSONL recording.
- `Viewer`: local session list, frame scrubber, overlay replay from saved frame payloads, and annotations API support.
- `Analyze`: image queue processing that writes completed items as Viewer sessions.
- `Settings`: compute capability, detector capability, presets, and backend logs.

## Setup

```sh
cd lib/py-feat-demo
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```sh
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device auto
```

Open <http://127.0.0.1:7861>.

Device options are `auto`, `cuda`, `mps`, and `cpu`. `auto` prefers CUDA when available, then Apple MPS, then CPU. Built-in presets cover `Detectorv2` standard/fast and `Detectorv1` retinaface/img2pose-style configurations.

On Apple Silicon Macs using Homebrew under `/opt/homebrew`, Py-Feat may need the Homebrew library paths at runtime:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device cpu
```

## First Run

The first `/api/status` request starts Py-Feat model loading in the background. Py-Feat may download model weights or populate its model cache on first use. The Start button remains disabled while the analyzer is loading and becomes available when the backend reports that it is ready.

## OpenCV Live Runner

`pyfeat_opencv_demo.py` runs the same Py-Feat analyzer directly through OpenCV, without the browser or FastAPI frame transport. This is useful for separating model speed from web rendering and JPEG upload overhead.

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
PYFEAT_LIVE_MAX_TRACK_INTERVAL=180 \
uv run --with py-feat --with numpy --with pandas --with opencv-python \
python pyfeat_opencv_demo.py --camera 0 --device auto --detection-size 640
```

For a headless FPS check with a fixture image:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
PYFEAT_LIVE_MAX_TRACK_INTERVAL=180 \
uv run --with py-feat --with numpy --with pandas --with opencv-python \
python pyfeat_opencv_demo.py --image /tmp/pyfeat-benchmark-640.jpg --benchmark --duration 15 --no-window
```

## Live Performance Notes

The default `Detectorv2 · realtime` preset uses a 360px detection budget and keeps blendshape serialization disabled unless the Blendshapes panel is enabled. The browser still renders the camera stream at native video speed; analysis overlays update as new backend results arrive.

On Apple MPS, `PYFEAT_LIVE_AMP=1` is available as an experiment but is not recommended in this workspace: it measured substantially slower than the default fp32 path. `PYFEAT_LIVE_REFINE_DETECT_ROI=1` restores the extra detect-frame ROI refinement pass if maximum detect-frame alignment is preferred over realtime latency.

## Outputs And Storage

Live and Viewer share a Py-Feat.Live-style face payload. The UI renders:

- Face boxes.
- 68 classic landmarks for Detectorv1 or 478-point MediaPipe face mesh for Detectorv2 when available.
- Emotion bars.
- Action Unit (AU) bars for all Py-Feat AU outputs, with AU descriptions.
- Valence/arousal, head pose, gaze, and blendshapes when the active detector provides them.
- FPS, latency, selected device, frame id, and face count.

Sessions are stored under:

```text
~/Documents/pyfeat-live/sessions/<timestamp>/
  metadata.json
  frames.jsonl
  annotations.json
```

Set `PYFEAT_LIVE_SESSION_DIR` to override the session root.

## Tests

From an activated virtual environment, run the portable suite that does not
require benchmark datasets:

```sh
python -m pytest -p no:cacheprovider tests -v \
  -k "not inspect_real_dataset_contract and not aflfp_sampling_balances_subjects_and_canonical_movements"
```

In this workspace, local `python` may not be on `PATH`; agents have used:

```sh
PYTHONDONTWRITEBYTECODE=1 \
uv run --with pytest --with numpy --with opencv-python-headless \
  --with pandas --with pillow --with matplotlib --with flask \
  python -m pytest -p no:cacheprovider tests -v \
  -k "not inspect_real_dataset_contract and not aflfp_sampling_balances_subjects_and_canonical_movements"
```

These tests use fake analyzer injection and do not require Py-Feat model weight
downloads. Once AFLFP and DISFA are available under the workspace `data` path,
omit the `-k` expression to run the complete dataset-contract checks.

`node --check static/app.js` is a quick frontend syntax check.

## Troubleshooting

- On macOS, importing Py-Feat can fail if xgboost cannot find `libomp.dylib`. Installing OpenMP with `/opt/homebrew/bin/brew install libomp` can resolve this.
- If Py-Feat fails with `Could not load libtorchcodec` or missing `libavutil.*.dylib`, install FFmpeg with `/opt/homebrew/bin/brew install ffmpeg`.
- The browser must be allowed to use the camera before frames can be analyzed.
- First load can be slow while Py-Feat imports, initializes models, and downloads or reads cached weights.
