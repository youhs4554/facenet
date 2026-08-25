# Facenet Research Workspace

Facenet is a research workspace for real-time facial behavior analysis with
[Py-Feat](https://py-feat.org/). Its main application is a local web demo built
around Py-Feat Detectorv2, with supporting benchmark scripts, design notes, and
a reproducible test-only evaluation paper.

Despite the workspace name, this project is not an implementation of the
FaceNet face-recognition model.

## What is included

- Live webcam analysis with face boxes, a 478-point mesh, emotions, Action
  Units (AUs), valence/arousal, gaze, head pose, and blendshapes.
- Viewer, session recording, annotations, and queued image analysis.
- Deterministic test-only benchmark tooling for AFLFP landmarks and DISFA AUs.
- An OpenCV runner for separating model inference speed from browser and API
  overhead.
- A standalone, browser-only MediaPipe Blendshape V2 webcam demo.
- Design notes, weekly progress notes, and a result-driven LaTeX paper.

The documented browser demo measurement is approximately 22.1 FPS at 45 ms
latency on an Apple Silicon development machine. This is an observed
end-to-end measurement, not a general model-performance claim.

## Repository layout

```text
.
├── docs/                  Design, implementation, and weekly notes
├── lib/
│   ├── mediapipe-blendshape-demo/  Browser-only Blendshape V2 demo
│   └── py-feat-demo/      Py-Feat web demo and benchmark tools
└── paper/                 LaTeX source, results, generated tables, and figures
```

Datasets, downloaded model weights, generated outputs, caches, and local tool
state are intentionally excluded from Git. The legacy local OpenFace checkout
is also outside this repository's managed scope.

## Quick start

Python 3.10 or later is recommended.

```sh
cd lib/py-feat-demo
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device auto
```

Open <http://127.0.0.1:7861>. The `--device` option accepts `auto`, `cuda`,
`mps`, or `cpu`. Model initialization can take time on the first request
because Py-Feat may download weights and populate its cache.

For Apple Silicon systems using Homebrew libraries under `/opt/homebrew`, the
runtime may also need:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device cpu
```

See [the demo README](lib/py-feat-demo/README.md) for the OpenCV runner,
session storage, performance options, and troubleshooting.

For the lightweight MediaPipe-only webcam demo, no Python model environment is
required:

```sh
cd lib/mediapipe-blendshape-demo
python3 -m http.server 8080
```

Open <http://localhost:8080>. See the
[MediaPipe demo README](lib/mediapipe-blendshape-demo/README.md) for model
configuration, interpretation, tests, and limitations.

## Tests

The portable test suite uses a fake analyzer and does not require model
downloads or benchmark datasets:

```sh
cd lib/py-feat-demo
python -m pytest -p no:cacheprovider tests -v \
  -k "not inspect_real_dataset_contract and not aflfp_sampling_balances_subjects_and_canonical_movements"
node --check static/app.js
```

If the local Python environment is not prepared, the Python tests can be run
with `uv`:

```sh
cd lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 \
uv run --with pytest --with numpy --with opencv-python-headless \
  --with pandas --with pillow --with matplotlib --with flask \
  python -m pytest -p no:cacheprovider tests -v \
  -k "not inspect_real_dataset_contract and not aflfp_sampling_balances_subjects_and_canonical_movements"
```

After compatible AFLFP and DISFA distributions are available through `data/`,
omit the `-k` expression to validate the full dataset contract.

## Data and model files

The benchmark scripts expect datasets to be supplied separately. The local
`data` path is not versioned, and no dataset license or redistribution right
is implied by this repository.

Py-Feat model checkpoints are not committed. Creating `Detectorv2` downloads
the required pretrained models on first use and stores them in the local model
cache; later runs reuse the cached files. A network connection is therefore
normally required for the first model initialization on a new machine.

## Upstream project

This workspace builds on [cosanlab/py-feat](https://github.com/cosanlab/py-feat)
and follows interaction patterns from
[cosanlab/pyfeat-live](https://github.com/cosanlab/pyfeat-live).

Py-Feat code and pretrained models have separate license considerations;
review the upstream model licenses before deployment. No repository-wide
license has been granted for the original workspace material.
