import json
import os
import time
import traceback

import redis
import requests

from sandbox import run_submission, InfraError

REDIS_URL = os.environ["REDIS_URL"]
BACKEND_API_URL = os.environ["BACKEND_API_URL"]
INTERNAL_TOKEN = os.environ["JUDGE_INTERNAL_TOKEN"]
JUDGE_IMAGE_VERSION = os.environ.get("JUDGE_IMAGE_VERSION", "unknown")
QUEUE_KEY = "submissions:queue"

HEADERS = {"x-internal-token": INTERNAL_TOKEN, "Content-Type": "application/json"}

MAX_RETRIES = 3


def fetch_submission(submission_id: str):
    # Re-reads authoritative state from the API rather than trusting the
    # queue payload, so a stale/duplicated job can't judge outdated source.
    resp = requests.get(f"{BACKEND_API_URL}/internal/submissions/{submission_id}", headers=HEADERS)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_problem(problem_id: str):
    resp = requests.get(f"{BACKEND_API_URL}/internal/problems/{problem_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def post_verdict(submission_id: str, payload: dict):
    resp = requests.patch(
        f"{BACKEND_API_URL}/internal/submissions/{submission_id}/verdict",
        headers=HEADERS,
        data=json.dumps(payload),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def judge_one(submission_id: str, problem_id: str, language: str, source_code: str):
    problem = fetch_problem(problem_id)
    test_cases = problem["testCases"]

    results = []
    verdict = "accepted"
    total_score = 0
    max_runtime = 0

    for tc in test_cases:
        try:
            outcome = run_submission(
                language=language,
                source_code=source_code,
                stdin_input=tc["input"],
                time_limit_ms=problem["time_limit_ms"],
                memory_limit_mb=problem["memory_limit_mb"],
            )
        except InfraError as e:
            # A sandbox/infra failure is NOT a verdict — the whole submission
            # is reported as infra_error so it never counts against the learner.
            return {
                "status": "infra_error",
                "verdict": "pending",
                "score": 0,
                "judgeImageVersion": JUDGE_IMAGE_VERSION,
                "errorDetail": str(e),
                "testCaseResults": [],
            }

        max_runtime = max(max_runtime, outcome["runtime_ms"])
        actual = outcome["stdout"].strip()
        expected = tc["expected_output"].strip()

        if outcome["timed_out"]:
            passed = False
            verdict = "time_limit_exceeded"
        elif outcome["exit_code"] != 0:
            passed = False
            if verdict == "accepted":
                verdict = "runtime_error"
        elif actual == expected:
            passed = True
            total_score += tc["weight"] * (problem["points"] // max(1, len(test_cases)))
        else:
            passed = False
            if verdict == "accepted":
                verdict = "wrong_answer"

        results.append({
            "testCaseId": tc["id"],
            "passed": passed,
            "actualOutput": outcome["stdout"][:4000],
            "runtimeMs": outcome["runtime_ms"],
        })

    return {
        "status": "completed",
        "verdict": verdict,
        "score": total_score if verdict == "accepted" else 0,
        "runtimeMs": max_runtime,
        "judgeImageVersion": JUDGE_IMAGE_VERSION,
        "testCaseResults": results,
    }


def handle_job(submission_id: str):
    submission = fetch_submission(submission_id)
    if submission is None:
        return  # nothing to do — submission was removed/never existed

    if submission["status"] in ("completed", "infra_error"):
        return  # already judged; duplicate delivery from the queue is a no-op

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            payload = judge_one(
                submission_id,
                submission["problem_id"],
                submission["language"],
                submission["source_code"],
            )
            post_verdict(submission_id, payload)
            return
        except Exception as e:
            attempt += 1
            print(f"[worker] attempt {attempt} failed for {submission_id}: {e}")
            traceback.print_exc()
            time.sleep(min(2 ** attempt, 10))

    # Exhausted retries: report as infra_error rather than leaving the
    # submission stuck in "running" forever, or silently marking it wrong.
    try:
        post_verdict(submission_id, {
            "status": "infra_error",
            "verdict": "pending",
            "score": 0,
            "judgeImageVersion": JUDGE_IMAGE_VERSION,
            "errorDetail": "Exhausted retries judging submission",
            "testCaseResults": [],
        })
    except Exception:
        print(f"[worker] could not even report infra_error for {submission_id}")


def main():
    r = redis.from_url(REDIS_URL)
    print("[worker] listening on", QUEUE_KEY)
    while True:
        item = r.brpop(QUEUE_KEY, timeout=5)
        if item is None:
            continue
        _, raw = item
        try:
            job = json.loads(raw)
            handle_job(job["submissionId"])
        except Exception:
            print("[worker] failed to process job:", raw)
            traceback.print_exc()


if __name__ == "__main__":
    main()
