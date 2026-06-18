"""Run the pipeline, which now PAUSES TWICE for a human (B8).

The graph stops at two gates: first to pick an idea, then to approve the guardrail's safety
verdict. Each `invoke` runs until the next pause (returning an "__interrupt__") or until the end,
so we just loop: show the pause, get the human's input, resume, repeat. Because state is
checkpointed, you can stop at either pause and resume later from a separate process.

Usage:
    cd backend
    uv run python run.py                              # run; you'll pick an idea, then approve
    uv run python run.py --pick idea_b --approve      # run, auto-pick + auto-approve (no prompts)
    uv run python run.py --pick idea_a --reject       # run, but reject at the safety gate
    uv run python run.py --thread t1 --stop-at-pause  # run to the next pause, then exit
    uv run python run.py --thread t1 --resume         # resume that paused thread
"""

import argparse

from langgraph.types import Command

from pipeline import build_graph, make_checkpointer


def is_pick_gate(payload: dict) -> bool:
    """The pick gate offers options; the safety gate carries a verdict instead."""
    return "options" in payload


def announce(payload: dict) -> None:
    print(f"\n  ⏸  PAUSED — {payload.get('question')}")
    if is_pick_gate(payload):
        for o in payload.get("options", []):
            mech = f"  [{o['mechanic']}]" if o.get("mechanic") else ""
            print(f"       · {o['id']}: {o.get('title', o['id'])}{mech}")
            print(f"           {o.get('summary', '')}")
            if o.get("aha_moment"):
                print(f"           aha → {o['aha_moment']}")
    else:
        v = payload.get("verdict", {})
        print(f"       AI safety check: {'safe' if v.get('safe') else 'UNSAFE'} — {v.get('reason', '')}")


def choose_idea(options: list[dict], pick_arg: str | None) -> str:
    """Decide the pick: --pick if given, else ask, else default to the first option."""
    ids = [o["id"] for o in options]
    if pick_arg:
        return pick_arg
    try:
        answer = input(f"     pick one {ids}: ").strip()
        return answer or ids[0]
    except EOFError:  # non-interactive (e.g. piped) -> just take the first
        return ids[0]


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


def resume_value(payload: dict, args) -> dict:
    """Turn the human's input for this gate into the value we resume the graph with."""
    if is_pick_gate(payload):
        return {"chosen_id": choose_idea(payload["options"], args.pick)}
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
    print("  chosen_idea =", state.get("chosen_idea"))
    print("  guardrail   =", state.get("guardrail_result"))
    print("  approval    =", state.get("approval"))
    if state.get("halted_reason"):
        print("  halted      =", state.get("halted_reason"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default="demo")
    ap.add_argument("--concept", default="knowledge cutoff", help="what to teach")
    ap.add_argument("--pick", help="idea id to choose (skips the pick prompt)")
    ap.add_argument("--approve", action="store_true", help="auto-approve at the safety gate")
    ap.add_argument("--reject", action="store_true", help="auto-reject at the safety gate")
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


if __name__ == "__main__":
    main()
