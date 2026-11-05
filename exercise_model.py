"""Decision-rights model behind the agent-delegation exercise.

Identical to the Excel workbook (Agent_Delegation_Exercise_*.xlsx) and to the
model in 'The Autonomy Paradox':
  * agent step  : error = p_A + rho_eff * (agent steps already run since the last human step)
  * human step  : error = p_H + epsilon_eff   if the AGENT plans (hand-off error), else p_H
  * whole case  : P(correct) = (1 - planning error) * prod(1 - step error)
  * value       : R * P(correct) - c_H * #human - c_A * #agent - planning cost (person plans) - codification cost
epsilon_eff = epsilon * eps_mult * (1 - cut if codified);  rho_eff = rho * rho_mult.
All workflows and numbers are hypothetical, chosen for teaching.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

WHO = {"B": "Both", "A": "Agent only", "H": "Human only"}

TASKS = [{'id': 'T1',
  'name': 'Mobile-data troubleshooting',
  'area': 'Telecom customer service',
  'desc': 'A customer reports that mobile data is not working. Diagnose and fix it: device settings plus '
          'operator back end.',
  'R': 40,
  'cH': 2.5,
  'cA': 0.1,
  'cplan': 14.0,
  'phiA': 0.05,
  'phiH': 0.03,
  'eps': 0.18,
  'rho': 0.015,
  'cut': 0.6,
  'ccod': 1.0,
  'steps': [{'name': 'Verify identity and account status', 'who': 'B', 'pA': 0.01, 'pH': 0.01},
            {'name': 'Check line status and data allowance', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Check airplane mode on the device', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Check mobile-data toggle and data saver', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Check APN settings', 'who': 'B', 'pA': 0.03, 'pH': 0.03},
            {'name': 'Check roaming setting (customer abroad)', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Re-seat SIM / restart device', 'who': 'B', 'pA': 0.03, 'pH': 0.01},
            {'name': 'Refuel data allowance in back end', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Confirm data works with a speed test', 'who': 'B', 'pA': 0.02, 'pH': 0.01}]},
 {'id': 'T2',
  'name': 'Expense report audit',
  'area': 'Finance operations',
  'desc': 'Check a submitted expense report against travel policy and approve, flag or reject it.',
  'R': 12,
  'cH': 3.0,
  'cA': 0.08,
  'cplan': 4.0,
  'phiA': 0.03,
  'phiH': 0.02,
  'eps': 0.05,
  'rho': 0.0,
  'cut': 0.5,
  'ccod': 0.5,
  'steps': [{'name': 'Extract line items from receipts', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Match receipts to card transactions', 'who': 'B', 'pA': 0.01, 'pH': 0.03},
            {'name': 'Check each item against policy limits', 'who': 'B', 'pA': 0.02, 'pH': 0.03},
            {'name': 'Check for duplicate claims', 'who': 'B', 'pA': 0.01, 'pH': 0.03},
            {'name': 'Compute reimbursable amount', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Approve / flag / reject', 'who': 'B', 'pA': 0.02, 'pH': 0.01}]},
 {'id': 'T3',
  'name': 'Invoice-to-payment',
  'area': 'Accounts payable',
  'desc': 'Process a supplier invoice from receipt to payment release.',
  'R': 60,
  'cH': 3.0,
  'cA': 0.1,
  'cplan': 15.0,
  'phiA': 0.03,
  'phiH': 0.02,
  'eps': 0.03,
  'rho': 0.025,
  'cut': 0.5,
  'ccod': 1.0,
  'steps': [{'name': 'Capture invoice data', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Validate supplier and bank details', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Three-way match: PO, receipt, invoice', 'who': 'B', 'pA': 0.03, 'pH': 0.03},
            {'name': 'Resolve price variance', 'who': 'B', 'pA': 0.04, 'pH': 0.02},
            {'name': 'Check tax and withholding', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Code to cost centre / GL', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Check budget availability', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Schedule payment run', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Fraud screen (duplicate / changed bank)', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Release payment', 'who': 'B', 'pA': 0.02, 'pH': 0.01}]},
 {'id': 'T4',
  'name': 'Online refund request',
  'area': 'E-commerce customer service',
  'desc': 'A customer asks for a refund on an order. Check eligibility and issue the refund.',
  'R': 15,
  'cH': 2.0,
  'cA': 0.05,
  'cplan': 3.0,
  'phiA': 0.03,
  'phiH': 0.02,
  'eps': 0.1,
  'rho': 0.03,
  'cut': 0.5,
  'ccod': 0.5,
  'steps': [{'name': 'Look up order and delivery status', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Check return-policy eligibility', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Issue refund to original payment method', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Send confirmation to customer', 'who': 'B', 'pA': 0.01, 'pH': 0.01}]},
 {'id': 'T5',
  'name': 'New-employee IT onboarding',
  'area': 'IT service management',
  'desc': 'Provision everything a new hire needs before day one.',
  'R': 80,
  'cH': 3.0,
  'cA': 0.1,
  'cplan': 18.0,
  'phiA': 0.04,
  'phiH': 0.02,
  'eps': 0.03,
  'rho': 0.03,
  'cut': 0.5,
  'ccod': 1.0,
  'steps': [{'name': 'Create directory account', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Assign licences', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Set up email and calendar', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Add to security groups by role', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Provision VPN and MFA', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Order and image laptop', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Install role software', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Grant application access (finance, CRM)', 'who': 'B', 'pA': 0.04, 'pH': 0.02},
            {'name': 'Set up shared drives', 'who': 'B', 'pA': 0.02, 'pH': 0.01},
            {'name': 'Schedule security training', 'who': 'B', 'pA': 0.01, 'pH': 0.01},
            {'name': 'Send welcome pack', 'who': 'B', 'pA': 0.01, 'pH': 0.01},
            {'name': 'Final access review', 'who': 'B', 'pA': 0.03, 'pH': 0.01}]},
 {'id': 'T6',
  'name': 'Insurance claim triage',
  'area': 'Insurance operations',
  'desc': 'Triage a motor insurance claim: coverage, damage, fraud flags, routing.',
  'R': 50,
  'cH': 4.0,
  'cA': 0.1,
  'cplan': 12.0,
  'phiA': 0.05,
  'phiH': 0.03,
  'eps': 0.25,
  'rho': 0.02,
  'cut': 0.7,
  'ccod': 1.5,
  'steps': [{'name': 'Verify policy is active', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Check coverage for the incident', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Collect photos and documents from claimant', 'who': 'H', 'pA': 0.0, 'pH': 0.02},
            {'name': 'Assess damage from photos', 'who': 'B', 'pA': 0.04, 'pH': 0.03},
            {'name': 'Run fraud indicators', 'who': 'B', 'pA': 0.03, 'pH': 0.03},
            {'name': 'Estimate reserve', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Route to adjuster or fast-track', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Notify claimant of next steps', 'who': 'B', 'pA': 0.01, 'pH': 0.01}]},
 {'id': 'T7',
  'name': 'Marketing campaign brief',
  'area': 'Marketing',
  'desc': 'Write the brief for a product-launch campaign: audience, message, channels, budget.',
  'R': 70,
  'cH': 4.0,
  'cA': 0.1,
  'cplan': 10.0,
  'phiA': 0.45,
  'phiH': 0.05,
  'eps': 0.08,
  'rho': 0.02,
  'cut': 0.5,
  'ccod': 1.0,
  'steps': [{'name': 'Summarise product and positioning', 'who': 'B', 'pA': 0.02, 'pH': 0.02},
            {'name': 'Define target audience', 'who': 'B', 'pA': 0.04, 'pH': 0.02},
            {'name': 'Draft key message', 'who': 'B', 'pA': 0.04, 'pH': 0.02},
            {'name': 'Choose channels', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Allocate budget across channels', 'who': 'B', 'pA': 0.03, 'pH': 0.02},
            {'name': 'Check brand and legal guidelines', 'who': 'B', 'pA': 0.03, 'pH': 0.02}]},
 {'id': 'T8',
  'name': 'Supplier contract renewal',
  'area': 'Procurement',
  'desc': 'Renew an expiring supplier contract: performance, pricing, terms, sign-off.',
  'R': 120,
  'cH': 6.0,
  'cA': 0.15,
  'cplan': 14.0,
  'phiA': 0.08,
  'phiH': 0.04,
  'eps': 0.1,
  'rho': 0.03,
  'cut': 0.5,
  'ccod': 2.0,
  'steps': [{'name': 'Pull contract and spend history', 'who': 'B', 'pA': 0.01, 'pH': 0.02},
            {'name': 'Score supplier performance', 'who': 'B', 'pA': 0.03, 'pH': 0.03},
            {'name': 'Benchmark prices', 'who': 'B', 'pA': 0.03, 'pH': 0.04},
            {'name': 'Draft renewal terms', 'who': 'B', 'pA': 0.04, 'pH': 0.03},
            {'name': 'Negotiate with supplier', 'who': 'B', 'pA': 0.06, 'pH': 0.03},
            {'name': 'Legal review of changes', 'who': 'H', 'pA': 0.0, 'pH': 0.02},
            {'name': 'Executive sign-off', 'who': 'H', 'pA': 0.0, 'pH': 0.01}]}]

TASK_BY_ID = {t["id"]: t for t in TASKS}


@dataclass
class Result:
    p_correct: float
    value: float
    n_human: int
    n_agent: int
    labour: float
    compute: float
    planning: float
    codify: float
    step_error: list
    run_depth: list
    eps_eff: float
    rho_eff: float


def feasible(task: dict, alloc: str) -> bool:
    return len(alloc) == len(task["steps"]) and all(
        a in "AH" and not (s["who"] == "A" and a == "H") and not (s["who"] == "H" and a == "A")
        for s, a in zip(task["steps"], alloc))


def evaluate(task: dict, alloc: str, plan: str, codify: bool, eps_mult: float = 1.0, rho_mult: float = 1.0) -> Result:
    """plan is 'Agent' or 'Human'; alloc is a string of 'A'/'H', one per step."""
    eps = task["eps"] * eps_mult * ((1 - task["cut"]) if codify else 1.0)
    rho = task["rho"] * rho_mult
    S = 1 - (task["phiA"] if plan == "Agent" else task["phiH"])
    u, errs, depth, nH, nA = 0, [], [], 0, 0
    for s, a in zip(task["steps"], alloc):
        depth.append(u)
        if a == "A":
            h = min(0.99, s["pA"] + rho * u); u += 1; nA += 1
        else:
            h = min(0.99, s["pH"] + (eps if plan == "Agent" else 0.0)); u = 0; nH += 1
        errs.append(h)
        S *= 1 - h
    labour, compute = task["cH"] * nH, task["cA"] * nA
    planning = task["cplan"] if plan == "Human" else 0.0
    cod = task["ccod"] if codify else 0.0
    return Result(S, task["R"] * S - labour - compute - planning - cod, nH, nA, labour, compute, planning, cod,
                  errs, depth, eps, rho)


def references(task: dict, eps_mult: float = 1.0, rho_mult: float = 1.0) -> dict:
    full = "".join("H" if s["who"] == "H" else "A" for s in task["steps"])
    human = "".join("A" if s["who"] == "A" else "H" for s in task["steps"])
    return {"Full autonomy": (full, "Agent", evaluate(task, full, "Agent", False, eps_mult, rho_mult)),
            "All human": (human, "Human", evaluate(task, human, "Human", False, eps_mult, rho_mult)),
            "Agent plans, person executes": (human, "Agent", evaluate(task, human, "Agent", False, eps_mult, rho_mult))}


def optimum(task: dict, codify_allowed: bool = True, eps_mult: float = 1.0, rho_mult: float = 1.0):
    """Exhaustive search: (value, p_correct, plan, codify, alloc)."""
    best = None
    for plan in ("Agent", "Human"):
        for cod in ((False, True) if codify_allowed else (False,)):
            for alloc in itertools.product("AH", repeat=len(task["steps"])):
                alloc = "".join(alloc)
                if not feasible(task, alloc):
                    continue
                r = evaluate(task, alloc, plan, cod, eps_mult, rho_mult)
                if best is None or r.value > best[0]:
                    best = (r.value, r.p_correct, plan, cod, alloc)
    return best


def default_alloc(task: dict) -> str:
    """Today's process: people do every step they are allowed to."""
    return "".join("A" if s["who"] == "A" else "H" for s in task["steps"])
