/**
 * FORMS-LAST-ACTIVITY browser-pass fix: the workflow submissions grid query with no sort chosen asks for
 * last activity newest first, never oldest first.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const post = vi.hoisted(() => vi.fn());
vi.mock('@/lib/list-query/listQueryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/list-query/listQueryService')>();
  return { ...actual, postListQuerySearch: (...a: unknown[]) => post(...a) };
});

import { useWorkflowSubmissionsGridQuery } from './useWorkflowForms';

const run = async (sorting: { id: string; desc: boolean }[]) => {
  post.mockReset();
  post.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  renderHook(
    () =>
      useWorkflowSubmissionsGridQuery({
        pageIndex: 0, pageSize: 25, sorting, searchQuery: '', advancedFilter: null, scopeDefinitionId: '__all', quickStateCode: '',
      }),
    { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> },
  );
  await waitFor(() => expect(post).toHaveBeenCalled());
  return post.mock.calls[0][0] as Record<string, unknown>;
};

describe('useWorkflowSubmissionsGridQuery - empty sorting', () => {
  it('sends last_activity_at descending', async () => {
    const body = await run([]);
    expect(body.sort).toBe('last_activity_at');
    expect(body.dir).toBe('desc');
  });

  it('keeps an explicit ascending sort', async () => {
    const body = await run([{ id: 'last_activity_at', desc: false }]);
    expect(body.dir).toBe('asc');
  });
});
