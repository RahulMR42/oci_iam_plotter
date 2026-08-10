import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'frontend',
  plugins: [react()],
  base: './',
  build: { outDir: '../oci_iam_plotter/static', emptyOutDir: true },
});
