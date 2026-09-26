/**
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248), AC-ND-13..16, owner rulings 26 Sep
 * 2026: ONE History dialog per sales order line (G2) with line tabs Rows | Decisions, plus
 * Reserve only when the line has reserve history (G3). Rows lists every row that is not
 * the line's current need, the used row included (G1, G6); the Was / now story reads only
 * here.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getOrderInquiryHeaderCancelledRows = vi.fn();
const getDecisionTrail = vi.fn();

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeaderCancelledRows: (...args: unknown[]) =>
      getOrderInquiryHeaderCancelledRows(...args),
  };
});

vi.mock('../../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryReserveService')>();
  return { ...actual, getDecisionTrail: (...args: unknown[]) => getDecisionTrail(...args) };
});

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { OrderInquiryLineHistoryDialog } from './OrderInquiryLineHistoryDialog';
import { foldInquiryLines } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function row(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    reserved_qty: '0',
    bundled_qty: '0',
    so_number: 'SO402757',
    item_code: 'CKS1050',
    core_line_id: 'cl-1',
    line_no: 1,
    ...overrides,
  } as OrderInquiryWorklistRow;
}

const USED = row({
  id: 'used',
  qty: '2',
  state: 'placed',
  redirected_to_pool: true,
  note: 'PO-2026/09-0023 received 24 Sep 2026, released at revision 3',
  raised_at: '2026-09-19T08:00:00Z',
  links: [{ kind: 'po', document: 'PO-2026/09-0023', qty: '2' }] as never,
});
const FRESH = row({
  id: 'fresh',
  qty: '5',
  previous_qty: '2',
  note: 'Replaces 2 used; PO-2026/09-0023 received',
  raised_at: '2026-09-25T08:00:00Z',
});

function renderDialog(
  rows: OrderInquiryWorklistRow[],
  props: Partial<React.ComponentProps<typeof OrderInquiryLineHistoryDialog>> = {},
) {
  const [line] = foldInquiryLines(rows);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLineHistoryDialog
        inquiryId="oi-1"
        line={line}
        onOpenChange={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryHeaderCancelledRows.mockResolvedValue([]);
  getDecisionTrail.mockResolvedValue([]);
});

describe('AC-ND-14: title and tabs', () => {
  it('is titled "History - <item> (<SO> L<n>)" with Rows | Decisions, Rows first', async () => {
    renderDialog([USED, FRESH]);
    const dialog = await screen.findByRole('dialog', { name: 'History - CKS1050 (SO402757 L1)' });
    const tabs = within(dialog).getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabs).toEqual(['Rows', 'Decisions']);
    expect(within(dialog).getByRole('tab', { name: 'Rows' })).toHaveAttribute('aria-selected', 'true');
  });

  it('adds a Reserve tab only when the line has reserve history, listing it', async () => {
    renderDialog([USED, FRESH], {
      reserveEntries: [
        { kind: 'reserved', qty: '2', location: 'BRW', reason: null, actor_name: 'Eling', created_at: '2026-09-24T04:25:00Z' },
      ],
    });
    const dialog = await screen.findByRole('dialog');
    const reserveTab = within(dialog).getByRole('tab', { name: 'Reserve' });
    fireEvent.mouseDown(reserveTab);
    fireEvent.click(reserveTab);
    expect(await within(dialog).findByText('Reserved 2 @ BRW')).toBeInTheDocument();
  });
});

describe('AC-ND-15 (G1, G6): the Rows tab', () => {
  it('lists Now first with its Was, then the used row with its document', async () => {
    renderDialog([USED, FRESH]);
    const dialog = await screen.findByRole('dialog');
    // S2: the grid renders once the cancelled rows have loaded.
    await within(dialog).findByText('Now');
    const bodyRows = within(dialog).getAllByRole('row').filter((r) => r.closest('tbody'));
    expect(bodyRows).toHaveLength(2);
    expect(within(bodyRows[0]).getByText('Now')).toBeInTheDocument();
    expect(within(bodyRows[0]).getByText('Was 2. Replaces 2 used; PO-2026/09-0023 received')).toBeInTheDocument();
    expect(within(bodyRows[1]).getByText('Used')).toBeInTheDocument();
    expect(within(bodyRows[1]).getByText('PO-2026/09-0023')).toBeInTheDocument();
  });

  it("reads the inquiry's cancelled rows for this line only, labelled", async () => {
    getOrderInquiryHeaderCancelledRows.mockResolvedValue([
      row({ id: 'sup', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-18T08:00:00Z' }),
      row({ id: 'other', core_line_id: 'cl-9', line_no: 9, state: 'cancelled', note: 'Superseded by revision 2' }),
    ]);
    renderDialog([USED, FRESH]);
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Superseded')).toBeInTheDocument();
    expect(getOrderInquiryHeaderCancelledRows).toHaveBeenCalledWith('oi-1');
    const bodyRows = within(dialog).getAllByRole('row').filter((r) => r.closest('tbody'));
    expect(bodyRows).toHaveLength(3);
  });

  it('AC-ND-16: a line with no earlier rows says so', async () => {
    renderDialog([FRESH]);
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('No earlier rows for this line.')).toBeInTheDocument();
  });
});

describe('S2: the Rows tab never shows a false empty state', () => {
  it('shows a skeleton, not "No earlier rows", while the cancelled rows are loading', async () => {
    getOrderInquiryHeaderCancelledRows.mockReturnValue(new Promise(() => {}));
    renderDialog([FRESH]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(within(dialog).queryByText('No earlier rows for this line.')).not.toBeInTheDocument();
  });

  it('shows the read error, not "No earlier rows", when the cancelled rows fail to load', async () => {
    getOrderInquiryHeaderCancelledRows.mockRejectedValue(new Error('Could not load cancelled rows'));
    renderDialog([FRESH]);
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Could not load cancelled rows')).toBeInTheDocument();
    expect(within(dialog).queryByText('No earlier rows for this line.')).not.toBeInTheDocument();
  });
});

describe('Decisions tab', () => {
  it('reads the line decision trail, and says so when the line names no core line', async () => {
    renderDialog([row({ id: 'x', core_line_id: null, line_no: null })]);
    const dialog = await screen.findByRole('dialog');
    const decisions = within(dialog).getByRole('tab', { name: 'Decisions' });
    fireEvent.mouseDown(decisions);
    fireEvent.click(decisions);
    expect(await within(dialog).findByText('No decisions recorded for this line.')).toBeInTheDocument();
    expect(getDecisionTrail).not.toHaveBeenCalled();
  });
});
