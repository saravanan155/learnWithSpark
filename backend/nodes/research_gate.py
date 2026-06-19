"""The research gate: a human pause to accept / edit / regenerate / abandon the ideas, + its router."""

from langgraph.types import interrupt

from state import State

# How many sets of ideas a human may reject before the gate stops offering "regenerate". This caps
# the research loop so a never-satisfied admin can't spin it forever (cf. B11's max-3 repair loop).
MAX_RESEARCH_ATTEMPTS = 3


# THE HUMAN GATE — this node PAUSES the graph. `interrupt(payload)` stops execution and sends
# `payload` out to whoever is running the graph. Nothing past this point runs until we resume
# with a value (see run.py). On resume, that value becomes the return of `interrupt()`.
#
# The human now has four moves, not one:
#   - accept    -> proceed with the chosen idea
#   - edit      -> tweak the chosen idea's fields, then proceed
#   - regenerate-> reject them all and loop back to research for a fresh set (until the cap)
#   - abandon   -> nothing fits; stop cleanly (no idea chosen) so the admin can start fresh
def pick_idea_gate(state: State) -> dict:
    """Pause for a human to accept, edit, regenerate, or abandon the researched ideas."""
    ideas = state.get("idea_options", [])
    attempt = state.get("research_attempts", 1)
    can_regenerate = attempt < MAX_RESEARCH_ATTEMPTS
    decision = interrupt({
        "question": "Which idea should we build?",
        "options": ideas,
        "attempt": attempt,
        "max_attempts": MAX_RESEARCH_ATTEMPTS,
        "can_regenerate": can_regenerate,  # the UI hides "regenerate" once this is False
    }) or {}
    action = decision.get("action")

    # Give up — a clean exit when nothing fits (always available, even on the first set).
    if action == "abandon":
        print(f"[gate] human abandoned the ideas (attempt {attempt}) — no idea chosen")
        return {"abandoned": True}

    # Reject everything and ask for a fresh batch — only honored while under the cap.
    if action == "regenerate" and can_regenerate:
        print(f"[gate] human rejected all ideas (attempt {attempt}) — regenerating")
        return {"regenerate": True}

    # Otherwise accept one idea (optionally replacing it with a fully edited LessonSpec).
    chosen_id = decision.get("chosen_id")
    chosen = next((i for i in ideas if i["id"] == chosen_id), ideas[0] if ideas else {})
    edited_idea = decision.get("edited_idea")
    if isinstance(edited_idea, dict):
        chosen = dict(edited_idea)
        chosen.setdefault("id", chosen_id or (ideas[0]["id"] if ideas else "idea_a"))
        print(f"[gate] human edited full LessonSpec for idea {chosen.get('id')!r}")
        return {"chosen_idea": chosen, "regenerate": False}

    # Backward-compatible path for the CLI's --edit FIELD=VALUE pairs.
    edits = decision.get("edits") or {}
    if edits:
        chosen = {**chosen, **edits}  # human's edits win over the model's text
        print(f"[gate] human edited idea {chosen.get('id')!r}: changed {', '.join(edits)}")
    print(f"[gate] human accepted idea {chosen.get('id')!r}")
    return {"chosen_idea": chosen, "regenerate": False}


# THE RESEARCH-GATE ROUTER — abandon stops the run, regenerate loops back to research, anything
# else moves on to the guardrail. This control-flow decision makes the gate more than a rubber stamp.
def route_after_pick(state: State) -> str:
    if state.get("abandoned"):
        return "abandoned"  # gave up -> clean stop
    if state.get("regenerate"):
        return "research"  # rejected all -> fresh ideas
    return "guardrail"  # accepted (or edited) -> safety check
