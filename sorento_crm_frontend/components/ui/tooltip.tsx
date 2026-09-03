'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { cva, type VariantProps } from 'class-variance-authority';
import { Tooltip as TooltipPrimitive } from 'radix-ui';

function TooltipProvider({ delayDuration = 0, ...props }: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" delayDuration={delayDuration} {...props} />;
}

/**
 * A bare Root (M2-07) - no per-instance TooltipProvider. Exactly one
 * TooltipProvider mounts app-wide, in ClientProviders.tsx: nesting a second
 * one here would shadow it for every Tooltip underneath, which is what
 * fragmented the delay into a per-toolbar (or even per-button) 0ms instead of
 * one shared 700ms-first/300ms-sibling rhythm.
 */
function Tooltip({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TooltipTrigger({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

const tooltipVariants = cva(
  // z-[70] keeps tooltips above cards AND dialog overlays/content (both z-50);
  // rendered through a Portal (below) so a card's stacking context can't clip them.
  //
  // No entry and no exit (M2-07). A tooltip is too small and too transient for
  // a spring, and the frequency gate puts hover at "none or a fast opacity" -
  // so this is the one surface with no motion at all. The transparent-to-opaque
  // CSS transition keyed on `data-state` that used to sit here could not run in
  // either direction and is gone rather than left as decoration: Radix mounts
  // the content already carrying `delayed-open`/`instant-open` (its
  // `stateAttribute` is only `closed` while the content is unmounted), so the
  // entry has no starting value to travel from, and Radix's Presence waits on
  // `animationend` alone, so a transition-only style unmounts on the closing
  // frame.
  'z-[70] overflow-hidden rounded-md px-3 py-1.5 text-xs',
  {
    variants: {
      variant: {
        light: 'border border-border bg-background text-foreground shadow-md shadow-black/5',
        dark: 'dark:border dark:border-border bg-zinc-950 text-white dark:bg-zinc-300 dark:text-black shadow-md shadow-black/5',
      },
    },
    defaultVariants: {
      variant: 'dark',
    },
  },
);

function TooltipContent({
  className,
  sideOffset = 4,
  variant,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content> & VariantProps<typeof tooltipVariants>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(tooltipVariants({ variant }), className)}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
