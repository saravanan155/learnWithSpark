"""Run the pipeline, or inspect previously-saved state (B4).

Because we now have a checkpointer, every run is saved to checkpoints.sqlite under a thread_id.

Usage:
    cd backend
    uv run python run.py                 # run the pipeline for thread "demo" and save state
    uv run python run.py --show          # DON'T run — just read back the saved state for "demo"
    uv run python run.py --thread other  # use a different thread_id
"""

import argparse

from pipeline import build_graph, make_checkpointer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default="demo", help="thread_id to save/read state under")
    ap.add_argument("--show", action="store_true", help="read back saved state instead of running")
    args = ap.parse_args()

    # The checkpointer + thread_id together decide WHERE state is saved and read from.
    graph = build_graph(checkpointer=make_checkpointer())
    config = {"configurable": {"thread_id": args.thread}}

    if args.show:
        # get_state reads the LAST saved checkpoint for this thread — no nodes run.
        snapshot = graph.get_state(config)
        if not snapshot.values:
            print(f"No saved state for thread {args.thread!r} yet. Run without --show first.")
            return
        print(f"Saved state for thread {args.thread!r} (read from disk, nothing ran):")
        _print_state(snapshot.values)
        return

    result = graph.invoke({"concept": "knowledge cutoff"}, config)
    print(f"\nRan thread {args.thread!r}. Final state:")
    _print_state(result)


def _print_state(state: dict):
    print("  concept   =", state.get("concept"))
    for idea in state.get("idea_options", []):
        print(f"  idea      = {idea['id']}: {idea['summary']}")
    print("  guardrail =", state.get("guardrail_result"))


if __name__ == "__main__":
    main()
