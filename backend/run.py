"""Run the pipeline, which PAUSES THREE TIMES for a human (B13).

The graph stops at three gates: first the research gate (accept / edit / regenerate an idea), then
the safety gate (approve the guardrail's verdict), then the play-test gate (approve the publish
WRITE). Each `invoke` runs until the next pause (returning an "__interrupt__") or until the end, so
we just loop: show the pause, get the human's input, resume, repeat. Because state is checkpointed,
you can stop at any pause and resume later from a separate process.

Usage:
    cd backend
    uv run python run.py                              # interactive: pick/edit/regenerate, approve, publish
    uv run python run.py --pick idea_b --approve --publish  # accept idea_b + approve + publish
    uv run python run.py --regenerate --approve       # reject the first set(s), then accept on the last
    uv run python run.py --abandon                    # give up at the research gate (no idea chosen)
    uv run python run.py --pick idea_a --edit "summary=Sort the animal cards" --approve  # edit then go
    uv run python run.py --pick idea_a --reject       # accept, but reject at the safety gate
    uv run python run.py --pick idea_a --approve --reject-play-test  # build, then reject at Gate 3
    uv run python run.py --thread t1 --stop-at-pause  # run to the next pause, then exit
    uv run python run.py --thread t1 --resume         # resume that paused thread
"""

import argparse
import re
from pathlib import Path

from langgraph.types import Command

from pipeline import build_graph, make_checkpointer


def is_pick_gate(payload: dict) -> bool:
    """The pick gate offers options; the safety gate carries a verdict instead."""
    return "options" in payload


def is_play_test_gate(payload: dict) -> bool:
    """Gate 3 identifies itself by stage; it carries generated code metadata, not a verdict."""
    return payload.get("stage") == "play_test"


def announce(payload: dict) -> None:
    print(f"\n  ⏸  PAUSED — {payload.get('question')}")
    if is_pick_gate(payload):
        if payload.get("max_attempts"):
            note = "" if payload.get("can_regenerate") else " — last set, regenerate no longer offered"
            print(f"       (idea set {payload.get('attempt')} of {payload.get('max_attempts')}{note})")
        for o in payload.get("options", []):
            mech = f"  [{o['mechanic']}]" if o.get("mechanic") else ""
            print(f"       · {o['id']}: {o.get('title', o['id'])}{mech}")
            print(f"           {o.get('summary', '')}")
            if o.get("concept"):
                print(f"           teaches → {o['concept']}")
    elif is_play_test_gate(payload):
        print(f"       Generated GameLevel.tsx: {payload.get('code_chars', 0)} chars")
        print("       Play it in the frontend Sandpack tab, then approve only if it is shippable.")
    else:
        v = payload.get("verdict", {})
        print(f"       AI safety check: {'safe' if v.get('safe') else 'UNSAFE'} — {v.get('reason', '')}")


def _parse_edits(pairs: list[str]) -> dict:
    """Turn CLI --edit "field=value" pairs into an edits dict."""
    edits = {}
    for pair in pairs:
        if "=" in pair:
            field, value = pair.split("=", 1)
            edits[field.strip()] = value.strip()
    return edits


def _prompt_edits(chosen_id: str) -> dict:
    """Interactively collect field edits for one idea (blank field name finishes)."""
    print(f"     editing {chosen_id} — enter a blank field name to finish")
    edits = {}
    while True:
        try:
            field = input("       field to change (e.g. title, summary, mechanic): ").strip()
            if not field:
                break
            edits[field] = input(f"       new value for {field!r}: ").strip()
        except EOFError:
            break
    return edits


def pick_decision(payload: dict, args) -> dict:
    """Decide what to do at the research gate: accept an idea, edit one, or regenerate them all."""
    ids = [o["id"] for o in payload["options"]]
    can_regen = payload.get("can_regenerate")

    # Non-interactive shortcuts from flags.
    if args.abandon:
        return {"action": "abandon"}
    if args.regenerate and can_regen:
        return {"action": "regenerate"}
    if args.edit:
        return {"action": "edit", "chosen_id": args.pick or ids[0], "edits": _parse_edits(args.edit)}
    if args.pick:
        return {"action": "accept", "chosen_id": args.pick}

    # Interactive prompt.
    extra = ", 'r' to regenerate" if can_regen else ""
    try:
        answer = input(f"     accept an id {ids}, 'e <id>' to edit{extra}, 'a' to abandon: ").strip()
    except EOFError:  # non-interactive (e.g. piped) -> just take the first
        return {"action": "accept", "chosen_id": ids[0]}
    if not answer:
        return {"action": "accept", "chosen_id": ids[0]}
    if answer.lower() in ("a", "abandon"):
        return {"action": "abandon"}
    if answer.lower() in ("r", "regenerate") and can_regen:
        return {"action": "regenerate"}
    if answer.lower().startswith("e"):
        parts = answer.split(maxsplit=1)
        chosen_id = parts[1].strip() if len(parts) > 1 else ids[0]
        return {"action": "edit", "chosen_id": chosen_id, "edits": _prompt_edits(chosen_id)}
    return {"action": "accept", "chosen_id": answer}


def decide_approval(verdict: dict, args) -> bool:
    """Approve at the safety gate: --approve/--reject if given, else ask (defaulting to the AI)."""
    if args.approve:
        return True
    if args.reject:
        return False
    default = bool(verdict.get("safe"))  # the human can override, but the AI's call is the default
    hint = "Y/n" if default else "y/N"
    try:
        answer = input(f"     approve for kids? [{hint}]: ").strip().lower()
    except EOFError:  # non-interactive -> follow the AI's recommendation
        return default
    return default if not answer else answer.startswith("y")


def decide_play_test(args) -> bool:
    """Approve Gate 3. Publishing is a write, so the non-interactive default is deliberately no."""
    if args.publish:
        return True
    if args.reject_play_test:
        return False
    try:
        answer = input("     publish this play-tested level? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer.startswith("y")


def resume_value(payload: dict, args) -> dict:
    """Turn the human's input for this gate into the value we resume the graph with."""
    if is_pick_gate(payload):
        return pick_decision(payload, args)
    if is_play_test_gate(payload):
        return {"approved": decide_play_test(args)}
    return {"approved": decide_approval(payload.get("verdict", {}), args)}


def pending_interrupt(snapshot) -> dict | None:
    """The interrupt payload a paused thread is waiting on, or None if it isn't paused."""
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def drive(graph, config, args, result: dict) -> dict | None:
    """Handle each pause until the graph finishes. Returns the final state, or None if we stopped."""
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        announce(payload)
        if args.stop_at_pause:
            print("\n  ⏹  Stopped at the pause. State is saved — re-run with --resume to continue.")
            return None
        result = graph.invoke(Command(resume=resume_value(payload, args)), config)
    return result


def print_final(thread: str, state: dict) -> None:
    print(f"\nFinal state for thread {thread!r}:")
    print("  research_attempts =", state.get("research_attempts"))
    print("  chosen_idea =", state.get("chosen_idea"))
    print("  guardrail   =", state.get("guardrail_result"))
    print("  approval    =", state.get("approval"))
    if state.get("game_code"):
        print("  game_code   =", f"<{len(state['game_code'])} chars of GameLevel.tsx>")
    if state.get("static_check"):
        print("  static_check =", state.get("static_check"))
    if state.get("test_results"):
        print("  test        =", state.get("test_results"))
    if state.get("repair_count"):
        print("  repairs     =", state.get("repair_count"), "—", state.get("error_log"))
    print("  play_test   =", state.get("play_test_approved"))
    if state.get("published"):
        print("  published   =", state.get("published"))
    if state.get("halted_reason"):
        print("  halted      =", state.get("halted_reason"))


def _slug(text: str, fallback: str = "level") -> str:
    """A short, filename-safe slug, e.g. 'How AI learns!' -> 'how-ai-learns'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:40] or fallback


def save_game(thread: str, state: dict) -> None:
    """Save the coding agent's React component to its own readable file under backend/generated/,
    named by concept + chosen idea (e.g. knowledge-cutoff__idea_a.tsx) so each level is easy to
    find. The SQLite level store is canonical after publish; this on-disk copy is for dev
    play-testing (rendered in Sandpack at B10)."""
    code = state.get("game_code")
    if not code:
        return
    out_dir = Path(__file__).resolve().parent / "generated"
    out_dir.mkdir(exist_ok=True)
    idea = state.get("chosen_idea") or {}
    name = f"{_slug(state.get('concept', ''))}__{idea.get('id') or thread}"
    path = out_dir / f"{name}.tsx"
    path.write_text(code, encoding="utf-8")
    print(f"\n  🎮 GameLevel.tsx saved to {path}")
    print("     (render it in the frontend / Sandpack to play-test — B10)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default="demo")
    ap.add_argument("--concept", default="knowledge cutoff", help="what to teach")
    ap.add_argument("--pick", help="idea id to accept (skips the pick prompt)")
    ap.add_argument("--regenerate", action="store_true",
                    help="reject all ideas and regenerate a fresh set (research gate)")
    ap.add_argument("--abandon", action="store_true",
                    help="give up at the research gate — stop with no idea chosen")
    ap.add_argument("--edit", action="append", metavar="FIELD=VALUE",
                    help="edit the picked idea before proceeding, e.g. --edit \"summary=...\"; repeatable")
    ap.add_argument("--approve", action="store_true", help="auto-approve at the safety gate")
    ap.add_argument("--reject", action="store_true", help="auto-reject at the safety gate")
    ap.add_argument("--publish", action="store_true", help="auto-approve Gate 3 and publish to SQLite")
    ap.add_argument("--reject-play-test", action="store_true", help="auto-reject at Gate 3 (no publish)")
    ap.add_argument("--stop-at-pause", action="store_true", help="stop at the next pause; resume later")
    ap.add_argument("--resume", action="store_true", help="resume a thread paused at a gate")
    args = ap.parse_args()

    graph = build_graph(checkpointer=make_checkpointer())
    config = {"configurable": {"thread_id": args.thread}}

    if args.resume:
        payload = pending_interrupt(graph.get_state(config))
        if payload is None:
            print(f"Thread {args.thread!r} is not paused at a gate.")
            return
        print(f"Resuming thread {args.thread!r}:")
        announce(payload)
        result = graph.invoke(Command(resume=resume_value(payload, args)), config)
    else:
        # Fresh run. It will pause at the first gate.
        result = graph.invoke({"concept": args.concept}, config)

    result = drive(graph, config, args, result)  # handle any remaining pauses
    if result is not None:
        print_final(args.thread, result)
        save_game(args.thread, result)


if __name__ == "__main__":
    main()
