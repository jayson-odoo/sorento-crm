/**
 * UI v2 phase 0, slice S4 (red first). UAC E-3 (playbook P4; P5 owner override: the plain reason, no pulse).
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   components/v2/shell/FloatingAction.tsx : FloatingAction(props)
 *     props: {
 *       label: string;                              // same label as the header primary
 *       onAction: () => void;                       // same handler as the header primary
 *       blockedReason?: string | null;              // when set, the action is blocked
 *       headerPrimaryRef: React.RefObject<HTMLElement | null>;   // the header's primary button
 *     }
 *   The component observes `headerPrimaryRef.current` with an IntersectionObserver (observe() is called with that
 *   element). Until the observer reports `isIntersecting: false` it renders nothing.
 *   Shown only on a phone (window.matchMedia/innerWidth <= 720) AND while the header primary is out of view:
 *     <button type="button" data-testid="floating-action"> with the label, class list containing `fixed` and a
 *     `bottom-*` class and an `end-*` or `right-*` class (lower right).
 *   Click runs onAction. When blockedReason is set, click does NOT run onAction and the reason text becomes
 *     visible (role="status") instead.
 *   Bottom room: while shown, sets CSS custom property `--floating-action-room` on <html> to
 *     (button offsetHeight + 16) px; removed when hidden or unmounted.
 *   Never shown above 720 px, whatever the observer says.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import { FloatingAction } from './FloatingAction';

type IOCallback = (entries: Partial<IntersectionObserverEntry>[]) => void;
const observers: { cb: IOCallback; observed: Element[] }[] = [];
class StubIntersectionObserver {
  cb: IOCallback;
  observed: Element[] = [];
  root = null;
  rootMargin = '';
  thresholds: ReadonlyArray<number> = [];
  constructor(cb: IOCallback) {
    this.cb = cb;
    observers.push(this);
  }
  observe = (el: Element) => {
    this.observed.push(el);
  };
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

function reportVisibility(isIntersecting: boolean) {
  act(() => {
    for (const o of observers) o.cb([{ isIntersecting, target: o.observed[0] }]);
  });
}

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => {
      const max = /max-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const min = /min-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const matches = max || min ? (max ? width <= Number(max[1]) : true) && (min ? width >= Number(min[1]) : true) : false;
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    },
  });
}

function Harness({ onAction, blockedReason }: { onAction: () => void; blockedReason?: string | null }) {
  const ref = React.useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={ref} type="button">Create order</button>
      <FloatingAction label="Create order" onAction={onAction} blockedReason={blockedReason} headerPrimaryRef={ref} />
    </>
  );
}

beforeEach(() => {
  observers.length = 0;
  vi.stubGlobal('IntersectionObserver', StubIntersectionObserver);
  setViewport(360);
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 48 });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty('--floating-action-room');
});

describe('FloatingAction (E-3)', () => {
  it('observes the header primary and renders nothing while it is in view', () => {
    render(<Harness onAction={vi.fn()} />);
    expect(observers.some((o) => o.observed.some((el) => el.textContent === 'Create order'))).toBe(true);
    expect(screen.queryByTestId('floating-action')).toBeNull();
    reportVisibility(true);
    expect(screen.queryByTestId('floating-action')).toBeNull();
  });

  it('once the header primary scrolls out of view it floats at the lower right with the same label', () => {
    render(<Harness onAction={vi.fn()} />);
    reportVisibility(false);
    const fab = screen.getByTestId('floating-action');
    expect(fab).toHaveTextContent('Create order');
    expect(fab.className).toMatch(/\bfixed\b/);
    expect(fab.className).toMatch(/\bbottom-/);
    expect(fab.className).toMatch(/\b(end|right)-/);
  });

  it('goes away again when the header primary scrolls back into view', () => {
    render(<Harness onAction={vi.fn()} />);
    reportVisibility(false);
    expect(screen.getByTestId('floating-action')).toBeInTheDocument();
    reportVisibility(true);
    expect(screen.queryByTestId('floating-action')).toBeNull();
  });

  it('runs the same handler as the page button', () => {
    const onAction = vi.fn();
    render(<Harness onAction={onAction} />);
    reportVisibility(false);
    fireEvent.click(screen.getByTestId('floating-action'));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('when blocked, click shows the reason instead of acting', () => {
    const onAction = vi.fn();
    render(<Harness onAction={onAction} blockedReason="Pick a customer first" />);
    reportVisibility(false);
    expect(screen.queryByText('Pick a customer first')).toBeNull();
    fireEvent.click(screen.getByTestId('floating-action'));
    expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('Pick a customer first');
  });

  it('reserves bottom room equal to its height plus 16 px, and releases it', () => {
    const { unmount } = render(<Harness onAction={vi.fn()} />);
    expect(document.documentElement.style.getPropertyValue('--floating-action-room')).toBe('');
    reportVisibility(false);
    expect(document.documentElement.style.getPropertyValue('--floating-action-room')).toBe('64px');
    reportVisibility(true);
    expect(document.documentElement.style.getPropertyValue('--floating-action-room')).toBe('');
    reportVisibility(false);
    unmount();
    expect(document.documentElement.style.getPropertyValue('--floating-action-room')).toBe('');
  });

  it('is never shown above 720 px', () => {
    setViewport(1280);
    render(<Harness onAction={vi.fn()} />);
    reportVisibility(false);
    expect(screen.queryByTestId('floating-action')).toBeNull();
  });
});
