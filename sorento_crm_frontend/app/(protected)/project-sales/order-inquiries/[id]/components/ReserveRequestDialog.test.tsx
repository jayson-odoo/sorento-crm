/**
 * `PLAN-oi-request-cs-reserve.md` section 3.7, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-22/AC-RS-23 (Slice 2).
 *
 * S5 (reviewer round 2): `rows` is the caller's own selected-row shape (already
 * resolved: item code, delivery date, remaining, the row's pool default location and
 * the stock-grid's location options); the actual write is `onSend`, a mutate function
 * the caller builds from `useCreateOrderInquiryReserveRequest`
 * (`_shared/hooks/useOrderInquiry.ts`) - this dialog no longer imports the feature
 * service directly (UI -> hook -> feature service -> api-client), and the success
 * toast ("Request #N sent to ...") is that hook's own job, not asserted here.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReserveRequestDialog } from './ReserveRequestDialog';

const ROWS = [
  {
    id: 'row-1',
    item_code: 'B2155-NL-BLUE',
    delivery_date: '2026-10-01',
    remaining: '90',
    defaultLocation: 'BRW',
    locationOptions: [
      { value: 'BRW', label: 'BRW' },
      { value: 'BRW-BB', label: 'BRW-BB' },
    ],
  },
  {
    id: 'row-2',
    item_code: 'CKS1050',
    delivery_date: '2026-10-05',
    remaining: '30',
    defaultLocation: 'MWH',
    locationOptions: [{ value: 'MWH', label: 'MWH' }],
  },
];

// S5 (reviewer round): the dialog no longer calls the feature service itself - it
// calls `onSend`, the mutate function the caller's own `useCreateOrderInquiryReserve
// Request` hook builds (`_shared/hooks/useOrderInquiry.ts`). Mocked here at the PROP
// boundary, not the service module, matching "dialogs receive the mutate functions as
// props" (UI -> hook -> feature service -> api-client).
const onSendSpy = vi.fn(async () => ({
  id: 'rr-1',
  ordinal: 1,
  first_to_name: 'Eling',
}));

function renderDialog(overrides: Partial<React.ComponentProps<typeof ReserveRequestDialog>> = {}) {
  return render(
    <ReserveRequestDialog
      open
      onOpenChange={vi.fn()}
      rows={ROWS as never}
      onSend={onSendSpy as never}
      {...overrides}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AC-RS-22: one line per selected row, Requested = remaining, Location = the pool', () => {
  it('shows item code, delivery date and remaining for every row', async () => {
    renderDialog();

    expect(await screen.findByText('B2155-NL-BLUE')).toBeInTheDocument();
    expect(screen.getByText('CKS1050')).toBeInTheDocument();
    expect(screen.getAllByText(/90|30/).length).toBeGreaterThanOrEqual(2);
  });

  it('Requested defaults to remaining and cannot exceed it', async () => {
    renderDialog();

    const requestedInputs = await screen.findAllByLabelText(/requested/i);
    expect(requestedInputs[0]).toHaveValue(90);
    expect(requestedInputs[0]).toHaveAttribute('max', '90');
    expect(requestedInputs[1]).toHaveValue(30);
  });

  it('Location defaults to the pool for each row', async () => {
    renderDialog();

    // SearchableSelect renders the selected option's label as visible text.
    expect(await screen.findAllByText('BRW')).not.toHaveLength(0);
    expect(screen.getByText('MWH')).toBeInTheDocument();
  });

  it('Send calls onSend with { rows: [{row_id, qty_requested, warehouse_id}], note } and closes on success', async () => {
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    fireEvent.click(await screen.findByRole('button', { name: /send request/i }));

    await waitFor(() => expect(onSendSpy).toHaveBeenCalledTimes(1));
    const [payload] = onSendSpy.mock.calls[0] as [{
      rows: Array<{ row_id: string; qty_requested: string | number; warehouse_id: string }>;
      note?: string | null;
    }];
    expect(payload.rows).toEqual([
      { row_id: 'row-1', qty_requested: 90, warehouse_id: 'BRW' },
      { row_id: 'row-2', qty_requested: 30, warehouse_id: 'MWH' },
    ]);

    // S5: toasting "Request #1 sent to Eling" is the CALLER's own mutation hook's job
    // now (`useCreateOrderInquiryReserveRequest`) - this dialog only closes on success.
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});

// --------------------------------------------------------------------------------- //
// Reviewer fix round, same lane                                                     //
// --------------------------------------------------------------------------------- //

describe('reviewer fix round: delivery date formats via formatDateInMalaysia, not raw ISO', () => {
  it('a row whose delivery_date is a raw ISO string prints dd/mm/yyyy on screen', async () => {
    renderDialog({
      rows: [
        {
          id: 'row-1',
          item_code: 'B2155-NL-BLUE',
          delivery_date: '2026-10-01',
          remaining: '90',
          defaultLocation: 'BRW',
          locationOptions: [{ value: 'BRW', label: 'BRW' }],
        },
      ] as never,
    });

    await screen.findByText('B2155-NL-BLUE');
    expect(screen.getByText(/01\/10\/2026/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-01/)).not.toBeInTheDocument();
  });
});

describe('reviewer fix round: a typed 0 cannot be sent', () => {
  it('typing 0 into Requested disables Send, or clamps the value up to 1', async () => {
    renderDialog({
      rows: [
        {
          id: 'row-1',
          item_code: 'B2155-NL-BLUE',
          delivery_date: '2026-10-01',
          remaining: '90',
          defaultLocation: 'BRW',
          locationOptions: [{ value: 'BRW', label: 'BRW' }],
        },
      ] as never,
    });

    const requestedInput = (await screen.findByLabelText(/requested/i)) as HTMLInputElement;
    fireEvent.change(requestedInput, { target: { value: '0' } });

    const sendButton = screen.getByRole('button', { name: /send request/i });
    if (requestedInput.value === '0') {
      expect(sendButton).toBeDisabled();
    } else {
      expect(requestedInput.value).toBe('1');
    }
  });
});
