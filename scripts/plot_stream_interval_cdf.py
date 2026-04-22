#!/usr/bin/env python3
"""Plot a CDF of browser stream inter-packet intervals."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


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


def plot_cdf(values: list[float], output_path: Path, title: str, x_limit: float | None) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "matplotlib is required for plotting. Run with: "
            "uv run --with matplotlib scripts/plot_stream_interval_cdf.py ..."
        ) from error

    sorted_values = sorted(values)
    y_values = [(index + 1) / len(sorted_values) for index in range(len(sorted_values))]

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.step(sorted_values, y_values, where="post", linewidth=2)
    ax.set_title(title)
    ax.set_xlabel("Browser stream inter-packet interval (ms)")
    ax.set_ylabel("CDF")
    ax.set_ylim(0, 1.01)
    ax.grid(True, alpha=0.3)
    if x_limit is not None:
        ax.set_xlim(0, x_limit)

    p50 = percentile(sorted_values, 0.5)
    p95 = percentile(sorted_values, 0.95)
    ax.axvline(p50, color="tab:orange", linestyle="--", linewidth=1, label=f"p50={p50:.1f} ms")
    ax.axvline(p95, color="tab:red", linestyle="--", linewidth=1, label=f"p95={p95:.1f} ms")
    ax.legend(loc="lower right")

    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a CDF from stream interval rows extracted by extract_stream_intervals.py."
    )
    parser.add_argument("input", type=Path, help="Extracted CSV or JSON interval file.")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        values = load_interval_values(args.input)
        if not values:
            print("No numeric inter_packet_interval_ms values found.", file=sys.stderr)
            return 1
        plot_cdf(values, args.output, args.title, args.x_limit)
    except (OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Wrote {args.output} with {len(values)} intervals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
