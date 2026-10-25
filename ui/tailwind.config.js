/** @type {import('tailwindcss').Config} */
const c = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: c('bg'),
        surface: c('surface'),
        rail: c('rail'),
        line: c('line'),
        ink: c('ink'),
        ink2: c('ink2'),
        ink3: c('ink3'),
        accent: c('accent'),
        'accent-strong': c('accent-strong'),
        'accent-tint': c('accent-tint'),
        danger: c('danger'),
        'danger-tint': c('danger-tint'),
        warn: c('warn'),
        'warn-tint': c('warn-tint'),
      },
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['ui-monospace', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        eyebrow: ['0.8125rem', { lineHeight: '1.2', letterSpacing: '0.08em' }],
        hero: ['clamp(2.5rem, 4.2vw, 4rem)', { lineHeight: '1.05', letterSpacing: '-0.035em' }],
        giant: ['clamp(4rem, 8vw, 8.5rem)', { lineHeight: '0.95', letterSpacing: '-0.05em' }],
        big: ['clamp(2.75rem, 4.6vw, 4.75rem)', { lineHeight: '1', letterSpacing: '-0.045em' }],
        stat: ['clamp(2.25rem, 3.3vw, 4.25rem)', { lineHeight: '1', letterSpacing: '-0.04em' }],
      },
      maxWidth: { page: '78rem' },
      boxShadow: {
        lift: '0 1px 2px rgb(13 27 42 / 0.06), 0 4px 16px -4px rgb(13 27 42 / 0.08)',
        seg: '0 1px 2px rgb(13 27 42 / 0.10), 0 2px 8px -2px rgb(13 27 42 / 0.10)',
      },
      keyframes: {
        rise: { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'none' } },
        fade: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        flash: { '0%': { backgroundColor: 'rgb(var(--c-accent-tint))' }, '100%': { backgroundColor: 'transparent' } },
        shake: { '0%,100%': { transform: 'none' }, '20%': { transform: 'translateX(-5px)' }, '40%': { transform: 'translateX(4px)' }, '60%': { transform: 'translateX(-3px)' }, '80%': { transform: 'translateX(2px)' } },
        pulseDot: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
      },
      animation: {
        rise: 'rise 420ms cubic-bezier(0.2, 0.7, 0.2, 1) both',
        fade: 'fade 300ms ease-out both',
        flash: 'flash 2.4s ease-out both',
        shake: 'shake 420ms ease-in-out',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
