'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Popover as PopoverPrimitive } from 'radix-ui';
import { AnimatePresence, motion } from 'motion/react';
import {
  surfaceExitTransition,
  surfaceTransition,
  surfaceVariants,
  useOpenState,
  useReducedMotion,
} from '@/lib/motion';

// Mirrors the Root's open state so PopoverContent can gate its own
// <AnimatePresence> (S8-01) - see the identical DialogOpenContext in dialog.tsx.
const PopoverOpenContext = React.createContext(true);

// Set by PopoverPortal (below) so PopoverContent can render the portal ITSELF,
// from inside its own AnimatePresence gate (M2-04).
type PopoverPortalOptions = {
  container: React.ComponentProps<typeof PopoverPrimitive.Portal>['container'];
};
const PopoverPortalContext = React.createContext<PopoverPortalOptions | null>(null);

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
  const portal = React.useContext(PopoverPortalContext);
  const prefersReducedMotion = useReducedMotion();
  const variants = surfaceVariants(prefersReducedMotion);
  const transition = surfaceTransition(prefersReducedMotion, 'menu');
  const exitTransition = surfaceExitTransition(prefersReducedMotion);

  // `PopoverPrimitive.Content` positions itself with an inline `transform`
  // (Radix Popper/floating-ui) that a motion.div rendered `asChild` would
  // immediately overwrite the moment the spring ticks (both want the same CSS
  // property on the same node). The spring instead animates an INNER div, so
  // Content's own positioning transform is left alone (S8-01, S8-02).
  //
  // Radix sets `--radix-popover-content-transform-origin` (not the generic
  // `--radix-popper-content-transform-origin`, which doesn't exist) as an
  // inline style on `Content` itself; the inner motion.div reads it via CSS
  // custom-property inheritance, which is also where the actual `scale`
  // animation runs, so the origin has to live there too (S8-02).
  const content = (
    <PopoverPrimitive.Content
      forceMount
      data-slot="popover-content"
      align={align}
      sideOffset={sideOffset}
      className="z-50 outline-hidden"
      {...props}
    >
      <motion.div
        className={cn(
          'w-72 rounded-md border border-border bg-popover p-4 text-popover-foreground shadow-md shadow-black/5 origin-(--radix-popover-content-transform-origin)',
          className,
        )}
        initial={variants.initial}
        animate={variants.animate}
        exit={{ ...variants.exit, transition: exitTransition }}
        transition={transition}
      >
        {children}
      </motion.div>
    </PopoverPrimitive.Content>
  );

  // Portalled callers (PopoverPortal, below) get the portal from HERE, inside
  // the gate, with `forceMount` - the same shape DropdownMenuContent uses. A
  // Radix Portal wrapped around this component from the outside drops its whole
  // subtree the instant the root's `open` flips false, which took the exit
  // spring with it: every SearchableSelect dropdown closed in ~21ms with no
  // fade, against ~300ms for the same pair used unportalled (M2-04).
  return (
    <AnimatePresence>
      {open &&
        (portal ? (
          <PopoverPrimitive.Portal forceMount container={portal.container}>
            {content}
          </PopoverPrimitive.Portal>
        ) : (
          content
        ))}
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
 *
 * This does not render Radix's Portal itself: it only tells PopoverContent to render one from
 * inside its own AnimatePresence (M2-04). Wrapping from the outside is what killed the exit
 * spring, and adding `forceMount` here instead would keep an empty portal div - plus a mounted
 * PopoverContent - alive for every closed popover on the page, which the packing-list schedule
 * matrix has one of per cell.
 */
function PopoverPortal({ children, container }: React.ComponentProps<typeof PopoverPrimitive.Portal>) {
  const value = React.useMemo(() => ({ container }), [container]);
  return <PopoverPortalContext.Provider value={value}>{children}</PopoverPortalContext.Provider>;
}

export { Popover, PopoverContent, PopoverPortal, PopoverTrigger };
