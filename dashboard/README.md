# dow · Drift Observation Workbench — Dashboard

An editorial, production-quality dashboard for **dow**, a tool that versions the
full AI inference spec and measures **semantic drift**, **stability**, and
**regressions** across versions. Built with **React + TypeScript + Tailwind CSS**.

> Every metric — drift score, stability delta, and the pass / warn / fail verdict
> — is recomputed **client-side from typed mock data**. No backend required.

---

## Quick start

```bash
cd dashboard
npm install
npm run dev
```

Open the printed URL (default <http://localhost:5173>).

Other scripts:

```bash
npm run build      # type-check (tsc -b) + production bundle to dist/
npm run preview    # preview the production build
npm run typecheck  # types only
```

Requirements: Node 18+ and npm.

---

## What's inside

### Information architecture

| View | Components |
| --- | --- |
| **Dashboard** | `VersionTree`, `VersionHistory`, `MetricsCards`, **New Run** CTA |
| **Version Details** | `ConfigSection`, `OutputsSection`, `MetricsSection` |
| **Compare** | `DiffView` (side-by-side / inline), `DriftScoreGauge`, `VerdictCard` |

### Behavior

- **Select a version** in the tree or history → updates Version Details **and** the Compare panel.
- **New Run** opens an accessible modal (focus-trapped) with form fields; submitting
  synthesizes a child version, evaluates it, and opens it in Details.
- **Compare** supports picking any two versions (A/B) with a swap control.
- **Drift score + verdict** recalculate from the mock data via `lib/drift.ts`,
  mirroring dow's real verdict thresholds:
  - `drift ≥ fail (0.40)` or stability drop `≥ 0.25` → **Likely Regression**
  - `drift ≥ warn (0.15)` or stability drop `≥ 0.10` → **Behavior Drift**
  - otherwise → **Consistent**

### Data

A typed dataset of **9 versions** forms a tree that branches at `v3` (→ `v4`, `v5`)
and `v6` (→ `v8`, `v9`). Metrics include `accuracy`, `rougeL`, `stability`,
`hallucinationRate`, `latencyMs`, `costUsd`, `tokenUsage`, and the custom
evaluator `avgWordCount`.

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
│  ├─ data/                # metric registry + typed mock versions
│  ├─ lib/                 # drift engine, diff, tree, formatters
│  ├─ hooks/               # useTheme
│  ├─ store/               # AppStore context (state + New Run synthesis)
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
