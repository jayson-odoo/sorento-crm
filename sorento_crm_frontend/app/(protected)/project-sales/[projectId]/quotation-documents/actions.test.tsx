/**
 * QUOTE-SEND-WHATSAPP: the "Send via WhatsApp" action (UAC section A).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, renderHook, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationDocument, QuotationIssue } from '../../_shared/services/quotationDocumentService';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
const listQuotationIssues = vi.fn();
const createQuotationSignLink = vi.fn();
vi.mock('../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    listQuotationIssues: (...args: unknown[]) => listQuotationIssues(...args),
    createQuotationSignLink: (...args: unknown[]) => createQuotationSignLink(...args),
  };
});
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ start: vi.fn(), isPending: false, countdown: null }),
}));

import { useQuotationDocumentActions } from './actions';

function doc(overrides: Partial<QuotationDocument> = {}): QuotationDocument {
  return {
    id: 'd1',
    project_id: 'p1',
    document_no: 'PRJQ-2026-0003',
    our_ref: 'PRJQ-2026-0003',
    is_issued: true,
    signatory_signature: null,
    scopes: [],
    ...overrides,
  } as unknown as QuotationDocument;
}

function run(document: QuotationDocument, canEdit: boolean) {
  const client = new QueryClient();
  return renderHook(
    () => useQuotationDocumentActions({ projectId: 'p1', document, canEdit }),
    {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    },
  ).result.current;
}

describe('useQuotationDocumentActions Send via WhatsApp', () => {
  it('sits right after Copy counter-sign link (AC-A1)', () => {
    const { actions } = run(doc(), true);
    const keys = actions.map((a) => a.key);
    const at = keys.indexOf('quotation_document.sign_link');
    expect(at).toBeGreaterThan(-1);
    expect(keys[at + 1]).toBe('quotation_document.whatsapp');
    expect(actions[at + 1].label).toBe('Send via WhatsApp');
  });

  it('is enabled once the quotation has been sent', () => {
    const action = run(doc(), true).actions.find((a) => a.key === 'quotation_document.whatsapp');
    expect(action?.disabled).toBeFalsy();
  });

  it('is disabled with a hint before the first send (AC-A3)', () => {
    const action = run(doc({ is_issued: false }), true).actions.find(
      (a) => a.key === 'quotation_document.whatsapp',
    );
    expect(action?.disabled).toBe(true);
    expect(action?.description).toBe('Send it to the customer first');
  });

  it('is absent without edit rights (AC-A2)', () => {
    const { actions } = run(doc(), false);
    expect(actions.some((a) => a.key === 'quotation_document.whatsapp')).toBe(false);
  });

  it('returns openWhatsApp for the send menu (AC-E3)', () => {
    expect(typeof run(doc(), true).openWhatsApp).toBe('function');
  });

  function Harness({ latestIssue }: { latestIssue?: QuotationIssue }) {
    const { actions, dialogs } = useQuotationDocumentActions({
      projectId: 'p1',
      document: doc(),
      canEdit: true,
      latestIssue,
    });
    const action = actions.find((a) => a.key === 'quotation_document.whatsapp')!;
    return (
      <>
        <button type="button" onClick={() => void action.run?.()}>
          go
        </button>
        {dialogs}
      </>
    );
  }

  function renderHarness(latestIssue?: QuotationIssue) {
    createQuotationSignLink.mockReturnValue(new Promise(() => {}));
    return render(
      <QueryClientProvider client={new QueryClient()}>
        <Harness latestIssue={latestIssue} />
      </QueryClientProvider>,
    );
  }

  it('opens the prompt for the given latest revision (AC-A4)', async () => {
    const latestIssue = { id: 'i3', document_id: 'd1', issue_no: 3 } as unknown as QuotationIssue;
    renderHarness(latestIssue);
    fireEvent.click(screen.getByText('go'));
    expect(await screen.findByText('Send R3 via WhatsApp')).toBeInTheDocument();
    expect(listQuotationIssues).not.toHaveBeenCalled();
  });

  it('looks up the first issue when none is given (AC-A4)', async () => {
    listQuotationIssues.mockResolvedValue([
      { id: 'i2', document_id: 'd1', issue_no: 2 },
      { id: 'i1', document_id: 'd1', issue_no: 1 },
    ]);
    renderHarness();
    fireEvent.click(screen.getByText('go'));
    expect(await screen.findByText('Send R2 via WhatsApp')).toBeInTheDocument();
    expect(listQuotationIssues).toHaveBeenCalledWith('p1', 'd1');
  });
});
