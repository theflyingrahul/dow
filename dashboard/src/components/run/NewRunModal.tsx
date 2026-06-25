import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { useStore } from '../../store/AppStore';
import type { NewRunInput, Provider } from '../../types';
import { classNames, formatDelta, formatMetric, formatPercent } from '../../lib/format';
import { METRICS } from '../../data/metrics';
import { semanticDrift } from '../../lib/drift';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { IconCheck, IconSparkle } from '../ui/icons';

const PROVIDERS: Provider[] = ['mock', 'openai', 'ollama'];

// Metrics surfaced in the draft preview (registry order is preserved on filter).
const PREVIEW_KEYS = new Set(['stability', 'accuracy', 'hallucinationRate', 'latencyMs']);

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="kicker mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-2xs text-muted">{hint}</span>}
    </label>
  );
}

const inputClass =
  'focus-ring h-11 w-full rounded-xl border border-border bg-surface px-3.5 text-sm text-ink transition-colors hover:border-brand/40 placeholder:text-muted';

export function NewRunModal() {
  const {
    isNewRunOpen,
    closeNewRun,
    previewNewRun,
    commitPreview,
    discardPreview,
    draftVersion,
    versions,
    versionsById,
    selectedId,
  } = useStore();
  const tempId = useId();

  const [baseId, setBaseId] = useState(selectedId);
  const [note, setNote] = useState('');
  const [provider, setProvider] = useState<Provider>('openai');
  const [modelName, setModelName] = useState('gpt-4o-mini');
  const [temperature, setTemperature] = useState(0.4);
  const [maxTokens, setMaxTokens] = useState(192);
  const [samples, setSamples] = useState(5);

  // Run-simulation state: a progress bar is shown after "Capture run".
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const pendingInput = useRef<NewRunInput | null>(null);

  // Seed the base from the current selection on open; reset run state on close.
  useEffect(() => {
    if (isNewRunOpen) {
      setBaseId(selectedId);
      setNote('');
    } else {
      setRunning(false);
      setProgress(0);
    }
  }, [isNewRunOpen, selectedId]);

  // Pre-fill sampling/model fields from the chosen base version.
  useEffect(() => {
    const base = versionsById[baseId];
    if (!base) return;
    setProvider(base.config.model.provider);
    setModelName(base.config.model.name);
    setTemperature(base.config.sampling.temperature);
    setMaxTokens(base.config.sampling.maxTokens);
    setSamples(base.config.evaluation.samples);
  }, [baseId, versionsById]);

  // Animate progress to 100%, then capture the version (closes + navigates).
  useEffect(() => {
    if (!running) return;
    let raf = 0;
    const start = performance.now();
    const DURATION = 2200;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      setProgress(Math.round(t * 100));
      if (t < 1) {
        raf = requestAnimationFrame(tick);
      } else if (pendingInput.current) {
        // Score the draft and move to the preview step instead of committing.
        previewNewRun(pendingInput.current);
        setRunning(false);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [running, previewNewRun]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Inputs are unconstrained; coerce to safe positive integers only on submit.
    pendingInput.current = {
      baseVersionId: baseId,
      note,
      provider,
      modelName: modelName.trim() || 'gpt-4o-mini',
      temperature,
      maxTokens: Math.max(1, Math.round(maxTokens) || 1),
      samples: Math.max(1, Math.round(samples) || 1),
    };
    setProgress(0);
    setRunning(true);
  };

  const safeSamples = Math.max(1, Math.round(samples) || 1);
  const steps = [
    { label: 'Resolve inference spec', at: 25 },
    { label: `Draw ${safeSamples} sample${safeSamples > 1 ? 's' : ''}`, at: 65 },
    { label: 'Embed outputs', at: 88 },
    { label: 'Score drift & stability', at: 100 },
  ];
  const activeIdx = steps.findIndex((s) => progress < s.at);
  const phaseLabel = activeIdx === -1 ? 'Capturing version' : steps[activeIdx].label;

  const phase: 'form' | 'running' | 'preview' = running
    ? 'running'
    : draftVersion
      ? 'preview'
      : 'form';

  // The preview always compares the draft against the version it branched from.
  const previewBase = draftVersion ? versionsById[draftVersion.parentId ?? baseId] : undefined;
  const previewDrift =
    draftVersion && previewBase ? semanticDrift(previewBase, draftVersion) : 0;
  const previewRows = METRICS.filter((m) => PREVIEW_KEYS.has(m.key));

  return (
    <Modal
      open={isNewRunOpen}
      onClose={closeNewRun}
      title="New Version"
      description="Adjust the spec, evaluate a draft, then commit when it looks right."
      footer={
        phase === 'running' ? (
          <>
            <Button variant="ghost" onClick={closeNewRun} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="button" disabled>
              Evaluating… {progress}%
            </Button>
          </>
        ) : phase === 'preview' ? (
          <>
            <Button variant="ghost" onClick={discardPreview} type="button">
              Keep tweaking
            </Button>
            <Button
              variant="primary"
              type="button"
              onClick={commitPreview}
              iconLeft={<IconCheck className="h-4 w-4" />}
            >
              Commit version
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={closeNewRun} type="button">
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              form="new-run-form"
              iconLeft={<IconSparkle className="h-4 w-4" />}
            >
              Evaluate draft
            </Button>
          </>
        )
      }
    >
      {phase === 'running' ? (
        <div className="space-y-5 py-2" role="status" aria-live="polite">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="h-9 w-9 shrink-0 animate-spin rounded-xl border-2 border-brand/30 border-t-brand"
            />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">{phaseLabel}…</p>
              <p className="text-2xs text-muted">
                Branching a child of <span className="font-mono">{baseId}</span>
              </p>
            </div>
            <span className="metric-num ml-auto text-lg font-semibold text-brand">{progress}%</span>
          </div>

          <div
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Capture progress"
            className="h-2.5 w-full overflow-hidden rounded-full bg-surface-3"
          >
            <div
              className="h-full rounded-full bg-brand-solid"
              style={{ width: `${progress}%` }}
            />
          </div>

          <ul className="space-y-2">
            {steps.map((s, i) => {
              const done = activeIdx === -1 || i < activeIdx;
              const active = i === activeIdx;
              return (
                <li key={s.label} className="flex items-center gap-2.5 text-xs">
                  <span
                    className={classNames(
                      'grid h-5 w-5 shrink-0 place-items-center rounded-full ring-1 ring-inset transition-colors',
                      done
                        ? 'bg-success/15 text-success-ink ring-success/30'
                        : active
                          ? 'bg-brand/12 text-brand ring-brand/30'
                          : 'text-muted ring-border',
                    )}
                  >
                    {done ? (
                      <IconCheck className="h-3 w-3" />
                    ) : active ? (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
                    ) : null}
                  </span>
                  <span
                    className={classNames(
                      done ? 'text-ink-soft' : active ? 'font-semibold text-ink' : 'text-muted',
                    )}
                  >
                    {s.label}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : phase === 'preview' && draftVersion ? (
        <div className="space-y-5 py-1" role="status" aria-live="polite">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-success/15 text-success-ink ring-1 ring-inset ring-success/30"
            >
              <IconCheck className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Draft evaluated</p>
              <p className="text-2xs text-muted">
                Nothing is committed yet — review the scores, then commit or keep tweaking.
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-surface-2/50 p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="kicker">Semantic drift vs {previewBase?.id ?? 'base'}</span>
              <span className="metric-num text-2xl font-semibold text-brand">
                {formatPercent(previewDrift)}
              </span>
            </div>
            <p className="mt-1 text-2xs text-muted">
              How far this draft moved from{' '}
              <span className="font-mono text-ink-soft">{previewBase?.id ?? 'its base'}</span>.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {previewRows.map((m) => {
              const value = draftVersion.metrics[m.key];
              const baseVal = previewBase?.metrics[m.key];
              const delta = baseVal === undefined ? 0 : value - baseVal;
              const improved = m.betterWhen === 'higher' ? delta >= 0 : delta <= 0;
              const flat = Math.abs(delta) < 1e-9;
              return (
                <div key={m.key} className="rounded-xl border border-border bg-surface px-3.5 py-3">
                  <p className="kicker">{m.label}</p>
                  <p className="metric-num mt-1 text-lg font-semibold text-ink">
                    {formatMetric(value, m.format)}
                  </p>
                  {baseVal !== undefined && (
                    <p
                      className={classNames(
                        'metric-num mt-0.5 text-2xs font-semibold',
                        flat ? 'text-muted' : improved ? 'text-success-ink' : 'text-danger-ink',
                      )}
                    >
                      {formatDelta(delta, m.format)} vs {previewBase?.id}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <p className="rounded-xl border border-border bg-surface-2/50 px-3 py-2.5 text-2xs leading-relaxed text-muted">
            Commit to save <span className="font-mono text-ink-soft">{draftVersion.id}</span> as a
            new version, or keep tweaking to adjust the spec and re-evaluate.
          </p>
        </div>
      ) : (
        <form id="new-run-form" onSubmit={onSubmit} className="space-y-4">
        <Field label="Branch from" hint={`Creates a child of ${baseId}.`}>
          <select
            value={baseId}
            onChange={(e) => setBaseId(e.target.value)}
            className={inputClass}
          >
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.id} · {v.summary}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Change note">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Lower temperature for steadier phrasing"
            className={inputClass}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as Provider)}
              className={inputClass}
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Model name">
            <input
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              className={inputClass}
            />
          </Field>
        </div>

        <Field label={`Temperature · ${temperature.toFixed(1)}`}>
          <div className="flex items-center gap-3">
            <input
              id={tempId}
              type="range"
              min={0}
              max={1.5}
              step={0.1}
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              className="focus-ring h-2 w-full cursor-pointer appearance-none rounded-full bg-surface-3 accent-brand"
              aria-valuetext={temperature.toFixed(1)}
            />
            <span className="metric-num w-10 shrink-0 text-right text-sm font-semibold text-ink">
              {temperature.toFixed(1)}
            </span>
          </div>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Max tokens">
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              className={inputClass}
            />
          </Field>
          <Field label="Samples (N)">
            <input
              type="number"
              value={samples}
              onChange={(e) => setSamples(Number(e.target.value))}
              className={inputClass}
            />
          </Field>
        </div>

          <p className="rounded-xl border border-border bg-surface-2/50 px-3 py-2.5 text-2xs leading-relaxed text-muted">
            Branches from <span className="font-mono text-ink-soft">{baseId}</span> and evaluates a
            draft offline against mock data. Nothing is committed until you review the scores and
            commit.
          </p>
        </form>
      )}
    </Modal>
  );
}
