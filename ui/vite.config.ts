import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  preview: { port: 4173 },
  // The sample world (src/mock/real.json, ~1.2 MB) ships in the bundle on purpose: VITE_MOCK=1 must work offline.
  build: { chunkSizeWarningLimit: 2000 },
});
