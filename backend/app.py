"""A tiny Streamlit front end to drive and WATCH the pipeline (B8.5).

Run it from the backend folder:

    cd backend
    uv run streamlit run app.py

It lets you start a run, then step through the two human gates (pick an idea, approve the safety
verdict) with buttons — and it shows the per-step logs each node prints, so you can see exactly
what happened at every transition. State lives in the same SQLite checkpointer the CLI uses, keyed
by a per-run thread id, so Streamlit's reruns don't lose the paused graph.
"""

import io
import uuid
from contextlib import redirect_stdout

import streamlit as st
from langgraph.types import Command

from llm import has_nebius
from nodes.research_gate import MAX_RESEARCH_ATTEMPTS
from pipeline import build_graph, make_checkpointer

st.set_page_config(page_title="Learn with Spark — pipeline", page_icon="✨", layout="wide")

# Editable fields offered in the "edit an idea" form (text fields only — nested structures like
# example_round are left to the coding agent).
EDITABLE_FIELDS = ["title", "summary", "mechanic", "teaches", "aha_moment", "analogy"]


@st.cache_resource
def get_graph():
    """One compiled graph + checkpointer connection, reused across Streamlit reruns."""
    return build_graph(checkpointer=make_checkpointer())


def _config():
    return {"configurable": {"thread_id": st.session_state.thread_id}}


def _run(label: str, fn):
    """Run a graph call, capturing the nodes' stdout into a labelled step log, then route on it."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = fn()
    st.session_state.steps.append({"label": label, "logs": buf.getvalue().strip()})
    _route(result)


def _route(result: dict):
    """Decide the next UI phase from an invoke/resume result."""
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        st.session_state.payload = payload
        st.session_state.phase = "pick" if "options" in payload else "safety"
    else:
        st.session_state.phase = "done"
        st.session_state.payload = None


def start_run(concept: str):
    st.session_state.thread_id = f"ui-{uuid.uuid4().hex[:8]}"
    st.session_state.concept = concept
    st.session_state.steps = []
    g = get_graph()
    _run("research → pick gate", lambda: g.invoke({"concept": concept}, _config()))


def resume(decision: dict, label: str):
    g = get_graph()
    _run(label, lambda: g.invoke(Command(resume=decision), _config()))


# ---------- rendering helpers ----------

def render_idea(o: dict):
    """Show one LessonSpec idea."""
    mech = o.get("mechanic", "?")
    st.markdown(f"**{o.get('title', o['id'])}**  ·  `{mech}`  ·  _{o['id']}_")
    if o.get("summary"):
        st.write(o["summary"])
    if o.get("concept"):
        st.caption(f"🎯 Teaches: {o['concept']}")
    if o.get("story"):
        st.caption(f"💬 {o['story']}")
    if o.get("prompt"):
        st.caption(f"🎮 {o['prompt']}")
    items = o.get("items") or []
    if items:
        st.caption("Items: " + "  ".join(f"{it.get('imageHint', '')} {it.get('label', '')}" for it in items))
    extra = {k: o[k] for k in ("solution", "feedback", "sparkMoods") if o.get(k)}
    if extra:
        with st.expander("Spec details"):
            st.json(extra)


def render_pick():
    p = st.session_state.payload
    options = p["options"]
    st.subheader("🔬 Research gate — choose an idea")
    st.caption(f"Idea set {p.get('attempt')} of {p.get('max_attempts', MAX_RESEARCH_ATTEMPTS)}")

    for o in options:
        with st.container(border=True):
            render_idea(o)

    ids = [o["id"] for o in options]
    titles = {o["id"]: o.get("title", o["id"]) for o in options}
    chosen_id = st.radio("Selected idea", ids, format_func=lambda x: f"{x} — {titles[x]}")
    chosen = next(o for o in options if o["id"] == chosen_id)

    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Accept", type="primary", use_container_width=True):
        resume({"action": "accept", "chosen_id": chosen_id}, f"accept {chosen_id} → guardrail")
        st.rerun()
    regen_disabled = not p.get("can_regenerate")
    if c2.button("🔄 Regenerate all", use_container_width=True, disabled=regen_disabled,
                 help="Reject every idea and ask for a fresh set" if not regen_disabled
                 else "Cap reached — no more regenerations"):
        resume({"action": "regenerate"}, "regenerate → research")
        st.rerun()
    if c3.button("🛑 Abandon", use_container_width=True, help="Give up — stop with no idea chosen"):
        resume({"action": "abandon"}, "abandon → stop")
        st.rerun()

    with st.expander(f"✏️ Edit “{titles[chosen_id]}” before accepting"):
        with st.form("edit_form"):
            new_values = {f: st.text_input(f, value=str(chosen.get(f, ""))) for f in EDITABLE_FIELDS}
            if st.form_submit_button("Apply edits & accept"):
                edits = {f: v for f, v in new_values.items() if v != str(chosen.get(f, ""))}
                resume({"action": "edit", "chosen_id": chosen_id, "edits": edits},
                       f"edit {chosen_id} ({', '.join(edits) or 'no change'}) → guardrail")
                st.rerun()


def render_safety():
    v = st.session_state.payload.get("verdict", {})
    st.subheader("🛡️ Safety gate — approve or override")
    if v.get("safe"):
        st.success(f"AI verdict: **SAFE** — {v.get('reason', '')}")
    else:
        st.error(f"AI verdict: **UNSAFE** — {v.get('reason', '')}")
    st.caption("The model only recommends — you make the final call, and can override it.")

    c1, c2 = st.columns(2)
    if c1.button("✅ Approve & finish", type="primary", use_container_width=True):
        resume({"approved": True}, "approve → END")
        st.rerun()
    if c2.button("🚫 Reject (block)", use_container_width=True):
        resume({"approved": False}, "reject → blocked")
        st.rerun()


def render_done():
    state = get_graph().get_state(_config()).values
    st.subheader("🏁 Run finished")
    if state.get("halted_reason"):
        st.warning(f"Stopped: {state['halted_reason']}")
    else:
        st.success("Idea approved — ready for the coding agent (B9).")

    if state.get("chosen_idea"):
        with st.container(border=True):
            render_idea(state["chosen_idea"])
    with st.expander("Full final state"):
        st.json({k: state.get(k) for k in
                 ("concept", "research_attempts", "chosen_idea", "guardrail_result",
                  "approval", "halted_reason")})


def render_logs():
    st.subheader("📜 Step-by-step log")
    steps = st.session_state.get("steps", [])
    if not steps:
        st.caption("No steps yet — start a run from the sidebar.")
        return
    for i, step in enumerate(steps, 1):
        with st.expander(f"Step {i}: {step['label']}", expanded=(i == len(steps))):
            st.code(step["logs"] or "(no log output)", language="text")


# ---------- app ----------

if "phase" not in st.session_state:
    st.session_state.phase = "idle"
    st.session_state.steps = []
    st.session_state.payload = None

with st.sidebar:
    st.header("✨ Learn with Spark")
    st.caption("Drive the multi-agent pipeline and watch each step.")
    if has_nebius():
        st.success("Nebius key detected — real agents.")
    else:
        st.warning("No NEBIUS_API_KEY — agents use stub fallbacks.")

    concept = st.text_input("Concept to teach", value="knowledge cutoff")
    if st.button("▶ Start new run", type="primary", use_container_width=True):
        start_run(concept)
        st.rerun()
    if st.session_state.phase != "idle" and st.button("↺ Reset", use_container_width=True):
        for k in ("phase", "steps", "payload", "thread_id", "concept"):
            st.session_state.pop(k, None)
        st.rerun()

    if st.session_state.phase != "idle":
        st.divider()
        st.caption(f"Concept: **{st.session_state.get('concept', '')}**")
        st.caption(f"Thread: `{st.session_state.get('thread_id', '')}`")

st.title("✨ Learn with Spark — pipeline runner")

left, right = st.columns([3, 2])
with left:
    phase = st.session_state.phase
    if phase == "idle":
        st.info("Set a concept in the sidebar and click **Start new run**.")
    elif phase == "pick":
        render_pick()
    elif phase == "safety":
        render_safety()
    elif phase == "done":
        render_done()
with right:
    render_logs()
