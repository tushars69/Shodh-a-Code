"""
Seeds a small, reproducible dataset with the specific messiness Stage 3 asks
for: inconsistent learner names, a judge-version incident mid-contest, and
both current and superseded learning material. Run with:

    docker compose run --rm seed

Idempotent-ish: re-running against a fresh `docker compose up` (empty
volumes) is the supported path; it does not attempt to dedupe against a
partially-seeded database.
"""
import os
import uuid
import time
import psycopg2
from neo4j import GraphDatabase
import chromadb

PG_DSN = os.environ["DATABASE_URL"]
NEO4J_URI = os.environ["NEO4J_URI"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
CHROMA_HOST = os.environ["CHROMA_HOST"]
CHROMA_PORT = int(os.environ["CHROMA_PORT"])


def wait_for_pg(conn_str, attempts=20):
    for i in range(attempts):
        try:
            c = psycopg2.connect(conn_str)
            c.close()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("Postgres never became ready")


def main():
    wait_for_pg(PG_DSN)
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()

    org_id = str(uuid.uuid4())
    cur.execute("INSERT INTO organizations (id, name) VALUES (%s, %s)", (org_id, "NIE Test Org"))

    # --- Users: includes deliberately inconsistent names for the same two
    # underlying people, to force entity resolution rather than exact match.
    instructor_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, org_id, username, display_name, password_hash, role) VALUES (%s,%s,%s,%s,%s,'instructor')",
        (instructor_id, org_id, "instructor1", "Dr. A. Rao", "x"),
    )

    learners = [
        ("tushar_singh", "Tushar Singh"),
        ("t.singh", "T. Singh"),          # same person as above, inconsistent handle
        ("priya_k", "Priya K"),
        ("priyak2", "Priya K."),          # same person as above
        ("dev_r", "Dev R"),
    ]
    learner_ids = {}
    for username, display_name in learners:
        uid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO users (id, org_id, username, display_name, password_hash, role) VALUES (%s,%s,%s,%s,%s,'learner')",
            (uid, org_id, username, display_name, "x"),
        )
        learner_ids[username] = uid

    contest_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO contests (id, org_id, title, starts_at, ends_at, hint_policy) VALUES (%s,%s,%s, now() - interval '1 hour', now() + interval '2 hour', 'no_hints_during_contest')",
        (contest_id, org_id, "Weekly Contest #1"),
    )

    # --- Problems: one gets a hidden-until-instructor flag, one is at v2
    # (v1 superseded), to exercise "outdated problem" reasoning.
    problems = [
        {
            "slug": "two-sum",
            "title": "Two Sum",
            "statement_md": "Given a list of integers and a target, print indices i j (i<j) such that a[i]+a[j]==target.",
            "points": 100,
            "version": 1,
            "tests": [("2 7 11 15\n9", "0 1", True), ("3 2 4\n6", "1 2", False)],
        },
        {
            "slug": "reverse-string",
            "title": "Reverse a String",
            "statement_md": "Print the reverse of the input string.",
            "points": 100,
            "version": 2,  # v2: judge-visible correction after a v1 wording bug
            "tests": [("hello", "olleh", True), ("racecar", "racecar", False)],
        },
        {
            "slug": "prime-check",
            "title": "Prime Check",
            "statement_md": "Print YES if the input integer is prime, else NO.",
            "points": 100,
            "version": 1,
            "tests": [("7", "YES", True), ("10", "NO", False)],
        },
    ]
    problem_ids = {}
    for p in problems:
        pid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO problems (id, contest_id, slug, title, statement_md, points, version) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (pid, contest_id, p["slug"], p["title"], p["statement_md"], p["points"], p["version"]),
        )
        problem_ids[p["slug"]] = pid
        for inp, out, is_sample in p["tests"]:
            cur.execute(
                "INSERT INTO test_cases (id, problem_id, input, expected_output, is_sample) VALUES (%s,%s,%s,%s,%s)",
                (str(uuid.uuid4()), pid, inp, out, is_sample),
            )

    # --- Judge incident: a version bump mid-contest that broke `reverse-string`
    # for a window of time — the evidence an AI answer should surface when
    # asked "did a judge change affect outcomes".
    cur.execute(
        "INSERT INTO judge_incidents (judge_image_version, description, affected_language, occurred_at, resolved_at) "
        "VALUES (%s,%s,%s, now() - interval '40 minutes', now() - interval '25 minutes')",
        ("judge-v0.9", "Node runtime image briefly had a stdin buffering bug causing false runtime_errors", "javascript"),
    )

    # --- Submissions: tushar_singh and t.singh (same real person, different
    # accounts) both fail on problems that share the same "off-by-one /
    # indexing" prerequisite concept, despite different problems/verdicts.
    def add_submission(username, slug, verdict, score, status="completed", judge_version="judge-v1.0"):
        sid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO submissions (id, problem_id, user_id, contest_id, language, source_code,
               client_submission_key, status, verdict, score, judge_image_version, judged_at)
               VALUES (%s,%s,%s,%s,'python','# seeded submission',%s,%s,%s,%s,%s, now())""",
            (sid, problem_ids[slug], learner_ids[username], contest_id, str(uuid.uuid4()), status, verdict, score, judge_version),
        )
        return sid

    add_submission("tushar_singh", "two-sum", "wrong_answer", 0)
    add_submission("t.singh", "prime-check", "wrong_answer", 0)  # different problem, same underlying gap
    add_submission("priya_k", "reverse-string", "runtime_error", 0, judge_version="judge-v0.9")  # infra-affected window
    add_submission("priyak2", "reverse-string", "accepted", 100, judge_version="judge-v1.0")  # after fix
    add_submission("dev_r", "two-sum", "accepted", 100)

    # --- Learning material: current + one deliberately superseded version, so
    # the AI must flag staleness rather than treat both as equally valid.
    cur.execute(
        "INSERT INTO learning_materials (topic, title, body_md, version, is_current) VALUES (%s,%s,%s,1,false)",
        ("indexing", "Array Indexing Basics (old)", "Arrays start at index 1 in most languages."),  # wrong/outdated on purpose
    )
    cur.execute(
        "INSERT INTO learning_materials (topic, title, body_md, version, is_current) VALUES (%s,%s,%s,2,true)",
        ("indexing", "Array Indexing Basics", "Arrays start at index 0 in Python, JavaScript, and most C-family languages. Off-by-one errors usually come from looping one index too far."),
    )
    cur.execute(
        "INSERT INTO learning_materials (topic, title, body_md, version, is_current) VALUES (%s,%s,%s,1,true)",
        ("primality", "Checking Primality Efficiently", "A number n is prime if it has no divisors other than 1 and itself; only check divisors up to sqrt(n)."),
    )

    cur.close()
    conn.close()
    print("[seed] Postgres seeded.")

    # --- Neo4j: concept graph connecting problems -> concepts -> learners who
    # struggled with them, enabling the multi-hop "shared prerequisite gap" query.
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        session.run(
            """
            CREATE (c1:Concept {id:'concept-indexing', name:'Array Indexing / Off-by-one'})
            CREATE (c2:Concept {id:'concept-primality', name:'Primality Testing'})
            CREATE (p1:Problem {id:$two_sum, name:'Two Sum'})
            CREATE (p2:Problem {id:$prime_check, name:'Prime Check'})
            CREATE (l1:Learner {id:$tushar, name:'Tushar Singh (canonical)'})
            CREATE (l2:Learner {id:$priya, name:'Priya K (canonical)'})
            CREATE (p1)-[:REQUIRES]->(c1)
            CREATE (p2)-[:REQUIRES]->(c1)
            CREATE (p2)-[:REQUIRES]->(c2)
            CREATE (l1)-[:STRUGGLES_WITH]->(c1)
            """,
            two_sum=problem_ids["two-sum"],
            prime_check=problem_ids["prime-check"],
            tushar=learner_ids["tushar_singh"],
            priya=learner_ids["priya_k"],
        )
    driver.close()
    print("[seed] Neo4j seeded.")

    # --- Chroma: vector index over the same learning material (current only,
    # by convention — stale material is kept queryable via Postgres keyword
    # search for the hybrid-retrieval comparison, not duplicated into vectors).
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    coll = client.get_or_create_collection(name="learning_materials")
    coll.add(
        ids=["indexing-v2", "primality-v1"],
        documents=[
            "Arrays start at index 0 in Python, JavaScript, and most C-family languages. Off-by-one errors usually come from looping one index too far.",
            "A number n is prime if it has no divisors other than 1 and itself; only check divisors up to sqrt(n).",
        ],
        metadatas=[
            {"topic": "indexing", "is_current": True, "version": 2},
            {"topic": "primality", "is_current": True, "version": 1},
        ],
    )
    print("[seed] Chroma seeded.")

    print(f"\nContest ID: {contest_id}")
    print(f"Org ID: {org_id}")
    print("Sample learners to join with: tushar_singh, t.singh, priya_k, priyak2, dev_r")


if __name__ == "__main__":
    main()
