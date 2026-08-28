#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
install_root="$repo_root/.tools/audio2face-metahuman"
editor="$install_root/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
project="$install_root/KairosSample/KairosSample.uproject"
demo_map="${A2F_DEMO_MAP:-/Game/Maps/TaroA2F/TaroFaceBodyDemo}"
project_log="$install_root/KairosSample/Saved/Logs/TaroA2F/TaroA2FVNC.log"
console_log="$install_root/KairosSample/Saved/Logs/TaroA2F/TaroA2FVNC-console.log"
vnc_display="${DISPLAY:-:1}"
vnc_xauthority="${XAUTHORITY:-/home/aim/.Xauthority}"
ue_graphics_adapter="${A2F_UE_GRAPHICS_ADAPTER:-0}"
a2f_demo_mode="${A2F_DEMO_MODE:-low-latency}"

if [[ "$a2f_demo_mode" != "low-latency" && "$a2f_demo_mode" != "realtime" ]]; then
  echo "ERROR: A2F_DEMO_MODE must be 'low-latency' or 'realtime'." >&2
  exit 1
fi

if [[ ! -x "$editor" ]]; then
  echo "ERROR: Unreal Editor executable not found: $editor" >&2
  exit 1
fi

if [[ ! -f "$project" ]]; then
  echo "ERROR: Kairos project not found: $project" >&2
  exit 1
fi

existing_pid="$(pgrep -f "$editor $project" | head -n 1 || true)"
if [[ -n "$existing_pid" ]]; then
  echo "KairosSample Unreal Editor is already running (PID $existing_pid, DISPLAY $vnc_display)."
  exit 0
fi

if ! curl -fsS http://127.0.0.1:8000/v1/health/ready >/dev/null; then
  echo "Starting the pretrained Audio2Face-3D NIM container..."
  docker start audio2face-3d-pretrained >/dev/null

  for _ in {1..60}; do
    if curl -fsS http://127.0.0.1:8000/v1/health/ready >/dev/null; then
      break
    fi
    sleep 2
  done
fi

if ! curl -fsS http://127.0.0.1:8000/v1/health/ready >/dev/null; then
  echo "ERROR: Audio2Face-3D NIM is not ready on http://127.0.0.1:8000." >&2
  exit 1
fi

xfce_pid="$(pgrep -n xfce4-session || pgrep -n xfce4-panel || true)"
if [[ -z "$xfce_pid" ]]; then
  echo "ERROR: The VNC XFCE session was not found." >&2
  exit 1
fi

vnc_dbus="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -n 1)"
vnc_runtime="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^XDG_RUNTIME_DIR=//p' | head -n 1)"

if [[ -z "$vnc_dbus" || -z "$vnc_runtime" ]]; then
  echo "ERROR: Could not resolve DBus/XDG environment from the VNC session." >&2
  exit 1
fi

mkdir -p "$(dirname "$project_log")"

nohup env \
  DISPLAY="$vnc_display" \
  XAUTHORITY="$vnc_xauthority" \
  XDG_RUNTIME_DIR="$vnc_runtime" \
  DBUS_SESSION_BUS_ADDRESS="$vnc_dbus" \
  SDL_VIDEODRIVER=x11 \
  SDL_AUDIODRIVER=pulseaudio \
  "$editor" \
  "$project" \
  "$demo_map" \
  -vulkan \
  -graphicsadapter="$ue_graphics_adapter" \
  -NoSplash \
  -log \
  "-A2FDemoMode=$a2f_demo_mode" \
  '-ExecCmds=r.CEFGPUAcceleration 0' \
  -abslog="$project_log" \
  >"$console_log" 2>&1 </dev/null &

editor_pid=$!
echo "Started KairosSample Unreal Editor (PID $editor_pid, DISPLAY $vnc_display)."
echo "Map: $demo_map (official BP_Taro face, all original grooms, Body, and clothed torso)"
echo "NIM: http://127.0.0.1:8000 (health), 127.0.0.1:52000 (gRPC)"
echo "GPU split: NIM container on RTX A4500; UE Vulkan adapter $ue_graphics_adapter on the VNC-presenting Quadro RTX 5000."
echo "Inference mode: $a2f_demo_mode (use A2F_DEMO_MODE=realtime for clips longer than 10 seconds)."
echo "Editor log: $project_log"
echo "Console log: $console_log"
