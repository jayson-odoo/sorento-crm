/**
 * RESERVE-REQ-PICK (`documentation/plans/scm/PLAN-reserve-request-pick-30oct.md`,
 * AC-RP-1..5): the shared "Request CS to reserve" dialog lets the operator untick lines
 * before sending. Every line opens ticked (unless the caller names it in `untickedRowIds`),
 * the header reads "N of M lines", only ticked lines are validated and posted, and Send is
 * off when nothing is ticked.
 *
 * Same harness as `RequestReserveDialog.test.tsx`: service mocked at the service boundary,
 * the stock-grid read mocked at `useReserveRowOptions`.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const OPTIONS_BY_KEY: Record<string, { default: string; options: { value: string; label: string }[] }> = {
  'row-1': { default: 'BRW', options: [{ value: 'BRW', label: 'BRW' }] },
  'row-2': { default: 'MWH', options: [{ value: 'MWH', label: 'MWH' }] },
};
vi.mock('../hooks/useReserveRowOptions', () => ({
  useReserveRowOptions: (entries: Array<{ key: string }>) =>
    Object.fromEntries(
      entries.map((entry) => {
        const own = OPTIONS_BY_KEY[entry.key];
        return [
          entry.key,
          {
            isLoading: false,
            defaultWarehouseId: own?.default ?? null,
            options: own?.options ?? [],
            availableQtyByWarehouseId: {},
          },
        ];
      }),
    ),
}));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const createSpy = vi.fn(async (_inquiryId: string, _payload: unknown) => ({
  id: 'rr-1',
  ordinal: 1,
  first_to_name: 'Eling',
}));
vi.mock('../services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryReserveService')>();
  return {
    ...actual,
    createOrderInquiryReserveRequest: (inquiryId: string, payload: unknown) =>
      createSpy(inquiryId, payload),
  };
});

import { RequestReserveDialog } from './RequestReserveDialog';

function worklistRow(over: Record<string, unknown>) {
  return {
    id: 'row-1',
    item_code: 'B2155-NL-BLUE',
    product_id: 'prod-1',
    location: 'BRW',
    delivery_date: '2026-10-07',
    qty: '12',
    linked_qty: '0',
    reserved_qty: '0',
    bundled_qty: '0',
    verb: 'ORDER',
    state: 'raised',
    reserve_state: null,
    ...over,
  };
}

const ROWS = [
  worklistRow({}),
  worklistRow({ id: 'row-2', item_code: 'CKS1050', product_id: 'prod-2', location: 'MWH', qty: '2' }),
];

type SentPayload = {
  rows: Array<{ row_id: string; qty_requested: number; warehouse_id: string }>;
  park?: boolean;
};

function renderDialog(overrides: Partial<React.ComponentProps<typeof RequestReserveDialog>> = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const props = {
    inquiryId: 'oi-1',
    open: true,
    onOpenChange: vi.fn(),
    rows: ROWS as never,
    ...overrides,
  };
  const view = render(
    <QueryClientProvider client={qc}>
      <RequestReserveDialog {...props} />
    </QueryClientProvider>,
  );
  return {
    ...view,
    rerenderWith: (next: Partial<React.ComponentProps<typeof RequestReserveDialog>>) =>
      view.rerender(
        <QueryClientProvider client={qc}>
          <RequestReserveDialog {...props} {...next} />
        </QueryClientProvider>,
      ),
  };
}

const lineBox = (itemCode: string) => screen.getByRole('checkbox', { name: `Select ${itemCode}` });
const allBox = () => screen.getByRole('checkbox', { name: /select all/i });
const sendButton = () => screen.getByRole('button', { name: /send request/i });

async function sentRows() {
  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  const [, payload] = createSpy.mock.calls[0] as [string, SentPayload];
  return payload.rows;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AC-RP-1 / AC-RP-2: every line opens ticked, header reads N of M lines', () => {
  it('ticks every line and the header box on open, and reads "2 of 2 lines"', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    expect(lineBox('B2155-NL-BLUE')).toBeChecked();
    expect(lineBox('CKS1050')).toBeChecked();
    expect(allBox()).toBeChecked();
    expect(screen.getByText('2 of 2 lines')).toBeInTheDocument();
  });

  it('unticking one line updates the header to "1 of 2 lines"', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(lineBox('CKS1050'));
    expect(lineBox('CKS1050')).not.toBeChecked();
    expect(screen.getByText('1 of 2 lines')).toBeInTheDocument();
  });

  it('a row named in untickedRowIds opens unticked', async () => {
    renderDialog({ untickedRowIds: ['row-2'] });
    await screen.findByText('CKS1050');
    expect(lineBox('B2155-NL-BLUE')).toBeChecked();
    expect(lineBox('CKS1050')).not.toBeChecked();
    expect(screen.getByText('1 of 2 lines')).toBeInTheDocument();
  });

  it('reopening ticks every line again', async () => {
    const view = renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(lineBox('CKS1050'));
    expect(screen.getByText('1 of 2 lines')).toBeInTheDocument();
    view.rerenderWith({ open: false });
    view.rerenderWith({ open: true });
    await screen.findByText('CKS1050');
    expect(lineBox('CKS1050')).toBeChecked();
    expect(screen.getByText('2 of 2 lines')).toBeInTheDocument();
  });
});

describe('AC-RP-3: only ticked lines are sent', () => {
  it('Send request posts only the ticked line, with its own Requested and Location', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(lineBox('CKS1050'));
    fireEvent.click(sendButton());
    expect(await sentRows()).toEqual([{ row_id: 'row-1', qty_requested: 12, warehouse_id: 'BRW' }]);
  });

  it('a pre-unticked line is not sent unless ticked back', async () => {
    renderDialog({ untickedRowIds: ['row-2'] });
    await screen.findByText('CKS1050');
    fireEvent.click(sendButton());
    expect(await sentRows()).toEqual([{ row_id: 'row-1', qty_requested: 12, warehouse_id: 'BRW' }]);
  });

  it('ticking a pre-unticked line back sends it too', async () => {
    renderDialog({ untickedRowIds: ['row-2'] });
    await screen.findByText('CKS1050');
    fireEvent.click(lineBox('CKS1050'));
    expect(screen.getByText('2 of 2 lines')).toBeInTheDocument();
    fireEvent.click(sendButton());
    expect(await sentRows()).toEqual([
      { row_id: 'row-1', qty_requested: 12, warehouse_id: 'BRW' },
      { row_id: 'row-2', qty_requested: 2, warehouse_id: 'MWH' },
    ]);
  });
});

describe('AC-RP-4: an unticked line is inert', () => {
  it("disables an unticked line's Requested", async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    const requested = document.getElementById('reserve-requested-row-2') as HTMLInputElement;
    expect(requested).not.toBeDisabled();
    fireEvent.click(lineBox('CKS1050'));
    expect(document.getElementById('reserve-requested-row-2')).toBeDisabled();
  });

  it('an out-of-range Requested on an unticked line does not block Send', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    const requested = document.getElementById('reserve-requested-row-2') as HTMLInputElement;
    fireEvent.change(requested, { target: { value: '999' } });
    fireEvent.click(lineBox('CKS1050'));
    fireEvent.click(sendButton());
    expect(await sentRows()).toEqual([{ row_id: 'row-1', qty_requested: 12, warehouse_id: 'BRW' }]);
  });
});

describe('AC-RP-5: nothing ticked, nothing to send', () => {
  it('the header box unticks every line, reads "0 of 2 lines" and disables Send', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(allBox());
    expect(lineBox('B2155-NL-BLUE')).not.toBeChecked();
    expect(lineBox('CKS1050')).not.toBeChecked();
    expect(screen.getByText('0 of 2 lines')).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('Park request is disabled too when nothing is ticked', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(screen.getByLabelText(/park this first/i));
    fireEvent.click(allBox());
    expect(screen.getByRole('button', { name: /park request/i })).toBeDisabled();
  });

  it('the header box ticks every line back', async () => {
    renderDialog();
    await screen.findByText('CKS1050');
    fireEvent.click(allBox());
    fireEvent.click(allBox());
    expect(lineBox('B2155-NL-BLUE')).toBeChecked();
    expect(lineBox('CKS1050')).toBeChecked();
    expect(screen.getByText('2 of 2 lines')).toBeInTheDocument();
    expect(sendButton()).not.toBeDisabled();
  });
});
