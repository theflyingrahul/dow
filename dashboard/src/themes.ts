/**
 * Optional alternate color theme.
 *
 * The app is themed entirely through CSS variables defined in `src/index.css`.
 * To try this palette at runtime, call `applyTheme(ALT_THEME_HARBOR)` once on
 * startup (e.g. in `main.tsx`), or copy these values over the `:root` block in
 * `index.css` to make it the new default.
 *
 * "Harbor" trades the warm paper + violet identity for a cool slate surface
 * with a teal brand and amber accent.
 */

export type ThemeTokens = Record<string, string>;

export const ALT_THEME_HARBOR: ThemeTokens = {
  '--bg': '244 246 248',
  '--surface': '255 255 255',
  '--surface-2': '236 240 243',
  '--surface-3': '223 230 235',
  '--border': '213 222 229',

  '--ink': '16 24 33',
  '--ink-soft': '51 65 81',
  '--muted': '100 116 132',

  '--brand': '13 148 136', // teal-600
  '--brand-soft': '45 178 166',
  '--brand-solid': '13 148 136',
  '--brand-ink': '255 255 255',

  '--accent': '245 158 11', // amber-500

  '--success': '22 163 110',
  '--success-ink': '13 110 76',
  '--warning': '202 138 4',
  '--warning-ink': '133 92 0',
  '--danger': '220 38 38',
  '--danger-ink': '159 18 18',

  '--shadow': '15 35 45',
};

/** Apply a theme token map to the document root. */
export function applyTheme(tokens: ThemeTokens): void {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(tokens)) {
    root.style.setProperty(key, value);
  }
}
