# dow - Chatbot Version Tracking Demo

### 3-minute product demonstration for **dow - Drift Observation Workbench**

**Format:** Two people seated at a table, sharing one screen. The female
developer explains the version-tracking problem in her chatbot project. The male
developer shows how `dow` solves it: UI first, CLI second.

**Scenario:** A service chatbot for a Hyderabadi Biryani restaurant. In the
video, call it only **chatbot**. The demo code lives in [demo/](demo/).

**Duration:** 3 minutes.

**People on camera:**
- **Female developer** - owns the chatbot and needs a clear behavior history.
- **Male developer** - demonstrates `dow` through the UI and CLI.

---

## Timeline

| Time | Segment | Main feature |
|---|---|---|
| 0:00-0:35 | Problem introduction | Why chatbot behavior versioning is hard |
| 0:35-1:35 | UI demonstration | Versions, tags, drift, stability, eval scores |
| 1:35-2:35 | CLI demonstration | `history`, `compare`, `explain`, `eval`, `tree` |
| 2:35-3:00 | Wrap-up | What `dow` gives the team |

---

## 1. Problem Introduction (0:00-0:35)

**INT. OFFICE - TABLE SETUP**

Two developers are seated at a table with a laptop connected to a shared screen.
The screen shows the chatbot project UI. The female developer is looking at a
few different chatbot responses and configuration changes.

**FEMALE DEVELOPER:**
I am working on a service chatbot for a Hyderabadi Biryani restaurant. It handles
orders, menu questions, prices, spice level, delivery, and recommendations. The
problem is tracking versions. I keep changing prompts, sampling settings, and
evaluators, but after a few experiments I cannot clearly tell which change caused
which behavior.

**MALE DEVELOPER:**
That is what `dow` is for: version control for AI behavior. It tracks the prompt,
model/provider, sampling settings, outputs, evaluation metrics, drift, stability,
and lineage. Let me show it in the UI first, then in the CLI.

---

## 2. UI Demonstration (0:35-1:35)

**SCREEN: dow UI - Project Overview**

```text
Project: chatbot

Versions
v1  baseline ordering assistant          stability 0.95   tag: baseline
v2  warm welcome and quote prices         stability 0.97
v3  confirm spice level                   stability 0.98
v4  recommend special and pairing         stability 0.99   tags: good, golden
v5  high temperature stress test          stability 0.80   tag: bad
v6  deterministic release candidate       stability 1.00   tag: release
```

**MALE DEVELOPER:**
This is the behavior history. Each row is a captured chatbot version with its
stability score and tags.

**FEMALE DEVELOPER:**
So v1 is the baseline, v4 is the good version, v5 is the stress test, and v6 is a
release candidate.

**MALE DEVELOPER:**
Yes. Tags like `baseline`, `good`, `golden`, `bad`, and `release` make important
checkpoints easy to compare later.

**SCREEN: UI - Version Details for v4**

```text
Version: v4
Tags: good, golden
Stability: 0.99
Model provider: python
Model entry point: chatbot.py:reply
Samples: 6

Evaluation
captures_order       1.000
greets               1.000
names_dish           1.000
states_price         1.000
confirms_spice       1.000
recommends_special   1.000
suggests_pairing     1.000
avg_response_length  78.83
```

**MALE DEVELOPER:**
This is the golden version. It passes the service checklist: order capture,
greeting, dish name, price, spice level, recommendation, and pairing.

**FEMALE DEVELOPER:**
This is the kind of view I need. I can see not only that v4 exists, but why it is
considered good.

**SCREEN: UI - Compare v4 and v5**

```text
Compare: v4 -> v5

Changed field
sampling.temperature: 0.2 -> 0.9

Semantic drift: 0.084
Stability: 0.99 -> 0.80
Verdict: Behavior Drift

Evaluation changes
captures_order:      1.000 -> 1.000
avg_response_length: 78.83 -> 78.00
```

**MALE DEVELOPER:**
This comparison shows the key point: only `sampling.temperature` changed, and
stability dropped. The chatbot still captures the order, but its behavior became
less stable.

**FEMALE DEVELOPER:**
So I can see the behavior change without guessing from individual responses.

**MALE DEVELOPER:**
Now let us switch to the CLI.

---

## 3. CLI Demonstration (1:35-2:35)

**SCREEN: Terminal**

**MALE DEVELOPER:**
The same workflow is available from the CLI. This demo uses the local chatbot in
[demo/](demo/), so it runs offline.

**SCREEN (`python demo/run_demo.py --pause 1`):**
```text
Captured v1   stability 0.950   baseline
Captured v2   stability 0.970   warm welcome + prices
Captured v3   stability 0.978   confirm spice level
Captured v4   stability 0.988   good, golden
Captured v5   stability 0.801   bad
Captured v6   stability 1.000   release
```

**MALE DEVELOPER:**
Each run captures a version and evaluates it automatically. Now we can query the
same history from the terminal.

**SCREEN (`dow history`):**
```text
chatbot: behavior history

version   stability   change            tags
v1        0.950       baseline          baseline
v2        0.970       config changed
v3        0.978       config changed
v4        0.988       config changed    good, golden
v5        0.801       config changed    bad
v6        1.000       config changed    release
```

**MALE DEVELOPER:**
`dow history` gives the behavior timeline with the same tags from the UI.

**SCREEN (`dow compare v4 v5`):**
```text
What changed in the configuration

field                  A      B
sampling.temperature   0.2    0.9

signal               value
Output difference    0.470
Semantic drift       0.084  (warn 0.15, fail 0.40)
Stability v4         0.988
Stability v5         0.801

Verdict: Behavior Drift
```

**MALE DEVELOPER:**
`dow compare` shows the changed field and the behavior impact.

**SCREEN (`dow explain v4 v5`):**
```text
Cause:   sampling.temperature  (0.2 -> 0.9)
Effect:  semantic drift 0.084, stability change -0.187  ->  Behavior Drift
```

**MALE DEVELOPER:**
`dow explain` turns the comparison into a cause-and-effect statement.

**SCREEN (`dow eval golden`):**
```text
metric                golden
captures_order        1.000
greets                1.000
names_dish            1.000
states_price          1.000
confirms_spice        1.000
recommends_special    1.000
suggests_pairing      1.000
avg_response_length   78.830
```

**MALE DEVELOPER:**
`dow eval` shows the chatbot-specific checklist from custom Python evaluators.

**SCREEN (`dow tree`):**
```text
chatbot - behavior evolution
v1 -> v2 -> v3 -> v4 -> v5
                 |
                 -> v6 release
```

**MALE DEVELOPER:**
`dow tree` shows the evolution path and the release branch. It can also be
exported as Mermaid for documentation.

---

## 4. Wrap-up (2:35-3:00)

**FEMALE DEVELOPER:**
This solves the problem. I can track chatbot versions, compare behavior, explain
drift, and keep a release candidate without losing experiment history.

**MALE DEVELOPER:**
That is the workflow: run, compare, explain, evaluate, tag, and inspect the tree.
`dow` gives the team a measurable behavior history for the chatbot.

**END CARD:**
```text
dow
Version control for AI behavior
Track prompts, settings, outputs, drift, evaluations, and lineage.
```

---

## Recording Notes

- Start with both developers seated at a table and the UI already visible.
- In the video, call the project simply **chatbot**. Avoid giving the chatbot a
  separate product name.
- The code used for the demo lives in [demo/](demo/). The demo currently uses the
  restaurant chatbot implementation in [demo/chatbot.py](demo/chatbot.py), custom
  evaluators in [demo/evals.py](demo/evals.py), and the guided script in
  [demo/run_demo.py](demo/run_demo.py).
- Keep the language direct and product-focused. No cinematic setup, no quirky
  jokes, no special effects.
- Target runtime is 3 minutes. Keep UI shots readable but brief; hold the
  `compare` and `explain` screens slightly longer because they show the main
  value of `dow`.
