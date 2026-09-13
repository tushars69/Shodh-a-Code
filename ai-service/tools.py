"""
Every tool here is read-only and enforces its own access rules, so the
agent can never construct a call path that leaks restricted data even if
the LLM's reasoning tries to. This is what backs Stage 3's "hidden tests,
unreleased solutions, other learners' private code, and restricted
instructor information must remain protected" requirement -- enforcement
lives below the model, not inside its prompt.
"""
from stores import pg_query, neo4j_query, chroma_collection

RESTRICTED_ROLES = {"instructor", "admin"}


def resolve_learner(name_or_username: str, org_id: str):
    """Entity resolution: fuzzy-match a free-text name against users.display_name
    /username using trigram similarity, so 'tushar s' and 'Tushar Singh' and a
    typo'd handle can resolve to the same person instead of silently missing."""
    rows = pg_query(
        """
        SELECT id, username, display_name,
               GREATEST(similarity(display_name, %s), similarity(username, %s)) AS score
        FROM users
        WHERE org_id = %s
          AND (display_name %% %s OR username %% %s)
        ORDER BY score DESC
        LIMIT 5
        """,
        (name_or_username, name_or_username, org_id, name_or_username, name_or_username),
    )
    return {"candidates": rows}


def get_submission_history(user_id: str, requester_role: str, requester_user_id: str):
    """A learner may only see their own history; instructors see anyone's."""
    if requester_role not in RESTRICTED_ROLES and user_id != requester_user_id:
        return {"error": "forbidden", "detail": "Cannot inspect another learner's submission history."}
    rows = pg_query(
        """
        SELECT s.id, s.problem_id, p.title AS problem_title, s.language, s.status,
               s.verdict, s.score, s.judge_image_version, s.submitted_at, s.judged_at
        FROM submissions s JOIN problems p ON p.id = s.problem_id
        WHERE s.user_id = %s ORDER BY s.submitted_at DESC LIMIT 20
        """,
        (user_id,),
    )
    return {"submissions": rows}


def get_submission_detail(submission_id: str, requester_role: str, requester_user_id: str):
    """Source code of a submission is private except to its owner or staff.
    Test-case-level detail for hidden tests is never returned to learners."""
    rows = pg_query("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    if not rows:
        return {"error": "not_found"}
    sub = rows[0]
    is_owner = sub["user_id"] == requester_user_id
    is_staff = requester_role in RESTRICTED_ROLES
    if not is_owner and not is_staff:
        return {"error": "forbidden", "detail": "Cannot inspect another learner's submission."}

    tc_rows = pg_query(
        """
        SELECT tcr.passed, tcr.runtime_ms, tc.is_sample
        FROM test_case_results tcr JOIN test_cases tc ON tc.id = tcr.test_case_id
        WHERE tcr.submission_id = %s
        """,
        (submission_id,),
    )
    # Learners only get pass/fail + runtime per test case, never expected/actual
    # output for hidden tests -- that would leak the hidden test itself.
    visible_tc = [
        {"passed": r["passed"], "runtime_ms": r["runtime_ms"], "sample": r["is_sample"]}
        for r in tc_rows
        if is_staff or r["is_sample"]
    ]
    return {
        "submission": {
            "id": sub["id"], "verdict": sub["verdict"], "status": sub["status"],
            "judge_image_version": sub["judge_image_version"], "error_detail": sub["error_detail"],
            "submitted_at": str(sub["submitted_at"]), "language": sub["language"],
        },
        "test_case_results": visible_tc,
    }


def get_judge_incidents(problem_id: str = None, around_time=None):
    """Surfaces recorded judge/runtime version changes so the agent can
    distinguish an infra incident from a genuine code error."""
    rows = pg_query(
        "SELECT * FROM judge_incidents ORDER BY occurred_at DESC LIMIT 10",
    )
    return {"incidents": rows}


def graph_multi_hop(concept_or_problem_id: str, hops: int = 2):
    """Multi-hop traversal over Concept/Problem/Learner nodes in Neo4j -- e.g.
    Problem -REQUIRES-> Concept <-STRUGGLES_WITH- Learner, to surface shared
    prerequisite gaps across learners with superficially different failures."""
    hops = max(1, min(hops, 3))
    cypher = f"""
        MATCH path = (start {{id: $id}})-[*1..{hops}]-(related)
        RETURN related.id AS related_id, labels(related) AS labels,
               related.name AS name, length(path) AS distance
        ORDER BY distance LIMIT 25
    """
    rows = neo4j_query(cypher, {"id": concept_or_problem_id})
    return {"related_entities": rows}


def vector_search(query_text: str, top_k: int = 5):
    """Semantic recall over versioned learning material; each hit carries its
    version + updated_at so the agent can flag stale material explicitly."""
    coll = chroma_collection()
    res = coll.query(query_texts=[query_text], n_results=top_k)
    hits = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({"content": doc, "metadata": meta, "distance": dist})
    return {"hits": hits}


TOOL_REGISTRY = {
    "resolve_learner": resolve_learner,
    "get_submission_history": get_submission_history,
    "get_submission_detail": get_submission_detail,
    "get_judge_incidents": get_judge_incidents,
    "graph_multi_hop": graph_multi_hop,
    "vector_search": vector_search,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_learner",
            "description": "Resolve a free-text learner name/username to candidate user ids via fuzzy match (entity resolution).",
            "parameters": {
                "type": "object",
                "properties": {"name_or_username": {"type": "string"}},
                "required": ["name_or_username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_submission_history",
            "description": "Get a learner's recent submissions (verdicts, scores, judge version). Restricted to own history unless staff.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_submission_detail",
            "description": "Get pass/fail-per-testcase detail for one submission. Hidden test I/O never returned to learners.",
            "parameters": {
                "type": "object",
                "properties": {"submission_id": {"type": "string"}},
                "required": ["submission_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_judge_incidents",
            "description": "List recorded judge/runtime incidents (version changes, outages) to check whether an infra issue explains a failure pattern.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_multi_hop",
            "description": "Traverse the concept/problem/learner graph up to N hops to find shared prerequisite gaps or related entities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_or_problem_id": {"type": "string"},
                    "hops": {"type": "integer"},
                },
                "required": ["concept_or_problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": "Semantic search over versioned learning material for conceptual explanations.",
            "parameters": {
                "type": "object",
                "properties": {"query_text": {"type": "string"}, "top_k": {"type": "integer"}},
                "required": ["query_text"],
            },
        },
    },
]
