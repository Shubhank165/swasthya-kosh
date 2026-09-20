import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig } from 'vite';

// The dashboard is served from the same origin as the API in production, so the
// client asks for a relative `/api/...` and nothing in the bundle knows a
// hostname. In development that origin does not exist, and this proxy stands in
// for it — which keeps the one code path rather than teaching the client about
// a second host it would only use here.
//
// `changeOrigin` is required, not cosmetic: Cloud Run routes by the Host header,
// and without it the upgrade request for a websocket arrives at the wrong
// service and the worklist sits on "reconnecting" forever.
const API = process.env.MEDIKIOSK_API ?? 'http://localhost:8000';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      proxy: {
        '/api': { target: API, changeOrigin: true },
        '/ws': { target: API, ws: true, changeOrigin: true },
      },
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});
