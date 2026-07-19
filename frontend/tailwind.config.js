/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class", // toggled by ThemeProvider (also respects prefers-color-scheme)
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // WCAG AA-contrast brand palette (verify pairs before shipping).
        brand: { DEFAULT: "#2563eb", fg: "#ffffff" },
        risk: {
          critical: "#dc2626",
          high: "#ea580c",
          medium: "#ca8a04",
          low: "#2563eb",
          info: "#64748b",
        },
      },
    },
  },
  plugins: [],
};
