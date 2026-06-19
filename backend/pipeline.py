"""The Learn with Spark graph (B11) — wiring only.

The agents, gates, and dead-ends each live in their own module under `nodes/`; this file just
imports them and assembles the LangGraph, plus the SQLite checkpointer. Research + guardrail run on
Nebius, coding on Claude, and the testing agent uses deterministic checks + a Nebius judge. Every
model call falls back to a stub if its key is missing, so the graph never crashes.

                 +---------------- regenerate (while attempts < cap) ----------------+
                 v                                                                    |
    research (Nebius) --> pick_idea_gate (PAUSE) --accept/edit--> guardrail (Nebius) --> safety_gate (PAUSE) --+
                                |                                                                               |
                              abandon              (rejected)--> blocked --> END                               |
                                v                  (approved)--> coding (Claude) --> static_check --> test --> END
                            abandoned --> END
"""

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from nodes.coding import coding_node
from nodes.guardrail import guardrail_node
from nodes.research import research_node
from nodes.research_gate import pick_idea_gate, route_after_pick
from nodes.safety_gate import route_after_safety, safety_gate
from nodes.terminals import abandoned_node, blocked_node
from nodes.testing import static_check_node, test_node
from state import State


# THE CHECKPOINTER — saves state to a SQLite file so it survives across processes/restarts.
DB_PATH = Path(__file__).resolve().parent / "checkpoints.sqlite"


def make_checkpointer(db_path: Path | str = DB_PATH) -> SqliteSaver:
    # check_same_thread=False lets the one connection be reused across LangGraph's calls.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


# THE GRAPH — research, the human pick gate, guardrail, the human safety gate, then coding.
# A checkpointer is REQUIRED for the gates' interrupts to work (they need somewhere to save the
# paused state), so build_graph expects one for B5 onward.
def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("research", research_node)
    g.add_node("pick_idea_gate", pick_idea_gate)
    g.add_node("guardrail", guardrail_node)
    g.add_node("safety_gate", safety_gate)
    g.add_node("coding", coding_node)
    g.add_node("static_check", static_check_node)
    g.add_node("test", test_node)
    g.add_node("abandoned", abandoned_node)
    g.add_node("blocked", blocked_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    # The research gate branches: abandon -> stop, regenerate -> back to research, else -> guardrail.
    g.add_conditional_edges("pick_idea_gate", route_after_pick, ["research", "guardrail", "abandoned"])
    g.add_edge("guardrail", "safety_gate")  # verdict -> second human pause
    # The conditional edge: the router reads the human's approval -> coding (Claude) or blocked.
    g.add_conditional_edges("safety_gate", route_after_safety, ["coding", "blocked"])
    g.add_edge("coding", "static_check")  # built -> deterministic checks
    g.add_edge("static_check", "test")  # checks -> quality judge
    g.add_edge("test", END)  # tested -> done (repair loop comes in B12)
    g.add_edge("abandoned", END)  # abandoned -> done (stopped, no idea chosen)
    g.add_edge("blocked", END)  # blocked -> done (stopped)
    return g.compile(checkpointer=checkpointer)
