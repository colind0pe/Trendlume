"""Offline replay and comparison for prompt-output snapshots.

This module only reads JSON fixtures and the deterministic baseline evaluator.
It never imports a provider, opens the database, or makes a network request.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.prompt_baseline import evaluate_case

ROOT = Path(__file__).resolve().parent
DEFAULT_LEFT = ROOT / "fixtures" / "prompt_compare_v1.json"
DEFAULT_RIGHT = ROOT / "fixtures" / "prompt_compare_v2_candidate.json"
MANUAL_REVIEW_FIELDS = {
    "factuality",
    "creative_quality",
    "tone_and_hook_quality",
    "visual_story_coherence",
}


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("snapshot cases must be a list")
    results = [evaluate_case(case) for case in cases]
    return {
        "snapshot_id": payload.get("snapshot_id", path.stem),
        "prompt_id": payload.get("prompt_id"),
        "prompt_version": payload.get("prompt_version"),
        "template_hash": payload.get("template_hash"),
        "results": results,
    }


def _automatic_score(result: dict[str, Any]) -> tuple[int, int]:
    metrics = [
        metric
        for metric in result.get("metrics", [])
        if metric.get("metric") not in MANUAL_REVIEW_FIELDS
    ]
    return sum(bool(metric.get("passed")) for metric in metrics), len(metrics)


def compare_snapshots(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_cases = {item["case_id"]: item for item in left["results"]}
    right_cases = {item["case_id"]: item for item in right["results"]}
    comparisons: list[dict[str, Any]] = []
    for case_id in sorted(left_cases.keys() | right_cases.keys()):
        before = left_cases.get(case_id)
        after = right_cases.get(case_id)
        if before is None or after is None:
            comparisons.append(
                {
                    "case_id": case_id,
                    "classification": "manual_review",
                    "reason": "case exists in only one snapshot",
                }
            )
            continue
        before_score, before_total = _automatic_score(before)
        after_score, after_total = _automatic_score(after)
        if after_score > before_score:
            classification = "improved"
        elif after_score < before_score:
            classification = "regressed"
        else:
            classification = "unchanged"
        comparisons.append(
            {
                "case_id": case_id,
                "classification": classification,
                "left": {"passed": before_score, "total": before_total, "status": before["status"]},
                "right": {"passed": after_score, "total": after_total, "status": after["status"]},
                "manual_review": sorted(set(before.get("manual_review", [])) | set(after.get("manual_review", []))),
            }
        )

    counts = {
        label: sum(item.get("classification") == label for item in comparisons)
        for label in ("improved", "regressed", "unchanged", "manual_review")
    }
    return {
        "offline": True,
        "left": {
            key: left.get(key)
            for key in ("snapshot_id", "prompt_id", "prompt_version", "template_hash")
        },
        "right": {
            key: right.get(key)
            for key in ("snapshot_id", "prompt_id", "prompt_version", "template_hash")
        },
        "counts": counts,
        "comparisons": comparisons,
        "manual_quality_is_not_scored": True,
    }


def compare_files(left_path: Path = DEFAULT_LEFT, right_path: Path = DEFAULT_RIGHT) -> dict[str, Any]:
    return compare_snapshots(load_snapshot(left_path), load_snapshot(right_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare offline prompt snapshots")
    parser.add_argument("--left", type=Path, default=DEFAULT_LEFT)
    parser.add_argument("--right", type=Path, default=DEFAULT_RIGHT)
    args = parser.parse_args()
    print(json.dumps(compare_files(args.left, args.right), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
