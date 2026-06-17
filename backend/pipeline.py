"""The Learn with Spark pipeline (B8).

Now TWO nodes are real agents. The guardrail joins research: it asks a model whether the chosen
idea is safe for kids (returning a verdict + reason), and then a SECOND human gate lets a person
approve or override that verdict before we'd build anything. Both real calls fall back to stubs
if Nebius is unreachable, so the graph never crashes.

    research (Nebius) --> pick_idea_gate (PAUSE) --> guardrail (Nebius) --> safety_gate (PAUSE) --+
                                                                                                  |
                                                          (approved)--> END    (rejected)--> blocked --> END
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from llm import get_nebius, has_nebius


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node
    chosen_idea: dict[str, Any]  # the one the human picks at the gate
    guardrail_result: dict[str, Any]  # the guardrail agent's verdict: {safe, reason, idea}
    approval: dict[str, Any]  # the human's call at the safety gate: {approved: bool}
    halted_reason: str  # set if the run is stopped early (e.g. blocked by the guardrail)


RESEARCH_PROMPT = """You are a curriculum designer for a game that teaches kids how AI works.
The teacher wants to teach this concept: "{concept}".

Propose 2-3 short, kid-friendly game-lesson ideas for it. Reply with ONLY a JSON array, where
each item is an object like {{"summary": "one sentence describing the game idea"}}.
No prose, no markdown — just the JSON array."""


def _stub_ideas(concept: str) -> list[dict]:
    """Fallback ideas used when no Nebius key is set, so the graph still runs."""
    return [
        {"id": "idea_a", "summary": f"Teach '{concept}' by sorting cards into two columns"},
        {"id": "idea_b", "summary": f"Teach '{concept}' with a multiple-choice quiz"},
    ]


def _parse_ideas(text: str) -> list[dict]:
    """Pull the JSON array out of the model's reply and tag each idea with an id."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)  # a list of {"summary": ...}
    return [{"id": f"idea_{chr(97 + i)}", "summary": item["summary"]} for i, item in enumerate(raw)]


# THE RESEARCH NODE — now a real agent. It asks Nebius to invent lesson ideas. If the key is
# missing or anything goes wrong, it falls back to stub ideas instead of crashing.
def research_node(state: State) -> dict:
    """Real research agent: asks Nebius for kid-lesson ideas (stub fallback on any failure)."""
    concept = state.get("concept", "")
    if not has_nebius():
        print(f"[research] no NEBIUS_API_KEY — using stub ideas for {concept!r}")
        return {"idea_options": _stub_ideas(concept)}
    try:
        print(f"[research] asking Nebius for ideas about {concept!r} ...")
        reply = get_nebius().invoke(RESEARCH_PROMPT.format(concept=concept))
        ideas = _parse_ideas(reply.content)
        print(f"[research] Nebius returned {len(ideas)} idea(s)")
        return {"idea_options": ideas}
    except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
        print(f"[research] Nebius call failed ({exc}); using stub ideas")
        return {"idea_options": _stub_ideas(concept)}


# THE HUMAN GATE — this node PAUSES the graph. `interrupt(payload)` stops execution and sends
# `payload` out to whoever is running the graph. Nothing past this point runs until we resume
# with a value (see run.py). On resume, that value becomes the return of `interrupt()`.
def pick_idea_gate(state: State) -> dict:
    """Stop and wait for a human to choose which researched idea to build."""
    ideas = state.get("idea_options", [])
    decision = interrupt({"question": "Which idea should we build?", "options": ideas})
    # `decision` is whatever we resumed with, e.g. {"chosen_id": "idea_a"}.
    chosen_id = (decision or {}).get("chosen_id")
    chosen = next((i for i in ideas if i["id"] == chosen_id), ideas[0] if ideas else {})
    print(f"[gate] human picked {chosen.get('id')!r}")
    return {"chosen_idea": chosen}


# THE GUARDRAIL — the SECOND real agent. It asks a model whether the chosen idea is kid-safe and
# returns a verdict {safe, reason}. Like research, it degrades to a stub (a tiny word blocklist)
# when no key is set or the call fails, so the graph keeps running.
BLOCKLIST = ["violence", "weapon", "scary", "gun"]

GUARDRAIL_PROMPT = """You are a child-safety reviewer for a game that teaches kids about AI.
Decide whether this game-lesson idea is appropriate and safe for children (roughly ages 7-12):

"{idea}"

Reply with ONLY a JSON object: {{"safe": true or false, "reason": "one short sentence"}}.
No prose, no markdown — just the JSON object."""


def _stub_verdict(concept: str) -> dict:
    """Fallback safety check (keyword blocklist) used when the model is unavailable."""
    safe = not any(word in concept.lower() for word in BLOCKLIST)
    reason = "no blocklisted words" if safe else "concept contains a kid-unsafe word"
    return {"safe": safe, "reason": reason}


def _parse_verdict(text: str) -> dict:
    """Pull the JSON verdict out of the model's reply."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)
    return {"safe": bool(raw["safe"]), "reason": str(raw.get("reason", "")).strip()}


def guardrail_node(state: State) -> dict:
    """Real safety agent: asks Nebius if the chosen idea is kid-safe (stub fallback on failure)."""
    chosen = state.get("chosen_idea") or {}
    summary = chosen.get("summary", "")
    if not has_nebius():
        print("[guardrail] no NEBIUS_API_KEY — using stub blocklist check")
        verdict = _stub_verdict(state.get("concept", ""))
    else:
        try:
            print(f"[guardrail] asking Nebius to safety-check idea {chosen.get('id')!r} ...")
            reply = get_nebius(temperature=0).invoke(GUARDRAIL_PROMPT.format(idea=summary))
            verdict = _parse_verdict(reply.content)
        except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
            print(f"[guardrail] Nebius call failed ({exc}); using stub blocklist check")
            verdict = _stub_verdict(state.get("concept", ""))
    verdict["idea"] = chosen.get("id")
    print(f"[guardrail] verdict: {'safe' if verdict['safe'] else 'UNSAFE'} — {verdict['reason']}")
    return {"guardrail_result": verdict}


# THE SAFETY GATE — the SECOND human-in-the-loop pause. The model only RECOMMENDS; a person makes
# the final call on whether an idea is safe enough to build for kids. They can approve the model's
# verdict or override it. On resume, the value we resume with becomes `decision`.
def safety_gate(state: State) -> dict:
    """Stop and wait for a human to approve (or override) the guardrail's safety verdict."""
    verdict = state.get("guardrail_result") or {}
    decision = interrupt({"question": "Approve this idea for kids?", "verdict": verdict})
    approved = bool((decision or {}).get("approved"))
    print(f"[safety_gate] human {'APPROVED' if approved else 'REJECTED'} idea {verdict.get('idea')!r}")
    return {"approval": {"approved": approved}}


# THE BLOCKED node — the dead-end we route to when the idea isn't approved. It stops the
# pipeline instead of building something unsafe for kids.
def blocked_node(state: State) -> dict:
    print("[blocked] idea not approved for kids — stopping, not building.")
    return {"halted_reason": "idea was not approved as kid-safe at the safety gate"}


# THE ROUTER — a plain function that returns the NAME of the next node based on state.
# This is the control-flow decision: the graph isn't on rails, it chooses. The human's approval
# at the safety gate is what decides — it can override the model either way.
def route_after_safety(state: State) -> str:
    if (state.get("approval") or {}).get("approved"):
        return END  # approved -> finish
    return "blocked"  # rejected -> the dead-end


# THE CHECKPOINTER — saves state to a SQLite file so it survives across processes/restarts.
DB_PATH = Path(__file__).resolve().parent / "checkpoints.sqlite"


def make_checkpointer(db_path: Path | str = DB_PATH) -> SqliteSaver:
    # check_same_thread=False lets the one connection be reused across LangGraph's calls.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


# THE GRAPH — research, then the human gate, then guardrail.
# A checkpointer is REQUIRED for the gate's interrupt to work (it needs somewhere to save the
# paused state), so build_graph expects one for B5 onward.
def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("research", research_node)
    g.add_node("pick_idea_gate", pick_idea_gate)
    g.add_node("guardrail", guardrail_node)
    g.add_node("safety_gate", safety_gate)
    g.add_node("blocked", blocked_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    g.add_edge("pick_idea_gate", "guardrail")  # (after resume) -> guardrail agent
    g.add_edge("guardrail", "safety_gate")  # verdict -> second human pause
    # The conditional edge: the router reads the human's approval -> END or blocked.
    g.add_conditional_edges("safety_gate", route_after_safety, [END, "blocked"])
    g.add_edge("blocked", END)  # blocked -> done (stopped)
    return g.compile(checkpointer=checkpointer)
