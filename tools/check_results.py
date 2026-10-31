#!/usr/bin/env python3
"""Reproduce the saved main matrix from sanitized native event-count records.

This is an offline arithmetic checker, not a benchmark collector or GPU test.
The export intentionally does not include prompt/output text or full token IDs.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def decode_rate(request: dict) -> float | None:
    """Fixed output-token window:512/(t641-t129), first cumulative crossing."""
    times = []
    for target in (129, 641):
        crossing = next((event["seconds"] for event in request["events"]
                         if event["count"] >= target), None)
        if crossing is None:
            return None
        times.append(crossing)
    if times[1] <= times[0]:
        raise ValueError("Nonpositive decode window")
    return 512.0 / (times[1] - times[0])


def close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8):
        raise ValueError(f"{label}: recomputed {actual} != saved {expected}")


def verify(root: Path = ROOT) -> dict:
    report = json.loads((root / "results/summary.json").read_text())
    observations = json.loads(gzip.decompress((root / "results/observations.json.gz").read_bytes()))
    waves = observations["waves"]
    phase_requests = Counter()
    cells = defaultdict(list)
    request_errors = 0
    for wave in waves:
        requests = wave["requests"]
        phase_requests[wave["phase"]] += len(requests)
        for request in requests:
            request_errors += bool(request["error"])
            assert request["done"] and request["attempts"] == 1
            assert request["native"]["completion_tokens"] == request["output_tokens"]
            assert request["events"][-1]["count"] == request["output_tokens"]
            assert request["output_tokens"] <= request["output_budget"]
            assert all(b["count"] >= a["count"] and b["seconds"] >= a["seconds"]
                       for a, b in zip(request["events"], request["events"][1:]))
        if wave["phase"] != "main":
            continue
        assert len(requests) == wave["concurrency"] and wave["complete"]
        assert not wave["isolation"]["excess_observed"]
        assert not wave["isolation"]["uncertain"]
        wall = max(r["finished_s"] for r in requests) - min(r["started_s"] for r in requests)
        throughput = sum(r["output_tokens"] for r in requests) / wall
        close(throughput, wave["aggregate_e2e_tps"], "wave aggregate")
        rates = [v for r in requests if (v := decode_rate(r)) is not None]
        cells[(wave["workload"], wave["context"], wave["concurrency"])].append(
            (throughput, median(rates) if rates else None))
    expected_phases = {"main": 756, "mixed": 126, "soak_corrected": 90, "soak": 96, "pilot": 17}
    assert dict(phase_requests) == expected_phases, dict(phase_requests)
    assert len(cells) == 60 and all(len(values) == 3 for values in cells.values())
    with (root / "results/matrix.csv").open(newline="") as stream:
        table = list(csv.DictReader(stream))
    assert len(table) == len(cells)
    for row in table:
        key = (row["workload"], int(row["input_tokens"]), int(row["concurrency"]))
        values = cells[key]
        close(median(v[0] for v in values), float(row["median_aggregate_e2e_tps"]), f"{key} aggregate")
        close(median(v[1] for v in values if v[1] is not None),
              float(row["median_of_wave_median_decode_tps"]), f"{key} decode")
        assert int(row["recorded_requests"]) == int(row["concurrency"]) * 3
        assert int(row["errors"]) == 0
    counts = report["counts"]
    assert counts["protocol_qualified_requests"] == sum(phase_requests[p] for p in ("main", "mixed", "soak_corrected")) == 972
    assert counts["all_retained_requests"] == sum(phase_requests.values()) == 1085
    assert request_errors == report["requests_with_errors"] == 0
    assert counts["excluded_original_soak_requests"] == phase_requests["soak"] == 96
    return {"matrix_cells_recomputed": len(cells), "main_waves_recomputed": sum(len(v) for v in cells.values()),
            "retained_requests_checked": sum(phase_requests.values()), "qualified_requests": 972,
            "excluded_original_soak": 96, "recorded_request_errors": request_errors,
            "scope": "Offline sanitized event-count arithmetic only; not fresh serving qualification"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
