/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2/F3/F4/F5, `oi-request-cs-reserve-
 * acceptance-criteria.md` AC-RS-55, AC-RS-61 (tabs half), AC-RS-63 (round 2).
 *
 * S2/S5 (reviewer round 2): `onReserve` is the caller's own `useReserveOrderInquiryRow`
 * mutate function (`_shared/hooks/useOrderInquiry.ts`) - Confirm reserved calls it
 * directly, never the feature service. Unreserve is a server-deferred pending action
 * (ADR-PRODUCT-STANDARDS D7): `unreserveControl` mirrors `cancelControl`'s own shape
 * (`isPending`, `isBlocked`, `countdown`, `start`), built by the caller from
 * `useDeferredAction` against `order_inquiry_reserve_row.unreserve` - `start({ qty,
 * note })` parks it, and `countdown` (once non-null) replaces the qty/note form the
 * same way `cancelControl.countdown` replaces the header's own button.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// S5: `onReserve` is a PROP now (the caller's own mutation), never a service import.
const onReserveSpy = vi.fn(async () => ({ id: 'rr-1', state: 'reserved' }));

// S2: Unreserve parks a deferred action through `unreserveControl.start`, never a
// direct service call - `unreserveStartSpy` stands in for the caller's own
// `useDeferredAction(...).start`.
const unreserveStartSpy = vi.fn();

// AC-RS-63: `formatDateTime` mocked so its OWN call can be asserted, and so the test does
// not depend on the real implementation's exact string - only that it is what renders.
// The formatted output carries NO raw ISO text (fixed date, not derived from `input`), so
// the "no raw ISO in the document" assertion below tests the COMPONENT (does it render
// through `formatDateTime` rather than the raw string it was handed), not the mock's own
// echo of its input.
const formatDateTimeSpy = vi.fn((input: unknown) => {
  void input;
  return '22/09/2026 09:00';
});
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

/** Not pending, not blocked, no countdown yet - the qty/note form renders (S2). */
function idleUnreserveControl() {
  return {
    isPending: false,
    isBlocked: false,
    countdown: null,
    start: (payload: { qty: string; note: string | null }) => unreserveStartSpy(payload),
  };
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
      onReserve={onReserveSpy as never}
      onConfirmed={vi.fn()}
      unreserveControl={idleUnreserveControl()}
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
  it('a row with net reserved and NO open request offers Unreserve, and starts the deferred action with { qty, note }', async () => {
    renderDialog({ openRequest: null, netReservedQty: '50' });

    const unreserveButton = await screen.findByRole('button', { name: /unreserve/i });
    fireEvent.click(unreserveButton);
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /unreserve/i }));

    await waitFor(() => expect(unreserveStartSpy).toHaveBeenCalledTimes(1));
    expect(unreserveStartSpy).toHaveBeenCalledWith(
      expect.objectContaining({ qty: '20' }),
    );
  });

  it('no Unreserve control while a request is still open', () => {
    renderDialog();

    expect(screen.queryByRole('button', { name: /unreserve/i })).not.toBeInTheDocument();
  });

  it('S2: once the deferred action is pending, the countdown replaces the qty/note form - no confirm step', async () => {
    renderDialog({
      openRequest: null,
      netReservedQty: '50',
      unreserveControl: {
        isPending: true,
        isBlocked: false,
        countdown: <div data-testid="unreserve-countdown">Unreserving in 5s</div>,
        start: unreserveStartSpy,
      },
    });

    expect(await screen.findByTestId('unreserve-countdown')).toBeInTheDocument();
    expect(screen.queryByLabelText(/qty/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^unreserve$/i })).not.toBeInTheDocument();
  });

  it('reviewer nit N2: the form does not reappear pre-filled once the countdown clears', async () => {
    const { rerender } = renderDialog({ openRequest: null, netReservedQty: '50' });
    const rerenderWith = (unreserveControl: React.ComponentProps<typeof ReserveRowDialog>['unreserveControl']) =>
      rerender(
        <ReserveRowDialog
          open
          onOpenChange={vi.fn()}
          rowId="row-1"
          itemCode="B2155-NL-BLUE"
          openRequest={null}
          history={historyFixture() as never}
          locationOptions={[]}
          defaultLocationId={null}
          availableQtyByLocation={{}}
          netReservedQty="50"
          canAct
          onReserve={onReserveSpy as never}
          onConfirmed={vi.fn()}
          unreserveControl={unreserveControl}
        />,
      );

    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText(/note/i), { target: { value: 'transferred back' } });

    // The countdown starts (the caller's own `start()` parked it) - the SAME shape
    // the test above already pins, reached here through a prop change rather than a
    // real click so the qty/note the reader typed is still asserted gone afterwards.
    rerenderWith({
      isPending: true,
      isBlocked: false,
      countdown: <div data-testid="unreserve-countdown">Unreserving in 5s</div>,
      start: unreserveStartSpy,
    });
    expect(await screen.findByTestId('unreserve-countdown')).toBeInTheDocument();

    // The window lapses - `pending` clears, the caller's own `onCommitted` refetches
    // (`OrderInquiryDetail.tsx`) and this prop settles back to idle.
    rerenderWith(idleUnreserveControl());

    const reopened = await screen.findByRole('button', { name: /^unreserve$/i });
    fireEvent.click(reopened);

    expect((await screen.findByLabelText(/qty/i)) as HTMLInputElement).toHaveValue(null);
    expect(screen.getByLabelText(/note/i)).toHaveValue('');
  });
});

describe('gap fix (browser evidence postfix-linescope-above-net-silent): the pre-check on Unreserve qty', () => {
  it('a qty typed above net reserved disables Unreserve and names the limit', async () => {
    renderDialog({ openRequest: null, netReservedQty: '50' });

    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '80' } });

    expect(screen.getByRole('button', { name: /^unreserve$/i })).toBeDisabled();
    expect(screen.getByText(/up to 50 can be released/i)).toBeInTheDocument();
    expect(unreserveStartSpy).not.toHaveBeenCalled();
  });

  it('a blank or zero qty disables Unreserve, never starting the deferred action', async () => {
    renderDialog({ openRequest: null, netReservedQty: '50' });

    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    const qtyInput = await screen.findByLabelText(/qty/i);

    // Blank - the form's own starting state.
    expect(screen.getByRole('button', { name: /^unreserve$/i })).toBeDisabled();

    fireEvent.change(qtyInput, { target: { value: '0' } });
    expect(screen.getByRole('button', { name: /^unreserve$/i })).toBeDisabled();
    expect(unreserveStartSpy).not.toHaveBeenCalled();
  });

  it('a qty within net stays enabled and carries no limit message', async () => {
    renderDialog({ openRequest: null, netReservedQty: '50' });

    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '20' } });

    expect(screen.getByRole('button', { name: /^unreserve$/i })).not.toBeDisabled();
    expect(screen.queryByText(/can be released/i)).not.toBeInTheDocument();
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

/**
 * Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G1, `oi-request-cs-reserve-
 * acceptance-criteria.md` AC-RS-66/AC-RS-67). The email deep link used to open this
 * dialog for ONE row (`rowId`/`itemCode`/`openRequest`/`history`/`netReservedQty` as
 * top-level scalar props, everything above this block). Round 3 replaces that shape
 * with `rows: [...]`, length 1..N, keeping every OTHER prop (`open`, `onOpenChange`,
 * `locationOptions`, `defaultLocationId`, `availableQtyByLocation`, `canAct`,
 * `onReserve`, `onConfirmed`, `unreserveControl`, `cancelControl`) at the top level -
 * ONE section per row, its own Confirm reserved, and a History tab ONLY when `rows`
 * carries exactly one entry (the line-click path keeps AC-RS-61's tabs unchanged; the
 * multi-row deep-link path has none, since history lives on the line - AC-RS-65 pins
 * that half in `OrderInquiryDetail.reserveIcon.test.tsx`).
 *
 * TEST-FIRST (Phase 2): today the component reads none of `rows` - it still reads the
 * OLD top-level `rowId`/`itemCode`/`openRequest`/`history`/`netReservedQty`, every one
 * of which is `undefined` when only `rows` is passed. `history` is read unguarded
 * (`history.find(...)`) even on the "nothing reserved" branch, so a bare `rows`-only
 * render throws before any assertion runs - `history={[]}`/`netReservedQty="0"` are
 * handed at the top level below PURELY to dodge that crash and land on the real
 * red: the dialog still renders through the OLD single-row reading (an item code /
 * Confirm button that belong to no row in `rows` at all), never the new shape.
 */
describe('AC-RS-66/AC-RS-67 (round 3): rows - one section per row, tabs only for a single row', () => {
  function rowFixture(over: Partial<Record<string, unknown>> = {}) {
    return {
      rowId: 'row-1',
      itemCode: 'B2155-NL-BLUE',
      openRequest: openRequestFixture(),
      history: historyFixture(),
      netReservedQty: '0',
      ...over,
    };
  }

  function renderMultiRowDialog(
    rows: unknown[],
    overrides: Partial<Record<string, unknown>> = {},
  ) {
    return render(
      <ReserveRowDialog
        open
        onOpenChange={vi.fn()}
        rows={rows as never}
        // Top-level fallbacks so the component's own unguarded `history.find(...)`
        // does not throw before the assertions below get to run - see the doc above.
        history={[] as never}
        netReservedQty="0"
        locationOptions={[
          { value: 'brw-id', label: 'BRW' },
          { value: 'dc1-id', label: 'DC1' },
        ]}
        defaultLocationId="brw-id"
        availableQtyByLocation={{ 'brw-id': 90, 'dc1-id': 5 }}
        canAct
        onReserve={onReserveSpy as never}
        onConfirmed={vi.fn()}
        unreserveControl={idleUnreserveControl()}
        {...(overrides as never)}
      />,
    );
  }

  it('rows length 1: tabs Reserve and History, and the ONE row’s own item code and Confirm reserved', async () => {
    renderMultiRowDialog([
      rowFixture({
        rowId: 'row-1',
        itemCode: 'B2155-NL-BLUE',
        openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '20' }),
      }),
    ]);

    expect(await screen.findByText(/B2155-NL-BLUE/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /reserve/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm reserved/i })).toBeInTheDocument();
  });

  it('rows length 2: no History tab, and each row gets its own section with its own Confirm reserved', async () => {
    renderMultiRowDialog([
      rowFixture({
        rowId: 'row-1',
        itemCode: 'B2155-NL-BLUE',
        openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '20' }),
      }),
      rowFixture({
        rowId: 'row-2',
        itemCode: 'B2155-NL-RED',
        openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '15' }),
      }),
    ]);

    expect(screen.queryByRole('tab', { name: /history/i })).not.toBeInTheDocument();
    expect(await screen.findAllByText(/B2155-NL-BLUE/)).not.toHaveLength(0);
    expect(screen.getAllByText(/B2155-NL-RED/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /confirm reserved/i })).toHaveLength(2);
  });

  it('confirming one section flips it to a read-only "Reserved N" line, the other stays editable; confirming the last closes the dialog', async () => {
    const onOpenChangeSpy = vi.fn();
    renderMultiRowDialog(
      [
        rowFixture({
          rowId: 'row-1',
          itemCode: 'B2155-NL-BLUE',
          openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '20' }),
        }),
        rowFixture({
          rowId: 'row-2',
          itemCode: 'B2155-NL-RED',
          openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '15' }),
        }),
      ],
      { onOpenChange: onOpenChangeSpy },
    );

    const confirmButtons = await screen.findAllByRole('button', { name: /confirm reserved/i });
    expect(confirmButtons).toHaveLength(2);

    fireEvent.click(confirmButtons[0]);
    await waitFor(() => expect(onReserveSpy).toHaveBeenCalledTimes(1));
    expect(onReserveSpy).toHaveBeenCalledWith('rr-1', 'row-1', expect.any(Object));

    // The first section is now read-only; the second row still offers its own Confirm.
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: /confirm reserved/i })).toHaveLength(1),
    );

    fireEvent.click(screen.getByRole('button', { name: /confirm reserved/i }));
    await waitFor(() => expect(onReserveSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(onOpenChangeSpy).toHaveBeenCalledWith(false));
  });

  /**
   * Fix round 1 (`PLAN-oi-request-cs-reserve.md` 6d "Fix round 1", `oi-request-cs-
   * reserve-acceptance-criteria.md` AC-RS-66b). TEST-FIRST: today `ReserveRowSection`
   * only ever reads the dialog's own TOP-LEVEL `locationOptions`/`availableQtyByLocation`
   * /`defaultLocationId` - every section of a multi-row dialog shares that one set, so
   * a row naming a different product still sees the FIRST row's own pools. A red here
   * is "the second section's own Location option leaked into the first" / "the Reserved
   * default came from the wrong row's own availability" - never a fixture bug.
   */
  it('AC-RS-66b: each row section reads its OWN per-row locationOptions/availableQtyByLocation/defaultLocationId, never the dialog-wide fallback', async () => {
    renderMultiRowDialog([
      rowFixture({
        rowId: 'row-1',
        itemCode: 'B2155-NL-BLUE',
        openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '20' }),
        locationOptions: [{ value: 'brw-id', label: 'BRW' }],
        availableQtyByLocation: { 'brw-id': 15 },
        defaultLocationId: 'brw-id',
      }),
      rowFixture({
        rowId: 'row-2',
        itemCode: 'B2155-NL-RED',
        openRequest: openRequestFixture({ requestId: 'rr-1', qtyRequested: '15' }),
        locationOptions: [{ value: 'dc1-id', label: 'DC1' }],
        availableQtyByLocation: { 'dc1-id': 9 },
        defaultLocationId: 'dc1-id',
      }),
    ]);

    // Reserved default is min(requested, THIS row's own available qty) - 15 for row-1
    // (min(20, 15)), 9 for row-2 (min(15, 9)) - never the dialog-wide fallback's own
    // { 'brw-id': 90, 'dc1-id': 5 }, which would read 20 and 15 respectively.
    const reservedInputs = await screen.findAllByLabelText('Reserved');
    expect(reservedInputs).toHaveLength(2);
    expect((reservedInputs[0] as HTMLInputElement).value).toBe('15');
    expect((reservedInputs[1] as HTMLInputElement).value).toBe('9');

    // Each Location select offers only ITS OWN row's own option - the dialog-wide
    // fallback carries both BRW and DC1, so an opened listbox naming both would mean
    // the fallback leaked in instead of the per-row list. Scoped to `role=option`
    // (the opened listbox's own entries) rather than the whole document, because the
    // SECOND section's own selected value already renders the text "DC1" too.
    const locationSelects = screen.getAllByLabelText('Location');
    fireEvent.click(locationSelects[0]);
    const options = await screen.findAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(['BRW']);
  });
});
