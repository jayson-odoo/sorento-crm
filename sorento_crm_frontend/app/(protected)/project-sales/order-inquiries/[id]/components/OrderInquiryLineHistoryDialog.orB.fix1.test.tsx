/**
 * SPARE-PART-OR-B fix round 1 (browser pass), red-first. Item 11: the line History lightbox
 * opened from a spare part line never says "sales order line" (it has no sales order): not in
 * the title, not in the description (sr-only included), not in any tab body.
 * Harness copied from `OrderInquiryLineHistoryDialog.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn(
  async () => new Response(JSON.stringify({ events: [] }), { status: 200, headers: { 'content-type': 'application/json' } }),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...(args as [])) }));
vi.mock('../../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryReserveService')>();
  return { ...actual, getDecisionTrail: vi.fn(async () => []) };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { OrderInquiryLineHistoryDialog } from './OrderInquiryLineHistoryDialog';
import { foldInquiryLines } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

const SPARE = {
  id: 'row-1',
  order_inquiry_id: 'spr-1',
  inquiry_no: 'OR-2611-0003',
  oi_no: 'OI-2611-0001',
  inquiry_type: 'spare_part_request',
  verb: 'REPLENISH',
  state: 'raised',
  ack_state: 'awaiting',
  item_code: 'ZZX-SEAL-40',
  qty: '10',
  linked_qty: '0',
  reserved_qty: '0',
  bundled_qty: '0',
  so_number: null,
  core_line_id: null,
} as unknown as OrderInquiryWorklistRow;

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const [line] = foldInquiryLines([SPARE]);
  render(
    <QueryClientProvider client={client}>
      <OrderInquiryLineHistoryDialog line={line} onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

const allText = () => document.body.textContent ?? '';

describe('item 11: a spare part line History never says "sales order line"', () => {
  it('the title and the description', () => {
    open();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(allText()).not.toMatch(/sales order line/i);
  });

  it.each(['Rows', 'Decisions'])('the %s tab', (name) => {
    open();
    fireEvent.mouseDown(screen.getByRole('tab', { name }));
    fireEvent.click(screen.getByRole('tab', { name }));
    expect(allText()).not.toMatch(/sales order line/i);
  });
});
