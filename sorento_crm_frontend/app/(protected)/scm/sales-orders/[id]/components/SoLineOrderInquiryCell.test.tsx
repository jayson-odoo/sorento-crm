/**
 * SO-LINE-OI-STATUS-UNIFY (`documentation/plans/scm/PLAN-so-line-oi-status-unify-05nov.md`,
 * owner 5 Nov 2026). The Sales Order Lines tab's Order inquiry cell reads the SAME status
 * as the OI Lines tab's State cell, from the same fold and the same pill, with the OI
 * page's own PO / SPO chips, reserve text and Rejected lightbox, on one row.
 *
 * The owner's case: SO429216 line 32 CKSW015, OI-2611-0048, `state='placed'` (linked to a
 * PO, not confirmed by purchasing), `ack_state='awaiting'`. The SO read "On PO/SPO", the OI
 * read "To order". Unified, it reads "To order" with its PO chip visible.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/app/(protected)/project-sales/_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/app/(protected)/project-sales/_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoDetail: vi.fn(() => new Promise(() => {})),
    getOrderInquirySpoDetail: vi.fn(() => new Promise(() => {})),
  };
});

import { SoLineOrderInquiryCell } from './SoLineOrderInquiryCell';
import type { OrderInquiryWorklistRow } from '@/app/(protected)/project-sales/_shared/types/orderInquiry.types';

function oiRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-cksw015',
    order_inquiry_id: 'oi-2611-0048',
    inquiry_no: 'OI-2611-0048',
    so_line_id: 'mirror-32',
    core_line_id: 'core-32',
    so_line_no: 32,
    item_code: 'CKSW015',
    qty: '4',
    verb: 'ORDER',
    state: 'raised',
    ack_state: 'awaiting',
    redirected_to_pool: false,
    links: [],
    ...over,
  } as OrderInquiryWorklistRow;
}

const PO_LINK = {
  id: 'link-1',
  kind: 'po',
  document: '202611-P0042',
  qty: '4',
  po_id: 'po-42',
  po_line_id: 'po-42-l3',
};

function renderCell(rows: OrderInquiryWorklistRow[] | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <table>
        <tbody>
          <tr>
            <td style={{ width: 360 }}>
              <SoLineOrderInquiryCell rows={rows} lineId="core-32" />
            </td>
          </tr>
        </tbody>
      </table>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SO line Order inquiry cell reads the OI row status', () => {
  it('CKSW015: placed but not confirmed reads "To order" (the OI word), never "On PO/SPO", with its PO chip', () => {
    renderCell([oiRow({ state: 'placed', ack_state: 'awaiting', links: [PO_LINK] as never })]);

    expect(screen.getByText('To order')).toBeInTheDocument();
    expect(screen.queryByText('On PO/SPO')).toBeNull();
    expect(screen.queryByText(/to buy/i)).toBeNull();
    // The OI page's own PO chip: the number, clickable.
    expect(screen.getByText('202611-P0042')).toBeInTheDocument();
    const oi = screen.getByText('OI-2611-0048').closest('a');
    expect(oi).toHaveAttribute(
      'href',
      '/project-sales/order-inquiries/oi-2611-0048?row=row-cksw015',
    );
  });

  it('a raised, unconfirmed row reads "To order", not "To Buy"', () => {
    renderCell([oiRow()]);
    expect(screen.getByText('To order')).toBeInTheDocument();
    expect(screen.queryByText(/to buy/i)).toBeNull();
  });

  it('a confirmed row reads "Done"', () => {
    renderCell([oiRow({ state: 'placed', ack_state: 'acknowledged', links: [PO_LINK] as never })]);
    expect(screen.getByText('Done')).toBeInTheDocument();
  });

  it('a part-covered row reads "To order · N left", the OI page text', () => {
    renderCell([oiRow({ qty: '33', open_qty: '29', state: 'partly_linked' } as never)]);
    expect(screen.getByText('To order · 29 left')).toBeInTheDocument();
  });

  it('hides used and cancelled rows: the live row decides, whatever row is newest', () => {
    renderCell([
      oiRow(),
      oiRow({ id: 'row-used', state: 'placed', redirected_to_pool: true, links: [PO_LINK] as never }),
      oiRow({ id: 'row-cancelled', state: 'cancelled' }),
    ]);
    expect(screen.getByText('To order')).toBeInTheDocument();
    // The used row's PO is not this line's live cover.
    expect(screen.queryByText('202611-P0042')).toBeNull();
    expect(screen.queryByText('On PO/SPO')).toBeNull();
  });

  it('a line whose only rows are used reads a dash', () => {
    renderCell([oiRow({ redirected_to_pool: true })]);
    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.queryByText('OI-2611-0048')).toBeNull();
  });

  it('no rows reads a dash', () => {
    renderCell(null);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('reserved reads the reserve pill and where it was reserved from, as on the OI row', () => {
    renderCell([
      oiRow({
        reserve_state: 'reserved',
        reserved_qty: '4',
        reserve_label: 'Reserved @ BRW',
      } as never),
    ]);
    expect(screen.getByText(/Reserved 4/)).toBeInTheDocument();
    expect(screen.getByText('Reserved @ BRW 4')).toBeInTheDocument();
  });

  it('rejected reads the Rejected pill with its reason; a click opens the lightbox with who and when', () => {
    renderCell([
      oiRow({
        ack_state: 'rejected',
        rejected_reason: 'Supplier discontinued this finish',
        rejected_by_name: 'Joey',
        rejected_at: '2026-11-05T03:05:00',
      }),
    ]);
    const badge = screen.getByTestId('so-line-oi-core-32-rejected');
    expect(within(badge).getByText('Rejected')).toBeInTheDocument();
    expect(within(badge).getByText('Supplier discontinued this finish')).toBeInTheDocument();
    expect(screen.queryByText('To order')).toBeNull();

    fireEvent.click(badge);
    const dialog = screen.getByTestId('so-line-oi-core-32-rejected-dialog');
    expect(within(dialog).getByText('Supplier discontinued this finish')).toBeInTheDocument();
    expect(within(dialog).getByText('Joey')).toBeInTheDocument();
    expect(within(dialog).getByText(/05\/11\/2026/)).toBeInTheDocument();
  });

  it('two OIs on one line stay on one row: the newest shows, the other sits behind "+1"', () => {
    renderCell([
      oiRow(),
      oiRow({
        id: 'row-amend',
        order_inquiry_id: 'oi-2611-0050',
        inquiry_no: 'OI-2611-0050',
        state: 'placed',
        ack_state: 'acknowledged',
        links: [PO_LINK] as never,
      }),
    ]);
    expect(screen.getByText('OI-2611-0050')).toBeInTheDocument();
    expect(screen.queryByText('OI-2611-0048')).toBeNull();
    const more = screen.getByRole('button', { name: '1 more order inquiry' });
    expect(more).toHaveTextContent('+1');
    fireEvent.click(more);
    expect(screen.getByText('OI-2611-0048')).toBeInTheDocument();
    expect(screen.getByText('To order')).toBeInTheDocument();
  });
});
