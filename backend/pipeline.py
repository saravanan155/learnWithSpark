"""The Learn with Spark pipeline (B9).

THREE agents are now real and on different providers — a genuine multi-agent system. Research and
the guardrail run on Nebius; the new CODING agent runs on Claude (Anthropic) and turns the approved
idea into a self-contained HTML game (as text). The coding step only ever runs on an idea a human
endorsed at both gates. Every model call falls back to a stub if its key is missing, so the graph
never crashes.

                 +---------------- regenerate (while attempts < cap) ----------------+
                 v                                                                    |
    research (Nebius) --> pick_idea_gate (PAUSE) --accept/edit--> guardrail (Nebius) --> safety_gate (PAUSE) --+
                                |                                                                               |
                              abandon                            (rejected)--> blocked --> END   (approved)--> coding (Claude) --> END
                                v
                            abandoned --> END
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from llm import claude_model, get_claude, get_nebius, has_anthropic, has_nebius


# 1. STATE — a dictionary with known keys. `total=False` means every key is optional,
#    so each node only has to return the parts it changed.
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
# missing or anything goes wrong, it falls back to stub ideas instead of crashing. The graph can
# loop back here when the human rejects every idea, so it counts its attempts (the regenerate cap).
def research_node(state: State) -> dict:
    """Real research agent: asks Nebius for kid-lesson ideas (stub fallback on any failure)."""
    concept = state.get("concept", "")
    attempt = state.get("research_attempts", 0) + 1  # 1 on the first run, +1 each regenerate
    if not has_nebius():
        print(f"[research] attempt {attempt}: no NEBIUS_API_KEY — using stub ideas for {concept!r}")
        ideas = _stub_ideas(concept)
    else:
        try:
            print(f"[research] attempt {attempt}: asking Nebius for ideas about {concept!r} ...")
            reply = get_nebius().invoke(RESEARCH_PROMPT.format(concept=concept))
            ideas = _parse_ideas(reply.content)
            print(f"[research] Nebius returned {len(ideas)} idea(s)")
        except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
            print(f"[research] Nebius call failed ({exc}); using stub ideas")
            ideas = _stub_ideas(concept)
    return {"idea_options": ideas, "research_attempts": attempt, "regenerate": False}


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

    # Otherwise accept one idea (optionally with edits applied on top).
    chosen_id = decision.get("chosen_id")
    chosen = next((i for i in ideas if i["id"] == chosen_id), ideas[0] if ideas else {})
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


# THE ROUTER — a plain function that returns the NAME of the next node based on state.
# This is the control-flow decision: the graph isn't on rails, it chooses. The human's approval
# at the safety gate is what decides — it can override the model either way.
def route_after_safety(state: State) -> str:
    if (state.get("approval") or {}).get("approved"):
        return "coding"  # approved -> hand the idea to the coding agent
    return "blocked"  # rejected -> the dead-end


# THE CODING AGENT — the THIRD agent, and the first on Claude (Anthropic). It turns the approved
# idea into a single self-contained HTML game (returned as text — we don't run it yet). Like the
# other agents it degrades to a stub if its key is missing, so the graph still completes.
CODING_SYSTEM = (
    "You are a senior front-end engineer who builds tiny, self-contained educational web games "
    "for young children (ages 7+). You write clean, modern, dependency-free HTML/CSS/JavaScript "
    "that runs by simply opening one .html file in a browser — no build step, no external "
    "libraries, no network calls."
)

CODING_PROMPT = """Build a playable kids' game level from this approved idea (JSON):

{idea}

Requirements:
- ONE self-contained HTML file: all CSS and JavaScript inline, no external resources, works offline.
- Implement the idea's "mechanic" faithfully and use the "example_round" content as the first round.
- Big friendly controls, cheerful kid-safe colors, minimal reading. Encouraging, gentle feedback
  for both right and wrong answers (never scary or punishing).
- Keep it to a single short level a 7-year-old can finish in a minute.

Output ONLY the HTML file contents, starting with <!DOCTYPE html>. No markdown fences, no commentary."""


def _strip_code_fences(text: str) -> str:
    """Drop ```html / ``` fences if the model wrapped the file in a code block."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text  # drop the opening ``` line
        text = text.removesuffix("```").strip()
    return text


def _stub_code(idea: dict) -> str:
    """Fallback game code when no Anthropic key is set, so the graph still finishes."""
    title = idea.get("title", "Spark's Game")
    summary = idea.get("summary", "")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'><title>"
        f"{title}</title></head>\n<body style='font-family:sans-serif;text-align:center'>\n"
        f"<h1>{title}</h1>\n<p>{summary}</p>\n"
        "<p><em>(Placeholder — set ANTHROPIC_API_KEY to have Claude build the real game.)</em></p>\n"
        "</body></html>\n"
    )


def coding_node(state: State) -> dict:
    """Real coding agent: asks Claude to build the game (stub fallback on any failure)."""
    idea = state.get("chosen_idea") or {}
    if not has_anthropic():
        print("[coding] no ANTHROPIC_API_KEY — using stub game code")
        return {"game_code": _stub_code(idea)}
    try:
        print(f"[coding] asking Claude to build idea {idea.get('id')!r} ...")
        # Stream + adaptive thinking: code is long, so streaming avoids request timeouts and the
        # model decides how much to reason. We keep only the text blocks (thinking blocks are empty).
        with get_claude().messages.stream(
            model=claude_model(),
            max_tokens=24000,
            system=CODING_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": CODING_PROMPT.format(idea=_idea_for_review(idea))}],
        ) as stream:
            reply = stream.get_final_message()
        code = _strip_code_fences("".join(b.text for b in reply.content if b.type == "text"))
        print(f"[coding] Claude returned {len(code)} chars of game code")
        return {"game_code": code}
    except Exception as exc:  # network error, refusal, etc. -> degrade gracefully
        print(f"[coding] Claude call failed ({exc}); using stub game code")
        return {"game_code": _stub_code(idea)}


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
    g.add_node("coding", coding_node)
    g.add_node("abandoned", abandoned_node)
    g.add_node("blocked", blocked_node)
    g.add_edge(START, "research")  # start -> research
    g.add_edge("research", "pick_idea_gate")  # research -> human pause
    # The research gate branches: abandon -> stop, regenerate -> back to research, else -> guardrail.
    g.add_conditional_edges("pick_idea_gate", route_after_pick, ["research", "guardrail", "abandoned"])
    g.add_edge("guardrail", "safety_gate")  # verdict -> second human pause
    # The conditional edge: the router reads the human's approval -> coding (Claude) or blocked.
    g.add_conditional_edges("safety_gate", route_after_safety, ["coding", "blocked"])
    g.add_edge("coding", END)  # built the game -> done
    g.add_edge("abandoned", END)  # abandoned -> done (stopped, no idea chosen)
    g.add_edge("blocked", END)  # blocked -> done (stopped)
    return g.compile(checkpointer=checkpointer)
