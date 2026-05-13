/** @type {import('tailwindcss').Config} */
module.exports = {
  corePlugins: {
    // Evita que el reset global rompa Angular Material (form-field, legend, etc.)
    preflight: false,
  },
  content: ["./src/**/*.{html,ts}"],
  theme: {
    extend: {
      colors: {
        oati: {
          ink: "#111827",
          muted: "#666666",
          accent: "#1e3a8a",
          line: "#434343",
          canvas: "#f8fafc",
        },
      },
    },
  },
  plugins: [],
};
