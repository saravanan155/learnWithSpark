"""LangGraph nodes — one module per agent / gate / terminal.

    research        -> the research agent (Nebius)
    research_gate   -> the pick-idea human gate + its router
    guardrail       -> the kid-safety agent (Nebius)
    safety_gate     -> the approval human gate + its router
    coding          -> the coding agent (Claude)
    terminals       -> the abandoned / blocked dead-ends

`pipeline.py` imports these and wires them into the graph.
"""
