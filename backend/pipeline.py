"""The Learn with Spark pipeline (B6).

Now the GRAPH decides where to go next. After the guardrail runs, a "router" function looks at
the result and picks the next step: if the idea is safe we finish; if it's flagged unsafe we go
to a `blocked` node and stop instead of building. This is control flow — the path is not fixed,
it depends on the state.

    research --> pick_idea_gate (PAUSE) --> guardrail --+--(safe)----> END
                                                        +--(unsafe)--> blocked --> END
"""

import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node
    chosen_idea: dict[str, Any]  # the one the human picks at the gate
    guardrail_result: dict[str, Any]  # filled in by the guardrail node
    halted_reason: str  # set if the run is stopped early (e.g. blocked by the guardrail)


# 2. A NODE — a function (state) -> partial update. LangGraph merges the returned dict
#    back into the state for you.
def research_node(state: State) -> dict:
    """Pretend research agent. In B7 this will call a real model; for now it returns fakes."""
    concept = state.get("concept", "")
    print(f"[research] thinking up ideas for: {concept!r}")
    return {
        "idea_options": [
            {"id": "idea_a", "summary": f"Teach '{concept}' by sorting cards into two columns"},
            {"id": "idea_b", "summary": f"Teach '{concept}' with a multiple-choice quiz"},
        ]
    }


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
