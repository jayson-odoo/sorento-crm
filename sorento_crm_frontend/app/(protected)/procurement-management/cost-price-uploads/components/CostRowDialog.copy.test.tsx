/**
 * CostRowDialog (#1305 reviewer pass, Lane A FE rows, Nit 7): "Both empty: always. Start
 * only: from that day on." is a feature explanation, not a label or a field name - the
 * cursor rule bars it from the UI itself. It moved to
 * `documentation/user-guides/procurement/cost-price-from-supplier.md`.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: null, start: vi.fn() }),
}));

import { CostRowDialog } from './CostRowDialog';

describe('Nit 7: no feature explanation inside the UI', () => {
  it('renders no "Both empty: always" sentence', () => {
    render(
      <CostRowDialog
        open
        onOpenChange={() => {}}
        link={{ id: 'link-1', product: { product_code: 'ZZT-001' }, currency: 'CNY' }}
        cost={null}
        onSaved={() => {}}
      />,
    );

    expect(screen.queryByText(/Both empty: always\. Start only: from that day on\./)).not.toBeInTheDocument();
  });
});

describe('Round 6 R5: cost, never price (owner, 28 Sep 2026)', () => {
  it('titles the dialog and labels the amount Cost', () => {
    render(
      <CostRowDialog
        open
        onOpenChange={() => {}}
        link={{ id: 'link-1', product: { product_code: 'ZZT-001' }, currency: 'CNY' }}
        cost={null}
        onSaved={() => {}}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Cost for ZZT-001' })).toBeInTheDocument();
    expect(screen.getByLabelText('Cost')).toBeInTheDocument();
    expect(screen.queryByText(/price/i)).not.toBeInTheDocument();
  });
});
