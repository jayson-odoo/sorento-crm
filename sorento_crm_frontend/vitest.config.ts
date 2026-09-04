import { defineConfig } from 'vitest/config';
import path from 'path';
import react from '@vitejs/plugin-react';

export default defineConfig({
  resolve: {
    // Array form so the tooltip shim can match EXACTLY '@/components/ui/tooltip'
    // and nothing else; order matters, first match wins.
    alias: [
      // M2-07 test-harness shim: Tooltip is a bare Root in production (one
      // ambient TooltipProvider in ClientProviders.tsx), so this wraps it in
      // the calibrated Provider for the test run only - see
      // test-mocks/ui-tooltip.tsx for the full rationale. It imports the real
      // component by relative path, so this alias does not recurse.
      {
        find: /^@\/components\/ui\/tooltip$/,
        replacement: path.resolve(__dirname, 'test-mocks/ui-tooltip.tsx'),
      },
      { find: '@', replacement: path.resolve(__dirname) },
    ],
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
  },
});

