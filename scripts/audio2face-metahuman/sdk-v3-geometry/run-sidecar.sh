#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../../.." && pwd)
output_root="$repo_root/.tools/audio2face3d/sdk-v3-geometry"
phase_a_result="$repo_root/.tools/audio2face3d/cross-avatar-phase-a/20260827-taro-route-two-avatar-audit/phase-a-result.json"
mode=${1:-run}
mkdir -p "$output_root"
export A2F_UID=$(id -u)
export A2F_GID=$(id -g)

capture_runtime_after_state() {
  original_rc=$?
  trap - EXIT
  set +e
  python3 "$script_dir/../a2f_geometry_sidecar.py" snapshot --output "$audit_dir/host-after.json"
  snapshot_rc=$?
  python3 "$script_dir/../a2f_geometry_sidecar.py" compare \
    --before "$audit_dir/host-before.json" \
    --after "$audit_dir/host-after.json" \
    --output "$audit_dir/host-non-impact.json"
  compare_rc=$?
  if [[ $original_rc -eq 0 && ( $snapshot_rc -ne 0 || $compare_rc -ne 0 ) ]]; then
    echo "Sidecar completed but host non-impact verification failed: $audit_dir" >&2
    exit 43
  fi
  exit "$original_rc"
}

case "$mode" in
  build)
    docker compose -f "$script_dir/compose.yaml" build geometry
    ;;
  inspect)
    docker compose -f "$script_dir/compose.yaml" run --rm -T geometry inspect
    ;;
  run)
    export A2F_SDK_RUN_ID=${A2F_SDK_RUN_ID:-sdk-v30-$(date -u +%Y%m%dT%H%M%SZ)}
    export A2F_SDK_IMAGE_DIGEST=$(docker image inspect \
      a2f-v3-geometry-sdk:cuda12.8-trt10.13 --format '{{.Id}}')
    audit_dir="$output_root/audits/$A2F_SDK_RUN_ID"
    mkdir -p "$audit_dir"
    python3 "$script_dir/../a2f_geometry_sidecar.py" snapshot --output "$audit_dir/host-before.json"
    trap capture_runtime_after_state EXIT
    python3 "$script_dir/../a2f_geometry_sidecar.py" phase-a \
      --input "$phase_a_result" --output "$audit_dir/phase-a-gate.json"
    if ! python3 "$script_dir/../a2f_geometry_sidecar.py" preflight --minimum-free-mib 8192 --output "$output_root/runtime-preflight.json"; then
      echo "Phase B runtime blocked by the conservative GPU1 attempt gate; no existing container was stopped." >&2
      exit 42
    fi
    docker compose -f "$script_dir/compose.yaml" run --rm -T geometry all \
      | tee "$audit_dir/sidecar-run.log"
    ;;
  *)
    echo "usage: run-sidecar.sh build|inspect|run" >&2
    exit 2
    ;;
esac

echo "cleanup (not run): docker image rm a2f-v3-geometry-sdk:cuda12.8-trt10.13"
