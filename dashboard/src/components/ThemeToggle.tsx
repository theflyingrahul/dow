import { useTheme } from '../hooks/useTheme';
import { IconMoon, IconSun } from './ui/icons';
import { classNames } from '../lib/format';

/** Light/dark toggle with an animated icon swap. Defaults to light. */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Light theme' : 'Dark theme'}
      className={classNames(
        'focus-ring relative grid h-10 w-10 place-items-center rounded-xl border border-border bg-surface text-ink-soft transition-colors hover:border-brand/40 hover:text-ink',
        className,
      )}
    >
      <span
        className={classNames(
          'absolute transition-all duration-300 ease-spring',
          isDark ? 'rotate-0 opacity-100' : '-rotate-90 opacity-0',
        )}
      >
        <IconMoon />
      </span>
      <span
        className={classNames(
          'absolute transition-all duration-300 ease-spring',
          isDark ? 'rotate-90 opacity-0' : 'rotate-0 opacity-100',
        )}
      >
        <IconSun />
      </span>
    </button>
  );
}
