"""The seminar questionnaire: when should an AI agent get access to do work, and when should it stay with a person?

Every answer is saved as one row of feedback.csv (long format):
question_id, question, item, answer. Edit the lists below to change the questions; the app and the
facilitator dashboard read them from here.
"""
from __future__ import annotations

# A six-rung access ladder, from no access to full autonomy.
ACCESS_LEVELS = [
    "0 · No access",
    "1 · Look up only",
    "2 · Suggest; person acts",
    "3 · Act after approval",
    "4 · Act; person reviews after",
    "5 · Act alone",
]
ACCESS_HELP = {
    ACCESS_LEVELS[0]: "A person does the whole case. The agent is not involved.",
    ACCESS_LEVELS[1]: "The agent may read systems and fetch information. It changes nothing.",
    ACCESS_LEVELS[2]: "The agent drafts or recommends. A person decides and carries out every action.",
    ACCESS_LEVELS[3]: "The agent carries out actions, but a person approves each one before it happens.",
    ACCESS_LEVELS[4]: "The agent acts on its own. A person reviews a sample or the log afterwards.",
    ACCESS_LEVELS[5]: "The agent acts on its own with no routine human review.",
}

PLANNER_OPTIONS = ["A person", "Together", "The agent"]

KEEP_WITH_PERSON = [
    "The action cannot be undone",
    "Money above a set limit is at stake",
    "The customer is upset or vulnerable",
    "A legal or regulatory sign-off is needed",
    "The person knows things the agent does not",
    "The agent's error rate has not been measured",
    "A person would have to carry out the agent's instructions",
    "The case is new or outside the written procedure",
    "Personal or sensitive data is involved",
    "The agent would run many steps with nobody checking",
]

GIVE_TO_AGENT = [
    "The procedure is written down (codified)",
    "Mistakes are cheap and easy to reverse",
    "The agent's error rate is measured and low",
    "Every action is logged and can be replayed",
    "There are spending and permission limits",
    "A person checks at set points in the run",
    "The work is high-volume and repetitive",
    "The agent can see the results of its own actions",
]

GUARDRAILS = [
    "Approval before irreversible actions",
    "Spending and permission limits",
    "Full action log with replay",
    "A kill switch to stop the agent",
    "Human checkpoints at set points in long runs",
    "Test the reviewers (planted errors)",
    "Least-privilege access credentials",
    "Try in a sandbox before production",
    "Clear owner accountable for the agent",
]
TOP_GUARDRAILS = 3

AUTONOMY_SCALE = ["1 · Very little", "2", "3 · Some", "4", "5 · A lot"]
AUTONOMY_QUESTION = "Today, how much freedom should AI agents get to do work on their own in your organization?"

UNATTENDED_MAX = 20     # slider maximum for "steps an agent may run before a person checks"
