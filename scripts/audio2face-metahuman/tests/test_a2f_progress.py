import importlib.util
import io
import json
import os
import pty
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_progress.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_progress", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MutableClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class ProgressReporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_non_tty_is_line_oriented_and_does_not_emit_heartbeat_spam(self):
        stream = io.StringIO()
        clock = MutableClock()
        reporter = self.module.ProgressReporter(
            mode="auto", stream=stream, clock=clock, is_tty=False, width=80
        )
        reporter.begin_run(
            run_id="run-1",
            model="v3.0-diffusion",
            endpoint="127.0.0.1:52100",
            avatar="Ada",
            shots=["close-up-front"],
            output_dir=Path("/runs/run-1"),
        )
        reporter.start("nim_health", "NIM health")
        for _ in range(10):
            reporter.update(detail="waiting")
        clock.value += 2.5
        reporter.complete("ONLINE")
        output = stream.getvalue()
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\r", output)
        self.assertEqual(output.count("nim_health"), 3)
        self.assertEqual(output.count("waiting"), 1)
        self.assertIn("run=run-1", output)
        self.assertIn("avatar=Ada", output)

    def test_tty_uses_bounded_single_line_spinner_and_measured_bar(self):
        stream = io.StringIO()
        clock = MutableClock()
        reporter = self.module.ProgressReporter(
            mode="always", stream=stream, clock=clock, is_tty=True, width=64
        )
        reporter.start("mrq", "MRQ close-up-front", current=0, total=109)
        clock.value += 1.0
        reporter.update(current=54, total=109, detail="frame 54/109")
        clock.value += 1.0
        reporter.complete("109/109 frames")
        output = stream.getvalue()
        self.assertIn("\r", output)
        self.assertIn("49%", output)
        self.assertIn("109/109", output)
        self.assertTrue(output.endswith("\n"))
        self.assertTrue(all(len(line) <= 72 for line in output.replace("\r", "\n").splitlines()))

    def test_never_suppresses_ui_but_jsonl_events_remain_auditable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "progress.jsonl"
            stream = io.StringIO()
            reporter = self.module.ProgressReporter(
                mode="never",
                stream=stream,
                clock=MutableClock(),
                is_tty=False,
                width=80,
                event_path=path,
            )
            reporter.start("preflight", "Preflight")
            reporter.complete("PASS")
            self.assertEqual(stream.getvalue(), "")
            events = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([event["state"] for event in events], ["started", "completed"])
        self.assertEqual([event["sequence"] for event in events], [1, 2])

    def test_failure_closes_tty_line_and_reports_manifest_and_log(self):
        stream = io.StringIO()
        reporter = self.module.ProgressReporter(
            mode="always", stream=stream, clock=MutableClock(), is_tty=True, width=100
        )
        reporter.start("capture", "ACE capture")
        reporter.fail(
            "Unreal exited",
            manifest=Path("/runs/x/manifest.json"),
            log=Path("/runs/x/capture.log"),
        )
        output = stream.getvalue()
        self.assertTrue(output.endswith("\n"))
        self.assertIn("FAILED", output)
        self.assertIn("manifest=/runs/x/manifest.json", output)
        self.assertIn("log=/runs/x/capture.log", output)

    def test_pseudo_tty_demo_leaves_a_complete_final_line(self):
        master_fd, slave_fd = pty.openpty()
        try:
            completed = subprocess.run(
                [sys.executable, str(MODULE), "--demo"],
                stdout=subprocess.DEVNULL,
                stderr=slave_fd,
                check=False,
                timeout=10,
            )
            os.close(slave_fd)
            slave_fd = -1
            chunks = []
            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(master_fd)
            if slave_fd >= 0:
                os.close(slave_fd)
        output = b"".join(chunks).decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("100%", output)
        self.assertTrue(output.endswith("\r\n") or output.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
