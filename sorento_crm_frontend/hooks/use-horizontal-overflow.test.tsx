/**
 * The measurement behind every right-edge fade (UAC S1-04, S1-05).
 *
 * A strip that scrolls sideways with no visible scrollbar is invisible: on a
 * phone the Settings tab list hid 7 of its 10 tabs and nothing on screen said
 * so. The fade is the only affordance, so it has to appear exactly when there
 * is more to the right - never over a strip that already fits, never over the
 * last column once the user has reached the end.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { act, fireEvent, render } from '@testing-library/react';

import { useHorizontalOverflow } from './use-horizontal-overflow';

function Harness() {
  const { ref, isOverflowing, isAtEnd } = useHorizontalOverflow<HTMLDivElement>();
  return (
    <div ref={ref} data-testid="scroller" data-overflowing={isOverflowing} data-at-end={isAtEnd}>
      content
    </div>
  );
}

function setMetrics(el: HTMLElement, metrics: { scrollWidth: number; clientWidth: number; scrollLeft: number }) {
  Object.defineProperty(el, 'scrollWidth', { value: metrics.scrollWidth, configurable: true });
  Object.defineProperty(el, 'clientWidth', { value: metrics.clientWidth, configurable: true });
  Object.defineProperty(el, 'scrollLeft', { value: metrics.scrollLeft, configurable: true, writable: true });
}

describe('useHorizontalOverflow', () => {
  it('reports no overflow when the content fits', () => {
    const { getByTestId } = render(<Harness />);
    // jsdom has no layout: every width is 0, which is the "it fits" case.
    expect(getByTestId('scroller')).toHaveAttribute('data-overflowing', 'false');
  });

  it('reports overflow once the content is wider than the box', () => {
    const { getByTestId } = render(<Harness />);
    const el = getByTestId('scroller');

    setMetrics(el, { scrollWidth: 1200, clientWidth: 375, scrollLeft: 0 });
    act(() => {
      fireEvent(window, new Event('resize'));
    });

    expect(el).toHaveAttribute('data-overflowing', 'true');
    expect(el).toHaveAttribute('data-at-end', 'false');
  });

  it('reports the end once the user has scrolled all the way right', () => {
    const { getByTestId } = render(<Harness />);
    const el = getByTestId('scroller');

    setMetrics(el, { scrollWidth: 1200, clientWidth: 375, scrollLeft: 825 });
    act(() => {
      fireEvent.scroll(el);
    });

    expect(el).toHaveAttribute('data-overflowing', 'true');
    expect(el).toHaveAttribute('data-at-end', 'true');
  });
});
