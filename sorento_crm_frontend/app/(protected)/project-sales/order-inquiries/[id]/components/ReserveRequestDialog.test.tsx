/**
 * `PLAN-oi-request-cs-reserve.md` section 3.7, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-22/AC-RS-23 (Slice 2).
 *
 * TEST-FIRST (Phase 2): `ReserveRequestDialog.tsx` does not exist yet - a red here is a
 * missing module, never an import typo.
 *
 * ASSUMPTIONS named for the captain/coder (neither the plan nor the UAC pins the exact
 * prop contract for this new dialog - only its ON-SCREEN behaviour, which is what this
 * test asserts):
 *
 * 1. Props: `{ open, onOpenChange, inquiryId, rows, onSent? }`, where `rows` is the
 *    caller's own selected-row shape (already resolved: item code, delivery date,
 *    remaining, the row's pool default location and the stock-grid's location options) -
 *    the OI detail page is what already holds the worklist rows this dialog only lays
 *    out, matching the plan's own "one line per selected row" framing (3.7).
 * 2. The dialog calls a new feature service, `createOrderInquiryReserveRequest` from a
 *    sibling `_shared/services/orderInquiryReserveService.ts` (mirroring every other
 *    write in this domain, `orderInquiryService.ts`'s own naming), never a hand-rolled
 *    fetch - mocked here at the service boundary per the layering rule (UI -> hook ->
 *    feature service -> api-client).
 * 3. Toast goes through `@/lib/toast`, matching `OrderInquiriesClient.confirm.test.tsx`.
 *
 * If the coder's real contract differs (a mutation hook instead of a bare service call,
 * a different prop shape), the shape of THIS mock needs updating to match - the BEHAVIOUR
 * asserted (defaults, the cap, the payload, the toast) is the part of the contract that
 * must not move.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// Reviewer fix round: typed `(..._args: unknown[])`, not `()` - the REAL
// `createOrderInquiryReserveRequest(inquiryId, payload)` takes two arguments, and a
// zero-arg inferred mock signature made the spread call below (and the tuple cast at
// its own read-back further down) a tsc error, never an assertion this suite owns.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const createReserveRequestSpy = vi.fn(async (..._args: unknown[]) => ({
  id: 'rr-1',
  ordinal: 1,
  first_to_name: 'Eling',
}));
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: (...args: unknown[]) => createReserveRequestSpy(...args),
}));

import { toast } from '@/lib/toast';
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

function renderDialog(overrides: Partial<React.ComponentProps<typeof ReserveRequestDialog>> = {}) {
  return render(
    <ReserveRequestDialog
      open
      onOpenChange={vi.fn()}
      inquiryId="oi-1"
      rows={ROWS as never}
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

  it('Send posts { rows: [{row_id, qty_requested, warehouse_id}], note } and toasts the first recipient', async () => {
    renderDialog();

    fireEvent.click(await screen.findByRole('button', { name: /send request/i }));

    await waitFor(() => expect(createReserveRequestSpy).toHaveBeenCalledTimes(1));
    const [inquiryId, payload] = createReserveRequestSpy.mock.calls[0] as [string, {
      rows: Array<{ row_id: string; qty_requested: string | number; warehouse_id: string }>;
      note?: string | null;
    }];
    expect(inquiryId).toBe('oi-1');
    expect(payload.rows).toEqual([
      { row_id: 'row-1', qty_requested: 90, warehouse_id: 'BRW' },
      { row_id: 'row-2', qty_requested: 30, warehouse_id: 'MWH' },
    ]);

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Eling')),
    );
    expect((toast.success as ReturnType<typeof vi.fn>).mock.calls[0][0]).toMatch(/Request #1/);
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
