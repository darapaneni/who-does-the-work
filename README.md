# Who should do the work? A seminar exercise on giving AI agents access to work

Participants join from their phones by scanning a QR code. They redesign a few everyday workflows and see
every choice scored live, using the decision-rights model of *The Autonomy Paradox*. The choices are who
plans each case (an AI agent or a person) and who carries out each step. Participants then answer a short
questionnaire on **when an agent should get access to the work and when it should stay with a person**.
You project a live results screen while the answers come in.

## Two ways to run it

- **On your laptop** (below): best for rehearsal and for venues with good Wi-Fi.
- **On Streamlit Community Cloud** (see "Run it on Streamlit Community Cloud"): a fixed public link that
  works on any network, with answers saved to GitHub.

## Quick start (Windows)

1. **Install Python 3.9 or later.** Tick "Add python.exe to PATH" during installation.
2. **Set a facilitator password.** Run any launcher once. It creates `local_config.toml`. Open that file
   and change `facilitator_password`.
3. **Pick a launcher:**

   | Launcher | When to use it | What participants open |
   |---|---|---|
   | `run_local.bat` | Rehearse on your own laptop | http://localhost:8501 |
   | `run_seminar.bat` | Venue Wi-Fi where phones can reach your laptop | The QR code on your screen |
   | `run_seminar_public.bat` | Any network. Phones can use mobile data. Recommended for large rooms. | The QR code on your screen (a temporary https link) |

   The seminar launchers open the **facilitator screen** at http://localhost:8501/?view=facilitator.
   Log in with your password and project the **Present** tab, which shows:
   - a QR code;
   - the join link;
   - the session code;
   - a live count of answers.

   On macOS or Linux, use `./run_local.sh`, `./run_local.sh --seminar` or `./run_local.sh --public`.

### The public link (`run_seminar_public.bat`)

The public launcher uses a free Cloudflare *quick tunnel* (`cloudflared`) or, if that is missing,
`ngrok`. Install one of them first:
- **cloudflared:** `winget install --id Cloudflare.cloudflared`
- **ngrok:** install it, then run `ngrok config add-authtoken <token>`

How the link behaves:
- The link appears on the Present tab about 10 seconds after start.
- The link is new each time and stops working when you close the "Public link" window.
- The app itself still runs on your laptop, and the answers are saved there.
- If the link shown is wrong, paste the correct one into **Session controls → Join address override**.

**Why not just use the Wi-Fi launcher?** Many venue and corporate Wi-Fi networks stop phones from reaching
other devices on the same network. The public link avoids this.

## What participants do (about 15 minutes)

1. **Join.** Give a name or alias (optional), the session code (filled in by the QR code), role, AI use,
   and a first answer to "how much freedom should agents get today?"
2. **How it works.** Three cards explain the rules: person steps, agent steps and the hand-off error.
3. **Play.** Three ⭐ workflows come first; the other five are optional:
   - T1 shows the split-rights valley.
   - T3 shows checkpoints in long runs.
   - T7 shows that people hold planning knowledge the agent lacks.

   On each workflow the participant:
   - chooses who plans the case, and taps 🧑 Person or 🤖 Agent for each step;
   - sees the value per case and the share of cases done right update instantly;
   - can open a 💡 Tip, which explains what is going wrong in their design;
   - sees how their design compares with three standard designs.
4. **Your view: when should an agent get access?**
   - An **access ladder** for each workflow they played:
     - 0 No access
     - 1 Look up only
     - 2 Suggest; person acts
     - 3 Act after approval
     - 4 Act; person reviews after
     - 5 Act alone
   - **Who should plan the case:** a person, together or the agent.
   - **Keep the work with a person when…** (pick all that apply)
   - **Give the agent access when…** (pick all that apply)
   - **Top 3 guardrails**
   - **How many steps an agent may run before a person checks**
   - **The freedom question again**, to measure any shift
   - **One rule** they would write for their organization, and work they would never hand over
5. **Results.** A summary of the participant's own designs. When you turn on *Show room results*, their
   phones also show how the room answered.

## Workflow labs and the library

After the game, participants can open two hands-on labs and a reading room:

- **🧭 Lab A: Rights Allocation Sprint.** The participant picks a workflow, predicts which candidate will win, and
  then steps through the sprint's four moves:
  1. build two candidates, one where a person plans and one where the agent plans;
  2. bundle execution with the plan;
  3. break long unchecked runs at m* = 2√(C ÷ (R·ρ));
  4. codify only where hand-offs remain.

  The result is compared with the participant's own design from the game and with the best possible design
  (found by exhaustive search).
- **🔎 Lab B: Hand-off Audit Loop.** The participant audits a live design in which the agent plans and the
  customer does the device steps, week by week, without knowing the true hand-off error.
  - The app shows the estimate and its 90% interval against the design's break-even hand-off error (1.5%).
  - The participant decides to keep, codify or re-bundle.
  - An optional model upgrade arrives in week 3.
  - At the end the app reveals the truth and the value of every option.
- **📚 Library** (`?view=library`, or the button on the join page). Readers can read in the browser, open the PDF
  in a new tab or download:
  - the research article;
  - its online supplement;
  - the teaching article.

  The PDFs live in `static/` and are served by Streamlit's static file serving (`enableStaticServing` in
  `.streamlit/config.toml`). Replace them with blinded copies if a journal's review requires it.

Lab answers are written to `feedback.csv` with the `question_id` values `lab_a_prediction`, `lab_a_result`,
`lab_a_reflection` and `lab_b_decision`.

The workflows are implemented in `workflows.py`. `analysis/misqe_analysis.py` reproduces the evidence quoted in the
teaching article:
- sprint against the best design on the exercise and on 2,000 random workflows;
- break-even hand-off errors;
- audit-loop decision rates.

It runs in seconds and writes `analysis/out/`.

## The facilitator screen (`?view=facilitator`)

- **📺 Present:**
  - the QR code, join link, session code and live counts;
  - **Session controls**: set the session code, open Round 2 (codification) or Round 3 (a better agent),
    and switch room results on or off for participants.
- **📊 Live: agent access.** Updates every 10 seconds and shows:
  - the access ladder by workflow;
  - who should plan;
  - keep-with-a-person and give-to-agent conditions;
  - top guardrails;
  - steps allowed unchecked;
  - before and after scores on the freedom question;
  - the rules and red lines people wrote.
- **🎮 Game results:**
  - value per workflow against the best possible design;
  - the share who let the agent plan;
  - codification uptake;
  - the leaderboard (names hidden by default);
  - the answer key.
- **⚙️ Data and settings:** download `responses.csv` and `feedback.csv`, and (in git mode) commit them.

## Run it on Streamlit Community Cloud (no laptop server, fixed link)

On Streamlit Community Cloud the app runs online at a fixed address such as
`https://who-does-the-work.streamlit.app`. Participants join over mobile data or any Wi-Fi, the link never
changes, and the QR code can be printed on a slide in advance.

**1. Put the app in its own GitHub repository.**
Create a new repository (for example `who-does-the-work`) and upload the **contents** of this folder to
its root, so that `app.py`, `requirements.txt` and the `.streamlit/` folder sit at the top level.
Community Cloud reads `.streamlit/config.toml` only from the repository root, and its working directory
is always the root. Do **not** upload `local_config.toml`, `.streamlit/secrets.toml`, `.venv/` or `data/`
(the `.gitignore` already excludes them). The repository can be private.

**2. Create a GitHub token for storing answers.**
A Cloud app's own disk is wiped whenever it restarts or goes to sleep, so answers are written to GitHub.
In GitHub, go to Settings → Developer settings → Fine-grained tokens and create a token with:
- Repository access: only the repository that should receive the answers (it can be the app repository);
- Permissions: Contents → Read and write. Nothing else.

**3. Deploy.** At https://share.streamlit.io, choose **Create app → Deploy a public app from GitHub**:
- Repository: your new repository; Branch: `main`; Main file path: `app.py`;
- App URL: pick a short name, for example `who-does-the-work`;
- **Advanced settings → Python version:** 3.12;
- **Advanced settings → Secrets:** paste the text below, with your own values.

```toml
[github]
token  = "github_pat_..."              # the token from step 2
repo   = "your-github-user/who-does-the-work"
branch = "exercise-data"               # created automatically; keep it different from the deployed branch
path   = "data/exercise/responses.csv" # feedback.csv is written next to it

[app]
facilitator_password  = "choose-a-strong-password"
session_codes         = ["GL-SEMINAR"] # or [] to accept any code
public_url            = "https://who-does-the-work.streamlit.app"
open_rounds           = [1, 2, 3]
round3_eps_multiplier = 0.5
round3_rho_multiplier = 0.5
```

Answers go to the `exercise-data` branch, not to `main`, so a submission never triggers a redeploy.

**4. Before the seminar.**
- Apps with no visitors for 12 hours go to sleep. Open the app 10–15 minutes before you start; if it shows
  "Yes, get this app back up!", click it and wait for it to load.
- Open `https://<your-app>.streamlit.app/?view=facilitator`, log in, and check that the Present tab shows
  your `streamlit.app` address and "Storage: github" at the bottom of the Data tab. A red warning on the
  Present tab means the `[github]` secrets are missing.
- Submit one test answer from your phone and check that `responses.csv` appears on the `exercise-data` branch.

**Limits to know.** Community Cloud gives an app roughly 0.7–2.7 GB of memory. That is enough for a seminar
room, but for very large classes (more than about 150 people at once) run it on your laptop with
`run_seminar_public.bat` instead. The facilitator's live controls (round, session code, room results) are
shared by everyone on the running app and reset if it restarts; set them again from the Present tab.

### Suggested run of show (45 minutes)

| Time | Step |
|---|---|
| 0–5 | Project the Present tab. Participants scan and join. |
| 5–20 | Round 1. Participants play the three ⭐ workflows. |
| 20–23 | Optional: open Round 2. Ask "does writing the procedure down change your design?" |
| 23–30 | Participants answer "Your view". Watch the Live tab fill. |
| 30–45 | Turn on *Show room results* and discuss the Live tab:<br>• Where did the room draw the line on the access ladder?<br>• Which conditions keep work with people?<br>• Which rules would you adopt? |

## Where the answers go

Both files sit next to each other: by default in `../data/exercise/` (your paper repo when this folder is
`<repo>/exercise_app/`). Set the location with `csv_path` in `local_config.toml`. You can turn on
`git_commit` and `git_push` to commit after every submission.

**`responses.csv`** has one row per participant × round × workflow, plus a TOTAL row. Its columns are the
same as in version 1:
- allocation, plan, codified;
- value, p_correct, the reference values and the optimum;
- `is_split_design`, `seconds_on_task`, edits and reflection.

**`feedback.csv`** has one row per answer, with these columns:
- `submitted_utc`, `submission_id`, `app_version`, `session_code`, `participant`, `role`, `ai_experience`
- `question_id`, `question`, `item`, `answer`

| question_id | item | answer |
|---|---|---|
| `pre_autonomy`, `post_autonomy` | before / after | 1–5 label |
| `access_level` | workflow | ladder rung (0–5 label) |
| `planner` | workflow | A person / Together / The agent |
| `keep_with_person`, `give_to_agent`, `guardrail_top` | the option chosen | 1 |
| `unattended_steps` | | number, or "no limit" |
| `rule`, `never` | | free text |

To change the questions, edit `survey.py`.

**Consent and privacy:**
- Participants can untick "Store my answers" and still play; their answers are then not saved.
- An alias is allowed and no e-mail is collected.
- Text is cleaned to block spreadsheet formula injection.

## Tests

`python -m pytest -q tests` runs these checks:
- the model (it must reproduce the Excel workbook);
- storage, including concurrent writes;
- a scripted participant and facilitator walk-through with Streamlit's AppTest;
- the join link and QR code using `public_url` on Streamlit Community Cloud.

All workflows and numbers are hypothetical, chosen for teaching.
