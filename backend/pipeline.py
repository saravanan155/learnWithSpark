"""The Learn with Spark pipeline (B3).

We now have TWO nodes: research, then guardrail. The point of B3 is to see how data flows
between nodes — the guardrail node READS the idea_options that the research node WROTE. Neither
node knows about the other; they only share the State. There is still NO LLM.

    research --(writes idea_options)--> guardrail --(reads them, writes guardrail_result)--> END
"""

from typing import Any, TypedDict

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


# THE GRAPH — now two nodes in a row, so state flows research -> guardrail.
def build_graph():
    g = StateGraph(State)
    g.add_node("research", research_node)
    g.add_node("guardrail", guardrail_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "guardrail")  # research -> guardrail (data flows here)
    g.add_edge("guardrail", END)  # guardrail -> done
    return g.compile()
