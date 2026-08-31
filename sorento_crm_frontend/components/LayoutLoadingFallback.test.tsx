/**
 * S7-04 - the OTHER loading fallback, held while the client-providers chunk
 * itself loads (before any route-level `loading.tsx` can even exist yet). This
 * one has to draw its own shell, because there is no real layout mounted for
 * it to sit inside of - a sidebar column and a header bar - and put its
 * skeletons only in the content pane beneath them.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LayoutLoadingFallback } from './LayoutLoadingFallback';

describe('LayoutLoadingFallback (S7-04)', () => {
  it('draws a sidebar column and a header bar around the content skeleton', () => {
    render(<LayoutLoadingFallback />);

    const status = screen.getByRole('status', { name: /loading/i });
    expect(status).toBeInTheDocument();

    // The logo anchors the sidebar column, distinct from the content skeleton.
    expect(screen.getByAltText('Sorento')).toBeInTheDocument();
  });

  it('holds skeletons in both the chrome and the content pane (nothing left blank)', () => {
    const { container } = render(<LayoutLoadingFallback />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(10);
  });

  it('does not show the refresh hint before 10s', () => {
    render(<LayoutLoadingFallback />);
    expect(screen.queryByText(/Refresh the page/i)).not.toBeInTheDocument();
  });
});
