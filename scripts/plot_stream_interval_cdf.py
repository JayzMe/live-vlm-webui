#!/usr/bin/env python3
"""Plot CDFs of browser stream inter-packet intervals."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def default_label(path: Path) -> str:
    return path.stem


def load_interval_values(path: Path) -> list[float]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Expected a JSON list produced by extract_stream_intervals.py")
        return [
            float(item["inter_packet_interval_ms"])
            for item in data
            if isinstance(item, dict) and is_number(item.get("inter_packet_interval_ms"))
        ]

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "inter_packet_interval_ms" not in (reader.fieldnames or []):
            raise ValueError("CSV input must include inter_packet_interval_ms")
        values = []
        for row in reader:
            raw_value = row.get("inter_packet_interval_ms")
            if raw_value in (None, ""):
                continue
            values.append(float(raw_value))
        return values


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute a percentile with no values")
    index = (len(sorted_values) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def plot_cdf(
    series: list[tuple[str, list[float]]],
    output_path: Path,
    title: str,
    x_limit: float | None,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "matplotlib is required for plotting. Run with: "
            "uv run --with matplotlib scripts/plot_stream_interval_cdf.py ..."
        ) from error

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])

    for index, (label, values) in enumerate(series):
        sorted_values = sorted(values)
        y_values = [(item_index + 1) / len(sorted_values) for item_index in range(len(sorted_values))]
        color = color_cycle[index % len(color_cycle)] if color_cycle else None
        p50 = percentile(sorted_values, 0.5)
        p95 = percentile(sorted_values, 0.95)
        legend_label = f"{label} (n={len(sorted_values)}, p50={p50:.1f} ms, p95={p95:.1f} ms)"
        line = ax.step(sorted_values, y_values, where="post", linewidth=2, label=legend_label, color=color)[0]

        for quantile, linestyle, linewidth in ((0.5, "--", 1.2), (0.95, ":", 1.6)):
            ax.axvline(
                percentile(sorted_values, quantile),
                color=line.get_color(),
                linestyle=linestyle,
                linewidth=linewidth,
                alpha=0.65,
            )

    ax.set_title(title)
    ax.set_xlabel("Browser stream inter-packet interval (ms)")
    ax.set_ylabel("CDF")
    ax.set_ylim(0, 1.01)
    ax.grid(True, alpha=0.3)
    if x_limit is not None:
        ax.set_xlim(0, x_limit)
    ax.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a CDF from stream interval rows extracted by extract_stream_intervals.py."
    )
    parser.add_argument("input", type=Path, nargs="+", help="One or more extracted CSV or JSON interval files.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("stream-interval-cdf.png"),
        help="Output image path. Defaults to stream-interval-cdf.png.",
    )
    parser.add_argument(
        "--title",
        default="Browser Stream Inter-Packet Interval CDF",
        help="Plot title.",
    )
    parser.add_argument(
        "--x-limit",
        type=float,
        help="Optional x-axis upper bound in milliseconds.",
    )
    parser.add_argument(
        "--percentiles",
        type=float,
        nargs="+",
        default=[50, 95],
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if [round(value, 6) for value in args.percentiles] != [50, 95]:
            print("Only p50 and p95 markers are supported.", file=sys.stderr)
            return 1

        series = []
        skipped = []
        for input_path in args.input:
            values = load_interval_values(input_path)
            if values:
                series.append((default_label(input_path), values))
            else:
                skipped.append(input_path)

        if not series:
            print("No numeric inter_packet_interval_ms values found.", file=sys.stderr)
            return 1

        plot_cdf(series, args.output, args.title, args.x_limit)
    except (OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1

    total_intervals = sum(len(values) for _, values in series)
    print(f"Wrote {args.output} with {total_intervals} intervals from {len(series)} file(s).")
    if skipped:
        skipped_names = ", ".join(str(path) for path in skipped)
        print(f"Skipped files with no numeric intervals: {skipped_names}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
