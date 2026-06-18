"""Shared data: the graph's `State` shape + a tiny helper to render an idea for a prompt.

Every node reads/writes this `State` (a plain dict with known keys). Keeping it in one place means
the nodes never have to import each other just to agree on the data contract.
"""

import json
from typing import Any, TypedDict


# THE STATE — a dictionary with known keys. `total=False` means every key is optional, so each
# node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node
    research_attempts: int  # how many times research has run (the regenerate cap counts these)
    regenerate: bool  # set by the gate: True = the human rejected all ideas, loop back to research
    abandoned: bool  # set by the gate: True = the human gave up at the research gate, stop cleanly
    chosen_idea: dict[str, Any]  # the one the human accepts (possibly edited) at the gate
    guardrail_result: dict[str, Any]  # the guardrail agent's verdict: {safe, reason, idea}
    approval: dict[str, Any]  # the human's call at the safety gate: {approved: bool}
    game_code: str  # the coding agent's output: a self-contained HTML game (text)
    halted_reason: str  # set if the run is stopped early (e.g. blocked by the guardrail)


def idea_to_json(idea: dict) -> str:
    """Render an idea as pretty JSON for a model prompt (drops our internal id).

    Shared by the guardrail (what it reviews) and the coding agent (its build brief)."""
    return json.dumps({k: v for k, v in idea.items() if k != "id"}, indent=2, ensure_ascii=False)
