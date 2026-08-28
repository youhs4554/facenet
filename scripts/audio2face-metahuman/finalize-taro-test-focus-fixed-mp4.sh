#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ffmpeg="$repo_root/.tools/ffmpeg/bin/ffmpeg"
ffprobe="$repo_root/.tools/ffmpeg/bin/ffprobe"
output_dir="$repo_root/.tools/audio2face3d/final-taro-test-mrq-focus-fixed"
wav="${1:-/home/aim/Downloads/test.wav}"
video_only="$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_video-only.mp4"
final="$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.mp4"

if [[ ! -x "$ffmpeg" || ! -x "$ffprobe" || ! -f "$wav" ]]; then
  echo "ERROR: project-local FFmpeg/FFprobe or test WAV is missing." >&2
  exit 1
fi

if [[ $(find "$output_dir" -maxdepth 1 -name 'Taro_A2F_test_focus_fixed.*.png' | wc -l) -ne 109 ]]; then
  echo "ERROR: expected 109 focus-corrected MRQ PNG frames." >&2
  exit 1
fi

"$ffmpeg" -hide_banner -y -loglevel warning \
  -framerate 30 -start_number 0 \
  -i "$output_dir/Taro_A2F_test_focus_fixed.%04d.png" \
  -frames:v 109 -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -movflags +faststart "$video_only"

"$ffmpeg" -hide_banner -y -loglevel warning \
  -i "$video_only" -i "$wav" \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k \
  -movflags +faststart "$final"

"$ffprobe" -v error \
  -show_entries format=filename,start_time,duration,size,bit_rate \
  -show_entries stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,sample_rate,channels,channel_layout,start_time,duration,nb_frames,bit_rate \
  -of json "$final" \
  | tee "$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.ffprobe.json"

"$ffmpeg" -v error -i "$final" -map 0:v:0 -map 0:a:0 -f null -
"$ffmpeg" -hide_banner -nostats -i "$final" -map 0:a:0 \
  -af volumedetect -f null - 2>&1 \
  | grep -E 'mean_volume|max_volume|Duration:' \
  | tee "$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.volume.txt"
"$ffmpeg" -hide_banner -nostats -i "$final" -map 0:a:0 \
  -af astats=metadata=1:reset=0 -f null - 2>&1 \
  | grep -E 'RMS level dB|Peak level dB|Number of samples' \
  | tee "$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.astats.txt"
sha256sum "$final" \
  | tee "$output_dir/Taro_Audio2Face_test_FOCUS_FIXED_FINAL.sha256"

echo "Focus-corrected final MP4: $final"
