"""
Tests the scoring/verdict logic in worker.judge_one in isolation by
monkeypatching run_submission and the backend HTTP calls, so this suite
doesn't need a live Docker daemon or Postgres — it's checking the judging
*logic*, which is what actually needs to be correct, separately from the
sandbox's I/O.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
import worker


FAKE_PROBLEM = {
    "id": "p1",
    "points": 100,
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
    "testCases": [
        {"id": "tc1", "input": "1", "expected_output": "YES", "weight": 1},
        {"id": "tc2", "input": "2", "expected_output": "NO", "weight": 1},
    ],
}


def _outcome(stdout, exit_code=0, timed_out=False, runtime_ms=100):
    return {"stdout": stdout, "exit_code": exit_code, "timed_out": timed_out, "runtime_ms": runtime_ms}


def test_all_pass_gives_accepted_full_score():
    with patch("worker.fetch_problem", return_value=FAKE_PROBLEM), \
         patch("worker.run_submission", side_effect=[_outcome("YES"), _outcome("NO")]):
        result = worker.judge_one("s1", "p1", "python", "code")
    assert result["status"] == "completed"
    assert result["verdict"] == "accepted"
    assert result["score"] == 100


def test_one_wrong_answer_zeroes_score_but_still_completes():
    with patch("worker.fetch_problem", return_value=FAKE_PROBLEM), \
         patch("worker.run_submission", side_effect=[_outcome("YES"), _outcome("WRONG")]):
        result = worker.judge_one("s1", "p1", "python", "code")
    assert result["status"] == "completed"
    assert result["verdict"] == "wrong_answer"
    assert result["score"] == 0
    assert result["testCaseResults"][0]["passed"] is True
    assert result["testCaseResults"][1]["passed"] is False


def test_infra_failure_is_never_a_verdict():
    from sandbox import InfraError
    with patch("worker.fetch_problem", return_value=FAKE_PROBLEM), \
         patch("worker.run_submission", side_effect=InfraError("docker daemon unreachable")):
        result = worker.judge_one("s1", "p1", "python", "code")
    assert result["status"] == "infra_error"
    assert result["score"] == 0
    # Critically: this must never surface as wrong_answer/runtime_error etc.
    assert result["verdict"] == "pending"


def test_timeout_is_time_limit_exceeded_not_wrong_answer():
    with patch("worker.fetch_problem", return_value=FAKE_PROBLEM), \
         patch("worker.run_submission", side_effect=[_outcome("", timed_out=True), _outcome("NO")]):
        result = worker.judge_one("s1", "p1", "python", "code")
    assert result["verdict"] == "time_limit_exceeded"
