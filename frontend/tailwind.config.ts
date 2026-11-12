import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Cyber-Vanguard tokens. Values resolve from CSS variables so the same
        // classes restyle instantly between light and dark mode.
        canvas: "rgb(var(--cv-canvas) / <alpha-value>)",
        structural: "rgb(var(--cv-structural) / <alpha-value>)",
        foreground: "rgb(var(--cv-fg) / <alpha-value>)",
        muted: "rgb(var(--cv-muted) / <alpha-value>)",
        accent: "rgb(var(--cv-accent) / <alpha-value>)",
        "accent-ink": "rgb(var(--cv-accent-ink) / <alpha-value>)",

        // Legacy ramps mapped onto the new tokens so existing classes
        // (bg-ink-950, text-slate-200, bg-ember-500, ...) restyle in place.
        ink: {
          950: "rgb(var(--cv-canvas) / <alpha-value>)",
          900: "rgb(var(--cv-structural) / <alpha-value>)",
          850: "rgb(var(--cv-structural) / <alpha-value>)",
          800: "rgb(var(--cv-structural) / <alpha-value>)",
          700: "rgb(var(--cv-line) / <alpha-value>)",
          600: "rgb(var(--cv-line) / <alpha-value>)",
        },
        ember: {
          400: "rgb(var(--cv-accent) / <alpha-value>)",
          500: "rgb(var(--cv-accent) / <alpha-value>)",
          600: "rgb(var(--cv-accent) / <alpha-value>)",
        },
        mint: {
          400: "rgb(var(--cv-accent) / <alpha-value>)",
          500: "rgb(var(--cv-accent) / <alpha-value>)",
        },
        slate: {
          100: "rgb(var(--cv-fg) / <alpha-value>)",
          200: "rgb(var(--cv-fg) / <alpha-value>)",
          300: "rgb(var(--cv-fg-soft) / <alpha-value>)",
          400: "rgb(var(--cv-muted) / <alpha-value>)",
          500: "rgb(var(--cv-muted) / <alpha-value>)",
          600: "rgb(var(--cv-muted) / <alpha-value>)",
        },
        volt: {
          DEFAULT: "rgb(var(--cv-accent) / <alpha-value>)",
          ink: "rgb(var(--cv-accent-ink) / <alpha-value>)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 40px rgba(204, 255, 0, 0.16)",
        "glow-sm": "0 0 14px rgba(204, 255, 0, 0.28)",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-14px)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.75)" },
        },
      },
      animation: {
        shimmer: "shimmer 2.4s linear infinite",
        "scan-line": "scan-line 7s linear infinite",
        marquee: "marquee 36s linear infinite",
        float: "float 7s ease-in-out infinite",
        "float-slow": "float 11s ease-in-out infinite",
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
