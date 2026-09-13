# Shodh-a-Code — Contest Platform + AI Layer

Take-home submission for the AI Engineer Intern role. One product, four
services, submitted as one repo per the assignment's instructions.

## Quick start

```bash
git clone <this repo>
cd shodh-a-code
docker compose up --build
# in a second terminal, once postgres/neo4j report healthy:
docker compose run --rm seed
```

Then open http://localhost:3000, join with **Contest ID** printed by the seed
script and username `tushar_singh` (or `priya_k`, `dev_r`, etc — see seed
output). Backend API: `:4000`. AI service: `:8000`. Neo4j browser: `:7474`.

Run the scripted evaluation (normal flow + recovery + access check + AI
questions) with:

```bash
./scripts/smoke_test.sh
```

## Architecture

```
frontend (Next.js)  →  backend-api (NestJS)  →  Postgres (source of truth)
                              │                        ▲
                              │ enqueue                 │ read authoritative state
                              ▼                        │
                        Redis queue  →  judge-worker (Python, Docker-in-Docker sandbox)
                                                          │
                        backend-api  ←────────── verdict (internal endpoint)

frontend  →  ai-service (FastAPI)  →  Postgres (facts) + Neo4j (relationships) + Chroma (semantic recall)
                                    →  Groq (Llama 3.3 70B) for the agentic reasoning loop
```

**Why this split:** NestJS owns the contest domain (identity, org/role
scoping, submission lifecycle) because that's where strict typing and
decorator-based guards pay for themselves. FastAPI owns the AI layer because
Python has the better retrieval/agent ecosystem. The judge is its own Python
worker, deliberately decoupled from the API process, so a stuck or crashed
sandbox can never block a request thread — it only ever talks to the API
through the async queue + a small internal HTTP contract.

**Data store roles (Stage 3 requirement — distinct responsibilities, not three
copies of the same data):**
- **Postgres** — source of truth. Submissions, verdicts, timestamps, judge
  incidents, versioned learning material. Anything the AI states as fact
  should be traceable to a row here.
- **Neo4j** — relationships. Problem→Concept→Learner edges, so "which
  learners share a prerequisite gap despite different failed submissions" is
  a graph traversal, not a join no relational schema was designed for.
- **Chroma** — semantic recall over learning material for "what should I
  review" style grounding.

## AI layer design

- **Entity resolution**: Postgres trigram similarity (`pg_trgm`) over
  `username`/`display_name`, exposed as a `resolve_learner` tool — handles
  the seeded case of the same person appearing as `tushar_singh` / `t.singh`.
- **Hybrid retrieval + reranking**: `ai-service/retrieval.py` combines vector
  search (Chroma) with keyword search (Postgres), then reranks with a
  transparent, explainable score (keyword/vector agreement + a staleness
  penalty for `is_current=false` material) rather than a black-box
  cross-encoder. `GET /retrieval/compare?query=...` runs the naive
  vector-only baseline alongside the hybrid path on the same query so the
  lift is inspectable, not asserted.
- **Multi-hop GraphRAG**: `graph_multi_hop` walks 1–3 hops in Neo4j from a
  problem or concept node.
- **Agentic tool use**: `ai-service/agent.py` is a bounded ReAct-style loop
  against Groq (`llama-3.3-70b-versatile`) — up to `AI_MAX_TOOL_CALLS` (6)
  tool calls and a wall-clock timeout (`AI_TIMEOUT_SECONDS`, 20s), after which
  it's forced to answer from whatever evidence it already gathered rather
  than looping or hanging a request.
- **Grounding & access control**: every tool enforces ownership/role checks
  itself (see `tools.py`) — hidden test I/O, other learners' source code, and
  instructor-only fields never reach the model in the first place, so the
  system prompt's instructions are a second layer, not the only one.
- **Cost/fallback**: no `GROQ_API_KEY` or a timeout returns a clear
  `ai_unavailable` response; the contest platform (submissions, judging,
  leaderboard) lives in a separate service and is unaffected.

## Reliability & security (Stage 4)

- **Idempotency**: `(user_id, problem_id, client_submission_key)` is a unique
  constraint — a retried submit request returns the existing row instead of
  double-queuing a judge job. The internal verdict endpoint also checks
  current status before applying a verdict, so a retried/duplicated worker
  job can't double-apply.
- **Recovery demonstrated**: if the judge-worker crashes mid-job or the
  Docker sandbox errors, the submission is marked `infra_error` (never a
  wrong verdict) and the worker retries with backoff up to 3 times before
  giving up cleanly.
- **Access control**: role stored in the JWT; `RolesGuard` for
  instructor-only routes, and ownership checks in `SubmissionsService` —
  a learner requesting another learner's submission gets a 403 (this is the
  verified unauthorized-access case in `smoke_test.sh`).
- **Diagnostic visibility**: every submission carries `judge_image_version`,
  timestamps, and `error_detail`; every AI answer carries its evidence log.

## Known limitations / scope cuts (given the overnight timeline)

- Only Python and JavaScript are judged (two Docker base images); adding a
  compiled language mainly means adding a compile step before `run_submission`.
- The reranker is a simple transparent heuristic, not a trained cross-encoder
  — documented as a deliberate trade-off, not an oversight.
- No WebSocket/live-push; frontend polls submissions and the leaderboard.
  Straightforward to swap for SSE/WebSockets from `backend-api` later.
- RBAC is enforced at the two most security-relevant edges (submission
  ownership, instructor-only contest creation) rather than exhaustively on
  every field; the pattern (`RolesGuard` + per-query ownership check)
  generalizes directly to the rest.
- No distributed tracing/dashboards — timestamps + `judge_image_version` +
  the AI evidence log are the "basic timing/diagnostic" bar the spec asks for.
- Test suite is the focused set the spec asks for (normal flow, recovery,
  access check, a handful of AI Q&A), not a comprehensive benchmark.

## AI-assisted development

This codebase was scaffolded with heavy AI assistance under a tight deadline.
Verification approach: schema and access-control logic were hand-reviewed
line-by-line (these are the highest-consequence areas — a wrong verdict or a
data leak is worse than a missing feature); the sandbox/worker retry logic
was traced manually against the failure modes in the spec; the AI-service
tool contracts were designed first (as the access boundary), with the agent
loop built around them rather than the reverse. `docs/EVALUATION.md` records
expected vs. actual behavior for the test cases actually run.

## Time spent

Single overnight session. Roughly: schema + backend-api (~2h), judge-worker
sandbox (~1.5h), ai-service + agent loop (~2h), frontend (~1h), seed data +
docs/tests (~1h).
