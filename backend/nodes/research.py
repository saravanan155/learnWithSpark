"""The research agent (Nebius): drafts kid-friendly LessonSpec ideas for a concept.

Output shape = the LessonSpec the coding agent consumes (PLAN.md → "LessonSpec schema"): one of the
4 fixed mechanics, plus the items / solution / feedback / Spark moods a level needs. The model
authors the content fields; we stamp the system fields (id, version, status) in `_parse_ideas`.
"""

import json

from llm import get_nebius, has_nebius
from state import State

# The 4 mechanics the coding agent can build (PLAN.md → "Game mechanics"). Research must pick one.
MECHANICS = ["drag_drop", "multiple_choice", "match_line", "odd_one_out"]
# Spark's pre-made mascot moods (PLAN.md → "Spark mascot").
MOODS = ["curious", "proud", "confused", "excited", "unsure", "confident"]

RESEARCH_PROMPT = """You are a senior learning-game designer for "Learn with Spark", an app that
teaches children (ages 7+) how AI works. The CHILD is the teacher: they help Spark — a friendly
robot with an empty brain — understand an idea by playing one short, visual level that ends with a
small "aha!".

Given ONE AI concept, propose 2-3 genuinely different level ideas. Each must be a COMPLETE spec a
coding agent can build directly into a small React game.

THE CONCEPT TO TEACH: "{concept}"

RULES
- Teach ONE small thing and engineer a clear "aha". Lead with a concrete, everyday example. Few
  words, big visuals (an emoji per item). Feedback is kind and encouraging — never scary or punishing.
- Pick exactly ONE mechanic per idea from this FIXED set:
    "drag_drop"        — drag items onto targets, or sort them into labeled groups/columns
    "multiple_choice"  — a question with a few tappable choices
    "match_line"       — draw a line to connect items across two sides
    "odd_one_out"      — tap the item that doesn't belong
- Make the 2-3 ideas genuinely different (different mechanic and/or angle).
- Age-appropriate for 7+: no violence, weapons, fear, sexual/romantic content, drugs, politics,
  religion, gender/identity topics, brands, or anything needing an adult.

OUTPUT — reply with ONLY a JSON array (no prose, no markdown fences). Each element exactly like this:
{{
  "title": "short, catchy level name a kid would love",
  "summary": "one sentence a grown-up can skim to choose this idea",
  "concept": "the one idea this level teaches, in plain kid words (the takeaway)",
  "mechanic": "one of: drag_drop | multiple_choice | match_line | odd_one_out",
  "story": "Spark's friendly setup / narration — 1-2 short sentences",
  "prompt": "what the child must do, in one short instruction",
  "items": [
    {{"id": "item_1", "label": "apple", "imageHint": "🍎"}}
  ],
  "solution": "the correct answer(s), shaped to fit the mechanic — drag_drop: a map of item id -> target/group; multiple_choice: the correct item id; match_line: pairs of ids; odd_one_out: the odd item id",
  "feedback": {{"correct": "what Spark says when the child is right", "incorrect": "a kind nudge when wrong"}},
  "sparkMoods": {{"start": "one of: {moods}", "won": "one of: {moods}"}},
  "ageTier": "kid"
}}

Use 3-6 REAL items (actual labels + a single emoji each), never placeholders like "item 1" or URLs.
Output the JSON array only."""


def _stub_ideas(concept: str) -> list[dict]:
    """Fallback ideas (no Nebius key), shaped like a LessonSpec so the gate + coding agent agree."""
    return [
        {
            "id": "idea_a",
            "title": "Sort It Out",
            "summary": f"Teach '{concept}' by sorting cards into two groups",
            "concept": concept,
            "mechanic": "drag_drop",
            "story": "Spark wants to learn! Help it put things in the right place.",
            "prompt": "Drag each card into the group it belongs to.",
            "items": [
                {"id": "item_1", "label": "apple", "imageHint": "🍎"},
                {"id": "item_2", "label": "ball", "imageHint": "⚽"},
            ],
            "solution": {"item_1": "group_a", "item_2": "group_b"},
            "feedback": {"correct": "Yes! You taught me that!", "incorrect": "Hmm, try another group!"},
            "sparkMoods": {"start": "curious", "won": "proud"},
            "ageTier": "kid",
        },
        {
            "id": "idea_b",
            "title": "Quick Quiz",
            "summary": f"Teach '{concept}' with a tap-the-answer quiz",
            "concept": concept,
            "mechanic": "multiple_choice",
            "story": "Spark has a question for you!",
            "prompt": "Tap the right answer.",
            "items": [
                {"id": "item_1", "label": "yes", "imageHint": "✅"},
                {"id": "item_2", "label": "no", "imageHint": "❌"},
            ],
            "solution": "item_1",
            "feedback": {"correct": "Great pick!", "incorrect": "Not quite — try again!"},
            "sparkMoods": {"start": "curious", "won": "excited"},
            "ageTier": "kid",
        },
    ]


def _parse_ideas(text: str) -> list[dict]:
    """Pull the JSON array out of the model's reply and finish each into a LessonSpec: stamp the
    system fields (id, version, status), default ageTier, and guarantee the fields the gate needs
    (title, summary). Stays tolerant of a missing field so a parseable-but-imperfect reply runs."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)  # a list of LessonSpec-shaped objects (see RESEARCH_PROMPT)
    ideas = []
    for i, item in enumerate(raw):
        idea = dict(item)
        idea["id"] = f"idea_{chr(97 + i)}"  # our id wins even if the model invented one
        idea.setdefault("version", 1)
        idea.setdefault("status", "draft")
        idea.setdefault("ageTier", "kid")
        idea.setdefault("summary", idea.get("title", "untitled idea"))  # gate/guardrail need this
        ideas.append(idea)
    return ideas


# THE RESEARCH NODE — a real agent. It asks Nebius for LessonSpec ideas; on a missing key or any
# failure it falls back to stub ideas instead of crashing. The graph can loop back here when the
# human rejects every idea, so it counts its attempts (the regenerate cap).
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
            prompt = RESEARCH_PROMPT.format(concept=concept, moods="|".join(MOODS))
            reply = get_nebius().invoke(prompt)
            ideas = _parse_ideas(reply.content)
            print(f"[research] Nebius returned {len(ideas)} idea(s)")
        except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
            print(f"[research] Nebius call failed ({exc}); using stub ideas")
            ideas = _stub_ideas(concept)
    return {"idea_options": ideas, "research_attempts": attempt, "regenerate": False}
