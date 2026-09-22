/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2/F3/F4/F5, `oi-request-cs-reserve-
 * acceptance-criteria.md` AC-RS-55, AC-RS-61 (tabs half), AC-RS-63 (round 2).
 *
 * TEST-FIRST (Phase 2): `ReserveRowDialog.tsx` does not exist yet - round 2 deletes
 * `ReserveRequestsCard` (F2) and replaces it with ONE dialog opened per Lines-grid row,
 * carrying a Reserve tab (the act-mode form round 1's card used to render) and a History
 * tab (F3, new). A red here is a missing module, never an import typo.
 *
 * NAMED ASSUMPTIONS (per the tester's brief - neither the plan nor the UAC pins the
 * exact prop contract, only the on-screen behaviour):
 *
 * 1. Props: `{ open, onOpenChange, rowId, itemCode, openRequest, history,
 *    locationOptions, defaultLocationId, availableQtyByLocation, netReservedQty,
 *    canAct, onConfirmed?, onUnreserved? }`. `openRequest` is the OI row's own OPEN
 *    request row (Location/Reserved/Reason inputs render only while it is non-null);
 *    `history` is already resolved (newest first) for the History tab; `locationOptions`
 *    is F1's "every active pool" read, already resolved by the caller (mirrors how
 *    `ReserveRequestDialog` is handed `locationOptions` pre-resolved, `ReserveRequestDialog
 *    .tsx`'s own docstring assumption 1).
 * 2. Two feature-service calls, both added to the existing sibling
 *    `_shared/services/orderInquiryReserveService.ts` (never a hand-rolled fetch):
 *    `reserveOrderInquiryRow(requestId, rowId, { warehouse_id, qty_reserved, reason })`
 *    and `unreserveOrderInquiryRow(requestId, rowId, { qty, note })` - mirroring
 *    `reserveOrderInquiryRequest`'s own existing naming and two-argument shape.
 * 3. Dates render through `formatDateTime` from `@/lib/helpers` (AC-RS-63), the same
 *    helper `OrderInquiryDetail.tsx` already imports (`formatDateTimeInMalaysia` sits
 *    beside it in the same file) - never a raw ISO string.
 * 4. Tabs are the existing shadcn primitives (`@/components/ui/tabs`), the same ones
 *    `OrderInquiryDetail.tsx` already uses for Lines/General/Related PO/Related SPO, so
 *    `getByRole('tab', { name: ... })` resolves the same way `WarehouseForm.test.tsx`'s
 *    own tab assertions already do in this codebase.
 *
 * If the coder's real contract differs, the shape of THIS mock needs updating to match -
 * the BEHAVIOUR asserted (defaults, the recompute, the input surviving a same-values
 * re-render, no UUID text, the date format, the tabs) is the part that must not move.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const reserveRowSpy = vi.fn(async (..._args: unknown[]) => ({ id: 'rr-1', state: 'reserved' }));
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const unreserveRowSpy = vi.fn(async (..._args: unknown[]) => ({ id: 'rr-1', state: 'reserved' }));
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  reserveOrderInquiryRow: (...args: unknown[]) => reserveRowSpy(...args),
  unreserveOrderInquiryRow: (...args: unknown[]) => unreserveRowSpy(...args),
}));

// AC-RS-63: `formatDateTime` mocked so its OWN call can be asserted, and so the test does
// not depend on the real implementation's exact string - only that it is what renders.
// The formatted output carries NO raw ISO text (fixed date, not derived from `input`), so
// the "no raw ISO in the document" assertion below tests the COMPONENT (does it render
// through `formatDateTime` rather than the raw string it was handed), not the mock's own
// echo of its input.
const formatDateTimeSpy = vi.fn((_input: unknown) => '22/09/2026 09:00');
vi.mock('@/lib/helpers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/helpers')>();
  return { ...actual, formatDateTime: (input: unknown) => formatDateTimeSpy(input) };
});

import { ReserveRowDialog } from './ReserveRowDialog';

const WAREHOUSE_UUID = '3e9f9c9e-7c2a-4a3b-9a34-8f6a1c2d3e4f';
const RAW_ISO_PATTERN = /\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d/;

/** Radix's `Tabs.Trigger` inside a Radix `Dialog` switches on mouse down under jsdom; a
 * bare `click` leaves the old panel up. Same workaround `PlanRowDialog.test.tsx` and
 * `SimulationView.test.tsx` already carry for the identical primitive. */
function switchTab(name: string | RegExp) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

function openRequestFixture(over: Partial<Record<string, unknown>> = {}) {
  return {
    requestId: 'rr-1',
    ordinal: 1,
    qtyRequested: '139',
    requestedByName: 'Joey',
    requestedAt: '2026-09-22T09:00:00',
    ...over,
  };
}

function historyFixture() {
  return [
    {
      kind: 'reserved' as const,
      qty: '50',
      location: 'BRW',
      reason: null,
      actorName: 'Eling',
      createdAt: '2026-09-22T10:00:00',
    },
    {
      kind: 'requested' as const,
      qty: '139',
      location: null,
      reason: null,
      actorName: 'Joey',
      createdAt: '2026-09-22T09:00:00',
    },
  ];
}

function renderDialog(overrides: Partial<React.ComponentProps<typeof ReserveRowDialog>> = {}) {
  return render(
    <ReserveRowDialog
      open
      onOpenChange={vi.fn()}
      rowId="row-1"
      itemCode="B2155-NL-BLUE"
      openRequest={openRequestFixture() as never}
      history={historyFixture() as never}
      locationOptions={[
        { value: 'brw-id', label: 'BRW' },
        { value: 'dc1-id', label: 'DC1' },
        { value: 'wh3-id', label: 'WH3' },
      ]}
      defaultLocationId="brw-id"
      availableQtyByLocation={{ 'brw-id': 90, 'dc1-id': 5, 'wh3-id': 0 }}
      netReservedQty="0"
      canAct
      onConfirmed={vi.fn()}
      onUnreserved={vi.fn()}
      {...(overrides as never)}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AC-RS-61: two tabs, Reserve and History', () => {
  it('renders both tabs, Reserve active by default', async () => {
    renderDialog();

    expect(await screen.findByRole('tab', { name: /reserve/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument();
  });

  it('switching to History shows every entry, requested then reserved (as seeded)', async () => {
    renderDialog();

    await screen.findByRole('tab', { name: /history/i });
    switchTab(/history/i);

    expect(await screen.findByText(/eling/i)).toBeInTheDocument();
    expect(screen.getByText(/joey/i)).toBeInTheDocument();
  });
});

describe('AC-RS-55: Location defaults to the configured pool and recomputes Reserved', () => {
  it('Location starts at defaultLocationId, and Reserved defaults from ITS available qty', async () => {
    renderDialog();

    const reservedInput = (await screen.findByLabelText('Reserved')) as HTMLInputElement;
    // min(requested 139, available at BRW 90) = 90.
    expect(reservedInput.value).toBe('90');
  });

  it('changing Location recomputes Reserved from the NEW location, before the reader edits it', async () => {
    renderDialog();

    await screen.findByLabelText('Reserved');
    // SearchableSelect renders options as clickable text once opened - the same
    // interaction `ReserveRequestDialog`'s own location field already exercises
    // elsewhere in this codebase (`WarehouseForm.test.tsx` uses the identical primitive).
    fireEvent.click(screen.getByLabelText('Location'));
    fireEvent.click(await screen.findByText('DC1'));

    await waitFor(() =>
      expect((screen.getByLabelText('Reserved') as HTMLInputElement).value).toBe('5'),
    );
  });

  it('falls back to the row own site pool when defaultLocationId is null (AC-RS-55)', async () => {
    renderDialog({
      defaultLocationId: null,
      locationOptions: [{ value: 'site-pool-id', label: 'MWH' }],
      availableQtyByLocation: { 'site-pool-id': 12 },
    });

    await waitFor(() =>
      expect((screen.getByLabelText('Reserved') as HTMLInputElement).value).toBe('12'),
    );
  });
});

describe('ported AC-RS-28: typed Reserved/Reason input survives a same-values re-render', () => {
  it('a parent re-render with a NEW but value-identical openRequest does not wipe typed input', async () => {
    const { rerender } = renderDialog();

    const reservedInput = (await screen.findByLabelText('Reserved')) as HTMLInputElement;
    fireEvent.change(reservedInput, { target: { value: '30' } });
    fireEvent.change(await screen.findByLabelText(/reason/i), {
      target: { value: 'BRW only has 30 today' },
    });
    expect(reservedInput.value).toBe('30');

    rerender(
      <ReserveRowDialog
        open
        onOpenChange={vi.fn()}
        rowId="row-1"
        itemCode="B2155-NL-BLUE"
        openRequest={openRequestFixture() as never}
        history={historyFixture() as never}
        locationOptions={[
          { value: 'brw-id', label: 'BRW' },
          { value: 'dc1-id', label: 'DC1' },
          { value: 'wh3-id', label: 'WH3' },
        ]}
        defaultLocationId="brw-id"
        availableQtyByLocation={{ 'brw-id': 90, 'dc1-id': 5, 'wh3-id': 0 }}
        netReservedQty="0"
        canAct
      />,
    );

    expect((screen.getByLabelText('Reserved') as HTMLInputElement).value).toBe('30');
    expect(await screen.findByLabelText(/reason/i)).toHaveValue('BRW only has 30 today');
  });
});

describe('ported N-3: no raw warehouse UUID as Location text', () => {
  it('a row already reserved (no open request) shows the pool CODE, never a uuid', async () => {
    renderDialog({
      openRequest: null,
      netReservedQty: '50',
      // The server found no stock-grid option for the warehouse actually reserved
      // against - the same shape `ReserveRequestsCard.noUuid.test.tsx` pinned.
      locationOptions: [],
      defaultLocationId: WAREHOUSE_UUID,
      availableQtyByLocation: {},
      history: [
        {
          kind: 'reserved' as const,
          qty: '50',
          location: 'BRW',
          reason: null,
          actorName: 'Eling',
          createdAt: '2026-09-22T10:00:00',
        },
      ] as never,
    });

    expect(screen.queryByText(new RegExp(WAREHOUSE_UUID))).not.toBeInTheDocument();
    expect(screen.getByText(/BRW/)).toBeInTheDocument();
  });
});

describe('AC-RS-63: every date-time renders through formatDateTime', () => {
  it('the open request "requested on" date calls formatDateTime', async () => {
    renderDialog();

    await screen.findByLabelText('Reserved');
    expect(formatDateTimeSpy).toHaveBeenCalledWith('2026-09-22T09:00:00');
    expect(screen.queryByText(RAW_ISO_PATTERN)).not.toBeInTheDocument();
  });

  it('every History entry date calls formatDateTime, never raw ISO text', async () => {
    renderDialog();

    await screen.findByRole('tab', { name: /history/i });
    switchTab(/history/i);
    await screen.findByText(/eling/i);

    expect(formatDateTimeSpy).toHaveBeenCalledWith('2026-09-22T10:00:00');
    expect(formatDateTimeSpy).toHaveBeenCalledWith('2026-09-22T09:00:00');
    expect(document.body.textContent).not.toMatch(RAW_ISO_PATTERN);
  });
});

describe('F5: Unreserve is its own action, offered only once nothing is left open', () => {
  it('a row with net reserved and NO open request offers Unreserve, and posts { qty, note }', async () => {
    renderDialog({ openRequest: null, netReservedQty: '50' });

    const unreserveButton = await screen.findByRole('button', { name: /unreserve/i });
    fireEvent.click(unreserveButton);
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(unreserveRowSpy).toHaveBeenCalledTimes(1));
    const [, , payload] = unreserveRowSpy.mock.calls[0] as [string, string, { qty: unknown }];
    expect(String(payload.qty)).toBe('20');
  });

  it('no Unreserve control while a request is still open', () => {
    renderDialog();

    expect(screen.queryByRole('button', { name: /unreserve/i })).not.toBeInTheDocument();
  });
});

describe('read-only without the reserve permission (AC-RS-62 half)', () => {
  it('canAct=false: no Reserved/Reason inputs, no Confirm, no Unreserve', async () => {
    renderDialog({ canAct: false, openRequest: null, netReservedQty: '50' });

    await screen.findByRole('tab', { name: /reserve/i });
    expect(screen.queryByLabelText('Reserved')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm reserved/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /unreserve/i })).not.toBeInTheDocument();
  });
});
