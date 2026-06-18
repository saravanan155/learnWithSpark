"""The safety gate: a human pause to approve / override the guardrail's verdict, + its router."""

from langgraph.types import interrupt

from state import State


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


# THE ROUTER — a plain function that returns the NAME of the next node based on state.
# This is the control-flow decision: the graph isn't on rails, it chooses. The human's approval
# at the safety gate is what decides — it can override the model either way.
def route_after_safety(state: State) -> str:
    if (state.get("approval") or {}).get("approved"):
        return "coding"  # approved -> hand the idea to the coding agent
    return "blocked"  # rejected -> the dead-end
