/**
 * AlertDialog carries the same WAAPI hand-off race as Dialog (#1250, follow-up
 * to #1246's dialog.animation-boundary.test.tsx) - it renders the identical
 * shared-presence pattern (`AnimatePresence` gating `forceMount` overlay and
 * content `motion.div`s) with the same `surfaceVariants`/`SURFACE_SPRING`
 * pair, so motion-dom hands its opacity off to WAAPI the same way and the same
 * one-frame flicker applies (browser trace in the PR body).
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring -
 * `onUpdate={NOOP_ON_UPDATE}` present and actually invoked on each surface -
 * not the WAAPI race itself. See dialog.animation-boundary.test.tsx for the
 * full mechanism writeup; this file mirrors its structure and per-surface
 * split.
 *
 * `onUpdate` is called with the element's `latestValues`. The content's
 * variants (`surfaceVariants` in lib/motion.ts) animate `{ opacity, scale }`
 * while the overlay animates `opacity` alone, so a call's argument carries a
 * `scale` key if and only if it came from the content's `motion.div`.
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

import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription } from './alert-dialog';

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

function isContentCall(call: unknown[]): boolean {
  const latest = call[0] as Record<string, unknown> | undefined;
  return latest !== undefined && Object.prototype.hasOwnProperty.call(latest, 'scale');
}

function splitCallsBySurface(calls: unknown[][]) {
  const contentCalls = calls.filter(isContentCall);
  const overlayCalls = calls.filter((call) => !isContentCall(call));
  return { overlayCalls, contentCalls };
}

function renderAlertDialog(open: boolean) {
  return (
    <AlertDialog open={open}>
      <AlertDialogContent>
        <AlertDialogTitle>T</AlertDialogTitle>
        <AlertDialogDescription>D</AlertDialogDescription>
      </AlertDialogContent>
    </AlertDialog>
  );
}

describe('AlertDialog defeats WAAPI hand-off on its animated surfaces', () => {
  it('drives onUpdate on both the overlay and the content while entering', async () => {
    render(renderAlertDialog(true));

    await new Promise((resolve) => setTimeout(resolve, 500));

    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate on both the overlay and the content while closing', async () => {
    const { rerender } = render(renderAlertDialog(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderAlertDialog(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });
});
