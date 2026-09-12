import json

from evals.prompt_baseline import DEFAULT_FIXTURES, run_baseline


def test_offline_baseline_is_green_and_separates_manual_metrics():
    report = run_baseline(DEFAULT_FIXTURES)

    assert report["offline"] is True
    assert report["counts"] == {"pass": 5, "known_gap": 6, "fail": 0}
    gaps = {
        gap
        for result in report["results"]
        for gap in result["known_gaps"]
    }
    assert gaps == {"target_scene_count", "unsupported_claims", "tag_unique"}

    automatic_names = {
        metric["metric"]
        for result in report["results"]
        for metric in result["metrics"]
    }
    manual_names = {
        name
        for result in report["results"]
        for name in result["manual_review"]
    }
    assert automatic_names.isdisjoint(manual_names)


def test_fixture_coverage_matrix_is_representative_and_secret_free():
    payload = json.loads(DEFAULT_FIXTURES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    serialized = json.dumps(payload, ensure_ascii=False).casefold()

    assert {8, 14, 20}.issubset({case["input"].get("target_scene_count") for case in cases})
    assert {"9:16", "16:9"}.issubset({case["input"].get("aspect_ratio") for case in cases})
    assert any(case["input"].get("content_mode") == "online_asset" for case in cases)
    assert any(case["input"].get("mode") == "fixed" for case in cases)
    assert "ignore previous instructions" in serialized
    assert "api_key\"" not in serialized
    assert "authorization\"" not in serialized
    assert "cookie\"" not in serialized
    assert "signed_url" not in serialized
