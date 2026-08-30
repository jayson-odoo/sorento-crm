/**
 * S7-04 - a list route's `loading.tsx` renders INSIDE the layout: it draws only
 * the content pane (title, toolbar, grid rows), never a full-page wrapper. The
 * sidebar and header that keep the reader's place come from `app/(protected)/
 * layout.tsx`, which Next.js keeps mounted around a route-level `loading.tsx`
 * boundary - this is the one thing the ten identical files below rely on, and
 * it is Next's file-convention behaviour, not something asserted here.
 *
 * Representative of all ten - see `loading-inventory.test.tsx` for the rest.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import Loading from './loading';

describe('orders loading.tsx (S7-04, representative)', () => {
  it('renders the content-pane skeleton only - no full-page overlay of its own', () => {
    const { container } = render(<Loading />);

    // The shell fallback (LayoutLoadingFallback) uses a fixed, full-viewport,
    // role="status" wrapper. A route loading.tsx must not reproduce that - it
    // is meant to sit inside the shell, not replace it.
    expect(container.querySelector('[role="status"]')).not.toBeInTheDocument();
    expect(container.querySelector('.fixed.inset-0')).not.toBeInTheDocument();

    // It does draw a recognizable list shape: a title bar and a card of rows.
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(5);
  });

  it('has no data-fetching or navigation of its own - it is pure skeleton', () => {
    render(<Loading />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
