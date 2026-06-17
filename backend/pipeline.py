"""The Learn with Spark pipeline (B4).

Same two nodes as B3 (research -> guardrail), but now the graph has a CHECKPOINTER. A
checkpointer saves the State to a SQLite file after every step, keyed by a `thread_id`. That
means the state is durable: a completely separate process can read it back later. This is the
foundation for both "resume after a restart" and the human pauses we add in B5.

    research --> guardrail --> END   (and every step is saved to checkpoints.sqlite)
"""

import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node
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


# A SECOND NODE — the guardrail. It READS the ideas the research node put in state and
# checks them. For now it's a stub: it always says they're safe. (In B8 it calls a real model.)
def guardrail_node(state: State) -> dict:
    """Pretend safety check. Reads idea_options from state; in B8 this calls a real model."""
    ideas = state.get("idea_options", [])
    print(f"[guardrail] checking {len(ideas)} idea(s) for kid-safety")
    return {
        "guardrail_result": {
            "safe": True,
            "checked": len(ideas),
            "notes": "STUB guardrail — no real check yet",
        }
    }


# THE CHECKPOINTER — saves state to a SQLite file so it survives across processes/restarts.
DB_PATH = Path(__file__).resolve().parent / "checkpoints.sqlite"


def make_checkpointer(db_path: Path | str = DB_PATH) -> SqliteSaver:
    # check_same_thread=False lets the one connection be reused across LangGraph's calls.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


# THE GRAPH — two nodes in a row, plus an optional checkpointer.
# Passing a checkpointer is what makes the run resumable and durable.
def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("research", research_node)
    g.add_node("guardrail", guardrail_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "guardrail")  # research -> guardrail (data flows here)
    g.add_edge("guardrail", END)  # guardrail -> done
    return g.compile(checkpointer=checkpointer)
