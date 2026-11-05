"""Two practitioner workflows derived from the exercise model (exercise_model.py).

Workflow A, the Rights Allocation Sprint, designs a workflow before deployment in four moves:
  1. Build two candidates: one where a person plans, one where the agent plans.
  2. Bundle execution: give the agent every step it can do, except steps where a person is so much more accurate
     that the gain beats the extra labor (R * (pA - pH - eps_if_agent_plans) > cH - cA).
  3. Break long runs: insert a person checkpoint in any unchecked agent run longer than
         m* = 2 * sqrt(C / (R * rho)),  C = (cH - cA) + R * (pH_bar - pA_bar + eps * [agent plans])
     (a checkpoint in the middle of a run of length m saves about R*rho*m^2/4 of build-up loss).
  4. Codify only if hand-offs remain and  R * handoffs * eps * cut > cost of codifying.
  Keep the candidate with the higher value per case.

Workflow B, the Hand-off Audit Loop, runs after deployment: log the outcome of every hand-off (a person step
carried out on the agent's plan), estimate the hand-off error with an interval, compare it with the break-even
hand-off error of the workflow and act (keep, codify or re-bundle). Re-run the loop after every model upgrade.

All numbers are hypothetical teaching numbers.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import exercise_model as M


# ----------------------------------------------------------------- Workflow A: Rights Allocation Sprint
def _eps_eff(task, codify, eps_mult):
    return task["eps"] * eps_mult * ((1 - task["cut"]) if codify else 1.0)


def checkpoint_threshold(task, plan: str, codify: bool, eps_mult=1.0, rho_mult=1.0) -> float:
    """Longest unchecked agent run worth tolerating (m*). Infinite when errors do not build up."""
    rho = task["rho"] * rho_mult
    if rho <= 0:
        return math.inf
    steps = [s for s in task["steps"] if s["who"] == "B"] or task["steps"]
    pH = sum(s["pH"] for s in steps) / len(steps)
    pA = sum(s["pA"] for s in steps) / len(steps)
    eps = _eps_eff(task, codify, eps_mult) if plan == "Agent" else 0.0
    C = (task["cH"] - task["cA"]) + task["R"] * max(0.0, pH - pA + eps)
    return 2.0 * math.sqrt(C / (task["R"] * rho))


def _runs(alloc: str):
    """(start, length) of maximal runs of agent steps."""
    out, i = [], 0
    while i < len(alloc):
        if alloc[i] == "A":
            j = i
            while j < len(alloc) and alloc[j] == "A":
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def sprint_candidate(task, plan: str, codify_allowed: bool, eps_mult=1.0, rho_mult=1.0, trace=None):
    """Moves 2-4 of the sprint for one planner. Returns (alloc, codify)."""
    trace = trace if trace is not None else []
    steps = task["steps"]
    codify = False
    eps = _eps_eff(task, codify, eps_mult) if plan == "Agent" else 0.0
    R, dc = task["R"], task["cH"] - task["cA"]
    # move 2: bundle execution with the planner's side; keep a person only where they are much more accurate
    alloc = []
    for s in steps:
        if s["who"] == "H":
            alloc.append("H")
        elif s["who"] == "A":
            alloc.append("A")
        else:
            alloc.append("H" if R * (s["pA"] - s["pH"] - eps) > dc else "A")
    alloc = "".join(alloc)
    trace.append(("bundle", alloc))
    # move 3: break long runs
    alloc = _break_runs(task, alloc, plan, codify, eps_mult, rho_mult)
    trace.append(("checkpoints", alloc))
    # move 4: codify if hand-offs remain and the expected gain beats the cost
    if codify_allowed and plan == "Agent":
        handoffs = alloc.count("H")
        gain = R * handoffs * task["eps"] * eps_mult * task["cut"]
        if handoffs and gain > task["ccod"]:
            codify = True
            alloc = _break_runs(task, alloc, plan, codify, eps_mult, rho_mult)   # cheaper checkpoints: re-check runs
            trace.append(("codify", alloc))
    return alloc, codify


def _break_runs(task, alloc, plan, codify, eps_mult, rho_mult):
    """Split every unchecked agent run longer than m* with evenly spaced person checkpoints."""
    m_star = checkpoint_threshold(task, plan, codify, eps_mult, rho_mult)
    steps = task["steps"]
    alloc = list(alloc)
    for s0, L in _runs("".join(alloc)):
        if L <= m_star:
            continue
        q = 1
        while (L - q) / (q + 1) > m_star and q < L - 1:      # checkpoints needed so that every sub-run is <= m*
            q += 1
        for j in range(1, q + 1):
            target = s0 + round(j * (L + 1) / (q + 1)) - 1
            cand = [k for k in range(max(s0, target - 1), min(s0 + L - 1, target + 1) + 1) if steps[k]["who"] == "B"]
            if cand:
                k = min(cand, key=lambda k: (abs(k - target), steps[k]["pH"] - steps[k]["pA"]))
                alloc[k] = "H"
    return "".join(alloc)


@dataclass
class SprintResult:
    plan: str
    codify: bool
    alloc: str
    value: float
    p_correct: float
    candidates: dict = field(default_factory=dict)     # plan -> (alloc, codify, value)
    m_star: float = math.inf


def rights_allocation_sprint(task, codify_allowed=True, eps_mult=1.0, rho_mult=1.0) -> SprintResult:
    cands = {}
    for plan in ("Human", "Agent"):
        alloc, cod = sprint_candidate(task, plan, codify_allowed, eps_mult, rho_mult)
        r = M.evaluate(task, alloc, plan, cod, eps_mult, rho_mult)
        cands[plan] = (alloc, cod, r.value, r.p_correct)
    plan = max(cands, key=lambda p: cands[p][2])
    alloc, cod, v, p = cands[plan]
    return SprintResult(plan, cod, alloc, v, p, cands, checkpoint_threshold(task, plan, cod, eps_mult, rho_mult))


# ----------------------------------------------------------------- break-even hand-off error
def best_value(task, plan=None, alloc_filter=None, codify=False, eps_mult=1.0, rho_mult=1.0):
    """Exhaustive best value over feasible allocations (optionally for one planner)."""
    import itertools
    best = None
    for pl in ([plan] if plan else ["Human", "Agent"]):
        for a in itertools.product("AH", repeat=len(task["steps"])):
            a = "".join(a)
            if not M.feasible(task, a) or (alloc_filter and not alloc_filter(a)):
                continue
            r = M.evaluate(task, a, pl, codify, eps_mult, rho_mult)
            if best is None or r.value > best[0]:
                best = (r.value, pl, a)
    return best


def _no_handoff_value(task, eps_mult, rho_mult):
    """Best value without routine hand-offs: the best person-planned design, or full autonomy."""
    full = "".join("H" if s["who"] == "H" else "A" for s in task["steps"])
    return max(best_value(task, plan="Human", rho_mult=rho_mult)[0],
               M.evaluate(task, full, "Agent", False, eps_mult, rho_mult).value)


def _bisect(gap, tol=1e-5, hi=0.5):
    if gap(0.0) <= 0:
        return 0.0
    if gap(hi) > 0:
        return hi
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
    return lo


def break_even_eps(task, rho_mult=1.0):
    """Break-even hand-off error of the person-heavy split: the largest hand-off error at which a design where the
    agent plans and people carry out at least half of the steps (best placement) still matches the best design
    without routine hand-offs. 0 if such designs lose even with no hand-off error."""
    n = len(task["steps"])
    heavy = lambda a: a.count("H") >= n / 2

    def gap(e):
        mult = e / task["eps"] if task["eps"] > 0 else 0.0
        v = best_value(task, plan="Agent", alloc_filter=heavy, eps_mult=mult, rho_mult=rho_mult)[0]
        return v - _no_handoff_value(task, mult, rho_mult)
    return _bisect(gap)


def design_break_even(task, alloc, rho_mult=1.0):
    """Break-even hand-off error of one design in which the agent plans: above it, re-bundling pays."""
    def gap(e):
        mult = e / task["eps"] if task["eps"] > 0 else 0.0
        return M.evaluate(task, alloc, "Agent", False, mult, rho_mult).value - _no_handoff_value(task, mult, rho_mult)
    return _bisect(gap)


# The design used in the audit-loop exercise: in mobile-data troubleshooting the agent plans and works the back end
# (steps 1, 2, 8, 9) while the customer's device steps (3-7) are carried out by a person following its instructions.
AUDIT_TASK, AUDIT_ALLOC = "T1", "AAHHHHHAA"


# ----------------------------------------------------------------- Workflow B: Hand-off Audit Loop
def simulate_week(task, alloc, eps_true, cases, rng: random.Random):
    """Simulated hand-off log for one week of a design where the agent plans: returns (crossings, failures)
    of person steps carried out on the agent's plan. Each crossing fails with p_H(step) + eps_true."""
    hsteps = [k for k, a in enumerate(alloc) if a == "H"]
    fails = trials = 0
    for _ in range(cases):
        for k in hsteps:
            trials += 1
            if rng.random() < task["steps"][k]["pH"] + eps_true:
                fails += 1
    return trials, fails


def estimate_eps(task, alloc, trials, fails):
    """Hand-off error estimate and 90% Wilson interval: observed failure rate minus the person's own error rate."""
    if trials == 0:
        return float("nan"), float("nan"), float("nan")
    hsteps = [k for k, a in enumerate(alloc) if a == "H"]
    base = sum(task["steps"][k]["pH"] for k in hsteps) / len(hsteps)
    z = 1.645
    p = fails / trials
    den = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / den
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / den
    return p - base, max(0.0, centre - half - base), centre + half - base


def audit_decision(est, lo, hi, threshold):
    if math.isnan(est):
        return "collect more cases"
    if lo > threshold:
        return "re-bundle or codify"
    if hi < threshold:
        return "keep the design"
    return "collect more cases"


def audit_power(task, alloc, eps_true, threshold, cases_per_week, weeks=4, reps=400, seed=7):
    """Share of simulated audits that reach each decision within `weeks` weeks (pooling the weeks)."""
    rng = random.Random(seed)
    out = {"re-bundle or codify": 0, "keep the design": 0, "collect more cases": 0}
    week_hit = []
    for _ in range(reps):
        T = F = 0
        decided = None
        for w in range(1, weeks + 1):
            t, f = simulate_week(task, alloc, eps_true, cases_per_week, rng)
            T += t
            F += f
            d = audit_decision(*estimate_eps(task, alloc, T, F), threshold)
            if d != "collect more cases":
                decided = (d, w)
                break
        if decided:
            out[decided[0]] += 1
            week_hit.append(decided[1])
        else:
            out["collect more cases"] += 1
    return {k: v / reps for k, v in out.items()}, (sum(week_hit) / len(week_hit) if week_hit else float("nan"))


# ----------------------------------------------------------------- random workflows for robustness checks
def random_task(rng: random.Random, n=None):
    n = n or rng.randint(4, 12)
    steps = []
    for k in range(n):
        who = "B" if rng.random() > 0.12 else "H"
        pA = round(rng.uniform(0.005, 0.05), 3)
        pH = round(rng.uniform(0.005, 0.04), 3)
        steps.append(dict(name=f"step {k+1}", who=who, pA=0.0 if who == "H" else pA, pH=pH))
    phiH = round(rng.uniform(0.01, 0.06), 3)
    return dict(id="RND", name="random", area="", desc="", R=rng.choice([10, 20, 40, 60, 80, 120]),
                cH=round(rng.uniform(1.5, 6.0), 2), cA=round(rng.uniform(0.03, 0.2), 2),
                cplan=round(rng.uniform(2, 18), 1), phiA=round(phiH + rng.choice([0.0, 0.01, 0.03, 0.1, 0.3]), 3),
                phiH=phiH, eps=round(rng.choice([0.02, 0.05, 0.1, 0.18, 0.25]), 3),
                rho=round(rng.choice([0.0, 0.01, 0.02, 0.03, 0.04]), 3), cut=rng.choice([0.4, 0.5, 0.6, 0.7]),
                ccod=round(rng.uniform(0.3, 2.0), 2), steps=steps)
