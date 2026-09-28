/**
 * AC-U6 (#1312, PLAN-oi-line-attachments-27sep.md): the order inquiry Lines tab's own
 * State cell carries the same attachments paperclip the board does, on every line that
 * carries a core line id, next to the existing icons (the pill, the History icon, the
 * reserve actions). A sibling file to `orderInquiryHeaderLinesColumns.test.tsx` (that
 * file's own header comment), so its large existing suite is untouched.
 *
 * `SoLineAttachmentsButton` itself is mocked - its own contract is
 * `SoLineAttachmentsButton.test.tsx`'s job; this only pins that the column wires the
 * row's own `core_line_id` through to it.
 */
import React from 'react';
import { renderHook, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/app/(protected)/project-sales/_shared/components/SoLineAttachmentsButton', () => ({
  SoLineAttachmentsButton: ({ lineId, label }: { lineId: string; label: string }) => (
    <span data-testid={`attachments-button-${lineId}`}>{label}</span>
  ),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function linesRow(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

function stateCellFor(row: OrderInquiryWorklistRow) {
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
  const stateColumn = result.current.find(
    (column) =>
      ((column as { id?: string }).id ?? (column as { accessorKey?: string }).accessorKey) ===
      'state',
  ) as { cell: (context: unknown) => React.ReactNode } | undefined;
  expect(stateColumn).toBeDefined();
  return stateColumn!.cell({ row: { original: row } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AC-U6: the State cell carries the attachments paperclip beside the existing icons', () => {
  it('renders the paperclip wired to the row own core line id', () => {
    render(<>{stateCellFor(linesRow({ id: 'row-a', core_line_id: 'core-line-9' } as never))}</>);

    expect(screen.getByTestId('attachments-button-core-line-9')).toBeInTheDocument();
  });

  it('renders no paperclip for a row naming no core sales-order line', () => {
    render(<>{stateCellFor(linesRow({ id: 'row-b', core_line_id: undefined } as never))}</>);

    expect(screen.queryByTestId(/^attachments-button-/)).not.toBeInTheDocument();
  });
});
