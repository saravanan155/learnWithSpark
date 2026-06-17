"""The Learn with Spark pipeline (B7).

The research node is now a REAL agent: it asks a model (Nebius Token Factory) to invent
kid-friendly lesson ideas, instead of returning hard-coded fakes. Everything else (the human
gate, guardrail, routing, checkpointing) is unchanged. If no Nebius key is configured, research
falls back to the old stub ideas so the graph still runs — an early taste of error handling.

    research (Nebius) --> pick_idea_gate (PAUSE) --> guardrail --+--(safe)----> END
                                                                 +--(unsafe)--> blocked --> END
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
    guardrail_result: dict[str, Any]  # filled in by the guardrail node
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


# THE GUARDRAIL — checks the chosen idea and returns a verdict (safe or not). Still a stub:
# it just flags the concept if it contains an obviously kid-unsafe word. (In B8: a real model.)
BLOCKLIST = ["violence", "weapon", "scary", "gun"]


def guardrail_node(state: State) -> dict:
    """Pretend safety check on the chosen idea. In B8 this calls a real model."""
    chosen = state.get("chosen_idea") or {}
    concept = state.get("concept", "").lower()
    safe = not any(word in concept for word in BLOCKLIST)
    print(f"[guardrail] chosen idea {chosen.get('id')!r} -> {'safe' if safe else 'UNSAFE'}")
    return {"guardrail_result": {"safe": safe, "idea": chosen.get("id")}}


# THE BLOCKED node — the dead-end we route to when the guardrail flags the idea. It stops the
# pipeline instead of building something unsafe for kids.
def blocked_node(state: State) -> dict:
    print("[blocked] idea flagged unsafe for kids — stopping, not building.")
    return {"halted_reason": "guardrail flagged the concept as not kid-safe"}


# THE ROUTER — a plain function that returns the NAME of the next node based on state.
# This is the control-flow decision: the graph isn't on rails, it chooses.
def route_after_guardrail(state: State) -> str:
    if (state.get("guardrail_result") or {}).get("safe"):
        return END  # safe -> finish
    return "blocked"  # unsafe -> the dead-end


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
    g.add_node("blocked", blocked_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    g.add_edge("pick_idea_gate", "guardrail")  # (after resume) -> guardrail
    # The conditional edge: the router decides safe -> END or unsafe -> blocked.
    g.add_conditional_edges("guardrail", route_after_guardrail, [END, "blocked"])
    g.add_edge("blocked", END)  # blocked -> done (stopped)
    return g.compile(checkpointer=checkpointer)
