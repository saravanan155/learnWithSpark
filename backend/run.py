"""Run the pipeline, which now PAUSES for a human to pick an idea (B5).

When the graph hits the gate, `invoke` returns with an "__interrupt__" instead of finishing.
We show the options, get a choice, and resume with `Command(resume=...)`. Because state is
checkpointed, you can also stop at the pause and resume later from a separate process.

Usage:
    cd backend
    uv run python run.py                          # run; you'll be asked to pick an idea
    uv run python run.py --pick idea_b            # run; auto-pick idea_b (no prompt)
    uv run python run.py --thread t1 --stop-at-pause   # run until the pause, then exit
    uv run python run.py --thread t1 --resume --pick idea_a   # resume that paused thread
"""

import argparse

from langgraph.types import Command

from pipeline import build_graph, make_checkpointer


def show_options(payload: dict) -> None:
    print(f"\n  ⏸  PAUSED — {payload.get('question')}")
    for o in payload.get("options", []):
        print(f"       · {o['id']}: {o['summary']}")


def choose(options: list[dict], pick_arg: str | None) -> str:
    """Decide the pick: --pick if given, else ask, else default to the first option."""
    ids = [o["id"] for o in options]
    if pick_arg:
        return pick_arg
    try:
        answer = input(f"     pick one {ids}: ").strip()
        return answer or ids[0]
    except EOFError:  # non-interactive (e.g. piped) -> just take the first
        return ids[0]


def pending_interrupt(snapshot) -> dict | None:
    """The interrupt payload a paused thread is waiting on, or None if it isn't paused."""
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def print_final(thread: str, state: dict) -> None:
    print(f"\nFinal state for thread {thread!r}:")
    print("  chosen_idea =", state.get("chosen_idea"))
    print("  guardrail   =", state.get("guardrail_result"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default="demo")
    ap.add_argument("--pick", help="idea id to choose (skips the prompt)")
    ap.add_argument("--stop-at-pause", action="store_true", help="stop at the pause; resume later")
    ap.add_argument("--resume", action="store_true", help="resume a thread paused at the gate")
    args = ap.parse_args()

    graph = build_graph(checkpointer=make_checkpointer())
    config = {"configurable": {"thread_id": args.thread}}

    if args.resume:
        payload = pending_interrupt(graph.get_state(config))
        if payload is None:
            print(f"Thread {args.thread!r} is not paused at the gate.")
            return
        print(f"Resuming thread {args.thread!r}:")
        show_options(payload)
        pick = choose(payload["options"], args.pick)
        result = graph.invoke(Command(resume={"chosen_id": pick}), config)
        print_final(args.thread, result)
        return

    # Fresh run. It will pause at the gate.
    result = graph.invoke({"concept": "knowledge cutoff"}, config)
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        show_options(payload)
        if args.stop_at_pause:
            print("\n  ⏹  Stopped at the pause. State is saved — re-run with --resume to continue.")
            return
        pick = choose(payload["options"], args.pick)
        result = graph.invoke(Command(resume={"chosen_id": pick}), config)

    print_final(args.thread, result)


if __name__ == "__main__":
    main()
