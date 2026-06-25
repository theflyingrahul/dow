import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
// Relative base so the built bundle works when served from any path by the
// `dow dashboard` server. Output is emitted into the Python package's `web/`
// directory so it ships as package data on `pip install`.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../dow/web',
    emptyOutDir: true,
  },
});
