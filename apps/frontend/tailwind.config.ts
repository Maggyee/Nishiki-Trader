import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Manrope", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 2px rgb(15 23 42 / 0.04), 0 18px 40px -28px rgb(15 23 42 / 0.35)",
        lift: "0 10px 30px -20px rgb(15 23 42 / 0.28)",
      },
      colors: {
        ink: {
          DEFAULT: "#102033",
          soft: "#3d4f63",
          faint: "#6b7c8f",
        },
        sea: {
          50: "#f1f8f8",
          100: "#d9ecec",
          200: "#b7d8d9",
          500: "#1f7a78",
          700: "#145b5a",
        },
        ember: {
          50: "#fff7ed",
          500: "#c05621",
          700: "#9a3412",
        },
        coral: {
          50: "#fff1f2",
          500: "#be123c",
          700: "#9f1239",
        },
      },
    },
  },
  plugins: [],
};

export default config;
