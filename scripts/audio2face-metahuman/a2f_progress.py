#!/usr/bin/env python3
"""Dependency-free terminal progress and JSONL events for the A2F CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO


STAGE_COUNT = 11
SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class ProgressReporter:
    def __init__(
        self,
        *,
        mode: str = "auto",
        stream: TextIO = sys.stderr,
        clock: Callable[[], float] = time.monotonic,
        is_tty: bool | None = None,
        width: int | None = None,
        event_path: Path | None = None,
        stage_count: int = STAGE_COUNT,
    ) -> None:
        if mode not in {"auto", "always", "never"}:
            raise ValueError("progress mode must be auto, always, or never")
        self.mode = mode
        self.stream = stream
        self.clock = clock
        self.is_tty = bool(stream.isatty()) if is_tty is None else is_tty
        terminal_width = shutil.get_terminal_size((100, 24)).columns
        self.width = max(40, min(120, width or terminal_width))
        self.event_path = Path(event_path) if event_path is not None else None
        self.stage_count = stage_count
        self.run_started = clock()
        self.stage_started = self.run_started
        self.active_stage = ""
        self.active_label = ""
        self.completed_steps = 0
        self.sequence = 0
        self.spinner_index = 0
        self.current: int | None = None
        self.total: int | None = None
        self.detail = ""
        self._last_non_tty_bucket: int | None = None
        self._tty_line_open = False
        if self.event_path is not None:
            self.event_path.parent.mkdir(parents=True, exist_ok=True)
            self.event_path.touch(exist_ok=True)

    @property
    def visible(self) -> bool:
        return self.mode != "never"

    def set_event_path(self, path: Path) -> None:
        self.event_path = Path(path)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_path.touch(exist_ok=True)

    def _record(self, state: str, **extra: Any) -> None:
        self.sequence += 1
        event = {
            "schema_version": 1,
            "sequence": self.sequence,
            "state": state,
            "stage": self.active_stage,
            "label": self.active_label,
            "elapsed_seconds": round(self.clock() - self.run_started, 6),
            "stage_elapsed_seconds": round(self.clock() - self.stage_started, 6),
            "overall_completed": self.completed_steps,
            "overall_total": self.stage_count,
        }
        event.update(extra)
        if self.event_path is not None:
            with self.event_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    def _write_line(self, text: str) -> None:
        if self.visible:
            self.stream.write(text + "\n")
            self.stream.flush()

    def _bounded(self, text: str) -> str:
        if len(text) <= self.width:
            return text
        return text[: max(1, self.width - 1)] + "…"

    def _tty_render(self, state: str) -> None:
        if not self.visible:
            return
        elapsed = self.clock() - self.stage_started
        prefix = f"[{self.completed_steps:02d}/{self.stage_count:02d}]"
        if self.current is not None and self.total:
            fraction = min(1.0, max(0.0, self.current / self.total))
            percent = int(fraction * 100)
            bar_width = 12
            filled = round(fraction * bar_width)
            indicator = f"[{'#' * filled}{'-' * (bar_width - filled)}] {percent:3d}%"
        else:
            indicator = SPINNER[self.spinner_index % len(SPINNER)]
            self.spinner_index += 1
        subject = self.detail or self.active_label
        line = self._bounded(
            f"{prefix} {indicator} {state} {self.active_stage}: {subject} {elapsed:0.1f}s"
        )
        self.stream.write("\r" + line + "\x1b[K")
        self.stream.flush()
        self._tty_line_open = True

    def _close_tty_line(self) -> None:
        if self.visible and self.is_tty and self._tty_line_open:
            self.stream.write("\n")
            self.stream.flush()
            self._tty_line_open = False

    def begin_run(
        self,
        *,
        run_id: str,
        model: str,
        endpoint: str,
        avatar: str,
        shots: list[str],
        output_dir: Path,
    ) -> None:
        summary = (
            f"[A2F] run={run_id} model={model} endpoint={endpoint} "
            f"avatar={avatar} shots={','.join(shots)} output={output_dir}"
        )
        self._write_line(summary)
        self._record(
            "run_started",
            run_id=run_id,
            model=model,
            endpoint=endpoint,
            avatar=avatar,
            shots=shots,
            output_dir=str(output_dir),
        )

    def start(
        self,
        stage: str,
        label: str,
        *,
        current: int | None = None,
        total: int | None = None,
        detail: str = "",
    ) -> None:
        self._close_tty_line()
        self.active_stage = stage
        self.active_label = label
        self.stage_started = self.clock()
        self.current = current
        self.total = total
        self.detail = detail
        self._last_non_tty_bucket = None
        self._record("started", current=current, total=total, detail=detail)
        if not self.visible:
            return
        if self.is_tty:
            self._tty_render("RUN")
        else:
            self._write_line(
                f"[A2F][{self.completed_steps + 1:02d}/{self.stage_count:02d}]"
                f"[{stage}] START {label}"
            )

    def update(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        detail: str | None = None,
    ) -> None:
        changed = False
        if current is not None and current != self.current:
            self.current = current
            changed = True
        if total is not None and total != self.total:
            self.total = total
            changed = True
        detail_changed = detail is not None and detail != self.detail
        if detail is not None:
            self.detail = detail
        if changed or detail_changed:
            self._record(
                "progress", current=self.current, total=self.total, detail=self.detail
            )
        if self.visible and self.is_tty:
            self._tty_render("RUN")
        elif self.visible and not self.is_tty:
            should_print = False
            if self.current is not None and self.total:
                bucket = min(4, int(4 * self.current / self.total))
                if bucket != self._last_non_tty_bucket:
                    self._last_non_tty_bucket = bucket
                    should_print = True
            elif detail_changed:
                should_print = True
            if should_print:
                measured = (
                    f" {self.current}/{self.total}"
                    if self.current is not None and self.total
                    else ""
                )
                self._write_line(
                    f"[A2F][{self.completed_steps + 1:02d}/{self.stage_count:02d}]"
                    f"[{self.active_stage}] RUN{measured} {self.detail}".rstrip()
                )

    def complete(self, detail: str = "") -> None:
        if detail:
            self.detail = detail
        self.completed_steps = min(self.stage_count, self.completed_steps + 1)
        self._record(
            "completed", current=self.current, total=self.total, detail=self.detail
        )
        elapsed = self.clock() - self.stage_started
        if not self.visible:
            return
        if self.is_tty:
            if self.total:
                self.current = self.total
            self._tty_render("PASS")
            self._close_tty_line()
        else:
            suffix = f" {self.detail}" if self.detail else ""
            self._write_line(
                f"[A2F][{self.completed_steps:02d}/{self.stage_count:02d}]"
                f"[{self.active_stage}] PASS{suffix} elapsed={elapsed:0.1f}s"
            )

    def fail(
        self,
        reason: str,
        *,
        manifest: Path | None = None,
        log: Path | None = None,
    ) -> None:
        self._record(
            "failed",
            reason=reason,
            manifest=str(manifest) if manifest else None,
            log=str(log) if log else None,
        )
        self._close_tty_line()
        fields = [f"[A2F] FAILED stage={self.active_stage}", f"reason={reason}"]
        if manifest is not None:
            fields.append(f"manifest={manifest}")
        if log is not None:
            fields.append(f"log={log}")
        self._write_line(" ".join(fields))

    def manual(
        self,
        reason: str,
        *,
        manifest: Path | None = None,
        resume: str | None = None,
    ) -> None:
        self._record(
            "manual_action_required",
            reason=reason,
            manifest=str(manifest) if manifest else None,
            resume=resume,
        )
        self._close_tty_line()
        fields = [f"[A2F] MANUAL stage={self.active_stage}", f"reason={reason}"]
        if manifest is not None:
            fields.append(f"manifest={manifest}")
        if resume:
            fields.append(f"resume={resume}")
        self._write_line(" ".join(fields))

    def finish(self, *, outputs: list[Path], manifest: Path) -> None:
        self.completed_steps = self.stage_count
        self.active_stage = "complete"
        self.active_label = "Pipeline complete"
        elapsed = self.clock() - self.run_started
        self._record(
            "run_completed",
            percent=100,
            outputs=[str(path) for path in outputs],
            manifest=str(manifest),
        )
        self._close_tty_line()
        self._write_line(
            f"[A2F][{self.stage_count:02d}/{self.stage_count:02d}]"
            f"[complete] 100% elapsed={elapsed:0.1f}s manifest={manifest}"
        )
        for path in outputs:
            self._write_line(f"[A2F] output={path}")


def _demo() -> int:
    reporter = ProgressReporter(mode="always")
    reporter.start("mrq", "MRQ demo", current=0, total=4)
    for index in range(1, 5):
        reporter.update(current=index, total=4, detail=f"frame {index}/4")
    reporter.complete("4/4 frames")
    reporter.finish(outputs=[Path("/tmp/demo.mp4")], manifest=Path("/tmp/manifest.json"))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    raise SystemExit(_demo() if args.demo else 0)
