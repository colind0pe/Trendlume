"""Small, deterministic prompt-output baseline evaluator.

It reads committed fixtures only. It has no provider, database, or network imports.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURES = ROOT / "fixtures" / "baseline_cases.json"
TERMINAL_PUNCTUATION = "。！？!?.,，；;:："
ABSOLUTE_CLAIM = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*%|百分之\s*[零一二三四五六七八九十百\d]+|"
    r"所有人|任何人|绝对|彻底|永久|必然|保证|史上最高|历史最高)"
)
KNOWLEDGE_VISUAL_ROLES = {
    "concept",
    "process",
    "comparison",
    "timeline",
    "data",
    "example",
    "quote",
    "b_roll",
}


def _metric(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"metric": name, "passed": passed, "detail": detail}


def _visual_text(output: dict[str, Any]) -> str:
    prompts = [str(output.get("prompt") or "")]
    prompts.extend(str(scene.get("visual_prompt") or "") for scene in output.get("scenes", []))
    return " ".join(prompts).casefold()


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    output = case.get("output") or {}
    expected = case.get("expected") or {}
    metrics: list[dict[str, Any]] = []

    if "json_valid" in expected:
        raw = output.get("raw")
        parsed = output.get("parsed")
        metrics.append(_metric("json_valid", isinstance(raw, str) and isinstance(parsed, dict)))
        if isinstance(parsed, dict):
            output = parsed

    if "scenes" in output:
        scenes = output.get("scenes") or []
        required = all(
            isinstance(scene, dict)
            and isinstance(scene.get("sequence_index"), int)
            and bool(str(scene.get("narration_text") or "").strip())
            and bool(str(scene.get("visual_prompt") or "").strip())
            for scene in scenes
        )
        metrics.append(_metric("required_fields", bool(output.get("title")) and required))
        indexes = [scene.get("sequence_index") for scene in scenes]
        metrics.append(_metric("contiguous_scene_indexes", indexes == list(range(len(scenes)))))
        metrics.append(_metric("structured_shape", all(output.get(key) is not None for key in ("title", "hook", "narration", "scenes"))))

    if expected.get("knowledge_provenance"):
        brief = output.get("knowledge_brief") or {}
        claims = brief.get("key_claims") or []
        claim_ids = {str(claim.get("id")) for claim in claims if isinstance(claim, dict) and claim.get("id")}
        brief_sources = {str(ref) for ref in brief.get("source_refs") or []}
        metrics.append(
            _metric(
                "knowledge_brief_contract",
                all(bool(brief.get(field)) for field in ("audience", "thesis", "viewer_takeaway"))
                and bool(claims),
            )
        )
        claim_sources = {
            str(ref)
            for claim in claims
            if isinstance(claim, dict)
            for ref in claim.get("source_refs") or []
        }
        scene_claim_refs = {
            str(ref)
            for scene in output.get("scenes") or []
            if isinstance(scene, dict)
            for ref in scene.get("claim_refs") or []
        }
        scene_source_refs = {
            str(ref)
            for scene in output.get("scenes") or []
            if isinstance(scene, dict)
            for ref in scene.get("source_refs") or []
        }
        metrics.append(
            _metric(
                "knowledge_provenance_closed",
                bool(brief_sources)
                and claim_sources.issubset(brief_sources)
                and scene_source_refs.issubset(brief_sources)
                and scene_claim_refs.issubset(claim_ids),
            )
        )
        metrics.append(
            _metric(
                "visual_role_contract",
                all(scene.get("visual_role") in KNOWLEDGE_VISUAL_ROLES for scene in output.get("scenes") or []),
            )
        )

    target = expected.get("target_scene_count")
    if target is not None:
        actual = len(output.get("scenes", output.get("narrations", [])))
        metrics.append(_metric("target_scene_count", actual == target, f"expected={target}, actual={actual}"))

    title = str(output.get("title") or "")
    if "title_max_length" in expected:
        metrics.append(_metric("title_length", 0 < len(title) <= int(expected["title_max_length"]), f"length={len(title)}"))
    if expected.get("title_no_terminal_punctuation"):
        metrics.append(_metric("title_terminal_punctuation", bool(title) and title[-1] not in TERMINAL_PUNCTUATION))

    metadata = output.get("metadata") or (
        output if isinstance(output.get("tags"), list) else {}
    )
    if metadata:
        tags = metadata.get("tags") or []
        normalized = [str(tag).strip().lstrip("#").casefold() for tag in tags if str(tag).strip()]
        minimum, maximum = int(expected.get("tag_min", 0)), int(expected.get("tag_max", 5))
        metrics.append(_metric("tag_count", minimum <= len(tags) <= maximum, f"count={len(tags)}"))
        metrics.append(_metric("tag_unique", len(normalized) == len(set(normalized))))

    if not (case.get("input") or {}).get("sources"):
        claim_text = " ".join((title, str(output.get("description") or metadata.get("description") or ""), str(output.get("hook") or "")))
        metrics.append(_metric("unsupported_claims", ABSOLUTE_CLAIM.search(claim_text) is None))

    visual = _visual_text(output)
    medium = expected.get("visual_medium")
    if medium:
        tokens = (
            "video", "moving", "motion", "tracking", "镜头", "视频", "动态", "连续动作", "运镜"
        ) if medium == "video" else (
            "image", "photo", "illustration", "frame", "portrait", "图片", "照片", "插画", "摄影", "静态"
        )
        metrics.append(_metric("visual_medium_alignment", any(token in visual for token in tokens)))
    ratio = expected.get("aspect_ratio")
    if ratio:
        if ratio == "9:16":
            ratio_tokens = (ratio, "vertical", "portrait", "竖屏", "纵向")
        elif ratio == "16:9":
            ratio_tokens = (ratio, "wide", "landscape", "横屏", "宽幅", "横向")
        else:
            ratio_tokens = (ratio, "square", "方形")
        metrics.append(_metric("aspect_ratio_alignment", any(token in visual for token in ratio_tokens)))

    if "requires_visual_generation" in expected:
        actual = output.get("requires_visual_generation")
        metrics.append(_metric("online_asset_visual_generation", actual is expected["requires_visual_generation"]))

    budget = expected.get("max_calls")
    if budget is not None:
        actual_calls = int(case.get("observed_calls", 0))
        metrics.append(_metric("call_budget", actual_calls <= int(budget), f"budget={budget}, actual={actual_calls}"))

    known = set(case.get("known_gaps") or [])
    unexpected = [item["metric"] for item in metrics if not item["passed"] and item["metric"] not in known]
    observed_known = [item["metric"] for item in metrics if not item["passed"] and item["metric"] in known]
    status = "fail" if unexpected else ("known_gap" if observed_known else "pass")
    prompt_id = str(case["prompt_id"])
    prompt_version = case.get("prompt_version")
    if prompt_version is None and "." in prompt_id:
        suffix = prompt_id.rsplit(".", 1)[-1]
        if suffix.startswith("v"):
            prompt_version = suffix
            prompt_id = prompt_id[: -(len(suffix) + 1)]
    return {
        "case_id": case["case_id"],
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "status": status,
        "metrics": metrics,
        "known_gaps": observed_known,
        "manual_review": ["factuality", "creative_quality", "tone_and_hook_quality", "visual_story_coherence"],
    }


def run_baseline(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in payload["cases"]]
    counts = {status: sum(result["status"] == status for result in results) for status in ("pass", "known_gap", "fail")}
    return {"fixture_version": payload["version"], "offline": True, "counts": counts, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline prompt baseline")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    report = run_baseline(args.fixtures)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
