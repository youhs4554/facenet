#!/usr/bin/env python3

import argparse
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gst, Gtk


DEFAULT_VIDEO = Path(
    "/home/aim/workspace/hosang/repo/facenet/.tools/audio2face3d/"
    "final-taro-test-mrq-focus-fixed/"
    "Taro_Audio2Face_test_FOCUS_FIXED_FINAL.mp4"
)


class DemoPlayer(Gtk.Window):
    def __init__(self, video_path: Path):
        super().__init__(title="Taro Audio2Face — Focus Fixed Demo")
        self.set_default_size(1280, 780)
        self.connect("destroy", self._on_destroy)

        self.pipeline = Gst.ElementFactory.make("playbin", "player")
        self.video_sink = Gst.ElementFactory.make("gtksink", "video")
        if self.pipeline is None or self.video_sink is None:
            raise RuntimeError("GStreamer playbin or gtksink is unavailable")

        self.pipeline.set_property("uri", Gst.filename_to_uri(str(video_path)))
        self.pipeline.set_property("video-sink", self.video_sink)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(root)

        video_frame = Gtk.AspectFrame(
            xalign=0.5,
            yalign=0.5,
            ratio=16 / 9,
            obey_child=False,
        )
        video_frame.set_shadow_type(Gtk.ShadowType.NONE)
        video_frame.add(self.video_sink.get_property("widget"))
        root.pack_start(video_frame, True, True, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_border_width(10)
        root.pack_start(controls, False, False, 0)

        self.play_button = Gtk.Button(label="Pause")
        self.play_button.connect("clicked", self._toggle_playback)
        controls.pack_start(self.play_button, False, False, 0)

        restart_button = Gtk.Button(label="Restart")
        restart_button.connect("clicked", self._restart)
        controls.pack_start(restart_button, False, False, 0)

        self.loop_button = Gtk.CheckButton(label="Loop")
        self.loop_button.set_active(True)
        controls.pack_start(self.loop_button, False, False, 0)

        self.status = Gtk.Label(
            label=f"{video_path.name} · 1920×1080 · H.264/AAC · focus 96.4 cm"
        )
        self.status.set_xalign(0.0)
        controls.pack_start(self.status, True, True, 8)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        self.playing = True
        self.show_all()
        self.pipeline.set_state(Gst.State.PLAYING)

    def _toggle_playback(self, _button):
        self.playing = not self.playing
        state = Gst.State.PLAYING if self.playing else Gst.State.PAUSED
        self.pipeline.set_state(state)
        self.play_button.set_label("Pause" if self.playing else "Play")

    def _restart(self, _button):
        self.pipeline.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            0,
        )
        if not self.playing:
            self.playing = True
            self.play_button.set_label("Pause")
            self.pipeline.set_state(Gst.State.PLAYING)

    def _on_bus_message(self, _bus, message):
        if message.type == Gst.MessageType.EOS:
            if self.loop_button.get_active():
                self._restart(None)
            else:
                self.pipeline.set_state(Gst.State.PAUSED)
                self.playing = False
                self.play_button.set_label("Play")
        elif message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.status.set_text(f"Playback error: {error.message}")
            GLib.printerr(f"GStreamer error: {error}; {debug}")

    def _on_destroy(self, _window):
        self.pipeline.set_state(Gst.State.NULL)
        Gtk.main_quit()


def main():
    parser = argparse.ArgumentParser(
        description="Keep the focus-corrected Taro A2F demo visible on VNC."
    )
    parser.add_argument("video", nargs="?", type=Path, default=DEFAULT_VIDEO)
    args = parser.parse_args()
    video_path = args.video.expanduser().resolve()
    if not video_path.is_file():
        raise SystemExit(f"Video does not exist: {video_path}")

    Gst.init(None)
    DemoPlayer(video_path)
    Gtk.main()


if __name__ == "__main__":
    main()
