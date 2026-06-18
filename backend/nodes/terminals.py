"""Terminal dead-ends: abandoned (gave up at the research gate) and blocked (failed safety)."""

from state import State


# THE ABANDONED node — the dead-end we route to when the human gives up at the research gate.
# A clean stop with no idea chosen, so the admin can start a fresh run with a new concept.
def abandoned_node(state: State) -> dict:
    print("[abandoned] admin didn't like any idea — stopping. Start fresh with a new run.")
    return {"halted_reason": "admin abandoned the ideas at the research gate (none chosen)"}


# THE BLOCKED node — the dead-end we route to when the idea isn't approved. It stops the
# pipeline instead of building something unsafe for kids.
def blocked_node(state: State) -> dict:
    print("[blocked] idea not approved for kids — stopping, not building.")
    return {"halted_reason": "idea was not approved as kid-safe at the safety gate"}
