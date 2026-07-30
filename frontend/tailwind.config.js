/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#5B5BF6", dark: "#3E3ECF", bg: "#EEEDFE" },
        danger: { bg: "#FCEBEB", text: "#A32D2D", DEFAULT: "#E24B4A" },
        safe: { bg: "#E1FAF0", text: "#08795D", DEFAULT: "#10B981" },
        neutral: { bg: "#FAEEDA", text: "#854F0B", DEFAULT: "#F5A623" },
        disaster: { bg: "#FFEDD5", text: "#9A3412", DEFAULT: "#F97316" },
        ink: "#0F1115",
        muted: "#9295A0",
        paper: "#FAFAFA",
      },
    },
  },
  plugins: [],
};