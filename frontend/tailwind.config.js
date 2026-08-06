/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1320px" } },
    screens: {
      xs: "420px",
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        raised: "hsl(var(--raised))",
        grid: "hsl(var(--grid))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Financial semantics. Always paired with a sign or a word, never
        // carrying the meaning on their own.
        gain: {
          DEFAULT: "hsl(var(--gain))",
          wash: "hsl(var(--gain-wash))",
        },
        loss: {
          DEFAULT: "hsl(var(--loss))",
          wash: "hsl(var(--loss-wash))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        // Serif for company names and section titles: a financial document has
        // authority, and every other screener is sans throughout.
        display: ['ui-serif', 'Georgia', '"Iowan Old Style"', '"Times New Roman"', 'serif'],
        sans: [
          'system-ui',
          '-apple-system',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'sans-serif',
        ],
        // Numbers and micro-labels. Tabular by default via the .tabular class.
        mono: [
          'ui-monospace',
          '"SF Mono"',
          '"Cascadia Mono"',
          'Menlo',
          'Consolas',
          '"Liberation Mono"',
          'monospace',
        ],
      },
      fontSize: {
        // A deliberate scale. The jump from `data` to `hero` is the point:
        // financial UIs are uniformly 13px and have no hierarchy at all.
        micro: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.02em" }],
        data: ["0.8125rem", { lineHeight: "1.25rem" }],
        hero: ["clamp(2.75rem, 6vw, 4rem)", { lineHeight: "1", letterSpacing: "-0.03em" }],
        title: ["clamp(1.5rem, 3vw, 2rem)", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        tile: "var(--shadow-tile)",
        panel: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" },
        },
        "sweep-in": {
          from: { transform: "scaleX(0)" },
          to: { transform: "scaleX(1)" },
        },
      },
      animation: {
        // One page-load gesture, staggered by delay on the caller.
        "fade-up": "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        "sweep-in": "sweep-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
