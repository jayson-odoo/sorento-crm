/**
 * M2-01 - a palette opened by a keyboard shortcut never animates.
 *
 * `CommandDialog` with `motion={false}` renders `DialogContent` on the
 * no-motion path: no scale and no entry fade (initial === animate, nothing for
 * the spring to interpolate), a zero-duration `opacity: 0` exit, and the
 * content marked `data-motion="off"` so a browser pass can confirm the
 * DevTools Animations panel shows nothing running on it.
 */
import React from 'react';
import { afterEach, beforeEach, describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';

import { CommandDialog, CommandInput, CommandList, CommandItem } from './command';

describe('CommandDialog motion={false} (M2-01)', () => {
  it('marks the content data-motion="off" and gives it no scale to animate', () => {
    render(
      <CommandDialog open motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    const content = document.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content).toHaveAttribute('data-motion', 'off');
  });

  it('defaults to the animated path (no data-motion attribute) when motion is not set', () => {
    render(
      <CommandDialog open>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    const content = document.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content).not.toHaveAttribute('data-motion');
  });

  it('renders its content synchronously on open, with no distinct exit state to wait through', () => {
    render(
      <CommandDialog open motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    expect(screen.getByText('Result')).toBeInTheDocument();
  });
});

/**
 * M2-01 fix round - the no-motion content needs a REAL exit.
 *
 * `exit` used to equal `animate` (opacity 1) so the panel had nothing to
 * animate out; AnimatePresence still holds the whole fragment mounted for the
 * scrim's own 150ms fade, so the palette sat fully opaque over a fading scrim
 * and then popped. The tester measured the content node alive ~150-185ms after
 * Escape at full opacity (documentation/plans/design-system/evidence/M2/README.md,
 * M2-01 Escape). A zero-duration `opacity: 0` exit removes the panel on the
 * frame the shortcut fires - which is what "keyboard-triggered surfaces never
 * animate" asks for - while the scrim keeps its own fade.
 */
describe('CommandDialog motion={false} exits on the same frame (M2-01)', () => {
  /*
    The one describe that has to opt out of the global
    `MotionGlobalConfig.skipAnimations` (vitest.setup.ts), because it is the one
    that reads a value motion WROTE rather than the behaviour that follows from
    it. Skipping animations applies the final keyframe and reports completion in
    the same frame, so AnimatePresence unmounts the content before the style
    flush reaches it: the exit still happens, the held node just keeps the
    opacity it had and there is nothing left to read it off. Run the real
    (zero-duration) exit here instead.
  */
  const skipAnimations = MotionGlobalConfig.skipAnimations;
  beforeEach(() => {
    MotionGlobalConfig.skipAnimations = false;
  });
  afterEach(() => {
    MotionGlobalConfig.skipAnimations = skipAnimations;
  });

  it('drives the content to opacity 0 the moment it closes, not at the end of the scrim fade', async () => {
    const { rerender } = render(
      <CommandDialog open motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    // Hold the node itself: the assertion has to survive the unmount that
    // follows the scrim's fade, or it becomes a race against wall-clock.
    const content = document.querySelector('[data-slot="dialog-content"]') as HTMLElement;
    expect(content).not.toBeNull();
    expect(content.style.opacity).toBe('1');

    rerender(
      <CommandDialog open={false} motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    await waitFor(() => expect(content.style.opacity).toBe('0'));
  });
});
