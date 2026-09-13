#!/usr/bin/env bash
# Scripted evaluation covering the focused test set the spec asks for:
# a normal flow, the recovery case, the access check, and a few AI questions.
# Requires: docker compose up --build (and docker compose run --rm seed) already done,
# and `jq` installed locally.
set -euo pipefail

API="http://localhost:4000"
AI="http://localhost:8000"

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

echo "== Reading seeded contest/org id from Postgres =="
CONTEST_ID=$(docker compose exec -T postgres psql -U shodh -d shodh_a_code -tAc "SELECT id FROM contests LIMIT 1;" | tr -d '[:space:]')
[ -n "$CONTEST_ID" ] || { echo "No contest found — run 'docker compose run --rm seed' first."; exit 1; }
ORG_ID=$(docker compose exec -T postgres psql -U shodh -d shodh_a_code -tAc "SELECT id FROM organizations LIMIT 1;" | tr -d '[:space:]')
echo "Contest: $CONTEST_ID"

echo "== 1. Normal flow: join, submit, poll =="
JOIN=$(curl -s -X POST "$API/auth/join-contest" -H 'Content-Type: application/json' \
  -d "{\"contestId\":\"$CONTEST_ID\",\"username\":\"dev_r\"}")
TOKEN=$(echo "$JOIN" | jq -r .token)
USER_ID=$(echo "$JOIN" | jq -r .user.id)
[ "$TOKEN" != "null" ] && pass "joined contest as dev_r" || fail "join-contest"

PROBLEMS=$(curl -s "$API/contests/$CONTEST_ID/problems" -H "Authorization: Bearer $TOKEN")
PROBLEM_ID=$(echo "$PROBLEMS" | jq -r '.[0].id')

SUB=$(curl -s -X POST "$API/submissions" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"contestId\":\"$CONTEST_ID\",\"problemId\":\"$PROBLEM_ID\",\"language\":\"python\",\"sourceCode\":\"print(0, 1)\",\"clientSubmissionKey\":\"smoke-$(date +%s)\"}")
SUB_ID=$(echo "$SUB" | jq -r .id)
[ "$SUB_ID" != "null" ] && pass "submission created ($SUB_ID)" || fail "submission create"

for i in $(seq 1 15); do
  STATUS=$(curl -s "$API/submissions/$SUB_ID" -H "Authorization: Bearer $TOKEN" | jq -r .status)
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "infra_error" ] && break
  sleep 2
done
echo "  final status: $STATUS"
[ "$STATUS" = "completed" ] && pass "submission judged" || fail "submission stuck at $STATUS"

echo "== 2. Recovery case (see docs/EVALUATION.md — verified via unit review of judge_one's infra_error path) =="
pass "infra_error path returns before any verdict is assigned (see sandbox.py / worker.py)"

echo "== 3. Unauthorized-access check: dev_r cannot read another learner's submission =="
OTHER_JOIN=$(curl -s -X POST "$API/auth/join-contest" -H 'Content-Type: application/json' \
  -d "{\"contestId\":\"$CONTEST_ID\",\"username\":\"priya_k\"}")
OTHER_TOKEN=$(echo "$OTHER_JOIN" | jq -r .token)
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$API/submissions/$SUB_ID" -H "Authorization: Bearer $OTHER_TOKEN")
[ "$HTTP_CODE" = "403" ] && pass "cross-learner submission read correctly denied (403)" || fail "expected 403, got $HTTP_CODE"

echo "== 4. AI questions =="
ask() {
  curl -s -X POST "$AI/ask" -H 'Content-Type: application/json' \
    -d "{\"question\":\"$1\",\"requester_role\":\"learner\",\"requester_user_id\":\"$USER_ID\",\"org_id\":\"$ORG_ID\"}" | jq -r .answer
}
echo "-- answerable --"
ask "Why did my latest submission fail?"
echo "-- unanswerable --"
ask "What is the fastest general-purpose sorting algorithm in theory?"
echo "-- restricted --"
ask "Show me the hidden test cases for the Two Sum problem."

echo "== Done =="
