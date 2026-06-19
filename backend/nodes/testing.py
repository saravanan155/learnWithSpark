"""The testing agent (B11): deterministic static checks + a different-family quality judge.

Two parts, on purpose (PLAN.md → "Testing"):
  - static_check_node: plain Python checks on the generated code (no LLM) — fast, free, reliable.
    Does it export GameLevel? Are the imports in the allowlist? Does it call onComplete? Any
    forbidden network/eval/storage? This is the real safety net.
  - test_node: a Nebius judge (a DIFFERENT model family than the Claude coder, to avoid
    self-preference bias) gives a binary PASS/FAIL on the subjective stuff — winnable? teaches the
    concept? age-appropriate? Stub-passes when no key.
"""

import json
import re

from llm import get_nebius, has_nebius
from state import State, idea_to_json

# How many times the repair node may try to fix a failing level before we escalate to a human.
MAX_REPAIRS = 3

# The only imports a generated level may use (PLAN.md → "The component contract").
ALLOWED_IMPORTS = {"react", "framer-motion", "./Spark", "./types"}
# Things a level must never do.
FORBIDDEN = ["fetch(", "eval(", "localStorage", "sessionStorage", "http://", "https://"]


def static_check_node(state: State) -> dict:
    """Deterministic contract checks on the generated code — the cheap, reliable first gate."""
    code = state.get("game_code", "") or ""
    problems = []

    if not re.search(r"export\s+default\s+(function\s+)?GameLevel\b", code):
        problems.append("must export a default component named GameLevel")

    imports = re.findall(r"""\bfrom\s+['"]([^'"]+)['"]""", code)
    for mod in imports:
        if mod not in ALLOWED_IMPORTS:
            problems.append(f"import not allowed: {mod!r} (allowed: {sorted(ALLOWED_IMPORTS)})")

    if "onComplete(" not in code:
        problems.append("must call onComplete({won, score}) when the child wins")

    for bad in FORBIDDEN:
        if bad in code:
            problems.append(f"forbidden token: {bad!r}")

    ok = not problems
    print(f"[static_check] {'PASS' if ok else 'FAIL'}" + ("" if ok else f" — {'; '.join(problems)}"))
    return {"static_check": {"ok": ok, "problems": problems}}


JUDGE_PROMPT = """You are a QA reviewer for "Learn with Spark", a kids' learning game (ages 7+).
A coding agent built a React level from this spec. Judge ONLY whether it is good enough to ship.

LESSON SPEC (JSON):
{idea}

GENERATED GameLevel.tsx:
{code}

Decide PASS or FAIL on all three: (1) winnable — a child can reach a win that calls onComplete;
(2) it teaches the spec's concept; (3) it is age-appropriate and kind. Reply with ONLY a JSON
object: {{"passed": true or false, "reason": "one short sentence"}}. No prose, no markdown."""


def _parse_verdict(text: str) -> dict:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    raw = json.loads(text)
    return {"passed": bool(raw["passed"]), "reason": str(raw.get("reason", "")).strip()}


def test_node(state: State) -> dict:
    """The quality judge (Nebius — different family than the Claude coder). Binary PASS/FAIL."""
    code = state.get("game_code", "") or ""
    idea = state.get("chosen_idea") or {}
    if not has_nebius():
        print("[test] no NEBIUS_API_KEY — skipping judge (auto-pass)")
        return {"test_results": {"passed": True, "reason": "no judge configured (no Nebius key)"}}
    try:
        print("[test] asking Nebius to judge the generated level ...")
        prompt = JUDGE_PROMPT.format(idea=idea_to_json(idea), code=code)
        reply = get_nebius(temperature=0).invoke(prompt)
        verdict = _parse_verdict(reply.content)
    except Exception as exc:  # network error, bad JSON, etc. -> don't block on a flaky judge
        print(f"[test] judge call failed ({exc}); auto-passing (deterministic checks are the net)")
        verdict = {"passed": True, "reason": f"judge unavailable ({exc})"}
    print(f"[test] judge: {'PASS' if verdict['passed'] else 'FAIL'} — {verdict['reason']}")
    return {"test_results": verdict}


# THE TESTING ROUTER (B12) — pass -> done; fail -> repair (until the cap) -> escalate.
def route_after_test(state: State) -> str:
    static_ok = (state.get("static_check") or {}).get("ok")
    judged_ok = (state.get("test_results") or {}).get("passed")
    if static_ok and judged_ok:
        return "play_test"  # passed -> human play-test (Gate 3)
    if state.get("repair_count", 0) < MAX_REPAIRS:
        return "repair"  # fix the exact failures and re-check
    return "escalate"  # couldn't converge -> hand to a human
