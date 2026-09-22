/**
 * `PLAN-oi-request-cs-reserve.md` section 3.8, section 5 captain's test list row "RS-23"
 * (`ReserveRequestsCard.test.tsx`: "act mode: reason input appears when reserved <
 * requested, Confirm disabled until filled; read-only without permission").
 *
 * NUMBERING NOTE for the captain (named per the coordinator's instruction: "name any
 * gap"): the plan's own section 5 row labelled "RS-23" describes ACT MODE, which the UAC
 * file (`oi-request-cs-reserve-acceptance-criteria.md`) actually states under
 * **AC-RS-26** ("a Reason input appears inline the moment Reserved < Requested ... Confirm
 * reserved stays disabled until every such row has a non-blank reason") and **AC-RS-27**
 * ("a viewer without the reserve permission ... renders read-only"). The UAC's own
 * `AC-RS-23` is a DIFFERENT criterion (a disabled Actions-menu item with a tooltip, on the
 * REQUEST side of the flow) that this file does not test. Both plan and UAC content are
 * followed here - just under the UAC's real AC ids, since a docstring claiming AC-RS-23
 * would mislead the next reader into the wrong UAC row.
 *
 * TEST-FIRST (Phase 2): `ReserveRequestsCard.tsx` does not exist yet - a red here is a
 * missing module, never an import typo.
 *
 * ASSUMPTION (prop contract, undocumented beyond on-screen behaviour): `{ request, mode,
 * canAct, onConfirmed }`, `request.rows` each carrying `qty_requested` and a server-
 * computed `default_reserved` (plan 3.8: "default `min(requested, available at the chosen
 * location, 0 floor)`") - the CAP computation itself is the backend's (AC-RS-6..11), so
 * this card is handed the number already resolved. Confirm posts through a new service,
 * `reserveOrderInquiryRequest`, mirroring `createOrderInquiryReserveRequest`'s sibling
 * file.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const reserveSpy = vi.fn(async () => ({ id: 'rr-1', state: 'reserved' }));
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  reserveOrderInquiryRequest: (...args: unknown[]) => reserveSpy(...(args as [unknown])),
}));

import { ReserveRequestsCard } from './ReserveRequestsCard';

function requestFixture() {
  return {
    id: 'rr-1',
    ordinal: 1,
    state: 'requested' as const,
    requested_by_name: 'Joey',
    requested_at: '2026-09-22T09:00:00',
    rows: [
      {
        id: 'rr-row-1',
        item_code: 'B2155-NL-BLUE',
        qty_requested: '139',
        default_reserved: '50', // short: 50 < 139
        location_options: [{ value: 'BRW', label: 'BRW' }],
        default_location: 'BRW',
      },
      {
        id: 'rr-row-2',
        item_code: 'CKS1050',
        qty_requested: '30',
        default_reserved: '30', // full: not short
        location_options: [{ value: 'MWH', label: 'MWH' }],
        default_location: 'MWH',
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AC-RS-26: act mode shows a Reason input the moment Reserved < Requested, Confirm gated on it', () => {
  it('a row prefilled short shows a Reason input immediately, no typing needed to trigger it', async () => {
    render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    expect(await screen.findAllByLabelText(/reason/i)).toHaveLength(1);
  });

  it('Confirm reserved is disabled until every short row has a non-blank reason', async () => {
    render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    const confirmButton = await screen.findByRole('button', { name: /confirm reserved/i });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(await screen.findByLabelText(/reason/i), {
      target: { value: 'BRW only has 50 in stock' },
    });

    await waitFor(() => expect(confirmButton).toBeEnabled());
  });

  it('Confirm posts { rows: [{request_row_id, warehouse_id, qty_reserved, reason}] }', async () => {
    render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    fireEvent.change(await screen.findByLabelText(/reason/i), {
      target: { value: 'BRW only has 50 in stock' },
    });
    fireEvent.click(await screen.findByRole('button', { name: /confirm reserved/i }));

    await waitFor(() => expect(reserveSpy).toHaveBeenCalledTimes(1));
    const [, payload] = reserveSpy.mock.calls[0] as [string, {
      rows: Array<{ request_row_id: string; warehouse_id: string; qty_reserved: string | number; reason?: string | null }>;
    }];
    expect(payload.rows).toEqual([
      { request_row_id: 'rr-row-1', warehouse_id: 'BRW', qty_reserved: 50, reason: 'BRW only has 50 in stock' },
      { request_row_id: 'rr-row-2', warehouse_id: 'MWH', qty_reserved: 30, reason: null },
    ]);
  });
});

describe('AC-RS-27: a viewer without the reserve permission sees the same card read-only', () => {
  it('renders no inputs and no Confirm button', async () => {
    render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct={false}
        onConfirmed={vi.fn()}
      />,
    );

    await screen.findByText('B2155-NL-BLUE');
    expect(screen.queryByRole('button', { name: /confirm reserved/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/reason/i)).not.toBeInTheDocument();
  });
});
