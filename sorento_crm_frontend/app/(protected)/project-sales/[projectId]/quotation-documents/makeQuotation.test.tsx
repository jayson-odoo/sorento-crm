/**
 * PS-PROPOSAL-QUOTATION: the "Make quotation" action on an issued proposal of a won project.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../../_shared/services/quotationDocumentService';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
const listQuotationIssues = vi.fn();
const makeQuotation = vi.fn();
vi.mock('../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    listQuotationIssues: (...args: unknown[]) => listQuotationIssues(...args),
    makeQuotation: (...args: unknown[]) => makeQuotation(...args),
  };
});
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ start: vi.fn(), isPending: false, countdown: null }),
}));

import { useQuotationDocumentActions } from './actions';

const KEY = 'quotation_document.make_quotation';

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

function issue(no: number, label: string): QuotationIssue {
  return {
    id: `i${no}`,
    document_id: 'd1',
    issue_no: no,
    revision_label: label,
    our_ref_text: `PRJQ-2026-0003-${label}`,
    issued_at: null,
    grand_total: '100.00',
  } as unknown as QuotationIssue;
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

function offered(
  document: QuotationDocument,
  opts: { canEdit?: boolean; projectOutcome?: string | null; projectHasQuotation?: boolean } = {},
) {
  const { result } = renderHook(
    () =>
      useQuotationDocumentActions({
        projectId: 'p1',
        document,
        canEdit: opts.canEdit ?? true,
        projectOutcome: 'projectOutcome' in opts ? opts.projectOutcome : 'won',
        projectHasQuotation: opts.projectHasQuotation,
      }),
    { wrapper },
  );
  return result.current.actions.some((a) => a.key === KEY);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Make quotation action visibility', () => {
  it('is offered for an issued proposal on a won project', () => {
    expect(offered(doc())).toBe(true);
  });

  it('is offered when kind is explicitly proposal', () => {
    expect(offered(doc({ kind: 'proposal' }))).toBe(true);
  });

  it.each([['lost'], ['open'], [null], [undefined]])(
    'is absent when the project outcome is %s',
    (outcome) => {
      expect(offered(doc(), { projectOutcome: outcome as string | null })).toBe(false);
    },
  );

  it('is absent on a document that is already a quotation', () => {
    expect(offered(doc({ kind: 'quotation' }))).toBe(false);
  });

  it('is absent before the proposal has been issued', () => {
    expect(offered(doc({ is_issued: false }))).toBe(false);
  });

  it('is absent once a quotation has been made from the proposal', () => {
    expect(offered(doc({ quotation_document_id: 'q1' }))).toBe(false);
  });

  it('is absent once the project holds a quotation made from another proposal', () => {
    expect(offered(doc(), { projectHasQuotation: true })).toBe(false);
  });

  it('is absent without edit rights', () => {
    expect(offered(doc(), { canEdit: false })).toBe(false);
  });
});

describe('Make quotation dialog', () => {
  function Harness() {
    const { actions, dialogs } = useQuotationDocumentActions({
      projectId: 'p1',
      document: doc(),
      canEdit: true,
      projectOutcome: 'won',
    });
    const action = actions.find((a) => a.key === KEY)!;
    return (
      <>
        <button type="button" onClick={() => void action.run?.()}>
          go
        </button>
        {dialogs}
      </>
    );
  }

  function open() {
    render(<Harness />, { wrapper });
    fireEvent.click(screen.getByText('go'));
  }

  it('lists the revisions newest first with the newest preselected', async () => {
    listQuotationIssues.mockResolvedValue([issue(1, 'A'), issue(3, 'C'), issue(2, 'B')]);
    open();
    await screen.findByRole('radio', { name: 'PRJQ-2026-0003-C' });
    const radios = screen.getAllByRole('radio');
    expect(radios.map((r) => r.getAttribute('aria-label'))).toEqual([
      'PRJQ-2026-0003-C',
      'PRJQ-2026-0003-B',
      'PRJQ-2026-0003-A',
    ]);
    await waitFor(() => expect(radios[0]).toBeChecked());
    expect(radios[1]).not.toBeChecked();
    expect(listQuotationIssues).toHaveBeenCalledWith('p1', 'd1');
  });

  it('confirming calls makeQuotation(projectId, proposalId, issueId) with the newest revision', async () => {
    listQuotationIssues.mockResolvedValue([issue(1, 'A'), issue(2, 'B')]);
    makeQuotation.mockResolvedValue({ id: 'q9', document_no: 'QT-1' });
    open();
    const radio = await screen.findByRole('radio', { name: 'PRJQ-2026-0003-B' });
    await waitFor(() => expect(radio).toBeChecked());
    const buttons = screen.getAllByRole('button', { name: 'Make quotation' });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(makeQuotation).toHaveBeenCalledWith('p1', 'd1', 'i2'));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/q9'),
    );
  });
});
