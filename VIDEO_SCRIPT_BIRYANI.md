# dow - Chatbot Version Tracking Demo

### 3-minute product demonstration following [demo/RUNBOOK.md](demo/RUNBOOK.md)

**Format:** Two people seated at a table, sharing one screen. The female developer
owns a service chatbot for a Hyderabadi Biryani restaurant and is struggling to
track chatbot behavior across prompt and settings changes. The male developer
shows `dow` as the solution.

**Sequence:** Start with the **web dashboard**. Then show the command workflow
from the runbook that creates, evaluates, explains, and visualizes the same
chatbot history.

**Duration:** 3 minutes.

**People on camera:**
- **Female developer** - owns the chatbot and needs a reliable behavior history.
- **Male developer** - demonstrates `dow` through the dashboard and CLI.

---

## Timeline

| Time | Segment | What to show |
|---|---|---|
| 0:00-0:25 | Problem | Chatbot version tracking is unclear |
| 0:25-1:25 | Dashboard first | Version Tree, Version Details, Compare, Metrics cards |
| 1:25-2:35 | CLI workflow | `dow commit`, `tag`, `eval`, `compare`, `explain`, `tree` |
| 2:35-3:00 | UI capture + wrap | Edit spec / capture from dashboard, final summary |

---

## 1. Problem Setup (0:00-0:25)

**INT. OFFICE - TABLE SETUP**

Two developers sit at a table. A laptop is connected to a shared screen. The
browser is already open to the `dow` dashboard for the chatbot project.

**FEMALE DEVELOPER:**
I am working on a service chatbot for a Hyderabadi Biryani restaurant. I keep
changing the prompt, temperature, and evaluation metrics, but after a few runs I
cannot clearly tell which chatbot version is good or what caused a behavior
change.

**MALE DEVELOPER:**
That is exactly where `dow` helps. It records the chatbot's behavior history:
prompt, provider, settings, outputs, metrics, drift, stability, and lineage. Let
us start in the dashboard.

---

## 2. Dashboard Demonstration (0:25-1:25)

**SCREEN: Web dashboard at `dow dashboard` / `dow dash`**

Show the dashboard already loaded from the live `.dow` store in [demo/](demo/).

**MALE DEVELOPER:**
This is the same store visualized in the browser. The dashboard is local, so the
chatbot data stays on this machine.

**SCREEN: Version Tree**

```text
Version Tree
v1 baseline -> v2 -> v3 -> v4 good/golden
                              |-> v5 bad
                              |-> v6 release
```

**MALE DEVELOPER:**
The Version Tree shows how the chatbot evolved. v1 is the baseline. v4 is tagged
`good` and `golden`. v5 is the high-temperature stress test. v6 is the release
branch from v4.

**FEMALE DEVELOPER:**
So I can see experiments and releases in one place instead of reading old notes.

**SCREEN: Version Details - click `v4`**

```text
Version: v4
Tags: good, golden
Stability: 0.988
Provider: python
Model: chatbot.py:reply

Metrics
captures_order       1.000
greets               1.000
names_dish           1.000
states_price         1.000
confirms_spice       1.000
recommends_special   1.000
suggests_pairing     1.000
```

**MALE DEVELOPER:**
Version Details shows the config, sampled outputs, stability, and custom service
metrics. This tells us why v4 is the known-good version.

**SCREEN: Compare view - A = `baseline`, B = `golden`**

```text
Compare baseline -> golden
Changed field: prompt.system
Verdict: pass / consistent
Metrics improved: prices, spice level, special, pairing
```

**MALE DEVELOPER:**
Compare shows what changed between two versions and how much behavior drifted.
Here, the prompt improved the chatbot's service checklist without breaking order
capture.

**SCREEN: Metrics cards**

Show stability and evaluator cards at a glance.

**FEMALE DEVELOPER:**
This is the view I need for review: versions, metrics, drift, and release status.

---

## 3. CLI Workflow from the Runbook (1:25-2:35)

**SCREEN: Terminal in [demo/](demo/)**

**MALE DEVELOPER:**
Now I will show the commands that build the same history. The runbook starts by
opening the chatbot project.

**SCREEN:**
```powershell
cd C:\Users\t-pmurugaraj\code\dow\demo
Get-ChildItem
```

**MALE DEVELOPER:**
The project has three important files: `chatbot.py`, the local chatbot provider;
`specs\chatbot.yaml`, the versioned inference spec; and `evals.py`, the custom
metrics.

**SCREEN: optional bot test**

```powershell
python chatbot.py
# try: hi, can I order two chicken biryanis?
# then: quit
```

**FEMALE DEVELOPER:**
So before versioning, we can test the chatbot directly.

**SCREEN: Commit the behavior versions**

Show the commands quickly, one after another, not as a long typing sequence.

```powershell
dow commit -m "baseline ordering assistant"
dow tag baseline v1

# edit specs\chatbot.yaml: warm welcome + prices
dow commit -m "warm welcome and quote prices"

# edit specs\chatbot.yaml: confirm spice level
dow commit -m "confirm spice level"

# edit specs\chatbot.yaml: recommend special + suggest pairing
dow commit -m "recommend special and suggest a pairing"
dow tag good v4
dow tag golden v4

# edit temperature: 0.2 -> 0.9
dow commit -m "stress-test high temperature"
dow tag bad v5

# branch from v4 and pin temperature to 0.0
dow commit --from v4 -m "deterministic release"
dow tag release v6
```

**MALE DEVELOPER:**
Each `dow commit` captures one behavior version. Tags mark the baseline, the
golden version, the bad stress test, and the release.

**SCREEN: Test metrics and preview draft changes**

```powershell
dow eval

dow eval --draft
```

**MALE DEVELOPER:**
`dow eval` scores the committed version. `dow eval --draft` previews scores for a
spec edit without capturing it, so we can iterate before committing.

**SCREEN: Analyze one command at a time**

```powershell
dow history
dow inspect golden
dow compare baseline golden
dow explain v3 v4
dow explain v4 v5
dow tree
dow tree -o evolution.md
```

**MALE DEVELOPER:**
These commands answer the important questions: what versions exist, what is
inside a version, what changed, why behavior drifted, and how the chatbot evolved.
`dow tree -o` exports the graph for documentation.

---

## 4. Dashboard Can Drive the Loop (2:35-2:50)

**SCREEN: Return to dashboard**

Show **Edit spec + capture from the UI**.

**MALE DEVELOPER:**
The dashboard is not just read-only. We can edit the spec and capture a new
version from the browser, or run a commit in another terminal and click Refresh.

**SCREEN: Optional live capture**

```powershell
cd C:\Users\t-pmurugaraj\code\dow\demo
dow commit -m "live demo run"
```

**FEMALE DEVELOPER:**
So the team can use the dashboard for review and the CLI for automation.

---

## 5. Wrap-up (2:50-3:00)

**MALE DEVELOPER:**
That is the workflow: version the chatbot, evaluate it, compare behavior, explain
drift, and visualize the lineage.

**FEMALE DEVELOPER:**
Now we have a behavior history for the chatbot, not just code history.

**END CARD:**
```text
dow
Version control for AI behavior
Dashboard + CLI for prompts, settings, outputs, metrics, drift, and lineage.
```

---

## Recording Notes

- Follow [demo/RUNBOOK.md](demo/RUNBOOK.md) for the exact commands.
- Start with the dashboard already open from `dow dashboard` or `dow dash`.
- In the video, call the project only **chatbot**. Do not use a separate chatbot
  product name.
- Keep the dashboard section visual: Version Tree, Version Details, Compare,
  Metrics cards, then Edit spec + capture.
- Keep the CLI section quick: show commands and key outputs, not every line of
  terminal output.
- The runbook is fully offline. No API key is required.
