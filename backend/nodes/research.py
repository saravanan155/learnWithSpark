"""The research agent (Nebius): invents kid-friendly lesson ideas for a concept."""

import json

from llm import get_nebius, has_nebius
from state import State

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
