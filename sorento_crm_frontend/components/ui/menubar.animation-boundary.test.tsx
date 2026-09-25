/**
 * MenubarContent and MenubarSubContent each animate `{ opacity, scale }`
 * (`surfaceVariants`) in their own `motion.div`, so both carry the same WAAPI
 * hand-off race as Dialog's surfaces (#1250, follow-up to #1246's
 * dialog.animation-boundary.test.tsx).
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring -
 * `onUpdate={NOOP_ON_UPDATE}` present and actually invoked while animating -
 * not the WAAPI race itself. See dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
 *
 * MenubarContent has no controlled `open` prop and no `AnimatePresence`/exit
 * (Radix owns its mount/unmount lifecycle outright, per the comment in
 * menubar.tsx), so this drives it open with a real click on the trigger
 * rather than an `open` prop. MenubarSub DOES support controlled `open`, so
 * the SubContent describe opens the parent menu once via click, lets it
 * settle, then flips the Sub's `open` prop directly - isolating SubContent's
 * calls from the already-settled parent Content the same way the
 * dropdown-menu/context-menu tests do.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';

const { onUpdateSpy } = vi.hoisted(() => ({ onUpdateSpy: vi.fn() }));

vi.mock('@/lib/motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/motion')>();
  return { ...actual, NOOP_ON_UPDATE: onUpdateSpy };
});

import {
  Menubar,
  MenubarContent,
  MenubarItem,
  MenubarMenu,
  MenubarSub,
  MenubarSubContent,
  MenubarSubTrigger,
  MenubarTrigger,
} from './menubar';

const realMatchMedia = window.matchMedia;
const skipAnimations = MotionGlobalConfig.skipAnimations;

beforeEach(() => {
  onUpdateSpy.mockClear();
  MotionGlobalConfig.skipAnimations = false;
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

afterEach(() => {
  MotionGlobalConfig.skipAnimations = skipAnimations;
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: realMatchMedia });
});

describe('MenubarContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering', async () => {
    const { getByText } = render(
      <Menubar>
        <MenubarMenu>
          <MenubarTrigger>File</MenubarTrigger>
          <MenubarContent>
            <MenubarItem>Item one</MenubarItem>
          </MenubarContent>
        </MenubarMenu>
      </Menubar>,
    );

    fireEvent.pointerDown(getByText('File'), { button: 0 });
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});

function MenubarWithSub({ subOpen }: { subOpen: boolean }) {
  return (
    <Menubar>
      <MenubarMenu>
        <MenubarTrigger>File</MenubarTrigger>
        <MenubarContent>
          <MenubarSub open={subOpen} onOpenChange={() => {}}>
            <MenubarSubTrigger>Sub trigger</MenubarSubTrigger>
            <MenubarSubContent>
              <MenubarItem>Nested item</MenubarItem>
            </MenubarSubContent>
          </MenubarSub>
        </MenubarContent>
      </MenubarMenu>
    </Menubar>
  );
}

describe('MenubarSubContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering, isolated from the already-settled parent Content', async () => {
    const { getByText, rerender } = render(<MenubarWithSub subOpen={false} />);

    fireEvent.pointerDown(getByText('File'), { button: 0 });
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(<MenubarWithSub subOpen />);
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing, isolated from the settled parent Content', async () => {
    const { getByText, rerender } = render(<MenubarWithSub subOpen={false} />);

    fireEvent.pointerDown(getByText('File'), { button: 0 });
    await new Promise((resolve) => setTimeout(resolve, 500));
    rerender(<MenubarWithSub subOpen />);
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(<MenubarWithSub subOpen={false} />);
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
