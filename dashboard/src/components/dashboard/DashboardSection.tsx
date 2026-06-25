import { useStore } from '../../store/AppStore';
import { Reveal } from '../ui/Reveal';
import { IconSparkle } from '../ui/icons';
import { MetricsCards } from './MetricsCards';
import { VersionTree } from './VersionTree';
import { VersionHistory } from './VersionHistory';

function Hero() {
  const { versions, headId } = useStore();

  return (
    <div className="panel relative overflow-hidden p-6 lg:p-8">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-brand-sheen opacity-80" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-2xl">
          <span className="kicker inline-flex items-center gap-1.5">
            <IconSparkle className="h-3.5 w-3.5 text-brand" />
            spec · summarization
          </span>
          <h2 className="mt-2 font-display text-3xl font-semibold leading-[1.05] tracking-tight text-ink sm:text-4xl">
            Version your AI&rsquo;s behavior,
            <span className="text-brand"> measure the drift.</span>
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">
            Compare any two versions to see semantic drift, stability, and a pass / warn / fail
            verdict — attributed to the exact field that changed.
          </p>
        </div>

        <div className="flex shrink-0 items-stretch gap-3">
          <div className="rounded-2xl border border-border bg-surface/70 px-4 py-3 text-center">
            <p className="metric-num text-2xl font-semibold text-ink">{versions.length}</p>
            <p className="kicker mt-0.5">versions</p>
          </div>
          <div className="rounded-2xl border border-border bg-surface/70 px-4 py-3 text-center">
            <p className="metric-num text-2xl font-semibold text-brand">{headId}</p>
            <p className="kicker mt-0.5">head</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DashboardSection() {
  const { selectedId } = useStore();

  return (
    <div className="space-y-6 lg:space-y-7">
      <Reveal>
        <Hero />
      </Reveal>

      <section aria-label="Metrics overview" className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="kicker">
            Metrics · <span className="font-mono text-brand">{selectedId}</span>
          </h3>
          <p className="text-2xs text-muted">vs. parent · trend over lineage</p>
        </div>
        <MetricsCards />
      </section>

      <div className="grid gap-5 lg:grid-cols-12 lg:gap-6">
        <div className="lg:col-span-7">
          <Reveal index={2}>
            <VersionTree />
          </Reveal>
        </div>
        <div className="lg:col-span-5">
          <Reveal index={3}>
            <VersionHistory />
          </Reveal>
        </div>
      </div>
    </div>
  );
}
