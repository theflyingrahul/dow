# Demo runbook - install, version, and visualize the chatbot with dow

The full lifecycle on one page: install the package, start a project with
`dow init`, evolve a real chatbot through several versions with `dow commit`, test
and analyze the drift, and open the live web dashboard. Run one block at a time
(e.g. for a screen capture). Fully offline - no API key required.

## 0. Install dow (once)

```powershell
cd C:\Users\t-pmurugaraj\code\dow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
dow help                      # verify the CLI is installed
```

The web UI ships prebuilt, so the install needs no Node. (Only when building a
wheel on a Node-less machine do you need `$env:DOW_SKIP_DASHBOARD_BUILD=1`.)

## 1. See `dow init` start a project (optional aside)

Every dow project begins with `dow init`, which scaffolds a starter spec and an
`evals.py`. Watch it work in a throwaway folder:

```powershell
$p = Join-Path $env:TEMP "dow-init-demo"; New-Item $p -ItemType Directory -Force | Out-Null; Push-Location $p
dow init                      # creates specs/summarization.yaml + evals.py
dow commit -m "first capture" # captures v1 from the starter spec
dow history
Pop-Location; Remove-Item $p -Recurse -Force
```

For the rest of the runbook we use a project already initialized for a
**biryani-restaurant chatbot**.

## 2. Open the chatbot project

```powershell
cd C:\Users\t-pmurugaraj\code\dow\demo
Get-ChildItem                 # chatbot.py (the bot), evals.py (metrics), specs\chatbot.yaml (the spec)
```

`chatbot.py` is a local `python` provider, `specs/chatbot.yaml` is the versioned
inference spec, and `evals.py` scores each reply. Reset to a clean slate at any
time:

```powershell
Remove-Item .dow, runs, evolution.md -Recurse -Force -ErrorAction SilentlyContinue
```

## 3. Test the bot

Chat with it directly before versioning anything:

```powershell
python chatbot.py
# try:  hi, can I order two chicken biryanis?
# then: quit
```

## 4. v1 - baseline (commit)

```powershell
dow commit -m "baseline ordering assistant"
dow tag baseline v1
```

## 5. v2 - warm welcome + always quote prices

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "warm welcome and quote prices"
```

## 6. v3 - confirm the spice level

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "confirm spice level"
```

## 7. v4 - recommend the signature dish + suggest a pairing

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order. Recommend the chef's signature biryani and suggest a drink or dessert to pair." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "recommend special and suggest a pairing"
dow tag good v4
dow tag golden v4
```

## 8. v5 - stress test: raise temperature 0.2 -> 0.9

```powershell
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.9' | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "stress-test high temperature"
dow tag bad v5
```

## 9. v6 - branch from v4: pin temperature 0.0 for a deterministic release

```powershell
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.0' | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit --from v4 -m "deterministic release"
dow tag release v6
```

## 10. Test the metrics (eval)

Score the latest version (the release) against the previous version and the
known-good baseline:

```powershell
dow eval                      # service checklist for v6 vs the previous (v5) and last-good (golden)
```

Trying a change? Preview its scores **without committing** - edit the spec, run
`dow eval --draft`, iterate, then `dow commit` when you're happy:

```powershell
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.5' | Set-Content specs\chatbot.yaml -Encoding utf8
dow eval --draft              # preview vs the previous and last-good; nothing is captured
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.0' | Set-Content specs\chatbot.yaml -Encoding utf8
```

## 11. Analyze (one command at a time)

```powershell
dow history
```

```powershell
dow inspect golden
```

```powershell
dow compare baseline golden
```

```powershell
dow explain v3 v4
```

```powershell
dow explain v4 v5
```

```powershell
dow tree
```

```powershell
dow tree -o evolution.md      # then open evolution.md and "Open Preview" for the Mermaid graph
```

## 12. Show the UI - web dashboard

The same store, visualized. This opens your browser automatically and serves the
live `.dow` store (read-only, localhost only). Press Ctrl+C to stop the server.

```powershell
dow dashboard
```

On screen, walk through:

- **Version Tree** - v1 -> v4 on the trunk, where v4 forks into v5 (the
  high-temperature stress test) and the v6 release.
- **Version Details** - click a version to see its config, sampled outputs, and
  stability + service-checklist metrics.
- **Compare** - pick A = `baseline`, B = `golden` for the drift-score gauge and the
  pass / warn / fail verdict (the same engine as `dow compare`).
- **Metrics cards** - stability and the evaluator scores at a glance.

Live-update flourish (optional): leave the dashboard running, capture another
version from a **second terminal**, then click **Refresh** in the browser to watch
it appear.

```powershell
# in a new terminal
cd C:\Users\t-pmurugaraj\code\dow\demo
dow commit -m "live demo run"
```

---

## Prefer editing in the editor?

For steps 5-9, instead of the `Get-Content ... Set-Content` line, just change the
`system:` (or `temperature:`) line in `specs/chatbot.yaml` to the text shown, then
run the `dow commit` line. It makes a great capture - prompt change on the left,
metric change in the terminal.

## Reset after the capture

Restores the baseline so the runbook is repeatable:

```powershell
Remove-Item .dow, runs, evolution.md -Recurse -Force -ErrorAction SilentlyContinue
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani." -replace 'temperature: [0-9.]+', 'temperature: 0.2' | Set-Content specs\chatbot.yaml -Encoding utf8
```

## One-command alternative

Self-paced, no manual edits - a good fallback for a capture:

```powershell
python run_demo.py --pause 1
```
