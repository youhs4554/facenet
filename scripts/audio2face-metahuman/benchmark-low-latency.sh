#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <baseline|optimized> [run-id]" >&2
  exit 2
fi

mode="$1"
run_id="${2:-1}"
if [[ "$mode" != "baseline" && "$mode" != "optimized" ]]; then
  echo "ERROR: mode must be 'baseline' or 'optimized'." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
install_root="$repo_root/.tools/audio2face-metahuman"
editor="$install_root/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
project="$install_root/KairosSample/KairosSample.uproject"
wav="$repo_root/.tools/audio2face3d/Audio2Face-3D-Samples/example_audio/Claire_sadness_16khz_5_sec.wav"
output_dir="$repo_root/.ecc/benchmarks/audio2face"
log_file="$output_dir/$mode-$run_id.log"
json_file="$output_dir/$mode-$run_id.json"

if [[ ! -x "$editor" || ! -f "$project" || ! -f "$wav" ]]; then
  echo "ERROR: Audio2Face benchmark prerequisites are missing." >&2
  exit 2
fi
if ! curl -fsS http://127.0.0.1:8000/v1/health/ready >/dev/null; then
  echo "ERROR: Audio2Face-3D NIM is not ready." >&2
  exit 2
fi
if pgrep -f "$editor $project" >/dev/null; then
  echo "ERROR: KairosSample Unreal Editor is already running." >&2
  exit 2
fi

xfce_pid="$(pgrep -n xfce4-session || true)"
if [[ -z "$xfce_pid" ]]; then
  echo "ERROR: VNC XFCE session not found." >&2
  exit 2
fi
vnc_dbus="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -n 1)"
vnc_runtime="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^XDG_RUNTIME_DIR=//p' | head -n 1)"

mkdir -p "$output_dir"
set +e
env \
  DISPLAY=:1 \
  XAUTHORITY=/home/aim/.Xauthority \
  DBUS_SESSION_BUS_ADDRESS="$vnc_dbus" \
  XDG_RUNTIME_DIR="$vnc_runtime" \
  SDL_AUDIODRIVER=pulseaudio \
  CUDA_VISIBLE_DEVICES=1 \
  timeout 50s \
  "$editor" \
  "$project" \
  /Game/Maps/JesseAB/AB16_FaceAllGrooms \
  -game \
  -vulkan \
  -graphicsadapter=0 \
  -RenderOffscreen \
  -unattended \
  -nop4 \
  -nosplash \
  -ResX=640 \
  -ResY=360 \
  -A2FLatencyBenchmark \
  "-A2FLatencyMode=$mode" \
  "-A2FWav=$wav" \
  -A2FLatencyExit \
  '-ExecCmds=t.MaxFPS 30,r.CEFGPUAcceleration 0' \
  "-abslog=$log_file" \
  >/dev/null 2>&1
editor_exit=$?
set -e

start_line="$(rg 'A2F-LATENCY.*animation_started' "$log_file" | tail -n 1 || true)"
end_line="$(rg 'A2F-LATENCY.*animation_ended' "$log_file" | tail -n 1 || true)"
animation_ms="$(sed -n 's/.*elapsed_ms=\([0-9.]*\).*/\1/p' <<<"$start_line")"
send_ms="$(rg -o 'audio_send_completed success=true elapsed_ms=[0-9.]+' "$log_file" | tail -n 1 | sed 's/.*=//' || true)"
end_ms="$(sed -n 's/.*elapsed_ms=\([0-9.]*\).*/\1/p' <<<"$end_line")"
start_frame="$(sed -n 's/.*\[[[:space:]]*\([0-9][0-9]*\)\]LogTemp.*animation_started.*/\1/p' <<<"$start_line")"
end_frame="$(sed -n 's/.*\[[[:space:]]*\([0-9][0-9]*\)\]LogTemp.*animation_ended.*/\1/p' <<<"$end_line")"
received_line="$(rg 'received [0-9]+ animation samples, [0-9]+ audio samples' "$log_file" | tail -n 1 || true)"
animation_samples="$(sed -n 's/.*received \([0-9][0-9]*\) animation samples.*/\1/p' <<<"$received_line")"
audio_samples="$(sed -n 's/.*animation samples, \([0-9][0-9]*\) audio samples.*/\1/p' <<<"$received_line")"

if [[ $editor_exit -ne 0 || -z "$animation_ms" || -z "$send_ms" || -z "$end_ms" || -z "$start_frame" || -z "$end_frame" ]]; then
  echo "ERROR: benchmark failed (exit=$editor_exit, log=$log_file)." >&2
  exit 1
fi
render_fps="$(awk -v sf="$start_frame" -v ef="$end_frame" -v sm="$animation_ms" -v em="$end_ms" 'BEGIN { printf "%.3f", (ef - sf) / ((em - sm) / 1000.0) }')"

printf '{\n  "mode": "%s",\n  "run_id": "%s",\n  "wav": "%s",\n  "gpu_render": "Quadro RTX 5000",\n  "gpu_inference": "RTX A4500",\n  "ue_version": "5.6.0-43139311",\n  "ace_version": "2.5.0-20250614-2282",\n  "buffer_seconds": 0.1,\n  "animation_start_ms": %s,\n  "audio_send_complete_ms": %s,\n  "animation_end_ms": %s,\n  "animation_start_frame": %s,\n  "animation_end_frame": %s,\n  "render_fps": %s,\n  "animation_samples": %s,\n  "audio_samples": %s,\n  "editor_exit": %s,\n  "log": "%s"\n}\n' \
  "$mode" \
  "$run_id" \
  "$wav" \
  "$animation_ms" \
  "$send_ms" \
  "$end_ms" \
  "$start_frame" \
  "$end_frame" \
  "$render_fps" \
  "$animation_samples" \
  "$audio_samples" \
  "$editor_exit" \
  "$log_file" \
  >"$json_file"

printf 'mode=%s run=%s animation_start_ms=%s audio_send_complete_ms=%s animation_end_ms=%s render_fps=%s log=%s json=%s\n' \
  "$mode" "$run_id" "$animation_ms" "$send_ms" "$end_ms" "$render_fps" "$log_file" "$json_file"
