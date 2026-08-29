import importlib.util
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_head_motion.py"
MOTION_MODULE = ROOT / "a2f_motion.py"
SAMPLE_RATE = 48_000


def load_module(path, name):
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_synthetic_wav(path, duration_seconds):
    """Write deterministic speech-like bursts with leading/trailing silence."""
    sample_count = int(round(duration_seconds * SAMPLE_RATE))
    samples = []
    for index in range(sample_count):
        time_seconds = index / SAMPLE_RATE
        # The active interval leaves enough trailing silence to test settling.
        active = 0.25 <= time_seconds < max(0.30, duration_seconds - 0.55)
        if not active:
            samples.append(0)
            continue
        # A deterministic voiced carrier with a slow amplitude cadence.
        amplitude = 0.20 * (0.72 + 0.28 * math.sin(2.0 * math.pi * 0.65 * time_seconds))
        value = amplitude * math.sin(2.0 * math.pi * 180.0 * time_seconds)
        samples.append(max(-32768, min(32767, int(round(value * 32767.0)))))

    payload = b"".join(struct.pack("<h", value) for value in samples)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(payload)


class HeadMotionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep the RED signal attributable to the missing feature, rather than
        # turning a missing file into an import/setup error for every test.
        cls.module = load_module(MODULE, "a2f_head_motion")
        cls.motion_module = load_module(MOTION_MODULE, "a2f_motion_for_head_motion")

    def require_module(self):
        self.assertIsNotNone(
            self.module,
            "a2f_head_motion.py and its public contract are not implemented",
        )

    def enabled_config(self, **overrides):
        self.require_module()
        config = {
            "enabled": True,
            "profile": "subtle-conversational",
            "strength": 1.0,
            "pitch_limit_deg": 2.5,
            "yaw_limit_deg": 4.0,
            "roll_limit_deg": 1.5,
            "smoothing_seconds": 0.22,
            "silence_threshold_dbfs": -42.0,
        }
        config.update(overrides)
        return self.module.validate_head_motion_config(config)

    def get_frames(self, series):
        self.assertIsInstance(series, dict)
        frames = series.get("frames")
        self.assertIsInstance(frames, list)
        return frames

    def test_default_config_is_disabled_and_uses_no_head_motion_profile(self):
        self.require_module()
        config = self.module.resolve_head_motion_config()
        self.assertFalse(config["enabled"])
        self.assertEqual(config["profile"], "off")
        self.assertEqual(config["schema_version"], 1)

    def test_empty_optional_config_normalizes_to_the_backward_compatible_default(self):
        self.require_module()
        default = self.module.resolve_head_motion_config()
        self.assertEqual(self.module.validate_head_motion_config({}), default)

    def test_enabled_config_is_strictly_normalized(self):
        config = self.enabled_config(strength=1.25, yaw_limit_deg=3.5)
        self.assertTrue(config["enabled"])
        self.assertEqual(config["profile"], "subtle-conversational")
        self.assertEqual(config["strength"], 1.25)
        self.assertEqual(config["yaw_limit_deg"], 3.5)

    def test_unknown_profile_keys_and_nonfinite_values_are_rejected(self):
        self.require_module()
        invalid = [
            {"unknown": True},
            {"profile": "random-jitter"},
            {"enabled": True, "profile": "off"},
            {"enabled": "true"},
            {"strength": -0.01},
            {"strength": 1.50001},
            {"pitch_limit_deg": -0.01},
            {"pitch_limit_deg": 6.00001},
            {"yaw_limit_deg": -0.01},
            {"yaw_limit_deg": 8.00001},
            {"roll_limit_deg": -0.01},
            {"roll_limit_deg": 4.00001},
            {"smoothing_seconds": 0.079},
            {"smoothing_seconds": 0.801},
            {"silence_threshold_dbfs": -60.01},
            {"silence_threshold_dbfs": -24.99},
            {"strength": math.nan},
            {"strength": True},
            {"strength": "1.0"},
            {"pitch_limit_deg": math.inf},
            {"smoothing_seconds": -math.inf},
        ]
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(Exception):
                self.module.validate_head_motion_config(document)

    def test_generator_is_deterministic_and_artifact_bytes_are_identical(self):
        self.require_module()
        config = self.enabled_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "input.wav"
            write_synthetic_wav(audio, 1.75)
            first = self.module.generate_head_motion_series(audio, config, 30.0)
            second = self.module.generate_head_motion_series(audio, config, 30.0)

            first_bytes = json.dumps(
                first, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            second_bytes = json.dumps(
                second, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            self.assertEqual(first_bytes, second_bytes)

            first_dir = root / "artifacts-a"
            second_dir = root / "artifacts-b"
            self.module.write_head_motion_artifacts(first, first_dir)
            self.module.write_head_motion_artifacts(second, second_dir)
            for filename in (
                "head-motion.samples.json",
                "head-motion.applied.samples.json",
                "head-motion.samples.csv",
                "head-motion.metrics.json",
            ):
                self.assertEqual(
                    (first_dir / filename).read_bytes(),
                    (second_dir / filename).read_bytes(),
                    filename,
                )

    def test_frame_count_and_timebase_follow_duration_and_fps(self):
        self.require_module()
        config = self.enabled_config()
        cases = ((0.37, 24.0), (1.0, 30.0), (2.03, 60.0))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for duration, fps in cases:
                audio = root / ("input-%s.wav" % str(fps).replace(".", "_"))
                write_synthetic_wav(audio, duration)
                series = self.module.generate_head_motion_series(audio, config, fps)
                frames = self.get_frames(series)
                expected_count = math.ceil(duration * fps)
                self.assertEqual(len(frames), expected_count)
                self.assertEqual(series["frame_count"], expected_count)
                self.assertEqual(series["fps"], fps)
                for index, frame in enumerate(frames):
                    self.assertEqual(frame["frame_index"], index)
                    self.assertTrue(
                        math.isclose(
                            frame["time_seconds"], index / fps, rel_tol=0.0, abs_tol=1e-12
                        )
                    )
                self.assertEqual(
                    [frame["time_seconds"] for frame in frames],
                    sorted(frame["time_seconds"] for frame in frames),
                )

    def test_axis_values_are_finite_and_within_configured_anatomical_limits(self):
        self.require_module()
        config = self.enabled_config(
            pitch_limit_deg=1.5, yaw_limit_deg=3.0, roll_limit_deg=0.75
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "input.wav"
            write_synthetic_wav(audio, 2.0)
            series = self.module.generate_head_motion_series(audio, config, 60.0)
        frames = self.get_frames(series)
        for frame in frames:
            for axis, limit in (
                ("pitch_deg", config["pitch_limit_deg"]),
                ("yaw_deg", config["yaw_limit_deg"]),
                ("roll_deg", config["roll_limit_deg"]),
            ):
                self.assertTrue(math.isfinite(frame[axis]))
                self.assertLessEqual(abs(frame[axis]), limit + 1e-9)

    def test_smoothing_limits_frame_velocity_and_second_difference(self):
        self.require_module()
        config = self.enabled_config()
        fps = 60.0
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "input.wav"
            write_synthetic_wav(audio, 2.0)
            frames = self.get_frames(
                self.module.generate_head_motion_series(audio, config, fps)
            )

        dt = 1.0 / fps
        for axis, limit in (
            ("pitch_deg", config["pitch_limit_deg"]),
            ("yaw_deg", config["yaw_limit_deg"]),
            ("roll_deg", config["roll_limit_deg"]),
        ):
            values = [frame[axis] for frame in frames]
            velocities = [
                (right - left) / dt for left, right in zip(values, values[1:])
            ]
            jerks = [
                (right - 2.0 * middle + left) / (dt * dt)
                for left, middle, right in zip(values, values[1:], values[2:])
            ]
            # These are deliberately conservative limits tied to the public
            # smoothing control, not implementation-specific coefficients.
            self.assertLessEqual(
                max(map(abs, velocities), default=0.0),
                3.0 * limit / config["smoothing_seconds"] + 1e-6,
            )
            self.assertLessEqual(
                max(map(abs, jerks), default=0.0),
                24.0 * limit / (config["smoothing_seconds"] ** 2) + 1e-4,
            )

    def test_silence_attenuates_motion_and_final_frames_settle_neutral(self):
        self.require_module()
        config = self.enabled_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "input.wav"
            write_synthetic_wav(audio, 2.0)
            frames = self.get_frames(
                self.module.generate_head_motion_series(audio, config, 30.0)
            )

        active = [frame for frame in frames if frame["activity"] > 0.2]
        quiet_tail = frames[-max(3, len(frames) // 8) :]
        self.assertTrue(active, "synthetic voiced interval must produce activity")
        active_peak = max(
            max(abs(frame[axis]) for frame in active)
            for axis in ("pitch_deg", "yaw_deg", "roll_deg")
        )
        tail_mean = sum(
            max(abs(frame[axis]) for axis in ("pitch_deg", "yaw_deg", "roll_deg"))
            for frame in quiet_tail
        ) / len(quiet_tail)
        self.assertGreater(active_peak, 0.0)
        self.assertLess(tail_mean, max(0.05, active_peak * 0.25))
        self.assertLessEqual(
            max(
                max(abs(frame[axis]) for axis in ("pitch_deg", "yaw_deg", "roll_deg"))
                for frame in quiet_tail[-2:]
            ),
            0.25,
        )

    def test_zero_strength_is_a_deterministic_neutral_profile(self):
        self.require_module()
        config = self.enabled_config(strength=0.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "input.wav"
            write_synthetic_wav(audio, 1.25)
            frames = self.get_frames(
                self.module.generate_head_motion_series(audio, config, 24.0)
            )
        for frame in frames:
            self.assertEqual(frame["pitch_deg"], 0.0)
            self.assertEqual(frame["yaw_deg"], 0.0)
            self.assertEqual(frame["roll_deg"], 0.0)

    def test_motion_config_keeps_head_motion_optional_and_normalized(self):
        self.assertIsNotNone(self.motion_module, "a2f_motion.py must remain importable")
        default = self.motion_module.resolve_motion_config()
        self.assertIn("head_motion", default)
        self.assertFalse(default["head_motion"]["enabled"])

        result = self.motion_module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "baseline",
                "head_motion": {
                    "enabled": True,
                    "profile": "subtle-conversational",
                    "strength": 1.0,
                },
            },
            audio_duration=1.0,
        )
        self.assertTrue(result["head_motion"]["enabled"])
        self.assertEqual(result["head_motion"]["profile"], "subtle-conversational")

    def test_checked_in_head_motion_preset_uses_strict_final_render_lineage(self):
        preset = json.loads(
            (ROOT / "configs/motion-head-subtle-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(preset["curve_application"], "final_render")

    def test_render_lag_compensation_preserves_active_clock_and_settles_tail(self):
        self.require_module()
        frames = [
            {
                "frame_index": index,
                "time_seconds": index / 30.0,
                "activity": 1.0,
                "audio_dbfs": -18.0,
                "pitch_deg": float(index),
                "yaw_deg": float(index * 2),
                "roll_deg": float(-index),
            }
            for index in range(20)
        ]
        result = self.module.compensate_frames_for_video_advance(frames, 3)
        applied = result["frames"]
        self.assertEqual(result["video_advance_frames"], 3)
        self.assertEqual(len(applied), len(frames))
        self.assertEqual(applied[3]["yaw_deg"], frames[0]["yaw_deg"])
        self.assertEqual(applied[12]["yaw_deg"], frames[9]["yaw_deg"])
        self.assertEqual(applied[-1]["yaw_deg"], 0.0)
        self.assertEqual(applied[-1]["pitch_deg"], 0.0)
        self.assertEqual(applied[-1]["roll_deg"], 0.0)
        # After the measured +3-frame video advance, active output frame 9
        # reads raw frame 12 and therefore the authoritative source frame 9.
        self.assertEqual(applied[12]["source_frame_index"], 9)

    def test_render_lag_compensation_rejects_unsafe_or_impossible_offsets(self):
        self.require_module()
        frames = [
            {
                "frame_index": index,
                "time_seconds": index / 30.0,
                "activity": 0.0,
                "audio_dbfs": -120.0,
                "pitch_deg": 0.0,
                "yaw_deg": 0.0,
                "roll_deg": 0.0,
            }
            for index in range(10)
        ]
        for lag in (-1, 5, 10, True, 1.5):
            with self.subTest(lag=lag), self.assertRaises(Exception):
                self.module.compensate_frames_for_video_advance(frames, lag)


if __name__ == "__main__":
    unittest.main()
