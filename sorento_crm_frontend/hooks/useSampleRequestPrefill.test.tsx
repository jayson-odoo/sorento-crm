/**
 * SAMPLE-FROM-QUOTE: when a sample request form pre-fills from the project's quotation
 * (UAC SFQ-20..24). Both forms (the shared portal form and the staff form) call this hook.
 */
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useSampleRequestPrefill } from './useSampleRequestPrefill';
import { EMPTY_FORM, blankLine, type FormState } from '@/lib/sample-request-form';
import type { SampleRequestQuotationPrefill } from '@/types/sampleRequest';

const quote = (docId: string, ...codes: string[]): SampleRequestQuotationPrefill => ({
  documents: [
    { id: docId, document_no: `NO-${docId}`, issue_id: null, issue_no: null, label: `NO-${docId} (not issued)` },
    { id: 'doc-other', document_no: 'NO-other', issue_id: null, issue_no: null, label: 'NO-other (not issued)' },
  ],
  document_id: docId,
  issue_id: null,
  lines: codes.map((c) => ({ product_id: `id-${c}`, product_code: c, product_name: c, brand_name: null })),
  skipped: [],
});

function setup(
  fetchPrefill: (projectId: string, documentId?: string) => Promise<SampleRequestQuotationPrefill>,
  { enabled = true, initial }: { enabled?: boolean; initial?: Partial<FormState> } = {},
) {
  return renderHook(
    ({ projectId }: { projectId: string }) => {
      const [state, setState] = useState<FormState>({
        ...EMPTY_FORM,
        lines: [blankLine()],
        ...initial,
        project_id: projectId,
      });
      const patch = (p: Partial<FormState>) => setState((s) => ({ ...s, ...p }));
      const prefill = useSampleRequestPrefill({ enabled, projectId, state, patch, fetchPrefill });
      return { state, setState, ...prefill };
    },
    { initialProps: { projectId: '' } },
  );
}

const codes = (s: FormState) => s.lines.map((l) => l.product_id);

describe('useSampleRequestPrefill', () => {
  it('SFQ-20: setting the project fills the rows from its quotation', async () => {
    const fetchPrefill = vi.fn(async (pid: string) => quote(`doc-${pid}`, 'A', 'B'));
    const { result, rerender } = setup(fetchPrefill);
    expect(fetchPrefill).not.toHaveBeenCalled();

    rerender({ projectId: 'p1' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-A', 'id-B']));
    expect(fetchPrefill).toHaveBeenCalledWith('p1', undefined);
    expect(result.current.state.quotation_document_id).toBe('doc-p1');
    expect(result.current.documents.map((d) => d.id)).toEqual(['doc-p1', 'doc-other']);
  });

  it('SFQ-21: editing an existing draft never pre-fills', async () => {
    const fetchPrefill = vi.fn(async () => quote('doc', 'A'));
    const { result, rerender } = setup(fetchPrefill, { enabled: false });
    rerender({ projectId: 'p1' });
    await act(async () => {});
    expect(fetchPrefill).not.toHaveBeenCalled();
    expect(codes(result.current.state)).toEqual(['']);
  });

  it('SFQ-22: a new project replaces untouched pre-filled rows', async () => {
    const fetchPrefill = vi.fn(async (pid: string) =>
      pid === 'p1' ? quote('d1', 'A', 'B') : quote('d2', 'C'),
    );
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-A', 'id-B']));

    rerender({ projectId: 'p2' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-C']));
    expect(result.current.state.quotation_document_id).toBe('d2');
  });

  it('SFQ-22: a new project keeps rows the person changed and drops the source', async () => {
    const fetchPrefill = vi.fn(async (pid: string) =>
      pid === 'p1' ? quote('d1', 'A', 'B') : quote('d2', 'C'),
    );
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-A', 'id-B']));

    act(() => {
      result.current.setState((s) => ({ ...s, lines: s.lines.slice(1) }));
    });
    rerender({ projectId: 'p2' });
    await waitFor(() => expect(fetchPrefill).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(codes(result.current.state)).toEqual(['id-B']);
    expect(result.current.state.quotation_document_id).toBe('');
    expect(result.current.state.quotation_issue_id).toBe('');
  });

  it('SFQ-22: clearing the project keeps the rows and drops the source', async () => {
    const fetchPrefill = vi.fn(async () => quote('d1', 'A'));
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-A']));

    rerender({ projectId: '' });
    await waitFor(() => expect(result.current.state.quotation_document_id).toBe(''));
    expect(codes(result.current.state)).toEqual(['id-A']);
    expect(result.current.documents).toEqual([]);
  });

  it('SFQ-24: picking another quotation refills untouched rows from it', async () => {
    const fetchPrefill = vi.fn(async (_pid: string, docId?: string) =>
      docId === 'doc-other' ? { ...quote('doc-other', 'Z'), document_id: 'doc-other' } : quote('d1', 'A'),
    );
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-A']));

    act(() => result.current.pickDocument('doc-other'));
    await waitFor(() => expect(codes(result.current.state)).toEqual(['id-Z']));
    expect(fetchPrefill).toHaveBeenLastCalledWith('p1', 'doc-other');
    expect(result.current.documentId).toBe('doc-other');
  });

  it('a failed read leaves the form as it is', async () => {
    const fetchPrefill = vi.fn(async () => {
      throw new Error('boom');
    });
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(fetchPrefill).toHaveBeenCalled());
    await act(async () => {});
    expect(codes(result.current.state)).toEqual(['']);
    expect(result.current.note).toBeNull();
  });

  it('review B1: a loaded draft that moves to another project drops its recorded quotation', async () => {
    const fetchPrefill = vi.fn(async () => quote('d1', 'A'));
    const { result, rerender } = renderHook(
      ({ projectId }: { projectId: string }) => {
        const [state, setState] = useState<FormState>({
          ...EMPTY_FORM,
          lines: [{ ...blankLine(), product_id: 'id-A', label: 'A' }],
          quotation_document_id: 'd-saved',
          quotation_issue_id: 'i-saved',
          project_id: 'p-saved',
        });
        const patch = (p: Partial<FormState>) => setState((s) => ({ ...s, ...p }));
        const prefill = useSampleRequestPrefill({
          enabled: false,
          projectId: projectId || state.project_id,
          state,
          patch,
          fetchPrefill,
        });
        return { state, ...prefill };
      },
      { initialProps: { projectId: '' } },
    );
    await act(async () => {});
    expect(result.current.state.quotation_document_id).toBe('d-saved');

    rerender({ projectId: 'p-other' });
    await waitFor(() => expect(result.current.state.quotation_document_id).toBe(''));
    expect(result.current.state.quotation_issue_id).toBe('');
    expect(codes(result.current.state)).toEqual(['id-A']);
    expect(fetchPrefill).not.toHaveBeenCalled();
  });

  it('review S2: a project change drops the old source even if the new read fails', async () => {
    let fail = false;
    const fetchPrefill = vi.fn(async () => {
      if (fail) throw new Error('down');
      return quote('d1', 'A');
    });
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(result.current.state.quotation_document_id).toBe('d1'));

    fail = true;
    rerender({ projectId: 'p2' });
    await waitFor(() => expect(fetchPrefill).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(result.current.state.quotation_document_id).toBe('');
  });

  it('review S3: once the rows are edited the quotation picker is offered no more', async () => {
    const fetchPrefill = vi.fn(async () => quote('d1', 'A', 'B'));
    const { result, rerender } = setup(fetchPrefill);
    rerender({ projectId: 'p1' });
    await waitFor(() => expect(result.current.documents).toHaveLength(2));

    act(() => {
      result.current.setState((s) => ({ ...s, lines: s.lines.slice(1) }));
    });
    expect(result.current.documents).toEqual([]);
  });
});

