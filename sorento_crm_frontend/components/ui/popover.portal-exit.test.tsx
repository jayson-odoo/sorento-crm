/**
 * M2-04 fix round - a portalled popover still gets to play its exit.
 *
 * `PopoverContent` gates its own `<AnimatePresence>` (the spring is a JS
 * animation Radix's Presence cannot detect, see lib/motion.ts), so anything
 * that unmounts the content from ABOVE kills the exit. Radix's own
 * `Portal` does exactly that: without `forceMount` it drops its subtree the
 * instant the root's `open` flips false. Every `SearchableSelect` /
 * `SearchableMultiSelect` dropdown and the 14 SCM/project-sales popovers wrap
 * `PopoverContent` in `PopoverPortal`, and the tester measured all of them
 * closing in ~21ms with no fade at all, against ~300ms for the same pair used
 * without the portal (documentation/plans/design-system/evidence/M2/README.md,
 * M2-04 Popover close).
 */
import React from 'react';
import { describe, it, expect, beforeAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from './popover';

// The suite defaults to prefers-reduced-motion (vitest.setup.ts), which
// collapses the exit to a same-frame change and would leave nothing to observe.
// Set before the first render: motion reads the media query once, lazily.
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

function PortalledHarness({ open }: { open: boolean }) {
  return (
    <Popover open={open} onOpenChange={() => {}}>
      <PopoverTrigger>Open popover</PopoverTrigger>
      <PopoverPortal>
        <PopoverContent>Popover body</PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

describe('PopoverPortal lets the exit run (M2-04)', () => {
  it('keeps the animated node mounted while it exits, then removes it', async () => {
    const { rerender } = render(<PortalledHarness open />);

    const inner = (await screen.findByText('Popover body')).closest('div') as HTMLElement;
    expect(inner).not.toBeNull();

    rerender(<PortalledHarness open={false} />);

    // Synchronous: Radix's Presence unmounts in a layout effect during the same
    // commit, so a portal that does not forward forceMount has already taken the
    // node away by the time this line runs.
    expect(document.body.contains(inner)).toBe(true);

    await waitFor(() => expect(document.body.contains(inner)).toBe(false));
  });

  it('still portals the content out to the document body', async () => {
    render(<PortalledHarness open />);

    const inner = (await screen.findByText('Popover body')).closest('div') as HTMLElement;
    expect(inner.closest('[data-slot="popover-trigger"]')).toBeNull();
    expect(document.body.contains(inner)).toBe(true);
  });

  /**
   * The portal signal is context, so it reaches every PopoverContent below it,
   * not just the one the caller wrapped. A popover opened from inside a
   * portalled popover's body would inherit the signal and portal itself out to
   * the document root, away from the surface it belongs to - so PopoverContent
   * resets the context around its own children.
   */
  it('does not pass the portal signal on to a popover nested in its body', async () => {
    render(
      <Popover open onOpenChange={() => {}}>
        <PopoverTrigger>Open outer</PopoverTrigger>
        <PopoverPortal>
          <PopoverContent>
            Outer body
            <Popover open onOpenChange={() => {}}>
              <PopoverTrigger>Open nested</PopoverTrigger>
              <PopoverContent>Nested body</PopoverContent>
            </Popover>
          </PopoverContent>
        </PopoverPortal>
      </Popover>,
    );

    const outer = (await screen.findByText(/Outer body/)).closest(
      '[data-slot="popover-content"]',
    ) as HTMLElement;
    const nested = await screen.findByText('Nested body');

    expect(outer).not.toBeNull();
    expect(outer.contains(nested)).toBe(true);
  });
});
