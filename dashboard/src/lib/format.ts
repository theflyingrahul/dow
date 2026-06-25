import type { MetricDescriptor, MetricFormat } from '../types';

/** Format a raw metric value according to its descriptor. */
export function formatMetric(value: number, format: MetricFormat): string {
  switch (format) {
    case 'percent':
      return `${(value * 100).toFixed(1)}%`;
    case 'decimal':
      return value.toFixed(3);
    case 'ms':
      return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
    case 'usd':
      return `$${value.toFixed(4)}`;
    case 'int':
      return Math.round(value).toString();
    default:
      return String(value);
  }
}

export function formatMetricByDescriptor(value: number, d: MetricDescriptor): string {
  return formatMetric(value, d.format);
}

/** Signed, human-readable delta for a metric (e.g. "+2.0%", "−140ms"). */
export function formatDelta(delta: number, format: MetricFormat): string {
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '±';
  const abs = Math.abs(delta);
  switch (format) {
    case 'percent':
      return `${sign}${(abs * 100).toFixed(1)}%`;
    case 'decimal':
      return `${sign}${abs.toFixed(3)}`;
    case 'ms':
      return abs >= 1000 ? `${sign}${(abs / 1000).toFixed(2)}s` : `${sign}${Math.round(abs)}ms`;
    case 'usd':
      return `${sign}$${abs.toFixed(4)}`;
    case 'int':
      return `${sign}${Math.round(abs)}`;
    default:
      return `${sign}${abs}`;
  }
}

/** Compact percentage for drift / scores (0..1 → "0.0%"–"100.0%"). */
export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** Relative time like "2h ago", "3d ago", falling back to a date. */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diffMs = now.getTime() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Absolute timestamp for tooltips / detail headers. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Title-case a dotted config path segment, e.g. "sampling.temperature". */
export function humanizeField(field: string | null): string {
  if (!field) return '—';
  const last = field.split('.').pop() ?? field;
  return last
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}

export function classNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
