from evals.runner import run


def test_offline_evaluation_baseline() -> None:
    report = run()
    assert report["passed"], report
