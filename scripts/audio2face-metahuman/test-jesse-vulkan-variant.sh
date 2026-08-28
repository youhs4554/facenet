#!/usr/bin/env bash

set -u

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <variant> [run-tag]" >&2
  exit 2
fi

variant="$1"
run_tag="${2:-580-open}"
graphics_adapter="${A2F_UE_GRAPHICS_ADAPTER:-0}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
install_root="$repo_root/.tools/audio2face-metahuman"
editor="$install_root/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
project="$install_root/KairosSample/KairosSample.uproject"
map_file="$install_root/KairosSample/Content/Maps/JesseAB/$variant.umap"
log_dir="$install_root/KairosSample/Saved/Logs/JesseAB"
log_file="$log_dir/vulkan-$variant-$run_tag.log"

if [[ ! -f "$map_file" ]]; then
  echo "ERROR: A/B map does not exist: $map_file" >&2
  exit 2
fi

xfce_pid="$(pgrep -n xfce4-session || true)"
if [[ -z "$xfce_pid" ]]; then
  echo "ERROR: VNC XFCE session not found" >&2
  exit 2
fi

vnc_dbus="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -n 1)"
vnc_runtime="$(tr '\0' '\n' < "/proc/$xfce_pid/environ" | sed -n 's/^XDG_RUNTIME_DIR=//p' | head -n 1)"

mkdir -p "$log_dir"
export DISPLAY=:1
export XAUTHORITY=/home/aim/.Xauthority
export DBUS_SESSION_BUS_ADDRESS="$vnc_dbus"
export XDG_RUNTIME_DIR="$vnc_runtime"
export SDL_AUDIODRIVER=pulseaudio

set +e
"$editor" \
  "$project" \
  "/Game/Maps/JesseAB/$variant" \
  -game \
  -vulkan \
  -graphicsadapter="$graphics_adapter" \
  -RenderOffscreen \
  -unattended \
  -nop4 \
  -nosplash \
  -nosound \
  -benchmark \
  -fps=30 \
  -seconds=10 \
  -ResX=640 \
  -ResY=360 \
  '-ExecCmds=r.CEFGPUAcceleration 0' \
  -abslog="$log_file" \
  >/dev/null 2>&1
editor_exit=$?
set -e

if rg -q 'VkResult=-13|Fatal error' "$log_file"; then
  signature="VK_FAIL"
else
  signature="NO_VK_FAIL"
fi

printf 'variant=%s run_tag=%s adapter=%s exit=%s signature=%s log=%s\n' \
  "$variant" "$run_tag" "$graphics_adapter" "$editor_exit" "$signature" "$log_file"
