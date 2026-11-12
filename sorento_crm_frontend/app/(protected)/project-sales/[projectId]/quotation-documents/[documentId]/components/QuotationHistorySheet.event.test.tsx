/**
 * QUOTE-DUPLICATE-PARTY (UAC D6, D8): History lists "Copied from ..." / "Duplicated for ..." /
 * "Approval carried from ..." lines with who and when, and offers no View or Restore on them.
 */
import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    listQuotationHistory: async () => [
      {
        id: 'e2', version: 2, kind: 'event', note: 'Duplicated for ARKITEK CONTOH as PRJQ-2026-0009',
        grand_total: null, created_at: '2026-11-11T08:00:00', created_by_name: 'Test Salesperson',
      },
      {
        id: 'e1', version: 1, kind: 'saved', note: null,
        grand_total: '1000.00', created_at: '2026-11-10T08:00:00', created_by_name: 'Test Salesperson',
      },
    ],
  };
});

import { QuotationHistorySheet } from './QuotationHistorySheet';

afterEach(cleanup);

describe('QuotationHistorySheet event lines', () => {
  it('shows the note, who and when, with no View or Restore', async () => {
    render(
      <QuotationHistorySheet
        open
        onOpenChange={() => {}}
        projectId="p1"
        documentId="d1"
        documentNo="PRJQ-2026-0003"
        onRestore={async () => {}}
      />,
    );
    const event = await screen.findByTestId('quotation-history-e2');
    expect(within(event).getByText('Duplicated for ARKITEK CONTOH as PRJQ-2026-0009')).toBeTruthy();
    expect(within(event).getByText(/Test Salesperson/)).toBeTruthy();
    expect(within(event).queryByRole('button')).toBeNull();

    const saved = screen.getByTestId('quotation-history-e1');
    expect(within(saved).getByRole('button', { name: /Restore/ })).toBeTruthy();
  });
});
