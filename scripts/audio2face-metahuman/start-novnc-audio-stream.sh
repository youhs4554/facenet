#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
ffmpeg="$repo_root/.tools/ffmpeg/bin/ffmpeg"

if [[ ! -x "$ffmpeg" ]]; then
  echo "ERROR: project-local ffmpeg is missing: $ffmpeg" >&2
  exit 1
fi

runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_RUNTIME_DIR="$runtime_dir"
export PULSE_SERVER="${PULSE_SERVER:-unix:$runtime_dir/pulse/native}"

bind_ip="${NOVNC_AUDIO_BIND_IP:-}"
if [[ -z "$bind_ip" ]]; then
  bind_ip="$(ip -4 -brief address show tailscale0 2>/dev/null | awk '{split($3, address, "/"); print address[1]; exit}')"
fi
if [[ -z "$bind_ip" ]]; then
  echo "ERROR: NOVNC_AUDIO_BIND_IP is unset and tailscale0 has no IPv4 address." >&2
  exit 1
fi

port="${NOVNC_AUDIO_PORT:-8001}"
source_name="${NOVNC_AUDIO_SOURCE:-$(pactl get-default-source)}"

exec python3 "$script_dir/novnc_audio_stream.py" \
  --bind "$bind_ip" \
  --port "$port" \
  --source "$source_name" \
  --ffmpeg "$ffmpeg"
