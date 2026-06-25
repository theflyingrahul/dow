import { useState, type ReactNode } from 'react';
import type { Version } from '../../types';
import { serializeSpec } from '../../lib/diff';
import { classNames } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { Badge, type BadgeTone } from '../ui/Badge';
import { Button } from '../ui/Button';
import { IconCheck, IconCopy, IconSliders } from '../ui/icons';

const PROVIDER_TONE: Record<string, BadgeTone> = {
  mock: 'neutral',
  openai: 'brand',
  ollama: 'accent',
};

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <p className="kicker mb-2">{label}</p>
      <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface-2/40">
        {children}
      </div>
    </section>
  );
}

function KV({ k, v, mono = true }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 px-3 py-2">
      <span className="font-mono text-2xs text-muted">{k}</span>
      <span className={classNames('truncate text-sm text-ink', mono && 'font-mono')}>{v}</span>
    </div>
  );
}

function SamplingChip({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <p className="font-mono text-[10px] uppercase tracking-wide text-muted">{k}</p>
      <p className="metric-num mt-0.5 text-sm font-semibold text-ink">{v}</p>
    </div>
  );
}

export function ConfigSection({ version }: { version: Version }) {
  const { prompt, model, sampling, evaluation } = version.config;
  const [copied, setCopied] = useState(false);

  const copySpec = async () => {
    try {
      await navigator.clipboard.writeText(serializeSpec(version.config).join('\n'));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <Card className="p-5">
      <CardHeader
        kicker="Specification"
        title="Config"
        icon={<IconSliders className="h-5 w-5" />}
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={copySpec}
            iconLeft={copied ? <IconCheck className="h-3.5 w-3.5" /> : <IconCopy className="h-3.5 w-3.5" />}
          >
            {copied ? 'Copied' : 'Copy spec'}
          </Button>
        }
      />

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div className="space-y-5">
        <Group label="Prompt">
          <div className="px-3 py-3">
            <p className="font-mono text-2xs text-muted">system</p>
            <p className="mt-1 border-l-2 border-brand/40 pl-3 text-sm italic leading-relaxed text-ink-soft">
              {prompt.system}
            </p>
          </div>
          <div className="px-3 py-3">
            <p className="font-mono text-2xs text-muted">template</p>
            <pre className="scroll-slim mt-1 overflow-x-auto rounded-lg bg-ink/[0.04] p-3 font-mono text-xs leading-relaxed text-ink dark:bg-white/[0.04]">
              {prompt.template}
            </pre>
          </div>
          <div className="px-3 py-2.5">
            <KV
              k="few_shot"
              mono={false}
              v={
                prompt.fewShot.length === 0 ? (
                  <span className="text-muted">none</span>
                ) : (
                  <span className="text-ink">{prompt.fewShot.length} exemplars</span>
                )
              }
            />
          </div>
        </Group>
        </div>

        <div className="space-y-5">
        <Group label="Model">
          <KV
            k="provider"
            v={<Badge tone={PROVIDER_TONE[model.provider] ?? 'neutral'}>{model.provider}</Badge>}
            mono={false}
          />
          <KV k="name" v={model.name} />
          <KV k="version" v={model.version} />
          <KV k="revision" v={model.revision ?? 'null'} />
        </Group>

        <section>
          <p className="kicker mb-2">Sampling</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <SamplingChip k="temperature" v={sampling.temperature} />
            <SamplingChip k="top_p" v={sampling.topP} />
            <SamplingChip k="max_tokens" v={sampling.maxTokens} />
            <SamplingChip k="freq_penalty" v={sampling.frequencyPenalty} />
            <SamplingChip k="pres_penalty" v={sampling.presencePenalty} />
            <SamplingChip k="seed" v={sampling.seed} />
          </div>
        </section>

        <Group label="Evaluation">
          <KV k="embedding_model" v={evaluation.embeddingModel} />
          <KV k="samples" v={evaluation.samples} />
          <div className="px-3 py-2.5">
            <p className="font-mono text-2xs text-muted">metrics</p>
            <ul className="mt-1.5 space-y-1">
              {evaluation.metrics.map((m) => (
                <li
                  key={m}
                  className="rounded-md bg-surface px-2 py-1 font-mono text-xs text-ink ring-1 ring-border"
                >
                  {m}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex items-center justify-between gap-4 px-3 py-2">
            <span className="font-mono text-2xs text-muted">thresholds</span>
            <span className="flex items-center gap-2 font-mono text-xs">
              <span className="text-warning-ink">warn {evaluation.thresholds.warn}</span>
              <span className="text-danger-ink">fail {evaluation.thresholds.fail}</span>
            </span>
          </div>
        </Group>
        </div>
      </div>
    </Card>
  );
}
