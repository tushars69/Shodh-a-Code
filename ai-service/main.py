from fastapi import FastAPI
from pydantic import BaseModel
from agent import ask, AiUnavailableError
from retrieval import compare_retrieval

app = FastAPI(title="Shodh-a-Code AI Service")


class AskRequest(BaseModel):
    question: str
    requester_role: str  # 'learner' | 'instructor' | 'admin'
    requester_user_id: str
    org_id: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    try:
        return ask(req.question, req.requester_role, req.requester_user_id, req.org_id)
    except AiUnavailableError as e:
        # Stage 4 "cost & fallback" requirement: a timed-out or unconfigured AI
        # service degrades to a clear, honest message -- the contest platform
        # itself (submissions, judging, leaderboard) is entirely unaffected by
        # this failure since it lives in a separate service.
        return {
            "answer": None,
            "error": "ai_unavailable",
            "detail": str(e),
            "evidence": [],
        }


@app.get("/retrieval/compare")
def retrieval_compare(query: str, concept_id: str = None):
    return compare_retrieval(query, concept_id)
