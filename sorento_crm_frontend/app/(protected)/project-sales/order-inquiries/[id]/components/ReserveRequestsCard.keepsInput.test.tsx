/**
 * Reviewer fix round, same lane (`PLAN-oi-request-cs-reserve.md`).
 *
 * AC-RS-28 (reviewer 2): `ReserveRequestsCard`'s own `useEffect` resets `reserved` /
 * `location` / `reason` / `editedReserved` off `[request.id, request.rows]` - and
 * `request.rows` is compared by REFERENCE, not value. A parent re-render that recomputes
 * `rows` fresh (a query refetch landing the identical server data, a sibling state
 * change) hands down a NEW array every time, so typed Reserved/Reason input is wiped on
 * every such re-render even though nothing the reader is looking at actually changed. A
 * genuine `request.id` change (a different request rendered in the same slot) SHOULD
 * still reset - that half is asserted too, to pin it as the one legitimate trigger.
 *
 * AC-RS-24 (browser evidence run defect): `ReserveRequestsCard` renders "Cancel request"
 * only when `mode === 'request'` (line ~152), but `ReserveRequestsSection.tsx` forces ACT
 * mode for any reserve-permission holder - so Eling (who holds the reserve permission and
 * is ALSO shown as an eligible canceller per AC-RS-24's own words, "the requester or a
 * reserve-permission holder") can never reach the Cancel button at all once she can act.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const reserveSpy = vi.fn(async () => ({ id: 'rr-1', state: 'reserved' }));
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  reserveOrderInquiryRequest: (...args: unknown[]) => reserveSpy(...(args as [unknown])),
}));

import { ReserveRequestsCard } from './ReserveRequestsCard';

function requestFixture(overrides: { id?: string } = {}) {
  return {
    id: overrides.id ?? 'rr-1',
    ordinal: 1,
    state: 'requested' as const,
    requested_by_name: 'Joey',
    requested_at: '2026-09-22T09:00:00',
    rows: [
      {
        id: 'rr-row-1',
        item_code: 'B2155-NL-BLUE',
        qty_requested: '139',
        default_reserved: '139',
        location_options: [{ value: 'BRW', label: 'BRW' }],
        default_location: 'BRW',
      },
    ],
  };
}

describe('AC-RS-28: typed act-mode input survives a same-values re-render', () => {
  it('Reserved and Reason typed are not wiped when the parent hands a NEW rows array of the same values', async () => {
    const { rerender } = render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    const reservedInput = (await screen.findByLabelText('Reserved')) as HTMLInputElement;
    fireEvent.change(reservedInput, { target: { value: '30' } });
    fireEvent.change(await screen.findByLabelText(/reason/i), {
      target: { value: 'BRW only has 30 today' },
    });
    expect(reservedInput.value).toBe('30');

    // A brand-new `request` object AND a brand-new `rows` array (`requestFixture()`
    // called again), every id and value inside it identical - what a refetch that
    // returned the same server data looks like to the caller.
    rerender(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    expect((screen.getByLabelText('Reserved') as HTMLInputElement).value).toBe('30');
    expect(await screen.findByLabelText(/reason/i)).toHaveValue('BRW only has 30 today');
  });

  it('a re-render with a DIFFERENT request.id does reset the inputs', async () => {
    const { rerender } = render(
      <ReserveRequestsCard
        request={requestFixture({ id: 'rr-1' }) as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    const reservedInput = (await screen.findByLabelText('Reserved')) as HTMLInputElement;
    fireEvent.change(reservedInput, { target: { value: '30' } });
    expect(reservedInput.value).toBe('30');

    rerender(
      <ReserveRequestsCard
        request={requestFixture({ id: 'rr-2' }) as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
      />,
    );

    expect((screen.getByLabelText('Reserved') as HTMLInputElement).value).toBe('139');
  });
});

describe('AC-RS-24 defect: Cancel request must reach a reserve-permission holder in ACT mode too', () => {
  it('renders Cancel request in act mode when cancelControl is supplied, and clicking it calls start()', async () => {
    const start = vi.fn();
    render(
      <ReserveRequestsCard
        request={requestFixture() as never}
        mode="act"
        canAct
        onConfirmed={vi.fn()}
        cancelControl={{ isPending: false, isBlocked: false, countdown: null, start }}
      />,
    );

    const cancelButton = await screen.findByRole('button', { name: /cancel request/i });
    fireEvent.click(cancelButton);

    expect(start).toHaveBeenCalledTimes(1);
  });
});
