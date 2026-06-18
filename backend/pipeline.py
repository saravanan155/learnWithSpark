"""The Learn with Spark pipeline (B8).

Now TWO nodes are real agents. The guardrail joins research: it asks a model whether the chosen
idea is safe for kids (returning a verdict + reason), and then a SECOND human gate lets a person
approve or override that verdict before we'd build anything. Both real calls fall back to stubs
if Nebius is unreachable, so the graph never crashes.

    research (Nebius) --> pick_idea_gate (PAUSE) --> guardrail (Nebius) --> safety_gate (PAUSE) --+
                                                                                                  |
                                                          (approved)--> END    (rejected)--> blocked --> END
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from llm import get_nebius, has_nebius


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
class State(TypedDict, total=False):
    concept: str  # what we want to teach, e.g. "knowledge cutoff"
    idea_options: list[dict[str, Any]]  # filled in by the research node
    chosen_idea: dict[str, Any]  # the one the human picks at the gate
    guardrail_result: dict[str, Any]  # the guardrail agent's verdict: {safe, reason, idea}
    approval: dict[str, Any]  # the human's call at the safety gate: {approved: bool}
    halted_reason: str  # set if the run is stopped early (e.g. blocked by the guardrail)


RESEARCH_PROMPT = """You are a senior learning-game designer for "Learn with Spark", an app that
teaches children (ages 7 and up) how AI works. The twist that makes the game work: the CHILD is
the teacher. They help Spark — a friendly robot who starts with an empty brain — understand an
idea by playing one short, visual level. A great level leaves the child with a small "aha!" about
how AI really thinks.

Your job: given ONE AI concept, invent 2-3 genuinely different level ideas that a coding agent
can actually build. Think hard about what would truly click for a 7-year-old.

THE CONCEPT TO TEACH: "{concept}"

DESIGN PRINCIPLES — every idea must honor all of these:
- Teach ONE small thing well. A level is bite-sized, not a lecture. If this concept is big or has
  several parts, do NOT cram it all in. Pick the single most important slice for a first, basic
  level, set "is_multi_part" to true, and list the remaining parts in "suggested_next_levels" so
  they can each become their own level later. (The teacher can generate a basic level now, then
  come back for the sub-concepts.)
- Lead with a feeling, not a definition. Kids learn from one concrete, everyday example or a vivid
  analogy first (a lunchbox, a pet, sorting toys, a treasure map); the "aha" then lands on its own.
- Show, don't read. Many 7-year-olds read slowly, so lean on pictures, icons, colors, and actions.
  Keep any on-screen words short and simple.
- Be playful and kind. Mistakes are gentle and encouraging ("Spark is still learning — try
  again!"), never scary, sad, or punishing.
- Engineer a clear "aha moment" — the single realization the child walks away with.
- It MUST be buildable with exactly ONE of these simple interaction mechanics:
    "drag-and-drop"     — drag items onto targets
    "draw-a-line"       — connect or match pairs by drawing a line
    "sort-into-buckets" — drop items into labeled groups
    "tap-to-choose"     — tap the right answer (multiple choice)
    "put-in-order"      — arrange steps or items into a sequence
    "fill-the-blank"    — drop word or picture tiles into a slot
    "slider"            — move a slider to set an amount
- Make the 2-3 ideas genuinely DIFFERENT from each other — a different mechanic and/or a
  different angle on the concept, not three flavors of the same thing.

SAFETY — this is for children 7 and older. Every idea, word, example, and suggested image must be
age-appropriate: no violence, weapons, fighting, fear, blood, death, romance, politics, bias,
stereotypes, brands, or anything needing an adult's judgment. If the concept could drift somewhere
dark, find the kid-safe framing. Use vocabulary a 7-year-old understands.

OUTPUT — reply with ONLY a JSON array (no prose, no markdown fences). Each element is an object
exactly like this, to be passed straight to a coding agent:
{{
  "title": "short, catchy level name a kid would love",
  "summary": "one sentence a grown-up can skim to choose this idea",
  "teaches": "the single thing this level makes the child understand, in plain words",
  "aha_moment": "the realization the child should have by the end",
  "analogy": "a simple everyday comparison a 7-year-old already knows",
  "mechanic": "exactly one value from the mechanics list above",
  "how_to_play": ["step 1", "step 2", "step 3"],
  "example_round": {{
    "setup": "what the child sees at the start — use REAL sample content, not placeholders",
    "right_move": "the correct action and why it is right",
    "celebrate": "the friendly success moment / what Spark does when the child is correct",
    "gentle_retry": "the kind, encouraging message shown if the child misses"
  }},
  "is_multi_part": true or false,
  "suggested_next_levels": ["if is_multi_part is true, the other slices that each deserve their own level; else an empty list"],
  "why_kid_safe": "one line confirming it is appropriate for ages 7+"
}}

Use concrete, real sample content in "example_round" (actual items and labels), never placeholders
like "item 1". Output the JSON array only."""


def _stub_ideas(concept: str) -> list[dict]:
    """Fallback ideas used when no Nebius key is set, so the graph still runs. Thin on purpose,
    but shaped like the real schema so the gate and downstream code see consistent fields."""
    return [
        {
            "id": "idea_a",
            "title": "Sorting Cards",
            "summary": f"Teach '{concept}' by sorting cards into two columns",
            "mechanic": "sort-into-buckets",
            "aha_moment": f"You can understand '{concept}' by grouping examples",
        },
        {
            "id": "idea_b",
            "title": "Quick Quiz",
            "summary": f"Teach '{concept}' with a tap-to-choose quiz",
            "mechanic": "tap-to-choose",
            "aha_moment": f"You can spot '{concept}' by picking the right answer",
        },
    ]


def _parse_ideas(text: str) -> list[dict]:
    """Pull the JSON array out of the model's reply, tag each idea with an id, and keep ALL its
    fields — the full spec (mechanic, example_round, etc.) flows downstream to the coding agent.
    Stays tolerant if the model omits a field so a malformed-but-parseable reply still runs."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)  # a list of rich idea objects (see RESEARCH_PROMPT)
    ideas = []
    for i, item in enumerate(raw):
        idea = dict(item)
        idea["id"] = f"idea_{chr(97 + i)}"  # our id wins even if the model invented one
        idea.setdefault("summary", idea.get("title", "untitled idea"))  # gate/guardrail need this
        ideas.append(idea)
    return ideas


# THE RESEARCH NODE — now a real agent. It asks Nebius to invent lesson ideas. If the key is
# missing or anything goes wrong, it falls back to stub ideas instead of crashing.
def research_node(state: State) -> dict:
    """Real research agent: asks Nebius for kid-lesson ideas (stub fallback on any failure)."""
    concept = state.get("concept", "")
    if not has_nebius():
        print(f"[research] no NEBIUS_API_KEY — using stub ideas for {concept!r}")
        return {"idea_options": _stub_ideas(concept)}
    try:
        print(f"[research] asking Nebius for ideas about {concept!r} ...")
        reply = get_nebius().invoke(RESEARCH_PROMPT.format(concept=concept))
        ideas = _parse_ideas(reply.content)
        print(f"[research] Nebius returned {len(ideas)} idea(s)")
        return {"idea_options": ideas}
    except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
        print(f"[research] Nebius call failed ({exc}); using stub ideas")
        return {"idea_options": _stub_ideas(concept)}


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


# THE GUARDRAIL — the SECOND real agent. It asks a model whether the chosen idea is kid-safe and
# returns a verdict {safe, reason}. Like research, it degrades to a stub (a keyword blocklist) when
# no key is set or the call fails, so the graph keeps running.
#
# The BLOCKLIST is only the crude FALLBACK. A keyword list can't judge "is this right for a
# 7-year-old?" — that semantic call is the model's job (see GUARDRAIL_PROMPT). This is just a
# coarse net of obviously-not-for-kids words, grouped by theme; matched as WHOLE WORDS so we don't
# trip on "skill" (kill) or "begun" (gun). Extend it freely.
BLOCKLIST = [
    # violence / weapons
    "violence", "violent", "weapon", "gun", "knife", "blood", "bloody", "kill", "killing",
    "murder", "fight", "fighting", "war", "death", "dead", "hurt", "attack",
    # sexual / romance
    "sex", "sexy", "naked", "nude", "kiss", "romance", "dating",
    # substances
    "drug", "drugs", "alcohol", "beer", "wine", "smoking", "cigarette", "vape",
    # frightening
    "scary", "horror", "nightmare", "terror",
    # politics / religion / identity — topics that need an adult, not a kids' game
    "political", "politics", "election", "vote", "government",
    "religion", "religious", "god", "worship", "prayer",
    "gender", "transgender", "abortion",
    # hate / adult themes
    "hate", "racist", "racism", "suicide", "gambling", "casino",
]

GUARDRAIL_PROMPT = """You are a child-safety reviewer for "Learn with Spark", a game that teaches
children (ages 7+) how AI works. Review the ENTIRE level idea below — its title, what it teaches,
the analogy, how it is played, and especially the example round and any words shown to the child.

Flag it as UNSAFE if ANY part is inappropriate for a 7-year-old: violence, weapons, fighting,
fear, blood, death, sexual or romantic content, drugs or alcohol, politics, religion, gender or
identity topics, bias or stereotypes, scary imagery, brands, or — as a general rule — ANYTHING
you would not introduce to a child aged
7 or under, including any word or situation that needs an adult's judgment. When in doubt, flag it.

THE LEVEL IDEA (JSON):
{idea}

Reply with ONLY a JSON object: {{"safe": true or false, "reason": "one short sentence naming the
specific reason"}}. No prose, no markdown — just the JSON object."""


def _idea_for_review(idea: dict) -> str:
    """The text we hand the safety reviewer: the whole idea (minus our internal id) as JSON."""
    return json.dumps({k: v for k, v in idea.items() if k != "id"}, indent=2, ensure_ascii=False)


def _stub_verdict(idea: dict) -> dict:
    """Fallback safety check (keyword blocklist over the WHOLE idea) when the model is unavailable.
    Matches whole words only, so "skill" doesn't trip "kill"."""
    words = set(re.findall(r"[a-z]+", json.dumps(idea).lower()))
    hits = sorted(word for word in BLOCKLIST if word in words)
    reason = "no blocklisted words" if not hits else f"contains blocklisted word(s): {', '.join(hits)}"
    return {"safe": not hits, "reason": reason}


def _parse_verdict(text: str) -> dict:
    """Pull the JSON verdict out of the model's reply."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)
    return {"safe": bool(raw["safe"]), "reason": str(raw.get("reason", "")).strip()}


def guardrail_node(state: State) -> dict:
    """Real safety agent: asks Nebius if the chosen idea is kid-safe (stub fallback on failure)."""
    chosen = state.get("chosen_idea") or {}
    if not has_nebius():
        print("[guardrail] no NEBIUS_API_KEY — using stub blocklist check")
        verdict = _stub_verdict(chosen)
    else:
        try:
            print(f"[guardrail] asking Nebius to safety-check idea {chosen.get('id')!r} ...")
            reply = get_nebius(temperature=0).invoke(GUARDRAIL_PROMPT.format(idea=_idea_for_review(chosen)))
            verdict = _parse_verdict(reply.content)
        except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
            print(f"[guardrail] Nebius call failed ({exc}); using stub blocklist check")
            verdict = _stub_verdict(chosen)
    verdict["idea"] = chosen.get("id")
    print(f"[guardrail] verdict: {'safe' if verdict['safe'] else 'UNSAFE'} — {verdict['reason']}")
    return {"guardrail_result": verdict}


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


# THE BLOCKED node — the dead-end we route to when the idea isn't approved. It stops the
# pipeline instead of building something unsafe for kids.
def blocked_node(state: State) -> dict:
    print("[blocked] idea not approved for kids — stopping, not building.")
    return {"halted_reason": "idea was not approved as kid-safe at the safety gate"}


# THE ROUTER — a plain function that returns the NAME of the next node based on state.
# This is the control-flow decision: the graph isn't on rails, it chooses. The human's approval
# at the safety gate is what decides — it can override the model either way.
def route_after_safety(state: State) -> str:
    if (state.get("approval") or {}).get("approved"):
        return END  # approved -> finish
    return "blocked"  # rejected -> the dead-end


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
    g.add_node("safety_gate", safety_gate)
    g.add_node("blocked", blocked_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    g.add_edge("pick_idea_gate", "guardrail")  # (after resume) -> guardrail agent
    g.add_edge("guardrail", "safety_gate")  # verdict -> second human pause
    # The conditional edge: the router reads the human's approval -> END or blocked.
    g.add_conditional_edges("safety_gate", route_after_safety, [END, "blocked"])
    g.add_edge("blocked", END)  # blocked -> done (stopped)
    return g.compile(checkpointer=checkpointer)
