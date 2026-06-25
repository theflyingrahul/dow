import { useMemo } from 'react';
import { useStore } from '../../store/AppStore';
import { compareVersions } from '../../lib/drift';
import { Card, CardHeader } from '../ui/Card';
import { Reveal } from '../ui/Reveal';
import { VersionSelect } from '../ui/VersionSelect';
import { IconGauge, IconSwap } from '../ui/icons';
import { DriftScoreGauge } from './DriftScoreGauge';
import { VerdictCard } from './VerdictCard';
import { DiffView } from './DiffView';

function SelectorBar() {
  const { versions, compareFromId, compareToId, setCompareFrom, setCompareTo, swapCompare } =
    useStore();
  const same = compareFromId === compareToId;

  return (
    <Card className="p-5">
      <CardHeader kicker="Selection" title="Compare two versions" />
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <VersionSelect
          label="Baseline · A"
          value={compareFromId}
          versions={versions}
          onChange={setCompareFrom}
          dotClassName="bg-danger"
          className="flex-1"
        />
        <button
          type="button"
          onClick={swapCompare}
          aria-label="Swap baseline and candidate"
          title="Swap A and B"
          className="focus-ring mb-0.5 hidden h-11 w-11 shrink-0 place-items-center rounded-xl border border-border bg-surface text-ink-soft transition-colors hover:border-brand/40 hover:text-brand sm:grid"
        >
          <IconSwap className="h-4 w-4" />
        </button>
        <VersionSelect
          label="Candidate · B"
          value={compareToId}
          versions={versions}
          onChange={setCompareTo}
          dotClassName="bg-success"
          className="flex-1"
        />
      </div>
      {same && (
        <p className="mt-3 text-2xs text-warning-ink">
          A and B are the same version — pick two different versions to see drift.
        </p>
      )}
    </Card>
  );
}

export function CompareSection() {
  const { versionsById, compareFromId, compareToId, typicalDrift, comparisonFor } = useStore();
  const from = versionsById[compareFromId];
  const to = versionsById[compareToId];

  const comparison = useMemo(
    () =>
      from && to
        ? compareVersions(from, to, {
            typicalDrift,
            override: comparisonFor(from.id, to.id) ?? undefined,
          })
        : null,
    [from, to, typicalDrift, comparisonFor],
  );

  if (!from || !to || !comparison) return null;

  return (
    <div className="space-y-5 lg:space-y-6">
      <Reveal>
        <SelectorBar />
      </Reveal>

      <div className="grid gap-5 lg:grid-cols-12 lg:gap-6">
        <div className="space-y-5 lg:col-span-5 lg:space-y-6">
          <Reveal index={1}>
            <Card sheen className="p-5">
              <CardHeader kicker="Signal" title="Drift Score" icon={<IconGauge className="h-5 w-5" />} />
              <div className="mt-5">
                <DriftScoreGauge comparison={comparison} />
              </div>
            </Card>
          </Reveal>
          <Reveal index={2}>
            <VerdictCard comparison={comparison} />
          </Reveal>
        </div>

        <div className="lg:col-span-7">
          <Reveal index={3}>
            <DiffView from={from} to={to} />
          </Reveal>
        </div>
      </div>
    </div>
  );
}
