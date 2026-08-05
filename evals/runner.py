import json
from pathlib import Path

from advisory.domain import MatchPolicy


def run() -> dict[str, object]:
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    policy = MatchPolicy()
    failures: list[str] = []
    results = []
    for case in cases:
        assessment = policy.assess(case["cv"], case["job"])
        missing_required = sorted(set(case["required_gaps"]) - set(assessment.gaps))
        passed = assessment.band == case["expected_band"] and not missing_required
        if not passed:
            failures.append(case["id"])
        results.append(
            {"id": case["id"], "score": assessment.score, "band": assessment.band, "passed": passed}
        )
    return {
        "scoring_version": policy.scoring_version,
        "passed": not failures,
        "failures": failures,
        "results": results,
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
