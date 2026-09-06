import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import { PopoverScrollLock } from './PopoverScrollLock';

// `react-remove-scroll-bar` counts locks on `document.body`'s own attribute rather than
// per-instance state, so a leaked mount from one test would misreport the next one's.
afterEach(() => {
  cleanup();
  document.body.removeAttribute('data-scroll-locked');
});

const isLocked = () => document.body.hasAttribute('data-scroll-locked');

describe('PopoverScrollLock', () => {
  it('does not lock the body while its popover is closed, even when active', () => {
    render(
      <PopoverScrollLock open={false} active>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(false);
  });

  it('locks the body once the owning popover opens', () => {
    const { rerender } = render(
      <PopoverScrollLock open={false} active>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(false);

    rerender(
      <PopoverScrollLock open active>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(true);
  });

  it('releases the lock again once the popover closes', () => {
    const { rerender } = render(
      <PopoverScrollLock open active>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(true);

    rerender(
      <PopoverScrollLock open={false} active>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(false);
  });

  it('never locks when the popover does not need the wrap, even while open', () => {
    render(
      <PopoverScrollLock open active={false}>
        <div>content</div>
      </PopoverScrollLock>,
    );
    expect(isLocked()).toBe(false);
  });
});
