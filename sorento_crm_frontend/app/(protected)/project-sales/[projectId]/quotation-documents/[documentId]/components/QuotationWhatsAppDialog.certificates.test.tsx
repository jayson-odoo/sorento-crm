/** QUOTE-CERT-TAB FE-6: the Certificates.pdf line of the WhatsApp prompt (null = legacy, 0 = none, n). */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationDocument, QuotationIssue } from '../../../../_shared/services/quotationDocumentService';

vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/lib/clipboard', () => ({ copyTextToClipboard: vi.fn() }));
vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../_shared/services/quotationDocumentService')>();
  return {
    ...actual,
    createQuotationSignLink: vi.fn(async () => ({ token: 't', path: '/quotation-sign/t', expires_at: null })),
    logQuotationWhatsAppOpened: vi.fn(async () => undefined),
  };
});

import { QuotationWhatsAppDialog } from './QuotationWhatsAppDialog';

const document_ = {
  id: 'd1',
  project_id: 'p1',
  document_no: 'PRJQ-2026-0003',
  recipient_phone_snapshot: '012-000 0001',
  attn_name: 'ATTN A',
  subject_title: 'SUBJECT A',
  signatory_name: 'SALES REP A',
} as unknown as QuotationDocument;

function renderWith(count: number | null | undefined) {
  const issue = {
    id: 'i2',
    document_id: 'd1',
    issue_no: 2,
    revision_label: 'R2',
    our_ref_text: 'PRJQ-2026-0003 (R2)',
    certificates_count: count,
  } as unknown as QuotationIssue;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationWhatsAppDialog projectId="p1" document={document_} issue={issue} onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('QuotationWhatsAppDialog certificates line', () => {
  it('shows the count when the snapshot holds certificates', async () => {
    renderWith(3);
    expect(await screen.findByText('PRJQ-2026-0003 R2 Certificates.pdf (3)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
  });

  it('shows the line without a count for a revision issued before certificates were frozen', async () => {
    renderWith(null);
    expect(await screen.findByText('PRJQ-2026-0003 R2 Certificates.pdf')).toBeInTheDocument();
  });

  it('hides the line when the snapshot is empty', async () => {
    renderWith(0);
    await screen.findByText(/Send R2 to the customer via WhatsApp/);
    expect(screen.queryByText(/Certificates\.pdf/)).toBeNull();
  });
});
