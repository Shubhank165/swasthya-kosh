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
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
};
