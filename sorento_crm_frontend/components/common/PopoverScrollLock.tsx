'use client';

import * as React from 'react';
import { Slot } from 'radix-ui';
import { RemoveScroll } from 'react-remove-scroll';

/**
 * Wraps a Popover's content in the SAME `react-remove-scroll` lock Radix's own `modal`
 * Popover uses internally (`@radix-ui/react-popover`'s `PopoverContentModal`), via `Slot`
 * so no extra DOM node is introduced - `RemoveScroll`'s lock stack is last-mounted-wins,
 * so mounting one here makes IT the active lock while open, letting a wheel over THIS
 * content scroll even when it is portalled inside an open Dialog's own lock target.
 *
 * Deliberately NOT `<Popover modal>`: that also pulls in Radix's `hideOthers`, which
 * `aria-hide`s everything outside the popover while open - wrong for a small inline
 * picker (see `SearchableSelect`'s `needsDialogScrollLock` comment for the two real
 * regressions that traced back to it). This wrapper is the scroll-lock half only.
 */
export function PopoverScrollLock({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactElement;
}) {
  if (!active) return children;
  return (
    <RemoveScroll as={Slot.Slot} allowPinchZoom>
      {children}
    </RemoveScroll>
  );
}
