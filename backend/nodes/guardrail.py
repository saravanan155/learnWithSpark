"""The guardrail agent (Nebius): checks whether the chosen idea is kid-safe."""

import json
import re

from llm import get_nebius, has_nebius
from state import State, idea_to_json

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
            reply = get_nebius(temperature=0).invoke(GUARDRAIL_PROMPT.format(idea=idea_to_json(chosen)))
            verdict = _parse_verdict(reply.content)
        except Exception as exc:  # network error, bad JSON, etc. -> degrade gracefully
            print(f"[guardrail] Nebius call failed ({exc}); using stub blocklist check")
            verdict = _stub_verdict(chosen)
    verdict["idea"] = chosen.get("id")
    print(f"[guardrail] verdict: {'safe' if verdict['safe'] else 'UNSAFE'} — {verdict['reason']}")
    return {"guardrail_result": verdict}
