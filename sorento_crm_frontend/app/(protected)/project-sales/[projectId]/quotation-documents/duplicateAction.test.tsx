/**
 * QUOTE-DUPLICATE-PARTY (UAC D1): "Duplicate for another party" in the document's action set (the
 * gear and the list row's "..."), for editors only, sent or not.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../_shared/services/quotationDocumentService';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
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
    is_issued: false,
    signatory_signature: null,
    scopes: [],
    ...overrides,
  } as unknown as QuotationDocument;
}

function run(document: QuotationDocument, canEdit: boolean) {
  const client = new QueryClient();
  return renderHook(() => useQuotationDocumentActions({ projectId: 'p1', document, canEdit }), {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  }).result.current;
}

describe('Duplicate for another party', () => {
  it('is offered to an editor, enabled before and after the first send', () => {
    for (const issued of [false, true]) {
      const action = run(doc({ is_issued: issued }), true).actions.find(
        (a) => a.key === 'quotation_document.duplicate',
      );
      expect(action?.label).toBe('Duplicate for another party');
      expect(action?.disabled).toBeFalsy();
    }
  });

  it('is absent for a reader', () => {
    const { actions } = run(doc(), false);
    expect(actions.some((a) => a.key === 'quotation_document.duplicate')).toBe(false);
  });

  it('sits before Delete', () => {
    const keys = run(doc(), true).actions.map((a) => a.key);
    expect(keys.indexOf('quotation_document.duplicate')).toBeGreaterThan(-1);
    expect(keys.indexOf('quotation_document.duplicate')).toBeLessThan(
      keys.indexOf('quotation_document.delete'),
    );
  });
});
