/**
 * TAG-BRAND-CLASS (browser pass finding): applying tag settings writes the contact's brands and
 * allowed item classes, so the contact page's Brands card query must refetch; before, it kept
 * showing "All classes" until a reload.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/contactTagService', () => ({
  applyContactTagSettings: vi.fn().mockResolvedValue({ dry_run: false, results: [], counts: {} }),
  applyTagSettings: vi.fn().mockResolvedValue({ dry_run: false, results: [], counts: {} }),
}));

import { useApplyTagSettings } from './useContactTags';

describe('useApplyTagSettings', () => {
  it('a real apply invalidates the contact Brands card query', async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useApplyTagSettings({ contactIds: ['c1'] }), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(false);
    });
    const keys = spy.mock.calls.map(([f]) => JSON.stringify((f as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['contact-brand-scope']));
  });
});
