import { useStore } from '../../store/AppStore';
import { Card } from '../ui/Card';
import { SpecEditor } from './SpecEditor';

/**
 * Empty-state shown in live mode when a spec exists but no versions have been
 * captured yet (e.g. right after `dow init`). Lets you edit the spec and capture
 * the first version without leaving the dashboard.
 */
export function GetStarted() {
  const { specName } = useStore();
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <p className="kicker">Get started</p>
        <h2 className="mt-1 font-display text-2xl font-semibold text-ink">
          Capture your first version
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink-soft">{specName ?? 'your spec'}</span> has no versions
          yet. Edit the spec below and capture <span className="font-mono">v1</span> — dow runs it,
          measures stability, and starts tracking how its behavior drifts as you iterate.
        </p>
      </div>
      <Card className="p-5">
        <SpecEditor firstRun />
      </Card>
    </div>
  );
}
