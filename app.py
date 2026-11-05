"""Who should do the work? An agent-delegation exercise for seminars and classrooms (Streamlit).

Participants join from their phone or laptop (QR code), redesign everyday workflows (who plans each case:
an AI agent or a person; who carries out each step), see every design scored live with the decision-rights
model of 'The Autonomy Paradox', and then say when an agent should get access to the work and when it
should stay with a person. The facilitator projects a live results screen.

Participant view:   http://<host>:8501/?s=<SESSION>        (Streamlit Cloud: https://<app>.streamlit.app/?s=<SESSION>)
Facilitator view:   http://<host>:8501/?view=facilitator   (password in local_config.toml or secrets)

Run:  run_local.bat (this computer) | run_seminar.bat (same Wi-Fi) | run_seminar_public.bat (internet link)
      or deploy on Streamlit Community Cloud (see README, "Run it on Streamlit Community Cloud").
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import random
import re
import socket
import threading
import time
import uuid
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import exercise_model as M
import storage
import survey as SV

APP_VERSION = "2.0.0"
BASE = Path(__file__).resolve().parent
COL_A, COL_H, COL_WARN, COL_OK = "#0072B2", "#009E73", "#D55E00", "#2E7D32"
LADDER_COLORS = ["#9CA3AF", "#CFE3F3", "#9CC5E6", "#5B9BD5", "#2E75B6", "#1F3864"]
RECOMMENDED = ["T1", "T3", "T7"]          # a 10-minute path: the split-rights valley, long runs, planning knowledge

VIEW = str(st.query_params.get("view", "")).lower()
IS_FAC = VIEW in ("facilitator", "present", "admin")
st.set_page_config(page_title="Who should do the work?", page_icon="🤝",
                   layout="wide" if IS_FAC else "centered", initial_sidebar_state="collapsed")


# ----------------------------------------------------------------- settings
def _load_local_config() -> dict:
    path = BASE / "local_config.toml"
    if not path.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    return tomllib.loads(path.read_text(encoding="utf-8"))


LOCAL_CFG = _load_local_config()


def setting(section: str, key: str, default):
    try:
        v = st.secrets.get(section, {}).get(key, None)
        if v is not None:
            return v
    except Exception:
        pass
    return LOCAL_CFG.get(section, {}).get(key, default)


ROUND3_EPS = float(setting("app", "round3_eps_multiplier", 0.5))
ROUND3_RHO = float(setting("app", "round3_rho_multiplier", 0.5))
ROUNDS = {
    1: dict(label="Round 1 · Redesign the work", codify=False, eps=1.0, rho=1.0,
            note="Choose who plans each case and who does each step."),
    2: dict(label="Round 2 · Write the procedure down", codify=True, eps=1.0, rho=1.0,
            note="You may now codify the policy: write the rules as an explicit procedure. It cuts hand-off "
                 "errors but costs money per case."),
    3: dict(label="Round 3 · A better agent arrives", codify=True, eps=ROUND3_EPS, rho=ROUND3_RHO,
            note=f"A new agent model: hand-off errors ×{ROUND3_EPS:g}, error build-up ×{ROUND3_RHO:g}. "
                 "Which designs should change?"),
}
OPEN_ROUNDS = [int(r) for r in setting("app", "open_rounds", [1, 2, 3])]
SESSION_CODES = [str(c).strip().upper() for c in setting("app", "session_codes", [])]
FAC_PASSWORD = str(setting("app", "facilitator_password", ""))
PUBLIC_URL = str(setting("app", "public_url", "") or "").strip().rstrip("/")


def _request_host() -> str:
    """Host name the participant's browser used (e.g. myapp.streamlit.app), or '' if unknown."""
    try:
        return str(st.context.headers.get("Host", "") or "").strip()
    except Exception:
        return ""


def on_cloud() -> bool:
    """True when running on Streamlit Community Cloud (apps are checked out under /mount/src)."""
    return str(BASE).startswith("/mount/src") or _request_host().endswith(".streamlit.app")


@st.cache_resource
def get_stores():
    try:
        secrets = st.secrets
        _ = secrets.get("github", {})
    except Exception:
        secrets = {}
    loc = dict(LOCAL_CFG.get("local", {}))
    if str(BASE).startswith("/mount/src") and not loc.get("csv_path"):
        # Streamlit Cloud without GitHub settings: keep the fallback files inside the app folder
        # (writable, but wiped when the app restarts). Configure [github] in the Secrets for real sessions.
        loc["csv_path"] = "data/exercise/responses.csv"
    game, mode = storage.from_settings(secrets, BASE, loc)
    fb, _ = storage.from_settings(secrets, BASE, loc, filename="feedback.csv", columns=storage.FEEDBACK_COLUMNS)
    return game, fb, mode


GAME_STORE, FB_STORE, STORE_MODE = get_stores()


# ----------------------------------------------------------------- live state shared by everyone on this server
LIVE_PATH = BASE / "data" / "live_state.json"
_LIVE_LOCK = threading.Lock()
LIVE_DEFAULT = dict(round=OPEN_ROUNDS[0], show_results=False, join_url="",
                    session=(SESSION_CODES[0] if SESSION_CODES else "SEMINAR"))


def live_get() -> dict:
    with _LIVE_LOCK:
        try:
            d = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
    return {**LIVE_DEFAULT, **d}


def live_set(**kw):
    with _LIVE_LOCK:
        try:
            d = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d.update(kw)
        LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LIVE_PATH.write_text(json.dumps(d), encoding="utf-8")


# ----------------------------------------------------------------- styling
st.markdown("""
<style>
#MainMenu, footer, [data-testid="stToolbar"] {visibility:hidden}
.block-container{padding-top:1.6rem;padding-bottom:3rem}
.chip{display:inline-block;min-width:30px;padding:5px 7px;margin:2px;border-radius:8px;color:#fff;
      font-weight:700;text-align:center;font-size:13px}
.chipA{background:#0072B2;border-radius:2px}.chipH{background:#009E73;border-radius:12px}
.handoff{outline:3px dashed #D55E00;outline-offset:1px}
.steps{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 2px 0;font-size:13px;color:#374151}
.steps span{padding:4px 10px;border-radius:14px;background:#EEF2F7}
.steps span.on{background:#0072B2;color:#fff;font-weight:600}
.steps span.done{background:#DCEFE6;color:#14532D}
.score{border-radius:14px;padding:14px 18px;margin:6px 0 10px 0;background:#F2F6FB;border:1px solid #DCE5F0}
.score .v{font-size:28px;font-weight:800;line-height:1.15}
.score .row{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:6px}
.score .l{font-size:12px;color:#4B5563;text-transform:uppercase;letter-spacing:.04em}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:600}
.b-good{background:#DCFCE7;color:#14532D}.b-mid{background:#FEF9C3;color:#713F12}.b-bad{background:#FEE2E2;color:#7F1D1D}
.card{border:1px solid #E5E7EB;border-radius:14px;padding:12px 14px;margin-bottom:6px;background:#fff}
.card h4{margin:0 0 2px 0;font-size:17px}.muted{color:#6B7280;font-size:13px}
.rule{border-left:4px solid #0072B2;background:#F2F6FB;border-radius:8px;padding:10px 14px;margin:8px 0 12px 0}
.howcard{border-radius:14px;padding:14px;margin-bottom:8px;border:1px solid #E5E7EB}
.bigcode{font-size:56px;font-weight:800;letter-spacing:.08em;color:#1F3864}
.joinurl{font-size:22px;font-weight:600;word-break:break-all}
div.stButton > button{border-radius:10px;min-height:2.6rem}
</style>""", unsafe_allow_html=True)


def _full_kw():
    """Full-width keyword for buttons, tables, charts and images on both old and new Streamlit versions."""
    import inspect
    return {"width": "stretch"} if "width" in inspect.signature(st.button).parameters else {"use_container_width": True}


FULL = _full_kw()


def md(s: str) -> str:
    """Escape dollar signs so Streamlit markdown does not read them as LaTeX."""
    return str(s).replace("$", "\\$")


def money(x):
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


# ----------------------------------------------------------------- participant state
def init_state():
    ss = st.session_state
    ss.setdefault("step", "join")
    ss.setdefault("profile", {})
    ss.setdefault("designs", {})
    ss.setdefault("edits", {})
    ss.setdefault("seconds", {})
    ss.setdefault("visited", [])
    ss.setdefault("submitted", {})          # round -> submission id
    ss.setdefault("survey_done", False)
    ss.setdefault("task", None)
    ss.setdefault("t_open", None)


def go_step(step, task=None):
    ss = st.session_state
    _close_task_clock()
    ss.step = step
    if task:
        ss.task = task
        ss.t_open = (task, time.time())
        if task not in ss.visited:
            ss.visited.append(task)


def _close_task_clock():
    ss = st.session_state
    if ss.get("t_open"):
        tid, t0 = ss.t_open
        rnd = current_round()
        ss.seconds[(rnd, tid)] = ss.seconds.get((rnd, tid), 0.0) + min(time.time() - t0, 300.0)
        ss.t_open = None


def current_round() -> int:
    r = int(live_get().get("round", OPEN_ROUNDS[0]))
    return r if r in ROUNDS else OPEN_ROUNDS[0]


def design(rnd: int, tid: str) -> dict:
    d = st.session_state.designs.get((rnd, tid))
    if d is None:
        t = M.TASK_BY_ID[tid]
        prev = next((st.session_state.designs.get((r, tid)) for r in range(rnd - 1, 0, -1)
                     if st.session_state.designs.get((r, tid))), None)
        d = dict(prev) if prev else dict(plan="Human", codify=False, alloc=M.default_alloc(t))
        if not ROUNDS[rnd]["codify"]:
            d["codify"] = False
        st.session_state.designs[(rnd, tid)] = d
    return d


def result_for(rnd, tid):
    d, r = design(rnd, tid), ROUNDS[rnd]
    return M.evaluate(M.TASK_BY_ID[tid], d["alloc"], d["plan"], d["codify"], r["eps"], r["rho"])


def standing(rnd, tid, res=None):
    """(label, css class, gap to best standard design)."""
    res = res or result_for(rnd, tid)
    refs = M.references(M.TASK_BY_ID[tid], ROUNDS[rnd]["eps"], ROUNDS[rnd]["rho"])
    best = max(r[2].value for r in refs.values())
    gap = res.value - best
    if gap > 0.005:
        return f"🏆 Beats every standard design by {money(gap)}", "b-good", gap
    if gap > -0.005:
        return "Matches the best standard design", "b-mid", gap
    return f"{money(-gap)} below the best standard design", "b-bad", gap


def progress_bar(active: str):
    names = [("join", "Join"), ("how", "How it works"), ("play", "Play"), ("view", "Your view"), ("done", "Results")]
    order = [k for k, _ in names]
    a = "play" if active == "task" else active
    html = []
    for k, label in names:
        cls = "on" if k == a else ("done" if order.index(k) < order.index(a) else "")
        html.append(f'<span class="{cls}">{order.index(k)+1} {label}</span>')
    st.markdown(f'<div class="steps">{"".join(html)}</div>', unsafe_allow_html=True)


def round_banner():
    rnd = current_round()
    if len(OPEN_ROUNDS) > 1:
        st.info(f"**{ROUNDS[rnd]['label']}.** {ROUNDS[rnd]['note']}", icon="🔁")


# ----------------------------------------------------------------- step 1: join
def page_join():
    live = live_get()
    st.title("Who should do the work?")
    st.markdown("##### A short exercise on giving AI agents access to everyday work")
    progress_bar("join")
    st.write("You will redesign a few workflows, see what each choice does to quality and cost, and then tell us "
             "**when an agent should get access to the work and when it should stay with a person.** "
             "It takes about 15 minutes. There are no wrong answers in the survey part.")
    qs = str(st.query_params.get("s", "")).strip().upper()
    prof = st.session_state.profile
    with st.form("join"):
        name = st.text_input("Name or alias (optional)", value=prof.get("name", ""), max_chars=40,
                             placeholder="e.g. Priya, or Table 3")
        code_default = prof.get("session") or qs or live.get("session", "")
        session = st.text_input("Session code", value=code_default, max_chars=20,
                                help="Shown on the facilitator's screen. Already filled in if you scanned the QR code.")
        c1, c2 = st.columns(2)
        roles = ["", "Student", "Manager", "Individual contributor", "Executive", "Researcher", "Consultant", "Other"]
        role = c1.selectbox("Your role", roles, index=roles.index(prof.get("role", "")) if prof.get("role", "") in roles else 0)
        ais = ["", "Never", "Monthly", "Weekly", "Daily"]
        ai = c2.selectbox("I use AI tools at work", ais, index=ais.index(prof.get("ai", "")) if prof.get("ai", "") in ais else 0)
        pre = st.select_slider(SV.AUTONOMY_QUESTION, SV.AUTONOMY_SCALE, value=prof.get("pre", SV.AUTONOMY_SCALE[2]))
        consent = st.checkbox("Store my answers (no e-mail, alias allowed) for teaching and research on how people "
                              "delegate work to AI.", value=prof.get("consent", True))
        go_on = st.form_submit_button("Start  →", type="primary", **FULL)
    if go_on:
        code = session.strip().upper()
        if SESSION_CODES and code not in SESSION_CODES:
            st.error("That session code is not recognised. Check the facilitator's screen.")
            return
        if not code:
            code = "OPEN"
        alias = name.strip() or f"Guest-{random.randint(1000, 9999)}"
        st.session_state.profile = dict(name=alias, session=code, role=role, ai=ai, consent=consent, pre=pre, ok=True)
        go_step("how")
        st.rerun()
    st.caption("All workflows and numbers are hypothetical, chosen for teaching. The error model follows "
               "'The Autonomy Paradox' (Darapaneni).")
    st.button("📚 Read the articles behind this exercise", on_click=go_step, args=("library",))


# ----------------------------------------------------------------- step 2: how it works
def page_how():
    st.title("How it works")
    progress_bar("how")
    st.write("Every workflow is a chain of steps. For each case you decide **who plans it** (diagnoses the case "
             "and decides the steps) and **who carries out each step**. A case only ends well if every step does.")
    c1, c2, c3 = st.columns(3)
    c1.markdown('<div class="howcard" style="background:#E8F6F0"><b>🧑 Person</b><br>'
                '<span class="muted">Costs more per step. Each person step is also a check: it stops the agent\'s '
                'errors from building up.</span></div>', unsafe_allow_html=True)
    c2.markdown('<div class="howcard" style="background:#E6F1FA"><b>🤖 Agent</b><br>'
                '<span class="muted">Cheap and fast. But the longer it runs with nobody looking, the riskier '
                'each extra step gets.</span></div>', unsafe_allow_html=True)
    c3.markdown('<div class="howcard" style="background:#FDEEE6"><b>⚠️ Hand-off</b><br>'
                '<span class="muted">When the <i>agent</i> plans and a <i>person</i> does the step, instructions '
                'get misread. Every such step adds an error.</span></div>', unsafe_allow_html=True)
    st.markdown("**Your score is the value per case:** the value of a case done right × the chance it ends right, "
                "minus the cost of people, compute and planning. Each workflow also shows three *standard designs* "
                "(all agent, all person, agent plans and a person executes). Try to beat them.")
    with st.expander("See an example"):
        st.markdown('<span class="chip chipA">1A</span><span class="chip chipA">2A</span>'
                    '<span class="chip chipH handoff">3H</span><span class="chip chipA">4A</span>'
                    '<span class="chip chipA">5A</span>', unsafe_allow_html=True)
        st.caption("The agent plans and does steps 1, 2, 4 and 5; a person does step 3. Step 3 pays the hand-off "
                   "error (dashed outline) and resets the agent's run.")
    b1, b2 = st.columns(2)
    b1.button("← Back", on_click=go_step, args=("join",), **FULL)
    b2.button("Got it, let's play  →", type="primary", on_click=go_step, args=("play",), **FULL)


# ----------------------------------------------------------------- step 3: play hub
def task_card(tid, rnd, recommended=False):
    t = M.TASK_BY_ID[tid]
    res = result_for(rnd, tid)
    label, cls, _ = standing(rnd, tid, res)
    tried = st.session_state.edits.get((rnd, tid), 0) > 0
    status = "✓ redesigned" if tried else ("opened" if tid in st.session_state.visited else "not started")
    star = "⭐ " if recommended else ""
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
        c1.markdown(f"**{star}{tid} · {t['name']}**  \n<span class='muted'>{t['area']} · {len(t['steps'])} steps · "
                    f"{status}</span>  \n<span class='badge {cls}'>{md(money(res.value))} per case · {md(label)}</span>",
                    unsafe_allow_html=True)
        c2.button("Open", key=f"open_{tid}", on_click=go_step, args=("task", tid), **FULL,
                  type="primary" if not tried else "secondary")


def page_play():
    rnd = current_round()
    st.title("Redesign the work")
    progress_bar("play")
    round_banner()
    st.write("Start with the three ⭐ workflows (about 10 minutes). Open more if you have time.")
    for tid in RECOMMENDED:
        task_card(tid, rnd, recommended=True)
    with st.expander(f"More workflows ({len(M.TASKS) - len(RECOMMENDED)})"):
        for t in M.TASKS:
            if t["id"] not in RECOMMENDED:
                task_card(t["id"], rnd)
    st.divider()
    if not st.session_state.survey_done:
        st.button("I'm done playing  →  Share your view", type="primary", **FULL,
                  on_click=go_step, args=("view",))
        st.caption("You can also skip the game and go straight to the questions.")
    elif rnd not in st.session_state.submitted:
        if st.button(f"Submit my designs for {ROUNDS[rnd]['label']}", type="primary", **FULL):
            submit(rnd, feedback=False)
    else:
        st.success(f"Your designs for {ROUNDS[rnd]['label']} are saved.")
        st.button("See results", on_click=go_step, args=("done",), **FULL)
    explore_menu()


# ----------------------------------------------------------------- task page
def _ctl_changed(rnd, tid, key):
    ss = st.session_state
    if ss.get(key) is None:                       # a segmented control was clicked off: keep the old choice
        ss[key] = ss.get(key + "__prev")
    else:
        ss[key + "__prev"] = ss[key]
    ss.edits[(rnd, tid)] = ss.edits.get((rnd, tid), 0) + 1


def _bulk(rnd, tid, what):
    task, ss = M.TASK_BY_ID[tid], st.session_state
    if what == "reset":
        alloc = M.default_alloc(task)
        ss[f"plan_{rnd}_{tid}"] = ss[f"plan_{rnd}_{tid}__prev"] = "Human"
        ss[f"cod_{rnd}_{tid}"] = False
    elif what == "A":
        alloc = "".join("H" if s["who"] == "H" else "A" for s in task["steps"])
    else:
        alloc = "".join("A" if s["who"] == "A" else "H" for s in task["steps"])
    for k, a in enumerate(alloc):
        ss[f"s_{rnd}_{tid}_{k}"] = ss[f"s_{rnd}_{tid}_{k}__prev"] = a
    ss.edits[(rnd, tid)] = ss.edits.get((rnd, tid), 0) + 1


def hint(task, d, res, rnd):
    eps = res.eps_eff
    tips = []
    handoffs = sum(1 for a in d["alloc"] if a == "H") if d["plan"] == "Agent" else 0
    if handoffs >= 2 and eps > 0.02:
        tips.append(f"You have **{handoffs} hand-offs**: people carrying out the agent's plan. Each one adds a "
                    f"{eps:.0%} error. Try letting a person plan, or let the agent do those steps itself.")
    run = max(res.run_depth) + 1 if res.n_agent else 0
    if res.rho_eff > 0 and run >= 5:
        tips.append(f"The agent runs up to **{run} steps with nobody looking**, and errors build up. A person step "
                    "in the middle of a long run resets it.")
    if d["plan"] == "Agent" and task["phiA"] >= 0.15:
        tips.append(f"Here the agent gets the plan wrong **{task['phiA']:.0%}** of the time: people know things "
                    "it does not. Who should plan?")
    if res.rho_eff == 0 and res.n_human > 0 and d["plan"] == "Agent":
        tips.append("In this workflow agent errors do not build up, so checkpoints buy little.")
    if ROUNDS[rnd]["codify"] and not d["codify"] and handoffs >= 2:
        tips.append("Codifying the procedure cuts hand-off errors. Is it worth its cost here?")
    if not tips:
        tips.append("Compare your design with the standard designs below, then try moving one step at a time.")
    return tips


def page_task():
    ss = st.session_state
    rnd = current_round()
    tid = ss.task or RECOMMENDED[0]
    task = M.TASK_BY_ID[tid]
    d = design(rnd, tid)
    locked = rnd in ss.submitted
    st.button("← All workflows", on_click=go_step, args=("play",))
    st.markdown(f"### {tid} · {task['name']}")
    st.caption(f"{task['area']}. {task['desc']}")
    if locked:
        st.warning("You have submitted this round, so this design is locked. It reopens when the facilitator "
                   "starts the next round.")

    pk, ck = f"plan_{rnd}_{tid}", f"cod_{rnd}_{tid}"
    sk = [f"s_{rnd}_{tid}_{k}" for k in range(len(task["steps"]))]
    for key, val in [(pk, d["plan"]), (ck, d["codify"])] + list(zip(sk, d["alloc"])):
        if key not in ss:
            ss[key] = val
            ss[key + "__prev"] = val
    if not ROUNDS[rnd]["codify"]:
        ss[ck] = False

    score = st.empty()
    st.markdown("**Who plans the case?**")
    st.segmented_control("Who plans the case?", ["Human", "Agent"], key=pk, label_visibility="collapsed",
                         format_func=lambda v: "🧑 A person plans" if v == "Human" else "🤖 The agent plans",
                         on_change=_ctl_changed, args=(rnd, tid, pk), disabled=locked)
    if ROUNDS[rnd]["codify"]:
        st.toggle(f"📘 Codify the procedure (cuts hand-off errors by {task['cut']:.0%}, costs "
                  f"{money(task['ccod'])} per case)", key=ck, disabled=locked,
                  on_change=_ctl_changed, args=(rnd, tid, ck))
    st.markdown("**Who does each step?**")
    q1, q2, q3 = st.columns(3)
    q1.button("🤖 All to agent", key=f"allA_{rnd}_{tid}", disabled=locked, **FULL,
              on_click=_bulk, args=(rnd, tid, "A"))
    q2.button("🧑 All to people", key=f"allH_{rnd}_{tid}", disabled=locked, **FULL,
              on_click=_bulk, args=(rnd, tid, "H"))
    q3.button("↺ Today's process", key=f"reset_{rnd}_{tid}", disabled=locked, **FULL,
              on_click=_bulk, args=(rnd, tid, "reset"))
    plan_now = ss[pk]
    for k, s in enumerate(task["steps"]):
        with st.container(border=True):
            c1, c2 = st.columns([1.6, 1], vertical_alignment="center")
            fixed = s["who"] in ("A", "H")
            err = (f"agent error {s['pA']:.0%} · person error {s['pH']:.0%}" if not fixed else
                   ("only a person can do this step" if s["who"] == "H" else "only the agent can do this step"))
            flag = " ⚠️ hand-off" if (ss[sk[k]] == "H" and plan_now == "Agent") else ""
            c1.markdown(f"**{k+1}. {s['name']}**{flag}  \n<span class='muted'>{err}</span>", unsafe_allow_html=True)
            c2.segmented_control(f"Step {k+1}", ["H", "A"], key=sk[k], label_visibility="collapsed",
                                 format_func=lambda v: "🧑 Person" if v == "H" else "🤖 Agent",
                                 disabled=locked or fixed, on_change=_ctl_changed, args=(rnd, tid, sk[k]))
    d["plan"], d["codify"] = ss[pk], bool(ss[ck])
    d["alloc"] = "".join(ss[key] for key in sk)
    res = result_for(rnd, tid)
    label, cls, _ = standing(rnd, tid, res)

    with score.container():
        st.markdown(f'<div class="score"><div class="row"><div><div class="l">Value per case</div>'
                    f'<div class="v">{money(res.value)}</div></div><div><div class="l">Cases that end right</div>'
                    f'<div class="v">{res.p_correct:.0%}</div></div></div>'
                    f'<span class="badge {cls}">{label}</span> <span class="muted">&nbsp;{res.n_agent} agent · '
                    f'{res.n_human} person steps</span></div>', unsafe_allow_html=True)
        workflow_strip(task, d, res)
        with st.expander("💡 Tip", expanded=False):
            for t in hint(task, d, res, rnd):
                st.markdown(f"- {t}")

    st.markdown(f'<div class="score" style="padding:8px 14px"><b>Now:</b> {money(res.value)} per case · '
                f'{res.p_correct:.0%} end right · <span class="badge {cls}">{label}</span></div>',
                unsafe_allow_html=True)
    with st.expander("Compare with the standard designs"):
        reference_chart(task, rnd, res)
    with st.expander("Where do the errors come from?"):
        step_chart(task, d, res)
        st.caption("Bars: error of each step (orange = a person carrying out the agent's plan). Line: chance the "
                   "case is still on track after each step.")
    with st.expander("Assumptions"):
        r = ROUNDS[rnd]
        st.dataframe(pd.DataFrame([
            ("Value of a case done right", money(task["R"])), ("Cost per person step", money(task["cH"])),
            ("Cost per agent step", money(task["cA"])), ("Cost of a person planning", money(task["cplan"])),
            ("Agent plans wrong", f'{task["phiA"]:.0%}'), ("Person plans wrong", f'{task["phiH"]:.0%}'),
            ("Hand-off error per person step on the agent's plan", f'{task["eps"] * r["eps"]:.1%}'),
            ("Extra error per unsupervised agent step", f'{task["rho"] * r["rho"]:.3f}')],
            columns=["Assumption", "Value"]), hide_index=True, **FULL)

    ids = [t["id"] for t in M.TASKS]
    order = RECOMMENDED + [i for i in ids if i not in RECOMMENDED]
    nxt = order[(order.index(tid) + 1) % len(order)]
    b1, b2 = st.columns(2)
    b1.button("← All workflows", key="back2", on_click=go_step, args=("play",), **FULL)
    b2.button(f"Next: {nxt} {M.TASK_BY_ID[nxt]['name']}  →", on_click=go_step, args=("task", nxt),
              **FULL, type="primary")


def workflow_strip(task, d, res):
    chips = []
    for k, a in enumerate(d["alloc"]):
        cls = "chipA" if a == "A" else "chipH"
        hand = " handoff" if (a == "H" and d["plan"] == "Agent") else ""
        tip = f'{k+1}. {task["steps"][k]["name"]} | error {res.step_error[k]:.1%}'
        chips.append(f'<span class="chip {cls}{hand}" title="{tip}">{k+1}{"🤖" if a == "A" else "🧑"}</span>')
    st.markdown("".join(chips) + "<br><span class='muted'>🤖 square = agent · 🧑 round = person · dashed "
                "outline = hand-off</span>", unsafe_allow_html=True)


def step_chart(task, d, res):
    x = [str(k + 1) for k in range(len(task["steps"]))]
    cum, s = [], 1 - (task["phiA"] if d["plan"] == "Agent" else task["phiH"])
    for e in res.step_error:
        s *= 1 - e
        cum.append(s)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors = [COL_A if a == "A" else (COL_WARN if d["plan"] == "Agent" else COL_H) for a in d["alloc"]]
    fig.add_bar(x=x, y=res.step_error, marker_color=colors, name="Step error",
                hovertext=[s["name"] for s in task["steps"]], secondary_y=False)
    fig.add_scatter(x=x, y=cum, mode="lines+markers", name="Still on track", line=dict(color="#1F3864", width=3),
                    secondary_y=True)
    fig.update_yaxes(title_text="Step error", tickformat=".0%", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Still on track", tickformat=".0%", range=[0, 1], secondary_y=True)
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.18),
                      xaxis_title="Step", bargap=0.25)
    st.plotly_chart(fig, **FULL, config={"displayModeBar": False})


def reference_chart(task, rnd, res):
    refs = M.references(task, ROUNDS[rnd]["eps"], ROUNDS[rnd]["rho"])
    names = ["Your design", "All agent", "All person", "Agent plans, person does"]
    vals = [res.value] + [r[2].value for r in refs.values()]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=[COL_OK, "#9CA3AF", "#9CA3AF", "#9CA3AF"],
                           text=[money(v) for v in vals], textposition="auto"))
    fig.update_layout(height=210, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Value per case ($)",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, **FULL, config={"displayModeBar": False})


# ----------------------------------------------------------------- step 4: your view (the survey)
def survey_tasks():
    vis = [t for t in RECOMMENDED + [t["id"] for t in M.TASKS] if t in st.session_state.visited]
    seen = list(dict.fromkeys(vis))
    return seen if len(seen) >= 3 else list(dict.fromkeys(seen + RECOMMENDED))[:max(3, len(seen))]


def page_view():
    st.title("When should an agent get access?")
    progress_bar("view")
    st.write("Think of your own organization. Answer quickly; first instincts are useful.")

    st.markdown("#### 1 · How much access would you give the agent?")
    st.caption("For each workflow, pick a rung on the access ladder and say who should plan the case.")
    with st.expander("The access ladder", expanded=False):
        for lvl in SV.ACCESS_LEVELS:
            st.markdown(f"**{lvl}**: {SV.ACCESS_HELP[lvl]}")
    for tid in survey_tasks():
        t = M.TASK_BY_ID[tid]
        with st.container(border=True):
            st.markdown(f"**{tid} · {t['name']}**  \n<span class='muted'>{t['desc']}</span>", unsafe_allow_html=True)
            v = st.select_slider("Access for the agent", SV.ACCESS_LEVELS, value=SV.ACCESS_LEVELS[2],
                                 key=f"acc_{tid}")
            st.caption(SV.ACCESS_HELP[v])
            st.segmented_control("Who should plan (diagnose) the case?", SV.PLANNER_OPTIONS, key=f"pl_{tid}",
                                 default="Together")

    st.markdown("#### 2 · Keep the work with a person when…")
    st.pills("Pick all that apply", SV.KEEP_WITH_PERSON, selection_mode="multi", key="keep")
    st.markdown("#### 3 · Give the agent access when…")
    st.pills("Pick all that apply", SV.GIVE_TO_AGENT, selection_mode="multi", key="give")
    st.markdown(f"#### 4 · Your top {SV.TOP_GUARDRAILS} guardrails")
    g = st.pills(f"Pick up to {SV.TOP_GUARDRAILS}", SV.GUARDRAILS, selection_mode="multi", key="guard")
    if g and len(g) > SV.TOP_GUARDRAILS:
        st.warning(f"Please keep it to {SV.TOP_GUARDRAILS}: which matter most?")
    st.markdown("#### 5 · How long may an agent run unchecked?")
    nolimit = st.checkbox("No limit needed if the guardrails above are in place", key="nolimit")
    st.slider("Steps an agent may take in a row before a person checks", 1, SV.UNATTENDED_MAX, 5, key="unatt",
              disabled=nolimit)
    st.markdown("#### 6 · After the exercise")
    st.select_slider(SV.AUTONOMY_QUESTION, SV.AUTONOMY_SCALE,
                     value=st.session_state.profile.get("pre", SV.AUTONOMY_SCALE[2]), key="post")
    st.text_area("One rule you would write for your organization about agent access", key="rule", height=80,
                 placeholder="e.g. Agents may issue refunds up to $50 on their own; above that a person approves.")
    st.text_area("Which work would you never hand to an agent, and why? (optional)", key="never", height=70)

    b1, b2 = st.columns(2)
    b1.button("← Back to the workflows", on_click=go_step, args=("play",), **FULL)
    if b2.button("Submit my answers  ✓", type="primary", **FULL):
        if g and len(g) > SV.TOP_GUARDRAILS:
            st.error(f"Pick at most {SV.TOP_GUARDRAILS} guardrails.")
        else:
            submit(current_round(), feedback=True)


def feedback_rows(common: dict) -> list[dict]:
    ss = st.session_state
    rows = []

    def add(qid, question, item, answer):
        rows.append(dict(common, question_id=qid, question=question, item=item, answer=answer))

    add("pre_autonomy", SV.AUTONOMY_QUESTION, "before", ss.profile.get("pre", ""))
    add("post_autonomy", SV.AUTONOMY_QUESTION, "after", ss.get("post", ""))
    for tid in survey_tasks():
        name = f"{tid} {M.TASK_BY_ID[tid]['name']}"
        add("access_level", "Access for the agent", name, ss.get(f"acc_{tid}", ""))
        add("planner", "Who should plan the case", name, ss.get(f"pl_{tid}") or "")
    for x in ss.get("keep") or []:
        add("keep_with_person", "Keep the work with a person when", x, 1)
    for x in ss.get("give") or []:
        add("give_to_agent", "Give the agent access when", x, 1)
    for x in ss.get("guard") or []:
        add("guardrail_top", "Top guardrails", x, 1)
    add("unattended_steps", "Steps an agent may take before a person checks", "",
        "no limit" if ss.get("nolimit") else ss.get("unatt", ""))
    if (ss.get("rule") or "").strip():
        add("rule", "One rule about agent access", "", ss.rule.strip())
    if (ss.get("never") or "").strip():
        add("never", "Work never to hand to an agent", "", ss.never.strip())
    return rows


def submit(rnd: int, feedback: bool):
    ss = st.session_state
    prof = ss.profile
    _close_task_clock()
    sid = uuid.uuid4().hex[:12]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    common = dict(submitted_utc=now, submission_id=sid, app_version=APP_VERSION, session_code=prof.get("session", ""),
                  participant=prof.get("name", ""), role=prof.get("role", ""), ai_experience=prof.get("ai", ""))
    game = build_rows(rnd, common, reflection=(ss.get("never") or "").strip() if feedback else "")
    fb = feedback_rows(common) if feedback else []
    if not prof.get("consent"):
        ss.submitted[rnd] = "not-stored"
        ss.survey_done = ss.survey_done or feedback
        ss.my_feedback = fb
        go_step("done")
        st.rerun()
    try:
        with st.spinner("Saving..."):
            GAME_STORE.append(game)
            if fb:
                FB_STORE.append(fb)
        ss.submitted[rnd] = sid
        ss.survey_done = ss.survey_done or feedback
        ss.my_feedback = fb or ss.get("my_feedback", [])
        st.cache_data.clear()
        go_step("done")
        st.rerun()
    except Exception as e:
        st.error(f"Could not save your answers ({type(e).__name__}). Please press Submit again. "
                 "Your answers are still here.")


def build_rows(rnd, common, reflection=""):
    r = ROUNDS[rnd]
    common = dict(common, round=rnd, eps_multiplier=r["eps"], rho_multiplier=r["rho"])
    rows, tot = [], dict(value=0.0, opt=0.0, ref=0.0, fa=0.0, ah=0.0, sp=0.0, sec=0.0, ed=0)
    for t in M.TASKS:
        d = design(rnd, t["id"])
        res = result_for(rnd, t["id"])
        refs = M.references(t, r["eps"], r["rho"])
        best_name, best = max(refs.items(), key=lambda kv: kv[1][2].value)
        opt = optimum_cached(t["id"], r["codify"], r["eps"], r["rho"])[0]
        n = len(t["steps"])
        sec = round(st.session_state.seconds.get((rnd, t["id"]), 0.0), 1)
        ed = st.session_state.edits.get((rnd, t["id"]), 0)
        rows.append(dict(common, task_id=t["id"], task_name=t["name"], plan=d["plan"], codified=d["codify"],
                         allocation=d["alloc"], n_human=res.n_human, n_agent=res.n_agent,
                         p_correct=round(res.p_correct, 6), value=round(res.value, 4),
                         value_full_autonomy=round(refs["Full autonomy"][2].value, 4),
                         value_all_human=round(refs["All human"][2].value, 4),
                         value_split=round(refs["Agent plans, person executes"][2].value, 4),
                         best_reference=best_name, gain_over_best_reference=round(res.value - best[2].value, 4),
                         optimal_value=round(opt, 4), share_of_optimum=round(res.value / opt, 4) if opt > 0 else "",
                         is_split_design=(d["plan"] == "Agent" and res.n_human >= n / 2),
                         seconds_on_task=sec, edits=ed, reflection=""))
        tot["value"] += res.value; tot["opt"] += opt; tot["ref"] += best[2].value; tot["sec"] += sec; tot["ed"] += ed
        tot["fa"] += refs["Full autonomy"][2].value; tot["ah"] += refs["All human"][2].value
        tot["sp"] += refs["Agent plans, person executes"][2].value
    rows.append(dict(common, task_id="TOTAL", task_name="All workflows", value=round(tot["value"], 4),
                     value_full_autonomy=round(tot["fa"], 4), value_all_human=round(tot["ah"], 4),
                     value_split=round(tot["sp"], 4), gain_over_best_reference=round(tot["value"] - tot["ref"], 4),
                     optimal_value=round(tot["opt"], 4), share_of_optimum=round(tot["value"] / tot["opt"], 4),
                     seconds_on_task=round(tot["sec"], 1), edits=tot["ed"], reflection=reflection))
    return rows


@st.cache_data(show_spinner=False)
def optimum_cached(tid, codify, eps, rho):
    return M.optimum(M.TASK_BY_ID[tid], codify, eps, rho)


# ----------------------------------------------------------------- step 5: results
def page_done():
    ss = st.session_state
    rnd = current_round()
    st.title("Thank you!")
    progress_bar("done")
    if not ss.profile.get("consent"):
        st.info("You chose not to store your answers, so they were not saved. Your results are shown below.")
    else:
        st.success("Your answers are saved.")
    played = list(dict.fromkeys(ss.visited))
    if played:
        st.markdown("#### Your workflows")
        for tid in played:
            res = result_for(rnd, tid)
            label, cls, _ = standing(rnd, tid, res)
            d = design(rnd, tid)
            strip = "".join("🤖" if a == "A" else "🧑" for a in d["alloc"])
            who = "the agent plans" if d["plan"] == "Agent" else "a person plans"
            st.markdown(f'<div class="card"><h4>{tid} · {M.TASK_BY_ID[tid]["name"]}</h4>'
                        f'<span class="muted">{who} · {strip}</span><br>'
                        f'<span class="badge {cls}">{money(res.value)} per case · {label}</span></div>',
                        unsafe_allow_html=True)
    nxt = [r for r in OPEN_ROUNDS if r == rnd and r not in ss.submitted]
    if nxt:
        st.info(f"**{ROUNDS[rnd]['label']}** is open. {ROUNDS[rnd]['note']}", icon="🔁")
        st.button("Play this round  →", type="primary", on_click=go_step, args=("play",), **FULL)
    if not ss.survey_done:
        st.button("Share your view on agent access  →", on_click=go_step, args=("view",), **FULL)
    explore_menu()
    room_results()


@st.fragment(run_every=15)
def room_results():
    live = live_get()
    if not live.get("show_results"):
        st.caption("The facilitator will show how the room answered. This page updates by itself.")
        return
    st.divider()
    st.subheader("How the room answered")
    fb = load_csv("feedback")
    if fb.empty:
        st.caption("No answers yet.")
        return
    code = st.session_state.profile.get("session", "")
    sub = fb[fb.session_code.astype(str) == code] if code and (fb.session_code.astype(str) == code).any() else fb
    chart_access_ladder(sub, height=220, compact=True)
    chart_pick_share(sub, "keep_with_person", "Keep with a person when…", COL_H)
    chart_pick_share(sub, "give_to_agent", "Give the agent access when…", COL_A)


# ----------------------------------------------------------------- shared charts (participants + facilitator)
@st.cache_data(ttl=8, show_spinner=False)
def _read(which: str) -> str:
    return (FB_STORE if which == "feedback" else GAME_STORE).read()


def load_csv(which: str) -> pd.DataFrame:
    text = _read(which)
    if not text.strip():
        return pd.DataFrame(columns=storage.FEEDBACK_COLUMNS if which == "feedback" else storage.COLUMNS)
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def n_respondents(fb: pd.DataFrame) -> int:
    return fb.submission_id.nunique() if len(fb) else 0


def chart_access_ladder(fb: pd.DataFrame, height=360, compact=False):
    a = fb[fb.question_id == "access_level"]
    if a.empty:
        return
    if compact:                                   # phones: short labels, legend underneath
        a = a.assign(item=a["item"].str.split(" ").str[0])
    tab = pd.crosstab(a["item"], a["answer"], normalize="index").reindex(columns=SV.ACCESS_LEVELS, fill_value=0)
    lvl = a.answer.map({v: i for i, v in enumerate(SV.ACCESS_LEVELS)})
    med = lvl.groupby(a["item"]).median()
    tab = tab.loc[med.sort_values().index]
    fig = go.Figure()
    for lv, col in zip(SV.ACCESS_LEVELS, LADDER_COLORS):
        fig.add_bar(y=tab.index, x=tab[lv], name=lv, orientation="h", marker_color=col,
                    text=[f"{v:.0%}" if v >= 0.08 else "" for v in tab[lv]], textposition="inside",
                    insidetextanchor="middle")
    legend = (dict(orientation="h", y=-0.12, yanchor="top", x=0, traceorder="normal", font=dict(size=11))
              if compact else
              dict(orientation="h", y=1.0, yanchor="bottom", x=0, traceorder="normal", font=dict(size=11)))
    fig.update_layout(barmode="stack", height=height + (120 if compact else 40),
                      xaxis=dict(tickformat=".0%", range=[0, 1]), legend=legend,
                      margin=dict(l=10, r=10, t=40 if compact else 78, b=10),
                      title=dict(text="Access the room would give the agent", font=dict(size=16)))
    st.plotly_chart(fig, **FULL, config={"displayModeBar": False})


def chart_pick_share(fb: pd.DataFrame, qid: str, title: str, color: str, height=None):
    n = n_respondents(fb[fb.question_id.isin(["pre_autonomy"])]) or n_respondents(fb)
    q = fb[fb.question_id == qid]
    if q.empty or not n:
        return
    s = (q.groupby("item").submission_id.nunique() / n).sort_values()
    fig = go.Figure(go.Bar(x=s.values, y=s.index, orientation="h", marker_color=color,
                           text=[f"{v:.0%}" for v in s.values], textposition="outside"))
    fig.update_layout(height=height or 60 + 34 * len(s), xaxis=dict(tickformat=".0%", range=[0, 1.12]),
                      margin=dict(l=10, r=10, t=36, b=10), title=dict(text=f"{title} (share of {n})", font=dict(size=16)))
    st.plotly_chart(fig, **FULL, config={"displayModeBar": False})


# ----------------------------------------------------------------- facilitator
def join_url(live: dict) -> tuple[str, str]:
    """(url, how it was found). Priority: typed by the facilitator, public_url in the secrets, the address of a
    hosted app (Streamlit Community Cloud), a public tunnel, this computer's network address."""
    code = live.get("session", "")
    q = f"/?s={code}" if code else "/"
    if live.get("join_url"):
        return live["join_url"].rstrip("/") + q, "set by you"
    if PUBLIC_URL:
        return PUBLIC_URL + q, "public_url in the settings"
    host = _request_host()
    if host and not host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0") and not re.match(r"^\d+\.\d+\.\d+\.\d+", host):
        return f"https://{host}{q}", "address of this hosted app"
    log = BASE / "cloudflared.log"
    if log.exists():
        m = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read_text(errors="ignore"))
        if m:
            return m[-1] + q, "public link (Cloudflare tunnel)"
    try:
        import requests
        j = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=0.4).json()
        pub = [t["public_url"] for t in j.get("tunnels", []) if t.get("public_url", "").startswith("https")]
        if pub:
            return pub[0] + q, "public link (ngrok)"
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        ip = "localhost"
    port = st.get_option("server.port") or 8501
    return f"http://{ip}:{port}{q}", "this computer on the local network"


def qr_png(url: str) -> bytes:
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=10, border=2, dark="#1F3864")
    return buf.getvalue()


def page_facilitator():
    if not FAC_PASSWORD:
        st.error("Set facilitator_password under [app] in local_config.toml (or the secrets) to open this page.")
        return
    if not st.session_state.get("fac_ok"):
        st.title("Facilitator")
        pw = st.text_input("Facilitator password", type="password")
        if pw and pw == FAC_PASSWORD:
            st.session_state.fac_ok = True
            st.rerun()
        elif pw:
            st.error("Wrong password.")
        return
    tabs = st.tabs(["📺 Present", "📊 Live: agent access", "🎮 Game results", "⚙️ Data and settings"])
    with tabs[0]:
        fac_present()
    with tabs[1]:
        fac_live_access()
    with tabs[2]:
        fac_game()
    with tabs[3]:
        fac_data()


def fac_present():
    live = live_get()
    if FAC_PASSWORD in ("change-me", "seminar", "password"):
        st.warning("You are using a default facilitator password. Change facilitator_password in local_config.toml "
                   "(or in the app's Secrets on Streamlit Cloud) before sharing a public link.")
    if on_cloud() and STORE_MODE != "github":
        st.error("This app is running on Streamlit Cloud without GitHub storage. Answers are kept only until the app "
                 "restarts or goes to sleep. Add the [github] section to the app's Secrets before the seminar.")
    c1, c2 = st.columns([1.15, 1], gap="large")
    with c1:
        st.markdown("## Who should do the work?")
        st.markdown("#### Scan to join, or open the link")
        url, how = join_url(live)
        st.markdown(f'<div class="joinurl">{url}</div>', unsafe_allow_html=True)
        st.caption(f"Address: {how}.")
        st.markdown("Session code")
        st.markdown(f'<div class="bigcode">{live.get("session", "")}</div>', unsafe_allow_html=True)
        present_counter()
    with c2:
        st.image(qr_png(url), **FULL)
    with st.expander("Session controls", expanded=True):
        a, b, c = st.columns(3)
        code = a.text_input("Session code", value=live.get("session", ""), max_chars=20).strip().upper()
        rnd = b.selectbox("Open round", OPEN_ROUNDS, index=OPEN_ROUNDS.index(current_round()),
                          format_func=lambda r: ROUNDS[r]["label"])
        show = c.toggle("Show room results on participants' screens", value=bool(live.get("show_results")))
        override = st.text_input("Join address override (paste a public link here if the one above is wrong)",
                                 value=live.get("join_url", ""), placeholder="https://....trycloudflare.com")
        if st.button("Apply", type="primary"):
            live_set(session=code, round=int(rnd), show_results=bool(show), join_url=override.strip())
            st.rerun()


@st.fragment(run_every=5)
def present_counter():
    live = live_get()
    fb, game = load_csv("feedback"), load_csv("game")
    code = live.get("session", "")
    nfb = fb[fb.session_code == code].submission_id.nunique() if len(fb) else 0
    ngame = game[(game.session_code == code) & (game.task_id == "TOTAL")].participant.nunique() if len(game) else 0
    a, b = st.columns(2)
    a.metric("Answers received", nfb)
    b.metric("People who submitted designs", ngame)


def _session_filter(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df
    codes = sorted(df.session_code.unique())
    live = live_get()
    default = [live["session"]] if live.get("session") in codes else codes
    sel = st.multiselect("Sessions", codes, default=default, key=key)
    return df[df.session_code.isin(sel)]


def fac_live_access():
    fb = _session_filter(load_csv("feedback"), "sess_fb")
    live_access_charts(fb)


@st.fragment(run_every=10)
def live_access_charts(fb_static: pd.DataFrame):
    sel = st.session_state.get("sess_fb")
    fb = load_csv("feedback")
    if sel is not None and len(fb):
        fb = fb[fb.session_code.isin(sel)]
    n = n_respondents(fb)
    st.caption(f"{n} respondents. Updates every 10 seconds.")
    if not n:
        st.info("Waiting for the first answers.")
        return
    k1, k2, k3, k4 = st.columns(4)
    pre = fb[fb.question_id == "pre_autonomy"].answer.map(lambda v: int(str(v)[:1]) if str(v)[:1].isdigit() else None)
    post = fb[fb.question_id == "post_autonomy"].answer.map(lambda v: int(str(v)[:1]) if str(v)[:1].isdigit() else None)
    k1.metric("Respondents", n)
    k2.metric("Agent freedom, before (1–5)", f"{pre.mean():.1f}" if pre.notna().any() else "–")
    k3.metric("…after the exercise", f"{post.mean():.1f}" if post.notna().any() else "–",
              delta=f"{post.mean() - pre.mean():+.1f}" if pre.notna().any() and post.notna().any() else None)
    u = fb[fb.question_id == "unattended_steps"].answer
    nums = pd.to_numeric(u, errors="coerce")
    k4.metric("Median unchecked steps allowed", f"{nums.median():.0f}" if nums.notna().any() else "–",
              help=f"{(u == 'no limit').mean():.0%} said no limit is needed" if len(u) else None)
    chart_access_ladder(fb, height=90 + 60 * fb[fb.question_id == "access_level"]["item"].nunique())
    c1, c2 = st.columns(2)
    with c1:
        chart_pick_share(fb, "keep_with_person", "Keep with a person when…", COL_H)
    with c2:
        chart_pick_share(fb, "give_to_agent", "Give the agent access when…", COL_A)
    c3, c4 = st.columns(2)
    with c3:
        chart_pick_share(fb, "guardrail_top", "Top guardrails", "#CC79A7")
    with c4:
        p = fb[fb.question_id == "planner"]
        if len(p):
            tab = pd.crosstab(p["item"], p["answer"], normalize="index").reindex(columns=SV.PLANNER_OPTIONS,
                                                                                 fill_value=0)
            fig = go.Figure()
            for opt, col in zip(SV.PLANNER_OPTIONS, [COL_H, "#E69F00", COL_A]):
                fig.add_bar(y=tab.index, x=tab[opt], name=opt, orientation="h", marker_color=col)
            fig.update_layout(barmode="stack", height=90 + 45 * len(tab), xaxis=dict(tickformat=".0%"),
                              title=dict(text="Who should plan the case?", font=dict(size=16)),
                              legend=dict(orientation="h", y=-0.2), margin=dict(l=10, r=10, t=36, b=10))
            st.plotly_chart(fig, **FULL, config={"displayModeBar": False})
        if nums.notna().any():
            fig = go.Figure(go.Histogram(x=nums.dropna(), xbins=dict(start=0.5, end=SV.UNATTENDED_MAX + 0.5, size=1),
                                         marker_color=COL_A))
            fig.update_layout(height=230, title=dict(text="Steps an agent may run before a person checks",
                                                     font=dict(size=16)),
                              margin=dict(l=10, r=10, t=36, b=10), xaxis_title="steps", yaxis_title="people",
                              xaxis=dict(range=[0.5, SV.UNATTENDED_MAX + 0.5], dtick=1), bargap=0.15)
            st.plotly_chart(fig, **FULL, config={"displayModeBar": False})
    rules = fb[fb.question_id.isin(["rule", "never"])]
    if len(rules):
        st.subheader("Rules and red lines from the room")
        c1, c2 = st.columns(2)
        for col, qid, title in ((c1, "rule", "Rules for agent access"), (c2, "never", "Never hand to an agent")):
            r = rules[rules.question_id == qid].answer.str.strip()
            if len(r):
                vc = r.groupby(r.str.lower()).agg(["first", "size"]).sort_values("size", ascending=False)
                col.markdown(f"**{title}**")
                col.dataframe(pd.DataFrame({"Answer": vc["first"].values, "People": vc["size"].values}),
                              hide_index=True, **FULL)


def fac_game():
    df = _session_filter(load_csv("game"), "sess_game")
    if df.empty:
        st.info("No designs submitted yet.")
        show_answer_key()
        return
    for c in ["value", "optimal_value", "value_full_autonomy", "value_all_human", "share_of_optimum", "round"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    tasks = df[df.task_id != "TOTAL"].copy()
    totals = df[df.task_id == "TOTAL"].copy()
    edited = tasks[pd.to_numeric(tasks.edits, errors="coerce").fillna(0) > 0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Participants", df.participant.nunique())
    k2.metric("Submissions", df.submission_id.nunique())
    k3.metric("Mean share of best possible", f"{totals.share_of_optimum.mean():.0%}" if len(totals) else "–")
    k4.metric("Split designs (of redesigned)", f"{edited.is_split_design.eq('True').mean():.0%}" if len(edited) else "–")
    st.subheader("Average value per workflow (redesigned workflows only)")
    g = edited.groupby(["task_id", "round"]).agg(value=("value", "mean"), optimal=("optimal_value", "mean"),
                                                 n=("value", "size")).reset_index()
    fig = go.Figure()
    for rnd_, gg in g.groupby("round"):
        fig.add_bar(x=gg.task_id, y=gg.value, name=f"Participants, round {int(rnd_)}",
                    text=[f"n={k}" for k in gg.n], textposition="outside")
    g1 = g.drop_duplicates("task_id")
    fig.add_scatter(x=g1.task_id, y=g1.optimal, mode="markers", marker=dict(symbol="diamond", size=12, color=COL_WARN),
                    name="Best possible")
    fig.update_layout(barmode="group", height=380, yaxis_title="Value per case ($)", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, **FULL)
    c1, c2 = st.columns(2)
    with c1:
        p = edited.groupby("task_id").plan.apply(lambda s: (s == "Agent").mean()).reset_index(name="share")
        f2 = go.Figure(go.Bar(x=p.task_id, y=p.share, marker_color=COL_A))
        f2.update_layout(height=300, title="Share letting the agent plan", yaxis=dict(tickformat=".0%", range=[0, 1]))
        st.plotly_chart(f2, **FULL)
    with c2:
        cc = edited[edited["round"] >= 2]
        if len(cc):
            q = cc.groupby("task_id").codified.apply(lambda s: s.eq("True").mean()).reset_index(name="share")
            f3 = go.Figure(go.Bar(x=q.task_id, y=q.share, marker_color=COL_H))
            f3.update_layout(height=300, title="Share codifying (rounds 2–3)", yaxis=dict(tickformat=".0%", range=[0, 1]))
            st.plotly_chart(f3, **FULL)
        else:
            st.caption("No round 2 or 3 submissions yet.")
    st.subheader("Leaderboard")
    anon = st.toggle("Hide names", value=True)
    lb = totals.sort_values("value", ascending=False)[["participant", "session_code", "round", "value",
                                                         "share_of_optimum"]].copy()
    if anon:
        lb["participant"] = [f"Participant {i+1}" for i in range(len(lb))]
    lb["value"] = lb["value"].map(money)
    lb["share_of_optimum"] = lb["share_of_optimum"].map(lambda v: f"{v:.0%}" if pd.notna(v) else "")
    lb.columns = ["Participant", "Session", "Round", "Value, all 8 workflows", "Share of best possible"]
    st.dataframe(lb, hide_index=True, **FULL)
    show_answer_key()


def show_answer_key():
    with st.expander("Answer key (best designs)"):
        rows = []
        for rnd in (1, 2, 3):
            r = ROUNDS[rnd]
            for t in M.TASKS:
                v, p, plan, cod, alloc = optimum_cached(t["id"], r["codify"], r["eps"], r["rho"])
                rows.append(dict(Round=rnd, Task=t["id"], Workflow=t["name"], **{"Who plans": plan},
                                 Codify="Yes" if cod else "No", Design=" ".join(alloc), Value=money(v),
                                 **{"P(correct)": f"{p:.1%}"}))
        st.dataframe(pd.DataFrame(rows), hide_index=True, **FULL)


def fac_data():
    st.write(f"Designs are saved to **{GAME_STORE.label}**.  \nSurvey answers are saved to **{FB_STORE.label}**.")
    if STORE_MODE == "local-git":
        if st.button("Commit" + (" and push" if GAME_STORE.push else "") + " now"):
            GAME_STORE.sync("exercise: responses (facilitator sync)")
            FB_STORE.sync("exercise: feedback (facilitator sync)")
        st.caption(f"Git: {GAME_STORE.last_git_message}")
    c1, c2 = st.columns(2)
    c1.download_button("Download designs (responses.csv)", _read("game") or "", file_name="responses.csv",
                       mime="text/csv", **FULL)
    c2.download_button("Download survey answers (feedback.csv)", _read("feedback") or "", file_name="feedback.csv",
                       mime="text/csv", **FULL)
    base = join_url(live_get())[0].split("/?")[0]
    st.caption(f"Participant link: {base}  ·  Facilitator: add ?view=facilitator  ·  Articles only: add ?view=library  ·  "
               f"Storage: {STORE_MODE}" + (" (Streamlit Cloud)" if on_cloud() else ""))


# ----------------------------------------------------------------- explore: workflow labs and the library
def explore_menu(here=""):
    """Buttons to the two workflow labs and the library (shown on the play hub and the results page)."""
    st.markdown("#### Go further")
    c1, c2, c3 = st.columns(3)
    c1.button("🧭 Lab A · Rights Allocation Sprint", on_click=go_step, args=("lab_a",), **FULL,
              disabled=here == "lab_a", help="Design a workflow in four moves and compare it with the best possible.")
    c2.button("🔎 Lab B · Hand-off Audit Loop", on_click=go_step, args=("lab_b",), **FULL,
              disabled=here == "lab_b", help="Audit a live design week by week and decide when to change it.")
    c3.button("📚 Read the articles", on_click=go_step, args=("library",), **FULL, disabled=here == "library")


def _strip(alloc, plan="Agent"):
    chips = []
    for k, a in enumerate(alloc):
        hand = " handoff" if (a == "H" and plan == "Agent") else ""
        chips.append(f'<span class="chip {"chipA" if a == "A" else "chipH"}{hand}">{k+1}{"🤖" if a == "A" else "🧑"}</span>')
    return "".join(chips)


def _save_lab(rows):
    prof = st.session_state.profile
    if not prof.get("consent"):
        return "Not stored (you chose not to store answers)."
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sid = uuid.uuid4().hex[:12]
    common = dict(submitted_utc=now, submission_id=sid, app_version=APP_VERSION, session_code=prof.get("session", ""),
                  participant=prof.get("name", ""), role=prof.get("role", ""), ai_experience=prof.get("ai", ""))
    try:
        FB_STORE.append([dict(common, **r) for r in rows])
        st.cache_data.clear()
        return "Saved."
    except Exception as e:
        return f"Could not save ({type(e).__name__})."


SPRINT_MOVES = ["Pick a workflow", "1 · Two candidates", "2 · Bundle execution", "3 · Break long runs",
                "4 · Codify?", "Result"]


def page_lab_a():
    import workflows as W
    ss = st.session_state
    rnd = current_round()
    r = ROUNDS[rnd]
    ss.setdefault("la_move", 0)
    ss.setdefault("la_task", "T3")
    st.button("← Back", on_click=go_step, args=("done" if ss.survey_done else "play",))
    st.markdown("## 🧭 Lab A · The Rights Allocation Sprint")
    st.caption("Four moves that design a workflow before an agent goes live. Each move is a rule you can apply with a "
               "spreadsheet; the app does the arithmetic so you can watch what each move changes.")
    mv = ss.la_move
    st.markdown('<div class="steps">' + "".join(
        f'<span class="{"on" if i == mv else ("done" if i < mv else "")}">{m}</span>' for i, m in enumerate(SPRINT_MOVES))
        + "</div>", unsafe_allow_html=True)
    tid = ss.la_task
    t = M.TASK_BY_ID[tid]
    eps_m, rho_m, cod_ok = r["eps"], r["rho"], r["codify"]
    traces = {}
    cands = {}
    for plan in ("Human", "Agent"):
        tr = []
        alloc, cod = W.sprint_candidate(t, plan, cod_ok, eps_m, rho_m, trace=tr)
        traces[plan] = dict(tr)
        res = M.evaluate(t, alloc, plan, cod, eps_m, rho_m)
        cands[plan] = (alloc, cod, res)

    def nav(back=True, nxt="Next  →"):
        b1, b2 = st.columns(2)
        if back:
            b1.button("← Previous move", on_click=lambda: ss.update(la_move=ss.la_move - 1), **FULL)
        b2.button(nxt, type="primary", on_click=lambda: ss.update(la_move=ss.la_move + 1), **FULL)

    if mv == 0:
        opts = [x["id"] for x in M.TASKS]
        st.selectbox("Workflow", opts, index=opts.index(tid), key="la_task_pick",
                     format_func=lambda i: f"{i} · {M.TASK_BY_ID[i]['name']} ({len(M.TASK_BY_ID[i]['steps'])} steps)",
                     on_change=lambda: ss.update(la_task=ss.la_task_pick))
        t = M.TASK_BY_ID[ss.la_task]
        st.markdown(f"*{t['desc']}*")
        st.markdown("  \n".join(f"{k+1}. {s['name']}" + (" *(person only)*" if s["who"] == "H" else "")
                                for k, s in enumerate(t["steps"])))
        st.caption(f"Rules of {r['label']}.")
        nav(back=False, nxt="Start the sprint  →")
    elif mv == 1:
        st.subheader("Move 1 · Build two candidates, one for each planner")
        st.write("Do not decide up front who plans. Build one design in which a **person plans** the case and one in "
                 "which the **agent plans**, then keep the better. What decides it is who holds the knowledge the plan "
                 "needs, and what a person's planning time costs.")
        st.markdown(f'<div class="score"><div class="row"><div><div class="l">Agent plans wrong</div><div class="v">'
                    f'{t["phiA"]:.0%}</div></div><div><div class="l">Person plans wrong</div><div class="v">{t["phiH"]:.0%}'
                    f'</div></div><div><div class="l">Cost of a person planning</div><div class="v">{money(t["cplan"])}'
                    f'</div></div></div></div>', unsafe_allow_html=True)
        st.segmented_control("Your prediction: which candidate will win?", ["Human", "Agent"], key="la_pred",
                             format_func=lambda v: "🧑 A person plans" if v == "Human" else "🤖 The agent plans")
        nav()
    elif mv == 2:
        st.subheader("Move 2 · Bundle execution with the plan")
        st.write("Give the agent every step it can do. Keep a person on a step only where they are so much more "
                 "accurate that the gain beats the labor saved:")
        eps_e = t["eps"] * eps_m
        st.markdown(f'<div class="rule">Keep a person on a step if<br><b>case value × (agent error − person error − '
                    f'hand-off error) &gt; labor saved per step</b><br><span class="muted">Here: case value {money(t["R"])}, '
                    f'labor saved {money(t["cH"] - t["cA"])}, hand-off error {eps_e:.0%} (it counts only when the agent '
                    f'plans and a person executes).</span></div>', unsafe_allow_html=True)
        for plan in ("Human", "Agent"):
            st.markdown(f"**{'🧑 A person plans' if plan == 'Human' else '🤖 The agent plans'}**")
            st.markdown(_strip(traces[plan]["bundle"], plan), unsafe_allow_html=True)
        st.caption("Square = agent step · round = person step · dashed outline = hand-off. Person-only steps stay "
                   "with people.")
        nav()
    elif mv == 3:
        st.subheader("Move 3 · Break long unchecked runs")
        st.write("Errors build up when the agent runs many steps with nobody looking. A person checkpoint in the "
                 "middle of a run of *m* steps saves about R·ρ·m²/4 and costs C, so split any run longer than m* with evenly "
                 "spaced checkpoints:")
        st.markdown('<div class="rule"><b>m* = 2 × √( C ÷ (case value × build-up ρ) )</b><br>where C, the cost of a '
                    'checkpoint, is the labor it adds plus case value × (person error − agent error + hand-off error '
                    'if the agent plans).</div>', unsafe_allow_html=True)
        for plan in ("Human", "Agent"):
            m_star = W.checkpoint_threshold(t, plan, False, eps_m, rho_m)
            ms = "no limit (errors do not build up)" if m_star == math.inf else f"{m_star:.1f} steps"
            st.markdown(f"**{'🧑 A person plans' if plan == 'Human' else '🤖 The agent plans'}**: longest run "
                        f"worth tolerating m* = {ms}")
            st.markdown(_strip(traces[plan]["checkpoints"], plan), unsafe_allow_html=True)
        nav()
    elif mv == 4:
        st.subheader("Move 4 · Codify only where hand-offs remain")
        if not cod_ok:
            st.info("Codifying is not available in this round. The facilitator opens it in Round 2.")
        else:
            alloc_a = traces["Agent"]["checkpoints"]
            h = alloc_a.count("H")
            gain = t["R"] * h * t["eps"] * eps_m * t["cut"]
            st.write("Writing the procedure down cuts the hand-off error but costs money on every case. Codify the "
                     "agent-planned candidate only if:")
            st.markdown(f'<div class="rule"><b>case value × hand-offs × hand-off error × cut &gt; cost of codifying</b><br>'
                        f'Here: {money(t["R"])} × {h} × {t["eps"] * eps_m:.0%} × {t["cut"]:.0%} = <b>{money(gain)}</b> '
                        f'against <b>{money(t["ccod"])}</b> per case → <b>{"codify" if gain > t["ccod"] else "do not codify"}'
                        f'</b>.</div>', unsafe_allow_html=True)
            st.caption("A person-planned candidate has no hand-offs, so codifying cannot help it.")
        nav()
    else:
        st.subheader("Result")
        win = max(cands, key=lambda p: cands[p][2].value)
        for plan in ("Human", "Agent"):
            alloc, cod, res = cands[plan]
            tag = " · ✅ kept" if plan == win else ""
            st.markdown(f'<div class="card"><h4>{"🧑 A person plans" if plan == "Human" else "🤖 The agent plans"}{tag}'
                        f'</h4>{_strip(alloc, plan)}<br><span class="muted">{"codified · " if cod else ""}'
                        f'{res.p_correct:.0%} of cases end right</span> · <b>{money(res.value)}</b> per case</div>',
                        unsafe_allow_html=True)
        pred = ss.get("la_pred")
        if pred:
            st.write(("✅ Your prediction was right." if pred == win else "❌ Your prediction was wrong.")
                     + f" The {'person' if win == 'Human' else 'agent'}-planned design wins.")
        opt = optimum_cached(tid, cod_ok, eps_m, rho_m)
        refs = M.references(t, eps_m, rho_m)
        best_ref = max(v[2].value for v in refs.values())
        mine = result_for(rnd, tid).value if tid in ss.visited else None
        rows = [("The sprint", cands[win][2].value), ("Best possible (exhaustive search)", opt[0]),
                ("Best standard design", best_ref), ("Agent plans, person does every step", refs["Agent plans, person executes"][2].value)]
        if mine is not None:
            rows.insert(1, ("Your own design from the game", mine))
        fig = go.Figure(go.Bar(x=[v for _, v in rows], y=[n for n, _ in rows], orientation="h",
                               marker_color=[COL_OK] + ["#9CA3AF"] * (len(rows) - 1), text=[money(v) for _, v in rows],
                               textposition="auto"))
        fig.update_layout(height=60 + 42 * len(rows), margin=dict(l=10, r=10, t=10, b=10),
                          yaxis=dict(autorange="reversed"), xaxis_title="Value per case ($)")
        st.plotly_chart(fig, config={"displayModeBar": False}, **FULL)
        if opt[0] > 0:
            st.success(f"Four simple moves reach **{cands[win][2].value / opt[0]:.0%}** of the best possible value "
                       "in this workflow.")
        refl = st.text_area("Which move changed the design most here, and why?", key="la_refl", height=70)
        b1, b2 = st.columns(2)
        b1.button("↺ Try another workflow", on_click=lambda: ss.update(la_move=0), **FULL)
        if b2.button("Save my answers", type="primary", **FULL):
            msg = _save_lab([
                dict(question_id="lab_a_prediction", question="Which candidate will win", item=f"{tid} round {rnd}",
                     answer=pred or ""),
                dict(question_id="lab_a_result", question="Sprint share of best possible", item=f"{tid} round {rnd}",
                     answer=round(cands[win][2].value / opt[0], 4) if opt[0] > 0 else ""),
                dict(question_id="lab_a_reflection", question="Which move changed the design most", item=tid,
                     answer=refl.strip())])
            st.toast(msg)
    explore_menu("lab_a")


AUDIT_OPTIONS = {"keep": "Keep the design", "codify": "Codify the procedure",
                 "person": "Re-bundle: a person plans", "agent": "Re-bundle: the agent does it all"}


def page_lab_b():
    import workflows as W
    ss = st.session_state
    t = M.TASK_BY_ID[W.AUDIT_TASK]
    alloc = W.AUDIT_ALLOC
    thr = W.design_break_even(t, alloc)
    st.button("← Back", on_click=go_step, args=("done" if ss.survey_done else "play",))
    st.markdown("## 🔎 Lab B · The Hand-off Audit Loop")
    st.write(f"**The situation.** In *{t['name']}* the agent diagnoses the case and works the back end (steps 1, 2, "
             "8 and 9). The customer carries out the device steps 3 to 7, following the agent's instructions. Every "
             "one of those steps is a **hand-off**.")
    st.markdown(_strip(alloc, "Agent"), unsafe_allow_html=True)
    st.markdown(f"This design only pays if the **hand-off error stays below {thr:.1%}**, its break-even point. "
                "Above it, a design without routine hand-offs earns more per case. Nobody knows the true hand-off error, "
                "so you will measure it from the logs, week by week, and decide.")
    if "lb" not in ss or ss.get("lb_reset"):
        ss.lb = dict(started=False)
        ss.lb_reset = False
    lb = ss.lb
    if not lb["started"]:
        c1, c2 = st.columns(2)
        cases = c1.segmented_control("Cases per week", [10, 25, 50, 100], default=25, key="lb_cases")
        upg = c2.checkbox("Surprise me: a model upgrade may arrive mid-audit", value=False, key="lb_upg")
        if st.button("Start the audit", type="primary", **FULL):
            rng = random.Random()
            lb.update(started=True, eps=rng.choice([0.005, 0.02, 0.06, 0.18]), cases=int(cases or 25), week=0,
                      T=0, F=0, hist=[], upgrade_week=(3 if upg else None), decided=None, seed=rng.random())
            st.rerun()
        return

    def true_eps(week):
        return lb["eps"] * (0.5 if lb["upgrade_week"] and week >= lb["upgrade_week"] else 1.0)

    if lb["decided"] is None:
        c1, c2 = st.columns(2)
        if c1.button(f"▶ Run week {lb['week'] + 1}", type="primary", **FULL, disabled=lb["week"] >= 8):
            rng = random.Random(lb["seed"] * 1000 + lb["week"])
            w = lb["week"] + 1
            T, F = W.simulate_week(t, alloc, true_eps(w), lb["cases"], rng)
            lb["T"] += T
            lb["F"] += F
            lb["week"] = w
            est, lo, hi = W.estimate_eps(t, alloc, lb["T"], lb["F"])
            lb["hist"].append(dict(week=w, est=est, lo=lo, hi=hi, crossings=lb["T"], failures=lb["F"]))
            st.rerun()
        if c2.button("↺ Restart the count from next week", **FULL, disabled=lb["week"] == 0,
                     help="Use this after something changes, such as a model upgrade, so old logs do not mix with new."):
            lb["T"] = lb["F"] = 0
            lb["hist"].append(dict(week=lb["week"], est=None, lo=None, hi=None, crossings=0, failures=0, reset=True))
            st.rerun()
    if lb["upgrade_week"] and lb["week"] >= lb["upgrade_week"] - 1:
        st.info(f"📣 A new agent model goes live in week {lb['upgrade_week']}. Does your audit still measure the "
                "design you are running?", icon="🔁")
    pts = [h for h in lb["hist"] if h.get("est") is not None]
    if pts:
        fig = go.Figure()
        ys = [max(0.0, h["est"]) for h in pts]
        fig.add_scatter(x=[h["week"] for h in pts], y=ys, mode="lines+markers", name="Estimate",
                        line=dict(color=COL_A, width=3),
                        error_y=dict(type="data", symmetric=False, array=[h["hi"] - y for h, y in zip(pts, ys)],
                                     arrayminus=[y - h["lo"] for h, y in zip(pts, ys)], color=COL_A))
        fig.add_hline(y=thr, line=dict(color=COL_WARN, dash="dash", width=2),
                      annotation_text=f"break-even {thr:.1%}", annotation_position="top left")
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), xaxis=dict(title="week", dtick=1),
                          yaxis=dict(title="hand-off error", tickformat=".0%", rangemode="tozero"), showlegend=False)
        st.plotly_chart(fig, config={"displayModeBar": False}, **FULL)
        last = pts[-1]
        rec = W.audit_decision(last["est"], last["lo"], last["hi"], thr)
        st.markdown(f"After **{lb['T']} hand-offs** ({lb['F']} failed): estimated hand-off error **{max(0.0, last['est']):.1%}** "
                    f"(90% interval {last['lo']:.1%} to {last['hi']:.1%}). The loop's rule says: **{rec}**.")
        st.caption("Rule: re-bundle when the whole interval is above break-even; keep when it is entirely below; "
                   "otherwise collect more cases.")
    elif lb["week"] == 0:
        st.caption("Run the first week to see the logs.")
    if lb["decided"] is None and lb["week"] > 0:
        choice = st.radio("Your decision now", list(AUDIT_OPTIONS), format_func=AUDIT_OPTIONS.get, key="lb_choice",
                          horizontal=False)
        if st.button("Decide and reveal the truth", **FULL):
            lb["decided"] = (choice, lb["week"])
            st.rerun()
    if lb["decided"]:
        choice, wk = lb["decided"]
        e_now = true_eps(wk + 1)
        mult = e_now / t["eps"]
        full = "".join("H" if s["who"] == "H" else "A" for s in t["steps"])
        vals = {"keep": M.evaluate(t, alloc, "Agent", False, mult).value,
                "codify": M.evaluate(t, alloc, "Agent", True, mult).value,
                "person": W.best_value(t, plan="Human")[0],
                "agent": M.evaluate(t, full, "Agent", False, mult).value}
        best = max(vals, key=vals.get)
        st.subheader("The truth")
        st.write(f"The true hand-off error was **{lb['eps']:.1%}**"
                 + (f", halved to **{e_now:.1%}** by the upgrade" if lb["upgrade_week"] and wk + 1 >= lb["upgrade_week"]
                    else "") + f". Break-even is {thr:.1%}.")
        fig = go.Figure(go.Bar(x=[vals[k] for k in AUDIT_OPTIONS], y=[AUDIT_OPTIONS[k] for k in AUDIT_OPTIONS],
                               orientation="h", text=[money(vals[k]) for k in AUDIT_OPTIONS], textposition="auto",
                               marker_color=[COL_OK if k == best else ("#F59E0B" if k == choice else "#9CA3AF")
                                             for k in AUDIT_OPTIONS]))
        fig.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(autorange="reversed"),
                          xaxis_title="Value per case at the true hand-off error ($)")
        st.plotly_chart(fig, config={"displayModeBar": False}, **FULL)
        if choice == best:
            st.success(f"Your decision ({AUDIT_OPTIONS[choice]}) was the best option, reached after {wk} week(s).")
        else:
            st.warning(f"You chose *{AUDIT_OPTIONS[choice]}*; the best option was *{AUDIT_OPTIONS[best]}*, worth "
                       f"{money(vals[best] - vals[choice])} more per case.")
        b1, b2 = st.columns(2)
        b1.button("↺ Run another audit", on_click=lambda: ss.update(lb_reset=True), **FULL)
        if b2.button("Save my answers", type="primary", **FULL, key="lb_save"):
            msg = _save_lab([dict(question_id="lab_b_decision", question="Audit decision", item=f"true eps {lb['eps']}",
                                  answer=f"{choice}; week {wk}; cases/week {lb['cases']}; best {best}")])
            st.toast(msg)
    explore_menu("lab_b")


LIBRARY = [
    ("autonomy_paradox.pdf", "The Autonomy Paradox: When Does Agentic AI Create or Destroy Organizational Value?",
     "Research article: the decision-rights theory and the evidence behind this exercise (benchmark experiments, "
     "real-user logs, multi-agent failures)."),
    ("autonomy_paradox_supplement.pdf", "The Autonomy Paradox: Online Supplement",
     "Proofs, robustness checks, full study results, the control procedures and the replication guide."),
    ("misqe_who_should_do_the_work.pdf", "Stop Splitting the Work: Two Workflows for Deciding When AI Agents Get Access",
     "Practitioner article: the three forces, the Rights Allocation Sprint, the Hand-off Audit Loop and their fit with "
     "AI governance frameworks."),
    ("misqe_online_appendix.pdf", "Online Appendix: Teaching the Two Workflows",
     "The classroom game, both labs, the access questionnaire and a 75-minute session plan."),
]
STATIC = BASE / "static"


def page_library():
    ss = st.session_state
    if not IS_LIBRARY:
        st.button("← Back", on_click=go_step, args=("done" if ss.get("survey_done") else
                                                   ("play" if ss.get("profile", {}).get("ok") else "join"),))
    st.title("📚 The articles")
    st.write("Read in the browser or download. On a phone, *Open* shows the PDF in a new tab.")
    found = False
    for fname, title, desc in LIBRARY:
        f = STATIC / fname
        if not f.exists():
            continue
        found = True
        with st.container(border=True):
            st.markdown(f"**{title}**  \n<span class='muted'>{desc}</span>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.link_button("Open", f"app/static/{fname}", **FULL)
            c2.download_button("Download PDF", f.read_bytes(), file_name=fname, mime="application/pdf", **FULL,
                               key=f"dl_{fname}")
            with st.expander("Read here"):
                st.markdown(f'<iframe src="app/static/{fname}" width="100%" height="760" style="border:1px solid '
                            f'#E5E7EB;border-radius:8px"></iframe>', unsafe_allow_html=True)
    if not found:
        st.info("No articles are installed. Put the PDFs in the app's static/ folder.")


# ----------------------------------------------------------------- router
IS_LIBRARY = VIEW == "library"


def main():
    if IS_FAC:
        page_facilitator()
        return
    if IS_LIBRARY:
        page_library()
        return
    init_state()
    step = st.session_state.step
    if step not in ("join", "library") and not st.session_state.profile.get("ok"):
        step = "join"
    {"join": page_join, "how": page_how, "play": page_play, "task": page_task, "view": page_view,
     "done": page_done, "lab_a": page_lab_a, "lab_b": page_lab_b, "library": page_library}.get(step, page_join)()


main()
