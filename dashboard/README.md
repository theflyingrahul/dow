# dow · Drift Observation Workbench — Dashboard

An editorial, production-quality dashboard for **dow**, a tool that versions the
full AI inference spec and measures **semantic drift**, **stability**, and
**regressions** across versions. Built with **React + TypeScript + Tailwind CSS**.

> Run it with **`dow dashboard`** and the UI is backed by your **live `.dow`
> store**: a small local server (read-only, localhost-only) serves the captured
> versions as JSON and this prebuilt bundle. Run it **standalone** with
> `npm run dev` and it falls back to **typed mock data** so the front end can be
> developed without a store. Either way the drift score, stability delta, and
> pass / warn / fail verdict render through `lib/drift.ts` — in live mode reusing
> the same engine verdict the CLI shows for adjacent versions.

---

## Quick start

### Live data (recommended)

From a project that has captured versions with `dow commit`:

```bash
dow dashboard      # serves the bundled UI and opens it in your browser
```

This serves the production bundle (see [build](#build) below) together with a
`data.json` snapshot of your store. See the root [README](../README.md#dashboard)
for the full command and its options.

### Front-end development (mock data)

To iterate on the UI itself with hot-module reload and no store required:

```bash
cd dashboard
npm install
npm run dev
```

Open the printed URL (default <http://localhost:5173>). In this mode the app
loads the typed mock dataset described under [Data](#data).

### Build

```bash
npm run build      # type-check (tsc -b) + production bundle into ../dow/web/
npm run preview    # preview the production build
npm run typecheck  # types only
```

`npm run build` emits the bundle into **`../dow/web/`**, where it ships as
package data so a regular `pip install` includes the UI and `dow dashboard`
can serve it. Requirements: Node 18+ and npm.

---

## What's inside

### Information architecture

| View | Components |
| --- | --- |
| **Dashboard** | `VersionTree`, `VersionHistory`, `MetricsCards`, **New Version / Refresh** CTA |
| **Version Details** | `ConfigSection`, `OutputsSection`, `MetricsSection` |
| **Compare** | `DiffView` (side-by-side / inline), `DriftScoreGauge`, `VerdictCard` |

### Behavior

- **Select a version** in the tree or history → updates Version Details **and** the Compare panel.
- **Refresh** (live mode) re-reads the `.dow` store: the server rebuilds `data.json`
  on every request, so capturing new versions with `dow commit` and refreshing shows them.
- **New Version** (mock mode only) opens an accessible modal (focus-trapped) with form
  fields; submitting synthesizes a child version, evaluates it, and opens it in Details.
- **Compare** supports picking any two versions (A/B) with a swap control.
- **Drift score + verdict** mirror dow's real verdict thresholds. In live mode the
  server supplies the engine's own comparison for adjacent versions; otherwise they
  are recomputed client-side via `lib/drift.ts`:
  - `drift ≥ fail (0.40)` or stability drop `≥ 0.25` → **Likely Regression**
  - `drift ≥ warn (0.15)` or stability drop `≥ 0.10` → **Behavior Drift**
  - otherwise → **Consistent**

### Data

In **live mode** the app fetches `data.json` from the `dow dashboard` server,
which builds it from your `.dow` store: the real versions, their captured
configuration and outputs, stability, and any custom-evaluator metrics. The
metric registry is assembled dynamically from whatever each version measured, so
the cards and charts adapt to your spec (`src/data/loadData.ts` →
`applyMetricRegistry`).

When no `data.json` is available (standalone `npm run dev`), the app falls back
to a typed mock dataset of **9 versions** that forms a tree branching at `v3`
(→ `v4`, `v5`) and `v6` (→ `v8`, `v9`), with metrics such as `accuracy`,
`rougeL`, `stability`, `hallucinationRate`, `latencyMs`, `costUsd`,
`tokenUsage`, and the custom evaluator `avgWordCount`.

---

## Design system

- **Visual style:** "editorial data product" — warm paper surfaces, violet ink,
  layered gradients + a faint grid, and a distinctive font pairing.
- **Typography:** Fraunces (display serif) · Space Grotesk (UI) · JetBrains Mono (code/data).
- **Color system:** CSS variables for `brand`, `surface`, `accent`, `warning`,
  `success`, `danger` (+ ink variants), defined in `src/index.css` and surfaced
  to Tailwind in `tailwind.config.js`.
- **Theme:** defaults to a distinctive **light** theme; a **dark** theme is one
  toggle away (persisted to `localStorage`, applied before paint to avoid flashes).
- **Motion:** staggered reveal on load, card hover elevation, animated gauge sweep,
  and smooth tab / diff-mode transitions — all disabled under
  `prefers-reduced-motion`.

### Accessibility

- Semantic landmarks (`header`, `nav`, `main`, `aside`, `section`) with labels.
- Keyboard support: roving-tabindex tree, arrow-key tabs & segmented controls,
  focus-trapped modal with Escape + focus restoration.
- Visible focus rings, ARIA roles/labels, and AA-minded contrast in both themes.
- Responsive and verified at **375px**, **768px**, and **1440px**.

---

## Project structure

```text
dashboard/
├─ index.html              # fonts, theme bootstrap, root
├─ tailwind.config.js      # CSS-variable color system + motion
├─ src/
│  ├─ main.tsx · App.tsx
│  ├─ index.css            # theme tokens, base styles, keyframes
│  ├─ types.ts             # domain types/interfaces
│  ├─ themes.ts            # optional alternate theme object
│  ├─ data/                # metric registry, live loader (loadData.ts), mock versions
│  ├─ lib/                 # drift engine, diff, tree, formatters
│  ├─ hooks/               # useTheme
│  ├─ store/               # AppStore context (live dataset + mock New Version synthesis)
│  └─ components/
│     ├─ ui/               # Button, Badge, Card, Modal, Sparkline, …
│     ├─ dashboard/        # Tree, History, MetricsCards, DashboardSection
│     ├─ details/          # Config, Outputs, Metrics, VersionDetailsSection
│     ├─ compare/          # DiffView, DriftScoreGauge, VerdictCard, CompareSection
│     └─ run/              # NewRunModal
```

---

## Alternate theme

A ready-to-use **"Harbor"** palette (cool slate + teal + amber) ships in
[`src/themes.ts`](src/themes.ts). Apply it at runtime:

```ts
// src/main.tsx
import { applyTheme, ALT_THEME_HARBOR } from './themes';
applyTheme(ALT_THEME_HARBOR);
```

…or paste its values over the `:root` block in `src/index.css` to make it the default.
