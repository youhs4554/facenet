#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
container_name="audio2face-3d-diffusion"
image="nvcr.io/nim/nvidia/audio2face-3d:2.0"
engine_dir="$repo_root/.tools/audio2face3d/v3/nim-custom-engines"
config_dir="$repo_root/.tools/audio2face3d/v3/nim-custom-configs"
client_dir="$repo_root/.tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app"

required=(
  "$engine_dir/multi_v3.2.trt"
  "$engine_dir/a2e.trt"
  "$config_dir/diffusion-claire-single-stream.yaml"
  "$config_dir/deployment-single-stream.yaml"
  "$client_dir/.venv/bin/python"
  "$client_dir/a2f_3d.py"
)
for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    printf 'missing required v3 artifact: %s\n' "$path" >&2
    exit 10
  fi
done

expected_a2f_sha="5bcefb513c9ef858ea55c7847814e1a37cef93e68190f9fa17471be96c193cd4"
expected_a2e_sha="2d0de12b36fd17aa8b571a6ce707e996f737a0e7bf3012a3e4491f5b2185a6a6"
actual_a2f_sha="$(sha256sum "$engine_dir/multi_v3.2.trt" | cut -d' ' -f1)"
actual_a2e_sha="$(sha256sum "$engine_dir/a2e.trt" | cut -d' ' -f1)"
if [[ "$actual_a2f_sha" != "$expected_a2f_sha" || "$actual_a2e_sha" != "$expected_a2e_sha" ]]; then
  echo "v3 engine integrity check failed" >&2
  exit 11
fi

if docker container inspect "$container_name" >/dev/null 2>&1; then
  if [[ "$(docker inspect "$container_name" --format '{{.State.Running}}')" != "true" ]]; then
    docker start "$container_name" >/dev/null
  fi
else
  docker run -d \
    --name "$container_name" \
    --gpus 'device=1' \
    --shm-size=16g \
    -p 127.0.0.1:52100:52000 \
    --entrypoint /usr/local/bin/a2f_pipeline.run \
    -v "$engine_dir:/tmp/a2x:ro" \
    -v "$config_dir:/mnt/configs:ro" \
    "$image" \
    --stylization-config /mnt/configs/diffusion-claire-single-stream.yaml \
    --deployment-config /mnt/configs/deployment-single-stream.yaml \
    >/dev/null
fi

for _attempt in $(seq 1 30); do
  if "$client_dir/.venv/bin/python" "$client_dir/a2f_3d.py" \
      health_check --url 127.0.0.1:52100 2>/dev/null | grep -q ONLINE; then
    echo "Audio2Face-3D v3 diffusion ONLINE at 127.0.0.1:52100"
    exit 0
  fi
  if [[ "$(docker inspect "$container_name" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]]; then
    echo "v3 diffusion container exited during startup" >&2
    exit 20
  fi
  sleep 2
done

echo "v3 diffusion health check timed out" >&2
exit 21
