/**
 * PROJECT-RELATED-RECORDS fix round 3 (browser pass 1 D3): after a record's Project is changed on its
 * own page, its History (the audit list) and the projects' Related tabs refresh without a reload.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/services/recordProjectService', () => ({ setRecordProject: vi.fn().mockResolvedValue(undefined) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useSetRecordProject } from './useSetRecordProject';

describe('useSetRecordProject', () => {
  it('D3 refreshes the History and the Related tabs', async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSetRecordProject('stock_inquiry', 'si-1'), {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    });
    await result.current.mutateAsync('p-2');
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['audit-logs']));
    expect(keys).toContain(JSON.stringify(['project-related-records']));
  });
});
