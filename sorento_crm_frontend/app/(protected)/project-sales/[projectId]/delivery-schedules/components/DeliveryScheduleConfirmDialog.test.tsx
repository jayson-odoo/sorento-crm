/**
 * P6 - the confirm gate (contract section 4).
 *
 * The gate is deliberately not a wall: a schedule can genuinely disagree with the PO and still
 * be the document everyone works to, so the way past is an acknowledgement with a reason that
 * is recorded, never a silent pass. Both halves are pinned here: refused by default, and the
 * reason is not optional once it is refused.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleConfirmDialog } from './DeliveryScheduleConfirmDialog';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function column(overrides: Partial<ColumnState> = {}): ColumnState {
  return {
    index: 4,
    key: 'p5',
    productId: 'p5',
    productCode: 'SRTFV1001',
    productName: 'Sensor Urinal Flush Valve',
    customerCode: 'BUI-HB-SRTFV1001',
    fromRememberedMap: false,
    ourTotal: '8',
    reportedTotal: '16',
    poQty: '16',
    reconciled: false,
    blockers: [
      { code: 'po_mismatch', detail: 'Our total is 8, the PO orders 16 (-8).' },
    ],
    ...overrides,
  };
}

function renderDialog(blocking: ColumnState[]) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <DeliveryScheduleConfirmDialog
      open
      onOpenChange={onOpenChange}
      blocking={blocking}
      pending={false}
      onConfirm={onConfirm}
    />,
  );
  return { onConfirm, onOpenChange };
}

describe('DeliveryScheduleConfirmDialog', () => {
  it('confirms straight away when nothing is blocking', () => {
    const { onConfirm } = renderDialog([]);

    expect(screen.getByText(/Every column agrees with the PO/i)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/ }));
    expect(onConfirm).toHaveBeenCalledWith({});
  });

  it('names each blocking column with the numbers behind it', () => {
    renderDialog([
      column(),
      column({
        index: 5,
        key: '#5',
        productId: null,
        productCode: null,
        customerCode: 'BUI-HB-SRTWB7055',
        poQty: null,
        blockers: [
          {
            code: 'needs_product',
            detail: 'BUI-HB-SRTWB7055 is not matched to a product.',
          },
        ],
      }),
    ]);

    expect(screen.getByText('2 columns do not add up yet.')).toBeInTheDocument();
    expect(screen.getByText('SRTFV1001')).toBeInTheDocument();
    expect(screen.getByText('Our total is 8, the PO orders 16 (-8).')).toBeInTheDocument();
    expect(screen.getByText('BUI-HB-SRTWB7055')).toBeInTheDocument();
  });

  it('refuses until the acknowledgement carries a reason', () => {
    const { onConfirm } = renderDialog([column()]);

    const submit = screen.getByRole('button', { name: /^Confirm$/ });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox'));
    expect(submit).toBeDisabled();

    // Whitespace is not a reason.
    fireEvent.change(screen.getByLabelText(/Reason/i), { target: { value: '   ' } });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/i), {
      target: { value: 'Customer confirmed by email.' },
    });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onConfirm).toHaveBeenCalledWith({
      acknowledge_unreconciled: true,
      reason: 'Customer confirmed by email.',
    });
  });

  it('uses the singular when one column blocks', () => {
    renderDialog([column()]);
    expect(screen.getByText('1 column does not add up yet.')).toBeInTheDocument();
  });
});
