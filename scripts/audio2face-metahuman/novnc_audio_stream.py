#!/usr/bin/env python3
"""Serve a project-local PulseAudio monitor as an on-demand MP3 stream."""

from __future__ import annotations

import argparse
import html
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def build_handler(ffmpeg: Path, source: str):
    class AudioHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                body = (
                    "<!doctype html><html lang=\"ko\"><head>"
                    "<meta charset=\"utf-8\"><meta name=\"viewport\" "
                    "content=\"width=device-width,initial-scale=1\">"
                    "<title>noVNC 원격 오디오</title></head>"
                    "<body style=\"font-family:sans-serif;background:#111;color:#eee;"
                    "padding:2rem\"><h1>noVNC 원격 오디오</h1>"
                    "<p>재생 버튼을 누르면 서버의 현재 오디오 출력을 듣습니다.</p>"
                    "<audio controls autoplay src=\"/audio.mp3\" "
                    "style=\"width:min(36rem,100%)\"></audio>"
                    f"<p style=\"color:#aaa\">Source: {html.escape(source)}</p>"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/health":
                body = b"ready\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path != "/audio.mp3":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            command = [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "warning",
                "-fflags",
                "nobuffer",
                "-f",
                "pulse",
                "-fragment_size",
                "2048",
                "-i",
                source,
                "-vn",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-flush_packets",
                "1",
                "-f",
                "mp3",
                "pipe:1",
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
            )
            try:
                assert process.stdout is not None
                while chunk := process.stdout.read(16 * 1024):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

        def log_message(self, format_string: str, *args: object) -> None:
            print(f"[{self.log_date_time_string()}] {format_string % args}", flush=True)

    return AudioHandler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()

    server = ThreadingHTTPServer(
        (args.bind, args.port), build_handler(args.ffmpeg, args.source)
    )
    print(
        f"Serving PulseAudio source {args.source} at http://{args.bind}:{args.port}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
