import type { CSSProperties, ElementType, ReactNode } from 'react';
import { classNames } from '../../lib/format';

interface RevealProps {
  children: ReactNode;
  /** Sequence index used to stagger the entrance (≈70ms apart). */
  index?: number;
  delay?: number;
  as?: ElementType;
  className?: string;
}

/**
 * Wraps content in a staggered entrance animation. Honors prefers-reduced-motion
 * via the global CSS reset in index.css.
 */
export function Reveal({ children, index = 0, delay, as: Tag = 'div', className }: RevealProps) {
  const computed = delay ?? index * 70;
  return (
    <Tag
      className={classNames('reveal-on-load', className)}
      style={{ '--d': `${computed}ms` } as CSSProperties}
    >
      {children}
    </Tag>
  );
}
