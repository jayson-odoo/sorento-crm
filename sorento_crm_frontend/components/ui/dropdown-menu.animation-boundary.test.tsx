/**
 * DropdownMenuContent and DropdownMenuSubContent each animate `{ opacity,
 * scale }` (`surfaceVariants`) in their own `motion.div`, so both carry the
 * same WAAPI hand-off race as Dialog's surfaces (#1250, follow-up to #1246's
 * dialog.animation-boundary.test.tsx).
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring -
 * `onUpdate={NOOP_ON_UPDATE}` present and actually invoked while animating -
 * not the WAAPI race itself. See dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
 *
 * Content and SubContent both animate the identical `{ opacity, scale }`
 * shape, so `latestValues` cannot tell them apart the way Dialog's
 * overlay/content split does. Each site is instead guarded by a render that
 * isolates it: the Content-only describe below never mounts a Sub, so every
 * call is Content's; the SubContent describe lets Content's own entrance
 * settle first (its motion.div stops calling onUpdate once nothing is
 * changing), clears the spy, then opens only the Sub - so every call
 * afterwards can only have come from SubContent's own `motion.div`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';

const { onUpdateSpy } = vi.hoisted(() => ({ onUpdateSpy: vi.fn() }));

vi.mock('@/lib/motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/motion')>();
  return { ...actual, NOOP_ON_UPDATE: onUpdateSpy };
});

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from './dropdown-menu';

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

function renderMenuOnly(open: boolean) {
  return (
    <DropdownMenu open={open} onOpenChange={() => {}}>
      <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem>Item one</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

describe('DropdownMenuContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering', async () => {
    render(renderMenuOnly(true));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing', async () => {
    const { rerender } = render(renderMenuOnly(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderMenuOnly(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});

function renderMenuWithSub(subOpen: boolean) {
  return (
    <DropdownMenu open onOpenChange={() => {}}>
      <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuSub open={subOpen} onOpenChange={() => {}}>
          <DropdownMenuSubTrigger>Sub trigger</DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuItem>Nested item</DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

describe('DropdownMenuSubContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering, isolated from the already-settled parent Content', async () => {
    const { rerender } = render(renderMenuWithSub(false));
    // Let the parent Content's own entrance finish before touching the Sub -
    // once settled its motion.div stops calling onUpdate every frame, so any
    // calls captured below can only be the Sub's.
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderMenuWithSub(true));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing, isolated from the settled parent Content', async () => {
    const { rerender } = render(renderMenuWithSub(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderMenuWithSub(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
