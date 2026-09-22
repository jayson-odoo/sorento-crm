/**
 * Security fix round (N-3, `PLAN-oi-request-cs-reserve.md`): "No UUIDs in the frontend
 * UI" (CLAUDE.md Cursor rules). The read-only branch of `ReserveRequestsCard` resolves
 * its Location text ONLY from `row.location_options.find(...).label`, falling back to
 * the raw `row.default_location` id when nothing in `location_options` matches -
 * observable whenever the server hands back an empty `location_options` (e.g. the
 * reserved warehouse is not one of this row's own stock-grid options). This test is
 * written against the CONTRACT (the backend's own `_serialize_reserve_request` already
 * returns a `location` CODE string, e.g. `"BRW"`, alongside `default_location`), not
 * against the current `ReserveRequestsCardRow` type, which has no `location` field at
 * all - a red here is the raw uuid rendering, or the missing `location` prop being
 * silently ignored, never a fixture bug.
 *
 * ASSUMPTION (named per the tester's brief): the fix adds `location: string | null` to
 * `ReserveRequestsCardRow` and the read-only branch prefers it over resolving through
 * `location_options`. `as never` (same as the sibling suite) carries the row literal
 * past today's narrower type so this test exercises the RUNTIME behaviour the contract
 * promises, not a type the fix has not landed yet.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  reserveOrderInquiryRequest: vi.fn(),
}));

import { ReserveRequestsCard } from './ReserveRequestsCard';

const WAREHOUSE_UUID = '3e9f9c9e-7c2a-4a3b-9a34-8f6a1c2d3e4f';

function requestFixture() {
  return {
    id: 'rr-1',
    ordinal: 1,
    state: 'reserved' as const,
    requested_by_name: 'Joey',
    requested_at: '2026-09-22T09:00:00',
    rows: [
      {
        id: 'rr-row-1',
        item_code: 'B2155-NL-BLUE',
        qty_requested: '139',
        default_reserved: '50',
        // The server found no stock-grid option for the warehouse it actually reserved
        // against - exactly the shape that makes `location_options.find(...)` miss.
        location_options: [],
        default_location: WAREHOUSE_UUID,
        location: 'BRW',
        qty_reserved: '50',
        // Deliberately no "BRW" anywhere else on the row (no reason text mentioning the
        // location code) - the only place "BRW" can legitimately come from is the
        // location render itself, so this assertion cannot pass by coincidence.
        reason: null,
      },
    ],
  };
}

describe('read-only ReserveRequestsCard never renders a raw warehouse id', () => {
  it('shows the location CODE (BRW), not the uuid, when location_options is empty', async () => {
    render(
      <ReserveRequestsCard request={requestFixture() as never} mode="request" canAct={false} />,
    );

    await screen.findByText('B2155-NL-BLUE');
    expect(screen.queryByText(new RegExp(WAREHOUSE_UUID))).not.toBeInTheDocument();
    expect(screen.getByText(/BRW/)).toBeInTheDocument();
  });
});
