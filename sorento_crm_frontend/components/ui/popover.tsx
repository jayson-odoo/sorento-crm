'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Popover as PopoverPrimitive } from 'radix-ui';
import { AnimatePresence, motion } from 'motion/react';
import { surfaceTransition, surfaceVariants, useOpenState, useReducedMotion } from '@/lib/motion';

// Mirrors the Root's open state so PopoverContent can gate its own
// <AnimatePresence> (S8-01) - see the identical DialogOpenContext in dialog.tsx.
const PopoverOpenContext = React.createContext(true);

function Popover({
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  const [open, setOpen] = useOpenState(openProp, defaultOpen, onOpenChange);
  return (
    <PopoverOpenContext.Provider value={open}>
      <PopoverPrimitive.Root data-slot="popover" open={open} onOpenChange={setOpen} {...props} />
    </PopoverOpenContext.Provider>
  );
}

function PopoverTrigger({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

function PopoverContent({
  className,
  align = 'center',
  sideOffset = 4,
  children,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  const open = React.useContext(PopoverOpenContext);
  const prefersReducedMotion = useReducedMotion();

  // `PopoverPrimitive.Content` positions itself with an inline `transform`
  // (Radix Popper/floating-ui) that a motion.div rendered `asChild` would
  // immediately overwrite the moment the spring ticks (both want the same CSS
  // property on the same node). The spring instead animates an INNER div, so
  // Content's own positioning transform is left alone (S8-01, S8-02).
  return (
    <AnimatePresence>
      {open && (
        <PopoverPrimitive.Content
          forceMount
          data-slot="popover-content"
          align={align}
          sideOffset={sideOffset}
          className="z-50 outline-hidden origin-(--radix-popper-content-transform-origin)"
          {...props}
        >
          <motion.div
            className={cn(
              'w-72 rounded-md border border-border bg-popover p-4 text-popover-foreground shadow-md shadow-black/5',
              className,
            )}
            {...surfaceVariants(prefersReducedMotion)}
            transition={surfaceTransition(prefersReducedMotion)}
          >
            {children}
          </motion.div>
        </PopoverPrimitive.Content>
      )}
    </AnimatePresence>
  );
}

/**
 * Renders popover content in a portal at the document root.
 *
 * PopoverContent above deliberately does NOT portal (long-standing behaviour that existing
 * popovers rely on for stacking), but a popover nested inside a scrollable container is clipped
 * by that container's overflow the moment it flips to `side="top"` - the content is laid out at
 * the right coordinates yet never painted. Dialogs (`overflow-y-auto`) hit this constantly.
 * Wrap in this when the popover must escape its parent's overflow.
 */
function PopoverPortal({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Portal>) {
  return <PopoverPrimitive.Portal {...props} />;
}

export { Popover, PopoverContent, PopoverPortal, PopoverTrigger };
