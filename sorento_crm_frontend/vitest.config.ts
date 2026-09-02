import { defineConfig } from 'vitest/config';
import path from 'path';
import react from '@vitejs/plugin-react';

export default defineConfig({
  resolve: {
    alias: {
      // M2-07 test-harness shim: Tooltip is a bare Root in production (one
      // ambient TooltipProvider in ClientProviders.tsx), so this wraps Root
      // in the calibrated Provider for the test run only - see
      // test-mocks/radix-tooltip.tsx for the full rationale. Listed BEFORE
      // '@' so its own internal import of the real package (a relative disk
      // path, not this specifier) is unaffected.
      '@radix-ui/react-tooltip': path.resolve(__dirname, 'test-mocks/radix-tooltip.tsx'),
      '@': path.resolve(__dirname),
    },
  },
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    /*
      Comfortably above the 5s Testing Library gives one async assertion (see
      vitest.setup.ts). Equal budgets mean the TEST times out first and reports
      "timed out in 5000ms" instead of the assertion's own message, which says
      what was actually missing from the DOM - so a real failure arrives with no
      diagnosis at all.
    */
    testTimeout: 20000,
    exclude: ['node_modules/**', 'e2e/**', '.next/**'],
    // The M2-07 tooltip alias above only reaches an import Vite itself
    // resolves. `radix-ui` (the unified package Dialog/Popover/DropdownMenu/
    // AlertDialog/Sheet/Menubar/Tooltip all import from) ships as a single
    // externalized CJS module by default, so its OWN `require('@radix-ui/
    // react-tooltip')` runs through plain Node resolution and never sees the
    // alias. Inlining it makes Vite process its imports too.
    server: {
      deps: {
        inline: ['radix-ui'],
      },
    },
  },
});

