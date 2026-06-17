"""Run the pipeline once and print the result (B2).

Usage:
    cd backend
    uv run python run.py
"""

from pipeline import build_graph


def main():
    graph = build_graph()

    # `invoke` runs the graph from START to END. We hand it the initial state (just the concept).
    result = graph.invoke({"concept": "knowledge cutoff"})

    print("\nFinal state:")
    print("  concept  =", result.get("concept"))
    for idea in result.get("idea_options", []):
        print(f"  idea     = {idea['id']}: {idea['summary']}")
    print("  guardrail =", result.get("guardrail_result"))


if __name__ == "__main__":
    main()
