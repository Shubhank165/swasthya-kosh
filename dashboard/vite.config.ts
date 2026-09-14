import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The dashboard is served from the same origin as the API in production,
      // so the refresh cookie is first-party and nothing needs CORS. In dev the
      // proxy reproduces that, rather than teaching the client about a second
      // origin it will never see again.
      '/api': { target: process.env.MEDIKIOSK_API ?? 'http://localhost:8000', changeOrigin: true },
      // `changeOrigin` matters as much here as on `/api`: Cloud Run routes by
      // Host, so an upgrade forwarded with the dev server's own Host never
      // reaches the service and the worklist sits on "reconnecting" forever.
      '/ws': {
        target: process.env.MEDIKIOSK_API ?? 'http://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    // Testing Library's automatic cleanup hooks onto the global `afterEach`.
    // Without this each `render` stacks on the last one and every query finds
    // two of everything — which reads like a duplicate-rendering bug and is
    // really a missing teardown.
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./test/setup.ts'],
    include: ['test/**/*.test.{ts,tsx}'],
  },
});
