# Facenet Research Workspace

Facenet is a research workspace for real-time facial behavior analysis with
[Py-Feat](https://py-feat.org/). Its main application is a local web demo built
around Py-Feat Detectorv2, with supporting benchmark scripts, design notes, and
a research-paper draft.

Despite the workspace name, this project is not an implementation of the
FaceNet face-recognition model.

## What is included

- Live webcam analysis with face boxes, a 478-point mesh, emotions, Action
  Units (AUs), valence/arousal, gaze, head pose, and blendshapes.
- Viewer, session recording, annotations, and queued image analysis.
- Deterministic pilot benchmark tooling for AFLFP landmarks and DISFA AUs.
- An OpenCV runner for separating model inference speed from browser and API
  overhead.
- A vendored OpenFace 3.0 research baseline with local demo experiments.
- Design notes, weekly progress notes, and a LaTeX benchmark-paper draft.

The documented browser demo measurement is approximately 22.1 FPS at 45 ms
latency on an Apple Silicon development machine. This is an observed
end-to-end measurement, not a general model-performance claim.

## Repository layout

```text
.
├── docs/                  Design, implementation, and weekly notes
├── lib/
│   ├── py-feat-demo/      Primary Py-Feat web demo and benchmark tools
│   └── OpenFace-3.0/      Vendored OpenFace baseline and local experiments
└── paper/                 LaTeX source, bibliography, and rendered draft
```

Datasets, downloaded model weights, generated outputs, caches, and local tool
state are intentionally excluded from Git.

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
is implied by this repository. Model checkpoints are also excluded; follow
the upstream Py-Feat and OpenFace instructions to obtain compatible weights.

## Upstream projects

This workspace builds on:

- [cosanlab/py-feat](https://github.com/cosanlab/py-feat)
- [CMU-MultiComp-Lab/OpenFace-3.0](https://github.com/CMU-MultiComp-Lab/OpenFace-3.0)
- [biubug6/Pytorch_Retinaface](https://github.com/biubug6/Pytorch_Retinaface)
- [ZhenglinZhou/STAR](https://github.com/ZhenglinZhou/STAR)

Vendored third-party code remains subject to its upstream license files. No
repository-wide license has been granted for the original workspace material.
