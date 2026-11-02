/**
 * PS-PROPOSAL-QUOTATION fix round 3 (crew browser pass): a proposal says "proposal" wherever the
 * kind is known - the sign dialog title, the downloads list, the form title and Save button.
 */
import * as React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { downloadKindLabel } from '@/components/my-downloads/DownloadRow';
import { QuotationSignDialog } from './[documentId]/components/QuotationSignDialog';
import { formTitle, saveLabel } from './components/QuotationFormClient';

vi.mock('@/components/common/SignaturePad', () => ({ SignaturePad: () => null }), {
  virtual: true,
});

describe('proposal wording', () => {
  it('the sign dialog names the document kind', () => {
    render(
      <QuotationSignDialog
        open
        onOpenChange={() => {}}
        signatoryName={null}
        isSaving={false}
        onSign={() => {}}
        noun="proposal"
      />,
    );
    expect(screen.getByText('Sign this proposal')).toBeInTheDocument();
  });

  it('My Downloads labels a proposal export as a proposal', () => {
    expect(downloadKindLabel({ kind: 'quotation_pdf', filename: 'proposal-PRJQ-2026-0003-C.pdf' }))
      .toBe('Proposal PDF');
    expect(downloadKindLabel({ kind: 'quotation_xlsx', filename: 'proposal-PRJQ-2026-0003-C.xlsx' }))
      .toBe('Proposal Excel');
    expect(downloadKindLabel({ kind: 'quotation_pdf', filename: 'quotation-QT-2026-0001-R1.pdf' }))
      .toBe('Quotation PDF');
    expect(downloadKindLabel({ kind: 'complaint_pdf', filename: null })).toBe('Complaint PDF');
  });

  it('the form says New proposal / Save proposal, and the quotation kind keeps its own word', () => {
    expect(formTitle({ isEdit: false })).toBe('New proposal');
    expect(saveLabel(undefined)).toBe('Save proposal');
    expect(saveLabel('proposal')).toBe('Save proposal');
    expect(saveLabel('quotation')).toBe('Save quotation');
    expect(formTitle({ isEdit: true, documentNo: null, kind: 'quotation' })).toBe('Edit quotation');
  });
});
