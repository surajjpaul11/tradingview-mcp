import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  root: resolve(import.meta.dirname, 'src/tradingview_mcp/ui/charts_src'),
  base: '/static/charts/',
  plugins: [react()],
  build: {
    outDir: resolve(import.meta.dirname, 'src/tradingview_mcp/ui/static/charts'),
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8002',
    },
  },
});
