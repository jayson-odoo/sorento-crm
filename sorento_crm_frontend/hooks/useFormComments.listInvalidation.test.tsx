/**
 * FORMS-LAST-ACTIVITY crew browser pass: a posted comment is activity, so the form's cached list
 * (and its detail) must refetch, or Back shows the old order until a reload.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/formCommentsService', () => ({
  addFormComment: vi.fn(async () => ({ comment: { id: 'cm1' }, delivery: 'queued' })),
  editFormComment: vi.fn(async () => ({})),
  listFormComments: vi.fn(async () => []),
}));

import { useAddFormComment, useEditFormComment } from './useFormComments';
import type { FormCommentKind } from '@/types/formComments';

const LIST_KEYS: Record<FormCommentKind, [string, string]> = {
  complaint: ['complaints', 'complaint'],
  stock_inquiry: ['stock-inquiries', 'stock-inquiry'],
  purchase_request: ['purchase-requests', 'purchase-request'],
  sponsorship_form: ['purchase-requests', 'purchase-request'],
  sample_request: ['sample-requests', 'sample-request'],
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}
const keys = (spy: ReturnType<typeof vi.spyOn>) => spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);

describe('posting a form comment refreshes the form list', () => {
  it.each(Object.keys(LIST_KEYS) as FormCommentKind[])('%s: list and detail keys are invalidated', async (kind) => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAddFormComment(kind, 'rec-1'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ body: 'hi', files: [] });
    });
    const [list, detail] = LIST_KEYS[kind];
    expect(keys(spy)).toContainEqual([list]);
    expect(keys(spy)).toContainEqual([detail]);
  });

  it('a reply (parentId) refreshes the list too', async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAddFormComment('complaint', 'rec-1'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ body: 'hi', files: [], parentId: 'p1' });
    });
    expect(keys(spy)).toContainEqual(['complaints']);
  });

  it('an edit does not move the list (an edit is not activity)', async () => {
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useEditFormComment('complaint', 'rec-1'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ commentId: 'c1', body: 'x' });
    });
    expect(keys(spy)).not.toContainEqual(['complaints']);
  });
});
