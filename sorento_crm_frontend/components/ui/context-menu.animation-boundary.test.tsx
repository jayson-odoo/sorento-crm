/**
 * ContextMenuContent and ContextMenuSubContent each animate `{ opacity, scale
 * }` (`surfaceVariants`) in their own `motion.div`, so both carry the same
 * WAAPI hand-off race as Dialog's surfaces (#1250, follow-up to #1246's
 * dialog.animation-boundary.test.tsx).
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring -
 * `onUpdate={NOOP_ON_UPDATE}` present and actually invoked while animating -
 * not the WAAPI race itself. See dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
 *
 * Unlike Dialog/DropdownMenu, ContextMenu's own Root has no controlled `open`
 * prop (see the comment in context-menu.tsx) - it only opens on a real
 * right-click, so this drives it with `fireEvent.contextMenu` rather than an
 * `open` prop, the same way TagCanvasEditor.context-menu.test.tsx does. Sub
 * DOES support controlled `open`, so the SubContent describe below opens the
 * parent Content once via right-click, lets it settle, then flips the Sub's
 * `open` prop directly - isolating SubContent's calls from the
 * already-settled parent Content the same way the dropdown-menu test does.
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
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from './context-menu';

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

describe('ContextMenuContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering', async () => {
    const { getByText } = render(
      <ContextMenu>
        <ContextMenuTrigger>Right click me</ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem>Item one</ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>,
    );

    fireEvent.contextMenu(getByText('Right click me'));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing', async () => {
    const { getByText } = render(
      <ContextMenu>
        <ContextMenuTrigger>Right click me</ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem>Item one</ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>,
    );

    fireEvent.contextMenu(getByText('Right click me'));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});

function ContextMenuWithSub({ subOpen }: { subOpen: boolean }) {
  return (
    <ContextMenu>
      <ContextMenuTrigger>Right click me</ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuSub open={subOpen} onOpenChange={() => {}}>
          <ContextMenuSubTrigger>Sub trigger</ContextMenuSubTrigger>
          <ContextMenuSubContent>
            <ContextMenuItem>Nested item</ContextMenuItem>
          </ContextMenuSubContent>
        </ContextMenuSub>
      </ContextMenuContent>
    </ContextMenu>
  );
}

describe('ContextMenuSubContent defeats WAAPI hand-off', () => {
  it('drives onUpdate while entering, isolated from the already-settled parent Content', async () => {
    const { getByText, rerender } = render(<ContextMenuWithSub subOpen={false} />);

    fireEvent.contextMenu(getByText('Right click me'));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(<ContextMenuWithSub subOpen />);
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing, isolated from the settled parent Content', async () => {
    const { getByText, rerender } = render(<ContextMenuWithSub subOpen={false} />);

    fireEvent.contextMenu(getByText('Right click me'));
    await new Promise((resolve) => setTimeout(resolve, 500));
    rerender(<ContextMenuWithSub subOpen />);
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(<ContextMenuWithSub subOpen={false} />);
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
