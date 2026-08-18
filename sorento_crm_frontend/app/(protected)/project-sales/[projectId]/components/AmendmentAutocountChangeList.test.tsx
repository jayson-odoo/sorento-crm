/**
 * P11 section 9.4 - the AutoCount change list: accepted rows, export column order, empty
 * state when nothing was accepted.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AmendmentAutocountChangeList } from './AmendmentAutocountChangeList';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

describe('AmendmentAutocountChangeList', () => {
  it('lists an accepted row in the export column order', () => {
    render(
      <AmendmentAutocountChangeList
        rows={[
          {
            so_number: 'SO397450',
            line_no: 3,
            item_code: 'SRTWC8613-RL',
            product_name: 'One-Piece WC',
            verb: 'DELAY',
            old_qty: '135',
            new_qty: '135',
            old_date: '2026-07-01',
            new_date: '2027-01-07',
            new_so_number: null,
          },
        ]}
        declinedCount={1}
        isLoading={false}
        exporting={false}
        onExport={vi.fn()}
      />,
    );

    expect(screen.getByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8613-RL')).toBeInTheDocument();
    expect(screen.getByText('One-Piece WC')).toBeInTheDocument();
    expect(screen.getByText('01/07/2026')).toBeInTheDocument();
    expect(screen.getByText('07/01/2027')).toBeInTheDocument();
    expect(screen.getByText(/1 accepted row ready for AutoCount/)).toBeInTheDocument();
    expect(screen.getByText(/1 declined and excluded/)).toBeInTheDocument();
  });

  it('shows an empty state and disables export when nothing was accepted', () => {
    render(
      <AmendmentAutocountChangeList
        rows={[]}
        declinedCount={2}
        isLoading={false}
        exporting={false}
        onExport={vi.fn()}
      />,
    );

    expect(screen.getByText('Nothing to export yet')).toBeInTheDocument();
    expect(screen.getByText('Every row of this amendment was declined.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export for AutoCount' })).toBeDisabled();
  });

  it('calls onExport, and reads "Exporting…" while the download runs', () => {
    const onExport = vi.fn();
    const { rerender } = render(
      <AmendmentAutocountChangeList
        rows={[
          {
            so_number: 'SO397450',
            line_no: 3,
            item_code: 'SRTWC8613-RL',
            verb: 'DELAY',
            old_date: '2026-07-01',
            new_date: '2027-01-07',
          },
        ]}
        declinedCount={0}
        isLoading={false}
        exporting={false}
        onExport={onExport}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Export for AutoCount' }));
    expect(onExport).toHaveBeenCalledTimes(1);

    rerender(
      <AmendmentAutocountChangeList
        rows={[
          {
            so_number: 'SO397450',
            line_no: 3,
            item_code: 'SRTWC8613-RL',
            verb: 'DELAY',
            old_date: '2026-07-01',
            new_date: '2027-01-07',
          },
        ]}
        declinedCount={0}
        isLoading={false}
        exporting
        onExport={onExport}
      />,
    );
    expect(screen.getByRole('button', { name: 'Exporting…' })).toBeDisabled();
  });
});
