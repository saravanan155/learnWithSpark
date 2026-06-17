"""The Learn with Spark pipeline (B2).

Right now this is the smallest possible graph: a State and ONE node. The node pretends to be a
research agent — it just returns a couple of fake lesson ideas. There is NO LLM yet. The whole
point of B2 is to see the three core pieces clearly, with nothing else in the way:

    1. State   — the data the graph carries from step to step.
    2. A node  — a plain Python function that reads state and returns an update to it.
    3. A graph — wires the node between START and END so we can run it.
"""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node


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


# 3. THE GRAPH — declare the node and the order it runs in, then compile.
def build_graph():
    g = StateGraph(State)
    g.add_node("research", research_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", END)  # research -> done
    return g.compile()
