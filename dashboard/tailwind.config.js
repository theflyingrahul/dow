/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Color system is driven entirely by CSS variables (see src/index.css).
      // Channels are stored as "R G B" triplets so Tailwind's <alpha-value>
      // opacity modifiers (e.g. bg-brand/15) keep working.
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        'surface-2': 'rgb(var(--surface-2) / <alpha-value>)',
        'surface-3': 'rgb(var(--surface-3) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        'ink-soft': 'rgb(var(--ink-soft) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        brand: 'rgb(var(--brand) / <alpha-value>)',
        'brand-soft': 'rgb(var(--brand-soft) / <alpha-value>)',
        'brand-solid': 'rgb(var(--brand-solid) / <alpha-value>)',
        'brand-ink': 'rgb(var(--brand-ink) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        success: 'rgb(var(--success) / <alpha-value>)',
        'success-ink': 'rgb(var(--success-ink) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        'warning-ink': 'rgb(var(--warning-ink) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
        'danger-ink': 'rgb(var(--danger-ink) / <alpha-value>)',
      },
      fontFamily: {
        display: ['Fraunces', 'ui-serif', 'Georgia', 'Cambria', 'serif'],
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        kicker: '0.18em',
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        card: '0 1px 2px rgb(var(--shadow) / 0.04), 0 8px 24px -12px rgb(var(--shadow) / 0.18)',
        elevated:
          '0 2px 4px rgb(var(--shadow) / 0.05), 0 24px 48px -20px rgb(var(--shadow) / 0.30)',
        ring: '0 0 0 1px rgb(var(--border) / 1)',
        glow: '0 0 0 1px rgb(var(--brand) / 0.35), 0 12px 40px -12px rgb(var(--brand) / 0.45)',
      },
      backgroundImage: {
        'grid-faint':
          'linear-gradient(to right, rgb(var(--ink) / 0.035) 1px, transparent 1px), linear-gradient(to bottom, rgb(var(--ink) / 0.035) 1px, transparent 1px)',
        'brand-sheen':
          'radial-gradient(120% 120% at 0% 0%, rgb(var(--brand) / 0.18), transparent 55%), radial-gradient(120% 120% at 100% 0%, rgb(var(--accent) / 0.14), transparent 50%)',
      },
      keyframes: {
        reveal: {
          from: { opacity: '0', transform: 'translateY(14px) scale(0.99)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'slide-in-right': {
          from: { opacity: '0', transform: 'translateX(24px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'sweep': {
          from: { strokeDashoffset: 'var(--dash, 999)' },
          to: { strokeDashoffset: 'var(--dash-to, 0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        reveal: 'reveal 0.6s cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 0.4s ease both',
        'scale-in': 'scale-in 0.28s cubic-bezier(0.22, 1, 0.36, 1) both',
        'slide-in-right': 'slide-in-right 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
        sweep: 'sweep 1.1s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};
