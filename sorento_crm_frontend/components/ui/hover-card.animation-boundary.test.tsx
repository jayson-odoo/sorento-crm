/**
 * HoverCardContent's `motion.div` animates `{ opacity, scale }`
 * (`surfaceVariants`), so it carries the same WAAPI hand-off race as Dialog's
 * surfaces (#1250, follow-up to #1246's dialog.animation-boundary.test.tsx).
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring -
 * `onUpdate={NOOP_ON_UPDATE}` present and actually invoked while animating -
 * not the WAAPI race itself. See dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
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

import { HoverCard, HoverCardContent, HoverCardTrigger } from './hover-card';

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

function renderHoverCard(open: boolean) {
  return (
    <HoverCard open={open} onOpenChange={() => {}}>
      <HoverCardTrigger>Hover me</HoverCardTrigger>
      <HoverCardContent>Card body</HoverCardContent>
    </HoverCard>
  );
}

describe('HoverCardContent defeats WAAPI hand-off', () => {
  it('drives onUpdate on the content while entering', async () => {
    render(renderHoverCard(true));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate on the content while closing', async () => {
    const { rerender } = render(renderHoverCard(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderHoverCard(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
