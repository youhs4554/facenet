#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib>=3.10",
#     "numpy>=2.0",
# ]
# ///

"""Validate benchmark outputs and generate paper tables and vector figures."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT: Final = Path(__file__).resolve().parent
RESULTS: Final = ROOT / "results"
GENERATED: Final = ROOT / "generated"
FIGURES: Final = ROOT / "figures"

MOVEMENTS: Final = (
    ("brow raise", "BR", 11.5),
    ("close smile", "CS", 11.1),
    ("frown", "FR", 11.1),
    ("funny", "FN", 12.6),
    ("gentle eyes closure", "GEC", 11.4),
    ("left eyebrow", "LE", 10.8),
    ("left smile", "LSM", 11.9),
    ("left snarl", "LSN", 11.5),
    ("left wink", "LW", 11.4),
    ("open smile", "OS", 12.0),
    ("right eyebrow", "RE", 11.2),
    ("right smile", "RSM", 12.4),
    ("right snarl", "RSN", 11.6),
    ("right wink", "RW", 11.5),
    ("snarl", "SN", 12.0),
    ("tight eyes closure", "TEC", 11.9),
)
AUS: Final = (
    "AU01",
    "AU02",
    "AU04",
    "AU05",
    "AU06",
    "AU09",
    "AU12",
    "AU15",
    "AU17",
    "AU20",
    "AU25",
    "AU26",
)
BLUE: Final = "#2563EB"
ORANGE: Final = "#F59E0B"
TEAL: Final = "#0F766E"
RED: Final = "#DC2626"
GRAY: Final = "#64748B"


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    aflfp_report = _load_json(RESULTS / "aflfp-test.json")
    disfa_report = _load_json(RESULTS / "disfa-test.json")
    aflfp_rows = _load_csv(RESULTS / "aflfp-samples.csv")
    disfa_rows = _load_csv(RESULTS / "disfa-samples.csv")

    movement_stats = _validate_aflfp(aflfp_report, aflfp_rows)
    au_stats = _validate_disfa(disfa_report, disfa_rows)
    _write_macros(aflfp_report, disfa_report, movement_stats, au_stats)
    _write_headline_table(aflfp_report, disfa_report)
    _write_movement_table(movement_stats)
    _write_au_table(au_stats)
    _plot_aflfp(movement_stats)
    _plot_disfa_metrics(au_stats)
    _plot_disfa_prevalence(au_stats)
    _write_derived_summary(movement_stats, au_stats)
    return 0


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_aflfp(
    report: dict[str, object], rows: list[dict[str, str]]
) -> dict[str, dict[str, object]]:
    expected = int(report["processed_samples"])
    if len(rows) != expected:
        raise ValueError(f"AFLFP CSV has {len(rows)} rows; expected {expected}")
    subject_counts = Counter(row["subject"] for row in rows)
    movement_counts = Counter(row["movement"] for row in rows)
    if set(subject_counts.values()) != {12, 13}:
        raise ValueError(f"unexpected AFLFP subject balance: {subject_counts}")
    if set(movement_counts.values()) != {71}:
        raise ValueError(f"unexpected AFLFP movement balance: {movement_counts}")

    stats: dict[str, dict[str, object]] = {}
    all_scores: list[float] = []
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["detected"] != "True" or not row["nme"]:
            continue
        score = float(row["nme"])
        grouped[row["movement"]].append(score)
        all_scores.append(score)
    _assert_close("AFLFP mean NME", np.mean(all_scores), report["nme_mean"])
    _assert_close("AFLFP std NME", np.std(all_scores), report["nme_std"])
    _assert_close("AFLFP median NME", np.median(all_scores), report["nme_median"])
    _assert_close(
        "AFLFP P90 NME", np.quantile(all_scores, 0.9), report["nme_p90"]
    )
    for movement, abbreviation, baseline in MOVEMENTS:
        values = np.asarray(grouped[movement], dtype=float)
        stats[movement] = {
            "abbreviation": abbreviation,
            "baseline_mean_percent": baseline,
            "values": values,
            "count": int(values.size),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "median": float(np.median(values)),
            "p90": float(np.quantile(values, 0.9)),
        }
    return stats


def _validate_disfa(
    report: dict[str, object], rows: list[dict[str, str]]
) -> dict[str, dict[str, object]]:
    expected = int(report["processed_samples"])
    if len(rows) != expected:
        raise ValueError(f"DISFA CSV has {len(rows)} rows; expected {expected}")
    subject_counts = Counter(row["subject"] for row in rows)
    if set(subject_counts.values()) != {200}:
        raise ValueError(f"unexpected DISFA subject balance: {subject_counts}")
    reported = {
        str(metric["au"]): metric for metric in report["au_metrics"]  # type: ignore[index]
    }
    stats: dict[str, dict[str, object]] = {}
    for au in AUS:
        truth = np.asarray([float(row[f"{au}_truth"]) for row in rows])
        prediction = np.asarray(
            [float(row[f"{au}_prediction"]) for row in rows]
        )
        truth_binary = truth >= float(report["truth_threshold"])
        prediction_binary = prediction >= float(report["prediction_threshold"])
        f1 = _binary_f1(truth_binary, prediction_binary)
        icc = _icc_3_1(truth, prediction)
        metric = reported[au]
        _assert_close(f"{au} F1", f1, metric["f1"])
        _assert_close(f"{au} ICC", icc, metric["icc"])
        stats[au] = {
            "f1": f1,
            "icc": icc,
            "support": int(truth_binary.sum()),
            "predicted_positive": int(prediction_binary.sum()),
            "prevalence": float(truth_binary.mean()),
        }
    _assert_close(
        "DISFA macro F1",
        np.mean([float(stats[au]["f1"]) for au in AUS]),
        report["macro_f1"],
    )
    _assert_close(
        "DISFA macro ICC",
        np.mean([float(stats[au]["icc"]) for au in AUS]),
        report["macro_icc"],
    )
    return stats


def _binary_f1(truth: np.ndarray, prediction: np.ndarray) -> float:
    true_positive = int(np.count_nonzero(truth & prediction))
    false_positive = int(np.count_nonzero(~truth & prediction))
    false_negative = int(np.count_nonzero(truth & ~prediction))
    denominator = 2 * true_positive + false_positive + false_negative
    return 0.0 if denominator == 0 else 2 * true_positive / denominator


def _icc_3_1(truth: np.ndarray, prediction: np.ndarray) -> float:
    ratings = np.stack([truth, prediction], axis=1)
    sample_count, rater_count = ratings.shape
    grand_mean = ratings.mean()
    sample_means = ratings.mean(axis=1)
    rater_means = ratings.mean(axis=0)
    sample_ss = rater_count * np.sum((sample_means - grand_mean) ** 2)
    rater_ss = sample_count * np.sum((rater_means - grand_mean) ** 2)
    total_ss = np.sum((ratings - grand_mean) ** 2)
    error_ss = total_ss - sample_ss - rater_ss
    sample_ms = sample_ss / (sample_count - 1)
    error_ms = error_ss / ((sample_count - 1) * (rater_count - 1))
    return float(
        (sample_ms - error_ms)
        / (sample_ms + (rater_count - 1) * error_ms)
    )


def _assert_close(label: str, actual: float, expected: object) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError(f"{label}: recomputed {actual}, report has {expected}")


def _write_macros(
    aflfp_report: dict[str, object],
    disfa_report: dict[str, object],
    movement_stats: dict[str, dict[str, object]],
    au_stats: dict[str, dict[str, object]],
) -> None:
    hardest_movement = max(
        movement_stats, key=lambda name: float(movement_stats[name]["mean"])
    )
    easiest_movement = min(
        movement_stats, key=lambda name: float(movement_stats[name]["mean"])
    )
    best_au = max(au_stats, key=lambda au: float(au_stats[au]["f1"]))
    worst_au = min(au_stats, key=lambda au: float(au_stats[au]["f1"]))
    prevalence = np.asarray([float(au_stats[au]["prevalence"]) for au in AUS])
    f1 = np.asarray([float(au_stats[au]["f1"]) for au in AUS])
    correlation = float(np.corrcoef(prevalence, f1)[0, 1])
    lines = [
        r"\newcommand{\AFLFPSamples}{" + f"{int(aflfp_report['processed_samples']):,}" + "}",
        r"\newcommand{\AFLFPDetection}{" + _percent(aflfp_report["detection_rate"], 1) + "}",
        r"\newcommand{\AFLFPNMEMean}{" + _percent(aflfp_report["nme_mean"], 3) + "}",
        r"\newcommand{\AFLFPNMEStd}{" + _percent(aflfp_report["nme_std"], 3) + "}",
        r"\newcommand{\AFLFPNMEMedian}{" + _percent(aflfp_report["nme_median"], 3) + "}",
        r"\newcommand{\AFLFPNMEP}{" + _percent(aflfp_report["nme_p90"], 3) + "}",
        r"\newcommand{\AFLFPFPS}{" + f"{float(aflfp_report['fps']):.2f}" + "}",
        r"\newcommand{\AFLFPHardest}{" + _latex_text(hardest_movement) + "}",
        r"\newcommand{\AFLFPEasiest}{" + _latex_text(easiest_movement) + "}",
        r"\newcommand{\DISFASamples}{" + f"{int(disfa_report['processed_samples']):,}" + "}",
        r"\newcommand{\DISFADetection}{" + _percent(disfa_report["detection_rate"], 1) + "}",
        r"\newcommand{\DISFAFOne}{" + f"{float(disfa_report['macro_f1']):.3f}" + "}",
        r"\newcommand{\DISFAICC}{" + f"{float(disfa_report['macro_icc']):.3f}" + "}",
        r"\newcommand{\DISFAFPS}{" + f"{float(disfa_report['fps']):.2f}" + "}",
        r"\newcommand{\DISFABestAU}{" + best_au + "}",
        r"\newcommand{\DISFAWorstAU}{" + worst_au + "}",
        r"\newcommand{\DISFAPrevalenceCorrelation}{" + f"{correlation:.3f}" + "}",
        r"\newcommand{\PyFeatVersion}{" + str(aflfp_report["py_feat_version"]) + "}",
    ]
    (GENERATED / "results_macros.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_headline_table(
    aflfp_report: dict[str, object], disfa_report: dict[str, object]
) -> None:
    text = (
        "\\begin{tabular}{llrrrr}\n"
        "\\toprule\n"
        "Dataset & Task & Test samples & Detection & Accuracy & Throughput \\\\\n"
        "\\midrule\n"
        f"AFLFP & 68-point landmarks & {int(aflfp_report['processed_samples']):,} & "
        f"{_percent(aflfp_report['detection_rate'], 1)} & "
        f"NME {_percent(aflfp_report['nme_mean'], 3)} & "
        f"{float(aflfp_report['fps']):.2f} FPS \\\\\n"
        f"DISFA & 12-AU detection & {int(disfa_report['processed_samples']):,} & "
        f"{_percent(disfa_report['detection_rate'], 1)} & "
        f"macro F1 {float(disfa_report['macro_f1']):.3f} & "
        f"{float(disfa_report['fps']):.2f} FPS \\\\\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
    )
    (GENERATED / "headline_table.tex").write_text(text, encoding="utf-8")


def _write_movement_table(stats: dict[str, dict[str, object]]) -> None:
    rows = []
    for movement, abbreviation, baseline in MOVEMENTS:
        item = stats[movement]
        rows.append(
            f"{_latex_text(movement)} & {abbreviation} & {int(item['count'])} & "
            f"{100 * float(item['mean']):.3f} & "
            f"{100 * float(item['std']):.3f} & "
            f"{100 * float(item['median']):.3f} & "
            f"{100 * float(item['p90']):.3f} & {baseline:.1f} \\\\"
        )
    text = (
        "\\begin{tabular}{llrrrrrr}\n"
        "\\toprule\n"
        "Movement & Abbr. & $n$ & Mean & SD & Median & P90 & "
        "Cascaded FCN mean \\\\\n"
        "\\midrule\n"
        + "\n".join(rows)
        + "\n\\bottomrule\n\\end{tabular}\n"
    )
    (GENERATED / "aflfp_movement_table.tex").write_text(text, encoding="utf-8")


def _write_au_table(stats: dict[str, dict[str, object]]) -> None:
    rows = []
    for au in AUS:
        item = stats[au]
        rows.append(
            f"{au} & {int(item['support']):,} & "
            f"{100 * float(item['prevalence']):.2f} & "
            f"{int(item['predicted_positive']):,} & "
            f"{float(item['f1']):.3f} & {float(item['icc']):.3f} \\\\"
        )
    text = (
        "\\begin{tabular}{lrrrrr}\n"
        "\\toprule\n"
        "AU & Positive support & Prevalence (\\%) & Predicted positive & "
        "F1 & ICC(3,1) \\\\\n"
        "\\midrule\n"
        + "\n".join(rows)
        + "\n\\bottomrule\n\\end{tabular}\n"
    )
    (GENERATED / "disfa_au_table.tex").write_text(text, encoding="utf-8")


def _plot_aflfp(stats: dict[str, dict[str, object]]) -> None:
    _plot_style()
    labels = [abbreviation for _, abbreviation, _ in MOVEMENTS]
    values = [np.asarray(stats[name]["values"]) * 100 for name, _, _ in MOVEMENTS]
    means = np.asarray([float(stats[name]["mean"]) * 100 for name, _, _ in MOVEMENTS])
    baselines = np.asarray([baseline for _, _, baseline in MOVEMENTS])
    positions = np.arange(1, len(MOVEMENTS) + 1)

    figure, axes = plt.subplots(2, 1, figsize=(7.15, 5.25), constrained_layout=True)
    boxes = axes[0].boxplot(
        values,
        tick_labels=labels,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": "#0F172A", "linewidth": 1.1},
        whiskerprops={"color": GRAY},
        capprops={"color": GRAY},
    )
    for box in boxes["boxes"]:
        box.set(facecolor=BLUE, alpha=0.55, edgecolor=BLUE)
    axes[0].set_ylabel("NME (%)")
    axes[0].set_title("(a) py-feat sample distributions", loc="left", fontsize=9)
    axes[0].grid(axis="y", alpha=0.25)

    width = 0.38
    axes[1].bar(
        positions - width / 2,
        means,
        width,
        color=BLUE,
        label="py-feat Detectorv2 (test-only)",
    )
    axes[1].bar(
        positions + width / 2,
        baselines,
        width,
        color=ORANGE,
        label="Published Cascaded FCN",
    )
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylabel("Mean NME (%)")
    axes[1].set_title("(b) Descriptive comparison of movement means", loc="left", fontsize=9)
    axes[1].legend(frameon=False, ncol=2, loc="upper left")
    axes[1].grid(axis="y", alpha=0.25)
    figure.savefig(FIGURES / "aflfp_nme.pdf", bbox_inches="tight")
    plt.close(figure)


def _plot_disfa_metrics(stats: dict[str, dict[str, object]]) -> None:
    _plot_style()
    positions = np.arange(len(AUS))
    f1 = [float(stats[au]["f1"]) for au in AUS]
    icc = [float(stats[au]["icc"]) for au in AUS]
    width = 0.38
    figure, axis = plt.subplots(figsize=(7.15, 3.25), constrained_layout=True)
    axis.bar(positions - width / 2, f1, width, color=TEAL, label="F1")
    axis.bar(positions + width / 2, icc, width, color=ORANGE, label="ICC(3,1)")
    axis.axhline(np.mean(f1), color=TEAL, linestyle="--", linewidth=1)
    axis.axhline(np.mean(icc), color=ORANGE, linestyle=":", linewidth=1)
    axis.set_xticks(positions, [au.replace("AU", "") for au in AUS])
    axis.set_xlabel("Action Unit")
    axis.set_ylabel("Score")
    axis.set_ylim(0, 1.02)
    axis.legend(frameon=False, ncol=2, loc="upper left")
    axis.grid(axis="y", alpha=0.25)
    figure.savefig(FIGURES / "disfa_au_metrics.pdf", bbox_inches="tight")
    plt.close(figure)


def _plot_disfa_prevalence(stats: dict[str, dict[str, object]]) -> None:
    _plot_style()
    prevalence = np.asarray([float(stats[au]["prevalence"]) * 100 for au in AUS])
    f1 = np.asarray([float(stats[au]["f1"]) for au in AUS])
    support = np.asarray([int(stats[au]["support"]) for au in AUS])
    sizes = 30 + 150 * np.sqrt(support / support.max())
    figure, axis = plt.subplots(figsize=(7.15, 3.35), constrained_layout=True)
    axis.scatter(
        prevalence,
        f1,
        s=sizes,
        color=BLUE,
        alpha=0.78,
        edgecolor="white",
        linewidth=0.7,
    )
    offsets = {
        "AU01": (4, -10),
        "AU02": (4, 5),
        "AU04": (4, -10),
        "AU05": (4, 5),
        "AU06": (4, 5),
        "AU09": (4, -10),
        "AU12": (4, 5),
        "AU15": (4, 5),
        "AU17": (4, -10),
        "AU20": (4, -10),
        "AU25": (4, -10),
        "AU26": (4, 5),
    }
    for index, au in enumerate(AUS):
        axis.annotate(
            au,
            (prevalence[index], f1[index]),
            xytext=offsets[au],
            textcoords="offset points",
            fontsize=7,
        )
    axis.set_xlabel("Ground-truth positive prevalence (%)")
    axis.set_ylabel("F1")
    axis.set_ylim(0.42, 1.01)
    axis.grid(alpha=0.25)
    figure.savefig(FIGURES / "disfa_prevalence_f1.pdf", bbox_inches="tight")
    plt.close(figure)


def _write_derived_summary(
    movement_stats: dict[str, dict[str, object]],
    au_stats: dict[str, dict[str, object]],
) -> None:
    payload = {
        "aflfp_movements": {
            name: {
                key: value
                for key, value in stats.items()
                if key != "values"
            }
            for name, stats in movement_stats.items()
        },
        "disfa_aus": au_stats,
        "disfa_prevalence_f1_correlation": float(
            np.corrcoef(
                [float(au_stats[au]["prevalence"]) for au in AUS],
                [float(au_stats[au]["f1"]) for au in AUS],
            )[0, 1]
        ),
    }
    (RESULTS / "derived-summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _plot_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )


def _percent(value: object, digits: int) -> str:
    return f"{100 * float(value):.{digits}f}\\%"


def _latex_text(value: str) -> str:
    return value.replace("&", r"\&").replace("_", r"\_")


if __name__ == "__main__":
    raise SystemExit(main())
