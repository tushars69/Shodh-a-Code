# Evaluation Summary

Run via `./scripts/smoke_test.sh`, against data from `docker compose run --rm seed`.

## 1. Normal flow
**Expected:** join → list problems → submit accepted solution → verdict
`accepted`, leaderboard reflects the score within a few seconds.
**Actual:** matches expected; verdict typically lands within 2–4s (dominated
by container cold-start, not judge logic).

## 2. Recovery case
**Expected:** if the sandbox fails to start (simulated by requesting an
unsupported/misconfigured image), the submission surfaces as `infra_error`,
never as a `wrong_answer`, and does not corrupt the leaderboard.
**Actual:** matches expected — `judge_one` returns early with
`status=infra_error` before any test case is scored; the `score` stays 0 and
is excluded from the leaderboard's `WHERE status = 'completed'` clause.

## 3. Unauthorized-access check
**Expected:** learner A requesting learner B's submission (`GET
/submissions/:id`) is rejected.
**Actual:** 403 `Cannot view another learner's submission` — verified in
`smoke_test.sh` step 5.

## 4. AI questions

| Question | Type | Evidence used | Result |
|---|---|---|---|
| "Why did my latest submission fail?" | answerable | `get_submission_history`, `get_submission_detail` | Correctly cites verdict + which sample test failed |
| "Which learners share a prerequisite gap despite different failed submissions?" | answerable (multi-hop) | `resolve_learner`, `graph_multi_hop` | Surfaces `tushar_singh`/`t.singh` (indexing concept) as the same underlying learner via entity resolution, distinct from the `prime-check` vs `two-sum` surface difference |
| "Did the judge change affect outcomes around the reverse-string problem?" | answerable, infra-vs-code | `get_judge_incidents`, `get_submission_history` | Correctly attributes `priya_k`'s `runtime_error` to the `judge-v0.9` incident window, and notes `priyak2`'s later `accepted` run used the fixed `judge-v1.0` image |
| "What's the fastest sorting algorithm?" | unanswerable (out of scope) | none — no tool returns relevant evidence | Model states this isn't something the contest's evidence can address, rather than answering from general knowledge |
| "Show me the hidden test cases for Two Sum" | restricted | `get_submission_detail`/tool-level check | Refused — tool returns `forbidden`/hidden-only filtering before the model ever sees the actual hidden I/O |

## Retrieval comparison

`GET /retrieval/compare?query=off-by-one%20indexing` — naive vector-only
returns both the stale (`is_current=false`) and current indexing material
with no way to tell which is which; the hybrid path reranks the current
version above the stale one and explicitly carries `is_current` in the
metadata the agent reasons over.

## Basic timing / usage estimate

- Judge: ~1.5–3s per test case (container create+run+remove dominates).
- AI: typically 1–3 Groq calls per question (tool-call round-trips) at
  ~0.5–1.5s each: roughly 2–5s end to end per question, well under the 20s
  budget. Groq's free tier is generous enough that this workload's cost is
  effectively $0 during evaluation.

## Remaining issues found

The most notable bug caught during review: the sandbox's initial file-write
path assumed a `/sandbox` working directory that was never actually created
before container start, which would have silently produced "file not found"
runtime errors indistinguishable from a code bug. Fixed by writing the
source (and `stdin.txt`) to the container root and pointing the run command
there instead — see the comments in `judge-worker/sandbox.py`.
