/**
 * PS-QUOTE-MATRIX fix round 1: Show in Lines picks the scope by `scope_id` (two scopes may share
 * a label), by label when the row has none; a failed read says so instead of "no feedback".
 * Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
import type { Project, QuotationFeedbackRow } from '../../../../_shared/types/project.types';

const getQuotationFeedback = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/',
}));
vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    getQuotationFeedback: (...args: unknown[]) => getQuotationFeedback(...args),
    setQuotationFeedbackHandled: vi.fn(),
  };
});
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationDocumentProvider } from './QuotationDocumentContext';
import { QuotationFeedbackPanel } from './QuotationFeedbackPanel';

const SCOPES = [
  { id: 'scope-1', scope_label: 'UNIT' },
  { id: 'scope-2', scope_label: 'UNIT' },
  { id: 'scope-3', scope_label: 'LEVEL 9' },
];

function row(overrides: Partial<QuotationFeedbackRow>): QuotationFeedbackRow {
  return {
    id: 'f1',
    line_id: 'l1',
    scope_label: 'UNIT',
    line_description: 'Sink',
    cell_key: null,
    cell_label: null,
    kind: 'note',
    value_from: null,
    value_to: null,
    model: null,
    note: 'Hi',
    handled_at: null,
    handled_by_name: null,
    ...overrides,
  };
}

function renderPanel(selectScope = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationDocumentProvider
        value={{
          projectId: 'p1',
          documentId: 'd1',
          document: { id: 'd1', scopes: SCOPES } as unknown as QuotationDocument,
          project: { id: 'p1' } as Project,
          canEdit: true,
          latestIssue: null,
          sorentoSignature: null,
          activeScopeId: null,
          selectScope,
          versionNo: null,
          recheckResults: {},
          dismissRecheck: vi.fn(),
        }}
      >
        <QuotationFeedbackPanel />
      </QuotationDocumentProvider>
    </QueryClientProvider>,
  );
  return selectScope;
}

function feedback(rows: QuotationFeedbackRow[]) {
  return {
    open_count: rows.length,
    requests: [{ id: 'r1', issue_label: 'Rev A', submitted_at: null, requester_name: null, note: null, rows }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('QuotationFeedbackPanel Show in Lines', () => {
  it('opens the scope the row names by id, not the first with its label', async () => {
    getQuotationFeedback.mockResolvedValue(feedback([row({ scope_id: 'scope-2' })]));
    const selectScope = renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Show in Lines' }));
    expect(selectScope).toHaveBeenCalledWith('scope-2');
    // The lines sit on the Header tab now (PROPOSAL-HEADER-LAYOUT); there is no /lines tab.
    expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1');
  });

  it('falls back to the label when the row carries no scope id', async () => {
    getQuotationFeedback.mockResolvedValue(feedback([row({ scope_label: 'LEVEL 9' })]));
    const selectScope = renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Show in Lines' }));
    expect(selectScope).toHaveBeenCalledWith('scope-3');
  });
});

describe('QuotationFeedbackPanel load error', () => {
  it('says the read failed, with the server\'s message, not that there is no feedback', async () => {
    getQuotationFeedback.mockRejectedValue(new Error('Not allowed to read this document'));
    renderPanel();
    expect(
      await screen.findByRole('heading', { name: 'The customer feedback could not be loaded' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Not allowed to read this document')).toBeInTheDocument();
    expect(screen.queryByText('No customer feedback yet')).toBeNull();
  });
});
