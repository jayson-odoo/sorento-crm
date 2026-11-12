/**
 * QUOTE-DUPLICATE-PARTY (UAC D8): a copy's header shows "Copied from <source ref>" linking to the
 * source; a document that is not a copy shows no such row. Names are invented.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';

afterEach(cleanup);

function doc(overrides: Partial<QuotationDocument> = {}): QuotationDocument {
  return {
    id: 'd2',
    project_id: 'p1',
    document_no: 'PRJQ-2026-0009',
    our_ref: 'PRJQ-2026-0009',
    kind: 'proposal',
    recipient_name_snapshot: 'ARKITEK CONTOH',
    scopes: [],
    ...overrides,
  } as unknown as QuotationDocument;
}

describe('QuotationDocumentHeader Copied from', () => {
  it('links a copy to its source', () => {
    render(
      <QuotationDocumentHeader
        document={doc({ copied_from_document_id: 'd1', copied_from_label: 'PRJQ-2026-0003-A' })}
      />,
    );
    expect(screen.getByText('Copied from')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'PRJQ-2026-0003-A' });
    expect(link.getAttribute('href')).toBe('/project-sales/p1/quotation-documents/d1');
  });

  it('shows nothing for a document that is not a copy', () => {
    render(<QuotationDocumentHeader document={doc()} />);
    expect(screen.queryByText('Copied from')).toBeNull();
  });
});
