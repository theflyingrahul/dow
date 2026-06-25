# Demo runbook - version and evaluate the chatbot with dow

A command-by-command walkthrough that evolves the Spice Route Biryani chatbot
through six versions, runs dow's full analysis, and shows the live web dashboard.
Designed to be run one block at a time (e.g. for a screen capture). Fully offline -
no API key required.

## 0. Setup (once)

```powershell
cd C:\Users\t-pmurugaraj\code\dow\demo
# if `dow` isn't found, activate the venv once:  ..\.venv\Scripts\Activate.ps1
```

The web dashboard (step 8) is already built into `dow/web/`. If `dow dashboard`
ever reports that the assets aren't bundled, build them once:

```powershell
cd ..\dashboard; npm install; npm run build; cd ..\demo
```

Start from a clean slate at any time:

```powershell
Remove-Item .dow, runs, evolution.md -Recurse -Force -ErrorAction SilentlyContinue
```

## 1. v1 - baseline

```powershell
dow commit -m "baseline ordering assistant"
dow tag baseline v1
```

## 2. v2 - warm welcome + always quote prices

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "warm welcome and quote prices"
```

## 3. v3 - confirm the spice level

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "confirm spice level"
```

## 4. v4 - recommend the signature dish + suggest a pairing

```powershell
(Get-Content specs\chatbot.yaml) -replace '^\s*system:.*', "  system: You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order. Recommend the chef's signature biryani and suggest a drink or dessert to pair." | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "recommend special and suggest a pairing"
dow tag good v4
dow tag golden v4
```

## 5. v5 - stress test: raise temperature 0.2 -> 0.9

```powershell
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.9' | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit -m "stress-test high temperature"
dow tag bad v5
```

## 6. v6 - branch from v4: pin temperature 0.0 for a deterministic release

```powershell
(Get-Content specs\chatbot.yaml) -replace 'temperature: [0-9.]+', 'temperature: 0.0' | Set-Content specs\chatbot.yaml -Encoding utf8
dow commit --from v4 -m "deterministic release"
dow tag release v6
```

## 7. Analyze (one command at a time)

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
dow tree -o evolution.md   # then open evolution.md and "Open Preview" for the Mermaid graph
```

## 8. Show the UI - web dashboard

The same store, visualized. This opens your browser automatically and serves the
live `.dow` store (read-only, localhost only). Press Ctrl+C to stop the server.

```powershell
dow dashboard
```

On screen, walk through:

- **Version Tree** - the trunk v1 -> v4 and the branch (v5, v6) off v4.
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

For steps 2-6, instead of the `Get-Content ... Set-Content` line, just change the
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
