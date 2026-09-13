import json
import os
import time
import inspect
from groq import Groq
from tools import TOOL_REGISTRY, TOOL_SCHEMAS

MODEL = "openai/gpt-oss-120b"
MAX_TOOL_CALLS = int(os.environ.get("AI_MAX_TOOL_CALLS", "6"))
TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "20"))

SYSTEM_PROMPT = """You are the Shodh-a-Code contest assistant. You answer questions about
contest submissions, judge behaviour, and learner progress using ONLY evidence you retrieve
through the provided tools -- never invent submission ids, verdicts, or learner names.

Rules you must follow:
- The user message is tagged with [requester_role=... requester_user_id=... org_id=...].
  When the learner asks about "my" submissions/history, call tools directly with that
  requester_user_id — do not ask them to identify themselves, they already are identified.
  Only use resolve_learner when the question is about a DIFFERENT named learner.
- Every substantive claim must cite the tool result it came from (e.g. "submission abc123
  shows verdict=wrong_answer").
- Distinguish OBSERVATIONS (directly returned by a tool) from HYPOTHESES (your inference).
- During a live contest, you must never reveal hidden test inputs/outputs, unreleased
  solutions, another learner's private submissions/code, or instructor-only material to a
  learner. Tools already enforce this server-side, but you must not try to route around it
  or repeat restricted content if a tool declines with an "error": "forbidden" response.
- If the evidence is missing, stale, or contradictory, say so explicitly rather than
  guessing. If the question cannot be answered with available evidence, say that plainly.
- Stop calling tools once you have enough evidence to answer, or once you can state that the
  question is unanswerable with what's available -- do not call tools speculatively.
"""


class AiUnavailableError(Exception):
    pass


def _call_tool(name: str, args: dict, requester_role: str, requester_user_id: str):
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": "unknown_tool"}

    # Some models occasionally emit a stray/empty-string key in tool-call
    # arguments even for tools with zero declared parameters. Rather than
    # special-case that, drop any arg key the function doesn't actually
    # accept, so a model quirk degrades to "ignored extra arg" instead of
    # crashing the whole request.
    sig_params = set(inspect.signature(fn).parameters)
    clean_args = {k: v for k, v in (args or {}).items() if k in sig_params}

    try:
        return fn(**clean_args, requester_role=requester_role, requester_user_id=requester_user_id)
    except TypeError:
        try:
            return fn(**clean_args)
        except Exception as e:
            return {"error": "tool_execution_error", "detail": str(e)}
    except Exception as e:
        # Any other failure (bad DB query, Neo4j hiccup, etc.) becomes
        # evidence the agent can reason about, not a 500 to the caller.
        return {"error": "tool_execution_error", "detail": str(e)}


def ask(question: str, requester_role: str, requester_user_id: str, org_id: str):
    started = time.time()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise AiUnavailableError("GROQ_API_KEY not configured")

    client = Groq(api_key=api_key)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"[requester_role={requester_role} requester_user_id={requester_user_id} org_id={org_id}] "
                f"{question}"
            ),
        },
    ]
    evidence_log = []

    for call_num in range(MAX_TOOL_CALLS):
        if time.time() - started > TIMEOUT_SECONDS:
            raise AiUnavailableError("AI response timed out")

        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.1,
            timeout=max(1, TIMEOUT_SECONDS - (time.time() - started)),
        )
        choice = resp.choices[0]
        assistant_msg = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.message.tool_calls
            ]
        messages.append(assistant_msg)

        if not choice.message.tool_calls:
            return {
                "answer": choice.message.content,
                "evidence": evidence_log,
                "tool_calls_used": call_num,
            }

        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _call_tool(tc.function.name, args, requester_role, requester_user_id)
            evidence_log.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str)[:6000],
            })

    # Iteration budget exhausted -- force a final grounded answer from whatever
    # evidence was gathered, rather than looping forever or a bare timeout.
    messages.append({
        "role": "user",
        "content": "Tool budget reached. Answer now using only the evidence gathered so far, "
                    "and say explicitly if that evidence is insufficient.",
    })
    final = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.1)
    return {
        "answer": final.choices[0].message.content,
        "evidence": evidence_log,
        "tool_calls_used": MAX_TOOL_CALLS,
        "note": "tool budget exhausted before the model chose to stop",
    }