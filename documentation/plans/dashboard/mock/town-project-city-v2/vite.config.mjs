// Mock build only (build.sh). No `import 'vite'`: this folder has no node_modules; build.sh runs the frontend's vite.
import path from 'node:path';
import { createRequire } from 'node:module';
const here = path.dirname(new URL(import.meta.url).pathname);
const fe = path.resolve(here, '../../../../../sorento_crm_frontend');
const tw = createRequire(path.join(fe, 'package.json'))('@tailwindcss/postcss');
export default {
  root: here,
  base: './',
  logLevel: 'warn',
  resolve: { alias: [{ find: 'three', replacement: path.join(fe, 'node_modules/three') }, { find: /^@\//, replacement: fe + '/' }] },
  css: { postcss: { plugins: [tw()] } },
  build: { outDir: process.env.MOCK_OUT, emptyOutDir: true, assetsInlineLimit: 100000000, chunkSizeWarningLimit: 4000, rollupOptions: { input: path.join(here, 'mock.html') } },
};
