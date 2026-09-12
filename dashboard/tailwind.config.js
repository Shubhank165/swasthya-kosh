/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic names, never raw palette values in a component. A fact state
        // that is styled by `text-amber-600` in one place and `text-yellow-500`
        // in another is a fact state a physician learns twice.
        surface: { DEFAULT: '#ffffff', sunken: '#f6f7f9', raised: '#ffffff' },
        ink: { DEFAULT: '#14181f', muted: '#5a6472', faint: '#8b95a3' },
        line: { DEFAULT: '#dfe3e9', strong: '#c3cad4' },
        accent: { DEFAULT: '#1d4ed8', soft: '#eff4ff' },
        // The four states that mean "trust this less". Each also carries a
        // shape and a label — §4.2: never colour alone.
        uncertain: { DEFAULT: '#8a5a00', soft: '#fdf5e6' },
        repaired: { DEFAULT: '#5b3fa8', soft: '#f3f0fd' },
        conflict: { DEFAULT: '#a8321f', soft: '#fdf0ee' },
        verified: { DEFAULT: '#1a6b45', soft: '#eef8f2' },
        urgent: { DEFAULT: '#b3261e', soft: '#fdecea' },
      },
      // Inter was declared here and never loaded — no @font-face, no link in
      // index.html — so every screen has always rendered in system-ui while
      // the config claimed otherwise. A declared font that never arrives is a
      // design system that lies about itself, and the fix is to drop the name
      // rather than add the network request: this dashboard runs inside a
      // hospital, where a blocked CDN would mean the report reflows on the one
      // machine that could not reach it. What is listed is what renders.
      //
      // The Devanagari fallbacks are explicit because the report shows the
      // patient's own words in their own script (§9), and a stack that ends at
      // `sans-serif` leaves that to whatever the machine happens to pick.
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Noto Sans',
          'Noto Sans Devanagari',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};
