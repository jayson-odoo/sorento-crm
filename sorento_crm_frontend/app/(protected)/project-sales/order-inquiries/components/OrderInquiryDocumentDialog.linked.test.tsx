/**
 * AC-CF-24/AC-CF-26 (`PLAN-oi-confirm-per-so.md` S8, `oi-confirm-per-so-acceptance-
 * criteria.md`): written from the contract, not from reading the coder's diff.
 *
 * NAMING NOTE for whoever reviews this file's placement: S8's plan text calls the
 * dialog `OrderInquiryDocumentDialog`, which is why this spec sits beside that
 * component's own test file and carries its name with a `.linked` suffix. The dialog
 * "Choose document (1)" actually opens, today, is `LinkDocumentDialog`
 * (`_shared/components/LinkDocumentDialog.tsx`) - the read-only `OrderInquiryDocumentDialog`
 * in THIS folder is a different surface entirely (the document lightbox opened from a PO/
 * SPO number in a listing, `AC-D18`/`AC-D19`, no Take input at all). This file exercises
 * `LinkDocumentDialog` by its real import path so the assertions trace to the component
 * S8 actually has to change; flag it to the coder if the plan intends a rename/merge
 * instead, and adjust the import rather than the behaviour under test.
 *
 * CONCURRENT-EDIT NOTE (17 Sep): the coder was live in this same worktree while this
 * file was being written. By the time it first ran, `getOrderInquiryPoCandidates` had
 * already been widened to resolve `{ candidates, still_to_link }` (S8's envelope) rather
 * than a bare array, and `LinkDocumentDialog` already read `.candidates` off it, prefilled
 * `takeFor()` from `current_take` and rendered a `Current N` mark
 * (`po-candidate-current-<key>`, AC-CF-24 - DONE). The DataGrid table + full document
 * number + "line N of M" (AC-CF-26) were NOT yet done - the table was still the old bare
 * `<table>`. The mocks below resolve the REAL envelope shape so the AC-CF-24 tests pin
 * the finished behaviour as regression coverage and the AC-CF-26 tests stay genuinely red.
 *
 * Patterns copied from `LinkDocumentDialog.test.tsx` (candidate fixtures, the
 * `renderDialog` helper, mocking `../services/orderInquiryService`) and from
 * `OrderInquiryDocumentDialog.test.tsx` (the DataGrid assertion shape, AC-B1).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryPoCandidate } from '../../_shared/types/orderInquiry.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const getOrderInquiryPoCandidates = vi.fn();
const placeOrderInquiryRowOnPoAllocations = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
    placeOrderInquiryRowOnPoAllocations: (...args: unknown[]) =>
      placeOrderInquiryRowOnPoAllocations(...args),
  };
});

import { LinkDocumentDialog } from '../../_shared/components/LinkDocumentDialog';

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

/** The real GET envelope (S8): `{ candidates, still_to_link }`, not a bare array. */
function envelope(candidates: OrderInquiryPoCandidate[], stillToLink = '0') {
  return { candidates, still_to_link: stillToLink };
}

const onDone = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryPoCandidates.mockReset();
  placeOrderInquiryRowOnPoAllocations.mockReset();
});

/** A candidate this row is ALREADY linked to (AC-CF-24): `current_take` carries the
 * live link qty, and the cascade's own `default_take` reads `0` - re-opening the
 * dialog on an already-linked row must not look like the cascade suggests nothing. */
const ALREADY_LINKED: OrderInquiryPoCandidate & { current_take: string } = {
  kind: 'po',
  po_line_id: 'po-line-linked',
  tier: 1,
  location: 'BRW-IB',
  issue_date: '2026-08-01',
  cited: false,
  po_number: 'ZZT-PO-0001',
  supplier_name: 'Dafuyuan',
  expected_date: '2026-09-01',
  qty_ordered: '6',
  qty_received: '0',
  already_tagged: '0',
  remaining: '6',
  covers: false,
  recommended: false,
  default_take: '0',
  claims: [],
  current_take: '6',
};

describe('AC-CF-24: a linked candidate carries its current take, prefilled and marked', () => {
  it('prefills the Take input from current_take when the cascade default is 0', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope([ALREADY_LINKED], '4'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="10" linkedQty="6" onDone={onDone} />,
    );

    const input = (await screen.findByLabelText(
      'Take off ZZT-PO-0001',
    )) as HTMLInputElement;
    expect(input.value).toBe('6');
  });

  it('marks the row Current so a buyer can tell it apart from a fresh candidate', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope([ALREADY_LINKED], '4'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="10" linkedQty="6" onDone={onDone} />,
    );

    const row = await screen.findByTestId('po-candidate-po:po-line-linked');
    expect(within(row).getByText(/current/i)).toBeInTheDocument();
  });

  it('a candidate with no current take carries neither the mark nor a prefilled 6', async () => {
    const fresh: OrderInquiryPoCandidate = {
      ...ALREADY_LINKED,
      po_line_id: 'po-line-fresh',
      po_number: 'ZZT-PO-0002',
      current_take: '0',
      default_take: '0',
    } as OrderInquiryPoCandidate & { current_take: string };
    getOrderInquiryPoCandidates.mockResolvedValue(envelope([fresh], '10'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="10" onDone={onDone} />,
    );

    const row = await screen.findByTestId('po-candidate-po:po-line-fresh');
    expect(within(row).queryByText(/current/i)).not.toBeInTheDocument();
    const input = screen.getByLabelText('Take off ZZT-PO-0002') as HTMLInputElement;
    expect(input.value).toBe('');
  });
});

describe('AC-CF-26: the candidate table is a DataGrid, resizable, with the full document number', () => {
  const LONG_NUMBER = '202605-S0060-ZZTLONGDOCUMENTNUMBERPASTTHEOLDFIXEDWIDTH';

  function threeLinesOfOneDocument(): OrderInquiryPoCandidate[] {
    return [1, 2, 3].map((n) => ({
      ...ALREADY_LINKED,
      po_line_id: `po-line-${n}`,
      po_number: LONG_NUMBER,
      current_take: '0',
    }));
  }

  it('renders a fixed-layout, resizable DataGrid rather than the old bare table', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope(threeLinesOfOneDocument(), '30'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    const table = document.querySelector('table[data-slot="data-grid-table"]');
    expect(table).toBeTruthy();
    expect(table).toHaveClass('table-fixed');
    expect(document.querySelectorAll('.cursor-col-resize').length).toBeGreaterThan(0);
  });

  it('prints the FULL document number, never truncated, at the default width', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope(threeLinesOfOneDocument(), '30'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    const cells = await screen.findAllByText(LONG_NUMBER);
    expect(cells.length).toBeGreaterThan(0);
    for (const cell of cells) {
      expect(cell.className).not.toMatch(/\btruncate\b/);
    }
  });

  it('names "line N of M" when a document contributes several lines', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope(threeLinesOfOneDocument(), '30'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.getByText('line 1 of 3')).toBeInTheDocument();
    expect(screen.getByText('line 2 of 3')).toBeInTheDocument();
    expect(screen.getByText('line 3 of 3')).toBeInTheDocument();
  });

  it('names no "line N of M" for a document that contributes only one line', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue(envelope([ALREADY_LINKED], '4'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="10" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.queryByText(/line 1 of 1/)).not.toBeInTheDocument();
  });
});
