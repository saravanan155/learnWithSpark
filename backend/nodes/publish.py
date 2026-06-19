"""Gate 3 (play-test) + publish (B13).

The human play-tests the built level and approves/rejects; on approval a gated WRITE publishes it
to the versioned level store. This is the "write actions deserve a human" theme made concrete.
"""

from langgraph.graph import END
from langgraph.types import interrupt

from frontend_levels import publish_to_frontend_level
from levels_db import publish_level
from state import State


# GATE 3 — the THIRD human pause: play-test the built level before it goes live.
def play_test_node(state: State) -> dict:
    """Pause for the human to play-test the built level and approve/reject publishing."""
    code = state.get("game_code", "") or ""
    decision = interrupt(
        {"question": "Play-test the built level — publish it?", "stage": "play_test", "code_chars": len(code)}
    )
    approved = bool((decision or {}).get("approved"))
    print(f"[play_test] human {'APPROVED' if approved else 'REJECTED'} the built level")
    out: dict = {"play_test_approved": approved}
    if not approved:
        out["halted_reason"] = "level rejected by the human at the play-test gate"
    return out


def route_after_play_test(state: State) -> str:
    return "publish" if state.get("play_test_approved") else END


def publish_node(state: State) -> dict:
    """WRITE (gated): publish the approved level and append it to the learner game."""
    spec = state.get("chosen_idea") or {}
    code = state.get("game_code", "") or ""
    rec = publish_level(spec, code)
    frontend_rec = publish_to_frontend_level(spec, code)
    print(f"[publish] {rec['level_id']} v{rec['version']} is now {rec['status']}")
    print(f"[publish] added frontend lesson {frontend_rec['lesson_number']}: {frontend_rec['title']}")
    return {"published": {**rec, "frontend_lesson": frontend_rec}}
