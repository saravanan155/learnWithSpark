"""The Learn with Spark pipeline (B5).

Now there's a HUMAN PAUSE between research and guardrail. The new pick_idea_gate node calls
`interrupt()`, which stops the whole graph and hands the ideas out to a person. The graph only
continues when we resume it with the person's choice. This is "human-in-the-loop": the agent
does not decide which idea to build — a human does.

    research --> pick_idea_gate (PAUSE for a human) --> guardrail --> END

The pause relies on the checkpointer from B4: the graph saves itself, the program can even exit,
and we resume later with the saved choice.
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


# THE GUARDRAIL — now checks only the CHOSEN idea (cheaper than checking all of them, and it's
# the one that matters). Still a stub. (In B8 it calls a real model.)
def guardrail_node(state: State) -> dict:
    """Pretend safety check on the chosen idea. In B8 this calls a real model."""
    chosen = state.get("chosen_idea") or {}
    print(f"[guardrail] checking chosen idea {chosen.get('id')!r} for kid-safety")
    return {
        "guardrail_result": {
            "safe": True,
            "idea": chosen.get("id"),
            "notes": "STUB guardrail — no real check yet",
        }
    }


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
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    g.add_edge("pick_idea_gate", "guardrail")  # (after resume) -> guardrail
    g.add_edge("guardrail", END)  # guardrail -> done
    return g.compile(checkpointer=checkpointer)
