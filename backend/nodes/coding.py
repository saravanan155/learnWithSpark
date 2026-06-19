"""The coding agent (Claude): turns the approved LessonSpec into a React GameLevel.tsx.

It builds the React component the frontend/Sandpack will render. To pin quality it feeds Claude the
real artifacts from the frontend at runtime (single source of truth): the component contract
(types.ts) and the hand-built Lesson 1 worked example. Output obeys the contract: one default
GameLevel({ onComplete, onProgress }), importing only react + framer-motion + <Spark>. Falls back
to a tiny stub component if no Anthropic key, so the graph still completes.
"""

from pathlib import Path

from llm import claude_model, get_claude, has_anthropic
from state import State, idea_to_json

# The frontend artifacts we feed the model (read at runtime so they never drift from the real code).
_GAME_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "game"
_CONTRACT_FILE = _GAME_DIR / "types.ts"
_WORKED_EXAMPLE_FILE = _GAME_DIR / "levels" / "lesson1-see.tsx"

CODING_SYSTEM = (
    "You are a senior front-end engineer who builds tiny, delightful, accessible educational web "
    "games for young children (ages 7+) in React + TypeScript, styled with Tailwind classes and "
    "animated with Framer Motion. You write one self-contained component that runs inside a sandbox "
    "— no build config, no extra libraries, no network."
)

# The non-negotiable rails (PLAN.md → "The component contract"), stated verbatim in the prompt.
CODING_RAILS = """RAILS — obey ALL of these exactly:
- Export ONE default component named `GameLevel` with the signature `GameLevel({ onComplete, onProgress }: GameLevelProps)`.
- Import ONLY: `react`, `framer-motion`, the mascot `import { Spark } from "./Spark"`, and
  `import type { GameLevelProps, SparkMood } from "./types"`. Nothing else. Tailwind via className.
- NO network/fetch, NO external asset URLs, NO localStorage/sessionStorage, NO eval.
- Render Spark ONLY via `<Spark mood="..." />`. Show `sparkMoods.start` on load and `sparkMoods.won` on a win.
- Implement the LessonSpec's `mechanic` faithfully, using its `items` and `solution`. Use each item's
  `imageHint` emoji as its visual. Show `feedback.correct` / `feedback.incorrect` appropriately.
- MUST be keyboard-accessible AND work on touch (e.g. items are draggable buttons that also respond to click/Enter).
- MUST call `onComplete({ won: true, score })` when the child wins. Optionally call `onProgress(step)`.
- Self-contained: all state via React hooks; all data inline from the spec. Kind, encouraging, kid-friendly copy."""

CODING_PROMPT = """Build a playable React game level from this approved LessonSpec.

=== THE CONTRACT (types.ts the component must satisfy) ===
{contract}

{rails}

=== WORKED EXAMPLE (a hand-built level that follows the contract — match its shape and quality) ===
{worked_example}

=== THE LESSON SPEC TO BUILD (JSON) ===
{idea}

Output ONLY the contents of GameLevel.tsx — start with the import lines, end with the component.
No markdown fences, no commentary."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _strip_code_fences(text: str) -> str:
    """Drop ```tsx / ``` fences if the model wrapped the file in a code block."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text  # drop the opening ``` line
        text = text.removesuffix("```").strip()
    return text


def _stub_code(idea: dict) -> str:
    """Fallback React level when no Anthropic key is set — a tiny but contract-shaped GameLevel."""
    title = idea.get("title", "Spark's Game")
    prompt = idea.get("prompt", "Tap the button to win!")
    start = (idea.get("sparkMoods") or {}).get("start", "curious")
    won = (idea.get("sparkMoods") or {}).get("won", "proud")
    return (
        'import { useState } from "react";\n'
        'import { Spark } from "./Spark";\n'
        'import type { GameLevelProps, SparkMood } from "./types";\n\n'
        "// Placeholder level — set ANTHROPIC_API_KEY to have Claude build the real game.\n"
        "export default function GameLevel({ onComplete }: GameLevelProps) {\n"
        f'  const [mood, setMood] = useState<SparkMood>("{start}");\n'
        "  return (\n"
        '    <div className="flex flex-col items-center gap-4 p-6 text-center">\n'
        '      <Spark mood={mood} className="h-28 w-28" />\n'
        f"      <h1 className=\"text-2xl font-bold\">{title}</h1>\n"
        f"      <p className=\"text-slate-600\">{prompt}</p>\n"
        "      <button\n"
        '        className="rounded-2xl bg-sky-500 px-6 py-3 text-white"\n'
        f'        onClick={{() => {{ setMood("{won}"); onComplete({{ won: true, score: 1 }}); }}}}\n'
        "      >\n"
        "        Win\n"
        "      </button>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )


def coding_node(state: State) -> dict:
    """Real coding agent: asks Claude to build the React GameLevel.tsx (stub fallback on failure)."""
    idea = state.get("chosen_idea") or {}
    if not has_anthropic():
        print("[coding] no ANTHROPIC_API_KEY — using stub React level")
        return {"game_code": _stub_code(idea)}
    try:
        print(f"[coding] asking Claude to build React level for idea {idea.get('id')!r} ...")
        prompt = CODING_PROMPT.format(
            contract=_read(_CONTRACT_FILE),
            rails=CODING_RAILS,
            worked_example=_read(_WORKED_EXAMPLE_FILE),
            idea=idea_to_json(idea),
        )
        # Stream + adaptive thinking: code is long, so streaming avoids request timeouts and the
        # model decides how much to reason. We keep only the text blocks (thinking blocks are empty).
        with get_claude().messages.stream(
            model=claude_model(),
            max_tokens=24000,
            system=CODING_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            reply = stream.get_final_message()
        code = _strip_code_fences("".join(b.text for b in reply.content if b.type == "text"))
        print(f"[coding] Claude returned {len(code)} chars of GameLevel.tsx")
        return {"game_code": code}
    except Exception as exc:  # network error, refusal, etc. -> degrade gracefully
        print(f"[coding] Claude call failed ({exc}); using stub React level")
        return {"game_code": _stub_code(idea)}


# THE REPAIR NODE (B12) — the same Claude agent fixing its own output. When the testing agent fails
# the level, we feed Claude the EXACT failures + the current code and ask for a fix. The specific
# error feedback is what makes the loop converge instead of flailing; a counter caps the attempts.
REPAIR_PROMPT = """The GameLevel.tsx you wrote failed review. Fix it so it passes — keep everything
that already works and change only what's needed.

FAILURES TO FIX:
{failures}

CURRENT CODE:
{code}

{rails}

LESSON SPEC (JSON):
{idea}

Output ONLY the corrected GameLevel.tsx — start with the imports, no markdown fences, no commentary."""


def _failures(state: State) -> list[str]:
    """Collect the exact problems from the static check + the quality judge."""
    problems = list((state.get("static_check") or {}).get("problems") or [])
    test = state.get("test_results") or {}
    if not test.get("passed", True):
        problems.append(f"quality judge said FAIL: {test.get('reason', 'not good enough')}")
    return problems


def repair_node(state: State) -> dict:
    """Ask Claude to fix the failing level, feeding back the exact errors (stub: leaves code as-is)."""
    code = state.get("game_code", "") or ""
    idea = state.get("chosen_idea") or {}
    problems = _failures(state)
    count = state.get("repair_count", 0) + 1
    log = list(state.get("error_log") or [])
    log.append(f"attempt {count}: {'; '.join(problems) or '(unspecified)'}")
    if not has_anthropic():
        print(f"[repair] attempt {count}: no ANTHROPIC_API_KEY — cannot fix (will escalate)")
        return {"repair_count": count, "error_log": log}
    try:
        print(f"[repair] attempt {count}: asking Claude to fix {len(problems)} problem(s) ...")
        prompt = REPAIR_PROMPT.format(
            failures="\n".join(f"- {p}" for p in problems) or "- (unspecified)",
            code=code,
            rails=CODING_RAILS,
            idea=idea_to_json(idea),
        )
        with get_claude().messages.stream(
            model=claude_model(),
            max_tokens=24000,
            system=CODING_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            reply = stream.get_final_message()
        fixed = _strip_code_fences("".join(b.text for b in reply.content if b.type == "text"))
        print(f"[repair] Claude returned {len(fixed)} chars")
        return {"game_code": fixed, "repair_count": count, "error_log": log}
    except Exception as exc:  # don't crash the loop on a flaky call — re-check / escalate
        print(f"[repair] fix failed ({exc}); will re-check / escalate")
        return {"repair_count": count, "error_log": log}
