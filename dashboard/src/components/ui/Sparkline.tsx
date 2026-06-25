import { useId } from 'react';
import { classNames } from '../../lib/format';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  /** Stroke uses currentColor; set text color on a parent. */
  fill?: boolean;
  ariaLabel?: string;
}

/**
 * Minimal SVG sparkline. Normalizes the series to the view box and optionally
 * fills the area beneath the line with a soft gradient.
 */
export function Sparkline({
  data,
  width = 120,
  height = 36,
  className,
  fill = true,
  ariaLabel,
}: SparklineProps) {
  const gradientId = useId();
  if (data.length === 0) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = data.length > 1 ? width / (data.length - 1) : width;
  const pad = 3;

  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });

  const line = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height} L0,${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={classNames('overflow-visible', className)}
      role={ariaLabel ? 'img' : 'presentation'}
      aria-label={ariaLabel}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gradientId})`} stroke="none" />}
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r={2.4}
        fill="currentColor"
      />
    </svg>
  );
}
