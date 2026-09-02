/**
 * M2-07 test-harness shim for `@radix-ui/react-tooltip`, aliased in for
 * vitest ONLY (`resolve.alias` in vitest.config.ts) - never bundled into
 * the real app.
 *
 * `Tooltip` (components/ui/tooltip.tsx) is a bare Root in production; the
 * app supplies exactly ONE ambient `TooltipProvider` in
 * `components/ClientProviders.tsx`, and Radix throws "must be used within
 * TooltipProvider" without one. A unit test renders one component in
 * isolation, not the whole app shell, so the ~60 tests that happen to
 * render a page with a `Tooltip` somewhere in it - almost always incidental
 * to what they're actually testing - would each need their own
 * TooltipProvider wrapper, which is the same class of gap as jsdom missing
 * ResizeObserver/matchMedia (vitest.setup.ts): a real app-shell/environment
 * dependency the test harness doesn't supply by default.
 *
 * This wraps ONLY `Root` in the calibrated Provider and re-exports
 * everything else - Trigger/Content/Portal/Provider itself, and every other
 * Radix primitive (Dialog, Popover, DropdownMenu, ...), which live in
 * separate packages this file never touches - untouched. It imports the
 * REAL package via its resolved disk path (not the bare `@radix-ui/react-tooltip`
 * specifier) so the alias that points here does not recurse into itself.
 *
 * A test that specifically cares whether Tooltip's own body wraps in a
 * Provider reads the component SOURCE instead of relying on this shim's
 * runtime behaviour - see components/ui/tooltip.provider.test.tsx.
 */
import * as React from 'react';
// Deliberately NOT the bare `@radix-ui/react-tooltip` specifier: that string
// is what the vitest alias points HERE, so importing it here would recurse.
import * as actual from '../node_modules/@radix-ui/react-tooltip/dist/index.mjs';

const RealRoot = actual.Root;
const RealProvider = actual.Provider;

function Root(props: React.ComponentProps<typeof RealRoot>) {
  return (
    <RealProvider delayDuration={700} skipDelayDuration={300}>
      <RealRoot {...props} />
    </RealProvider>
  );
}

export const {
  Arrow,
  Content,
  Portal,
  Provider,
  Tooltip,
  TooltipArrow,
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipTrigger,
  Trigger,
  createTooltipScope,
} = actual;
export { Root };

const radixTooltipTestMock = { ...actual, Root };
export default radixTooltipTestMock;
