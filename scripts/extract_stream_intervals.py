#!/usr/bin/env python3
"""Extract browser stream inter-packet intervals from exported VLM logs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


FIELDNAMES = [
    "source_file",
    "schema",
    "entry_index",
    "log_id",
    "inference_id",
    "status",
    "sequence",
    "received_at",
    "receive_performance_ms",
    "inter_packet_interval_ms",
    "interval_source",
    "time_since_trigger_sent_ms",
    "delta_chars",
    "accumulated_text_chars",
    "format_source",
]


def iter_json_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.rglob("*.json") if item.is_file())
    raise FileNotFoundError(f"Input path does not exist: {path}")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Failed to parse JSON from {path}: {error}") from error


def log_entries(payload: Any) -> tuple[str | None, str, list[dict[str, Any]]]:
    if isinstance(payload, dict):
        schema = payload.get("schema")
        traces = payload.get("traces")
        if isinstance(traces, list):
            return schema, "analysis", [item for item in traces if isinstance(item, dict)]
        entries = payload.get("entries")
        if isinstance(entries, list):
            return schema, "debug", [item for item in entries if isinstance(item, dict)]
        if "browser_stream_intervals" in payload:
            return schema, "debug", [payload]
        return schema, "debug", []
    if isinstance(payload, list):
        return None, "debug", [item for item in payload if isinstance(item, dict)]
    return None, "debug", []


def number_or_none(value: Any) -> float | int | None:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def rows_from_debug_entry(
    json_file: Path,
    schema: str | None,
    entry_index: int,
    entry: dict[str, Any],
    include_null_intervals: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    intervals = entry.get("browser_stream_intervals") or []
    if not isinstance(intervals, list):
        return rows

    for interval in intervals:
        if not isinstance(interval, dict):
            continue

        interval_ms = number_or_none(interval.get("inter_packet_interval_ms"))
        if interval_ms is None and not include_null_intervals:
            continue

        accumulated_chars = interval.get("accumulated_text_chars")
        if accumulated_chars is None:
            accumulated_chars = interval.get("text_chars")

        rows.append(
            {
                "source_file": str(json_file),
                "schema": schema,
                "entry_index": entry_index,
                "log_id": entry.get("log_id"),
                "inference_id": entry.get("inference_id"),
                "status": entry.get("status"),
                "sequence": interval.get("sequence"),
                "received_at": interval.get("received_at"),
                "receive_performance_ms": interval.get("receive_performance_ms"),
                "inter_packet_interval_ms": interval_ms,
                "interval_source": interval.get("interval_source"),
                "time_since_trigger_sent_ms": interval.get("time_since_trigger_sent_ms"),
                "delta_chars": interval.get("delta_chars"),
                "accumulated_text_chars": accumulated_chars,
                "format_source": "debug",
            }
        )

    return rows


def rows_from_analysis_trace(
    json_file: Path,
    schema: str | None,
    entry_index: int,
    trace: dict[str, Any],
    include_null_intervals: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stream = trace.get("stream") or {}
    intervals = stream.get("intervals") or []
    if not isinstance(intervals, list):
        return rows

    for interval in intervals:
        if not isinstance(interval, dict):
            continue

        interval_ms = number_or_none(interval.get("interval_ms"))
        if interval_ms is None and not include_null_intervals:
            continue

        rows.append(
            {
                "source_file": str(json_file),
                "schema": schema,
                "entry_index": entry_index,
                "log_id": trace.get("log_id"),
                "inference_id": trace.get("inference_id"),
                "status": trace.get("status"),
                "sequence": interval.get("sequence"),
                "received_at": None,
                "receive_performance_ms": None,
                "inter_packet_interval_ms": interval_ms,
                "interval_source": (
                    "first_stream_no_previous_packet"
                    if interval_ms is None
                    else "analysis_report_interval"
                ),
                "time_since_trigger_sent_ms": interval.get("receive_offset_ms"),
                "delta_chars": interval.get("delta_chars"),
                "accumulated_text_chars": interval.get("accumulated_chars"),
                "format_source": "analysis",
            }
        )

    return rows


def extract_rows(path: Path, include_null_intervals: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for json_file in iter_json_files(path):
        payload = read_json(json_file)
        schema, format_source, entries = log_entries(payload)

        for entry_index, entry in enumerate(entries):
            if format_source == "analysis":
                rows.extend(
                    rows_from_analysis_trace(
                        json_file, schema, entry_index, entry, include_null_intervals
                    )
                )
            else:
                rows.extend(
                    rows_from_debug_entry(
                        json_file, schema, entry_index, entry, include_null_intervals
                    )
                )

    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path | None) -> None:
    output = output_path.open("w", newline="", encoding="utf-8") if output_path else sys.stdout
    try:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if output_path:
            output.close()


def write_json(rows: list[dict[str, Any]], output_path: Path | None) -> None:
    text = json.dumps(rows, indent=2)
    if output_path:
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract browser stream inter-packet intervals from trigger analysis reports "
            "or debug log JSON exports."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Exported analysis report/debug log JSON file or folder.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file. Defaults to stdout.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Output format. Defaults to csv.",
    )
    parser.add_argument(
        "--include-null-intervals",
        action="store_true",
        help="Include first stream packets whose interval is null.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rows = extract_rows(args.input, include_null_intervals=args.include_null_intervals)
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    try:
        if args.format == "json":
            write_json(rows, args.output)
        else:
            write_csv(rows, args.output)
    except BrokenPipeError:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
