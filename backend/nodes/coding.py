"""The coding agent (Claude): turns the approved idea into a self-contained HTML game.

Interim: per PLAN.md the output realigns to a React GameLevel.tsx (component contract + Sandpack)
in a later batch — for now it emits a single standalone HTML file.
"""

from llm import claude_model, get_claude, has_anthropic
from state import State, idea_to_json

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
            messages=[{"role": "user", "content": CODING_PROMPT.format(idea=idea_to_json(idea))}],
        ) as stream:
            reply = stream.get_final_message()
        code = _strip_code_fences("".join(b.text for b in reply.content if b.type == "text"))
        print(f"[coding] Claude returned {len(code)} chars of game code")
        return {"game_code": code}
    except Exception as exc:  # network error, refusal, etc. -> degrade gracefully
        print(f"[coding] Claude call failed ({exc}); using stub game code")
        return {"game_code": _stub_code(idea)}
