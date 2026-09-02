/**
 * Test-harness shim for `@/components/ui/tooltip`, aliased in for vitest ONLY
 * (`resolve.alias` in vitest.config.ts) - never bundled into the real app.
 *
 * `Tooltip` is a bare Root in production (M2-07): the app supplies exactly ONE
 * ambient `TooltipProvider`, in `components/ClientProviders.tsx`, and Radix
 * throws "must be used within TooltipProvider" without one. A unit test renders
 * one component in isolation, not the whole app shell, so the ~60 tests that
 * happen to render a page with a `Tooltip` somewhere in it - almost always
 * incidental to what they are testing - would each need their own wrapper.
 * That is the same class of gap as jsdom missing ResizeObserver/matchMedia
 * (vitest.setup.ts): an app-shell dependency the harness has to supply.
 *
 * This shims OUR module rather than Radix's package, so it reaches every
 * consumer through one Vite-resolved specifier and leaves Radix alone -
 * the earlier `@radix-ui/react-tooltip` alias needed `radix-ui` inlined
 * (the unified package resolves its own `require` outside Vite), which pulled
 * every Radix primitive in the app through Vite's transform pipeline.
 *
 * Everything else is re-exported untouched, and the real components are
 * imported by relative path so a test that wants them (see
 * `components/ui/tooltip.provider.test.tsx`, which imports `./tooltip`) still
 * gets the unwrapped module.
 */
import * as React from 'react';
import {
  Tooltip as RealTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/ui/tooltip';

function Tooltip(props: React.ComponentProps<typeof RealTooltip>) {
  return (
    <TooltipProvider delayDuration={700} skipDelayDuration={300}>
      <RealTooltip {...props} />
    </TooltipProvider>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
