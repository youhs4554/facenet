#!/usr/bin/env bash
set -euo pipefail

mode=${1:-inspect}
run_id=${A2F_SDK_RUN_ID:-inspect}
precision_profile=${A2F_SDK_PRECISION_PROFILE:-official}
case "$run_id" in
  *[!A-Za-z0-9._-]*|""|.*|-*) echo "invalid A2F_SDK_RUN_ID" >&2; exit 2 ;;
esac
run_out="/output/runs/$run_id"
model_out="$run_out/model"
export A2F_SDK_OUTPUT_DIR="$run_out"
export A2F_SDK_MODEL_DIR="$model_out"

inspect() {
  python3 - <<'PY'
import json, subprocess, tensorrt
print(json.dumps({
  "cuda": subprocess.check_output(["nvcc", "--version"], text=True).strip().splitlines()[-1],
  "tensorrt": tensorrt.__version__,
  "sdk_commit": "1ca0f02535ed774f5dbcd724a31cd486368dc783",
  "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free", "--format=csv,noheader"], text=True).strip(),
}, sort_keys=True))
PY
  /opt/a2f/bin/a2f-geometry-exporter --help
}

build_engine() {
  if [[ -e "$run_out" ]]; then
    echo "run-owned output already exists; choose a new A2F_SDK_RUN_ID: $run_out" >&2
    exit 2
  fi
  mkdir -p "$model_out"
  cp -a /models/. "$model_out/"
  python3 /opt/sidecar/build_engine.py build \
    --onnx "$model_out/network.onnx" \
    --trt-info "$model_out/trt_info.json" \
    --output "$model_out/network.trt" \
    --manifest "$model_out/engine-manifest.json" \
    --precision-profile "$precision_profile" | tee "$run_out/engine-build.json"
}

export_geometry() {
  python3 /opt/sidecar/build_engine.py verify \
    --onnx "$model_out/network.onnx" \
    --trt-info "$model_out/trt_info.json" \
    --output "$model_out/network.trt" \
    --manifest "$model_out/engine-manifest.json"
  mkdir -p "$run_out/geometry" "$run_out/weights"
  /opt/a2f/bin/a2f-geometry-exporter geometry "$model_out/model.json" /input/test.wav /input/emotions.csv /input/request.yml "$run_out/geometry"
  /opt/a2f/bin/a2f-geometry-exporter weights "$model_out/model.json" /input/test.wav /input/emotions.csv /input/request.yml "$run_out/weights"
  python3 /opt/sidecar/verify_outputs.py
}

case "$mode" in
  inspect) inspect ;;
  build-engine) inspect; build_engine ;;
  export) inspect; export_geometry ;;
  all) inspect; build_engine; export_geometry ;;
  *) echo "usage: entrypoint.sh inspect|build-engine|export|all" >&2; exit 2 ;;
esac
