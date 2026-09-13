"""
Three stores, three jobs (Stage 3 "distinct roles" requirement):

  Postgres  -> source of truth. Submissions, verdicts, timestamps, judge
              incidents. Anything the AI claims as fact should be traceable
              back to a row here.
  Neo4j     -> relationships. Learner -> Submission -> Problem -> Concept ->
              Prerequisite edges. This is what makes "which learners share a
              prerequisite gap despite different failed submissions" answerable
              at all -- a pure vector or SQL lookup can't traverse that.
  Chroma    -> semantic recall over unstructured learning material and past
              explanations, for "what should I review" style grounding.
"""
import os
import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase
import chromadb

_pg_conn = None


def pg():
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        _pg_conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return _pg_conn


def pg_query(sql: str, params: tuple = ()):
    conn = pg()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


_neo4j_driver = None


def neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
    return _neo4j_driver


def neo4j_query(cypher: str, params: dict = None):
    with neo4j_driver().session() as session:
        result = session.run(cypher, params or {})
        return [dict(r) for r in result]


_chroma_client = None


def chroma_collection():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(
            host=os.environ["CHROMA_HOST"], port=int(os.environ["CHROMA_PORT"])
        )
    return _chroma_client.get_or_create_collection(name="learning_materials")
