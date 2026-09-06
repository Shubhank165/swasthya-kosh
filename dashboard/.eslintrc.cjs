/**
 * Lint rules — 3/3 §11 item 10.
 *
 * Deliberately short. Most of what could go wrong on this screen is caught by
 * `tsc --noEmit` and by the tests; what is left worth a linter is the handful
 * of rules below, two of which are project rules rather than style:
 *
 * - **no-restricted-globals / no-restricted-properties on storage.** §8 and
 *   §12: a token in `localStorage` survives the tab being closed by the next
 *   person to sit down at a shared OPD terminal. This is the one place that can
 *   be enforced mechanically rather than by review.
 * - **no-console.** §1 rule 7. The console is readable by every extension the
 *   physician has installed, and every clinical string on this screen is one a
 *   `console.log` could put there.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', 'src/api/schema.d.ts'],
  rules: {
    'no-console': 'error',
    'no-restricted-globals': [
      'error',
      {
        name: 'localStorage',
        message:
          'Never (3/3 §12). A dashboard left open on a shared OPD terminal is the exposure; anything persisted survives the tab being closed.',
      },
      {
        name: 'sessionStorage',
        message:
          'Never (3/3 §8). The access token lives in memory; the refresh cookie is httpOnly and this code cannot read it, which is the point.',
      },
    ],
    'no-restricted-properties': [
      'error',
      { object: 'window', property: 'localStorage', message: 'See no-restricted-globals.' },
      { object: 'window', property: 'sessionStorage', message: 'See no-restricted-globals.' },
    ],
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    // The codebase uses `!` where the surrounding code has already proved the
    // value is present; `tsc` is strict and the alternative is noise.
    '@typescript-eslint/no-non-null-assertion': 'off',
  },
  overrides: [
    {
      files: ['test/**/*.{ts,tsx}'],
      env: { node: true },
      rules: {
        // A test that proves nothing clinical reaches the console has to be
        // able to reach for it.
        'no-console': 'off',
      },
    },
  ],
};
