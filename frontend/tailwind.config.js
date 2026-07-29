/**
 * Tailwind configuration — the bridge between the design tokens in
 * `src/styles/tokens.css` and the class names used in components.
 *
 * Colours resolve to `rgb(var(--token) / <alpha-value>)`. That indirection is
 * what lets a single set of class names (`bg-surface`, `text-muted`) work in
 * both themes: the theme swaps the variable, not the class. It also keeps
 * Tailwind's opacity modifiers working, so `bg-surface/50` is still valid.
 *
 * To change a colour, edit `tokens.css`, not this file.
 */

import animate from 'tailwindcss-animate'

/** @param {string} token */
function withAlpha(token) {
  return `rgb(var(${token}) / <alpha-value>)`
}

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: withAlpha('--bg'),
        'bg-subtle': withAlpha('--bg-subtle'),
        surface: withAlpha('--surface'),
        'surface-2': withAlpha('--surface-2'),
        border: withAlpha('--border'),
        'border-focus': withAlpha('--border-focus'),
        text: withAlpha('--text'),
        'text-muted': withAlpha('--text-muted'),
        'text-dim': withAlpha('--text-dim'),
        accent: withAlpha('--accent'),
        'accent-fg': withAlpha('--accent-fg'),
        sev: {
          critical: withAlpha('--sev-critical'),
          high: withAlpha('--sev-high'),
          medium: withAlpha('--sev-medium'),
          low: withAlpha('--sev-low'),
          info: withAlpha('--sev-info'),
        },
        ok: withAlpha('--ok'),
      },
      fontFamily: {
        // JetBrains Mono is mandatory for machine data — CVE IDs, hashes, IPs,
        // ports, versions, timestamps (SPEC §9.1).
        sans: ['Inter Variable', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        // SPEC §9.1: base 14px UI, 13px table text.
        xs: ['0.6875rem', { lineHeight: '1rem' }],
        sm: ['0.8125rem', { lineHeight: '1.125rem' }],
        base: ['0.875rem', { lineHeight: '1.25rem' }],
        lg: ['1rem', { lineHeight: '1.5rem' }],
        xl: ['1.125rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.375rem', { lineHeight: '1.875rem' }],
      },
      borderRadius: {
        // SPEC §9.1: rounded-md (6px) is the ceiling — sharp-ish, never pill.
        sm: '3px',
        DEFAULT: '4px',
        md: '6px',
        lg: '6px',
      },
      spacing: {
        // 4px grid (SPEC §9.1). Row heights for the density toggle.
        'row-comfortable': '2.75rem',
        'row-compact': '2rem',
      },
      keyframes: {
        'progress-hairline': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(400%)' },
        },
        'skeleton-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        // The thin top-of-viewport progress line shown during collection runs.
        'progress-hairline': 'progress-hairline 1.4s ease-in-out infinite',
        // SPEC §9.1: skeleton loaders for content, never spinners.
        skeleton: 'skeleton-pulse 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
}
