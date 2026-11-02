import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/services/uploadActivityService', () => ({
  fetchUploadActivity: vi.fn(),
}));

import { fetchUploadActivity } from '@/services/uploadActivityService';
import { UploadManagerProvider } from './UploadManagerContext';
import type { UploadActivitySession } from './types';
import { useUploadActivity } from './useUploadActivity';

/** The bell hook itself, not only pollCap.ts: a session stuck `processing` past the cap stops
 *  the 5 s poll; a fresh one keeps it (INTEGRATION-LOG-INDEXES, AC-5). */

function processing(minutesAgo: number, type: UploadActivitySession['session_type'] = 'single'): UploadActivitySession {
  return {
    session_id: `s-${type}-${minutesAgo}`,
    session_type: type,
    title: 'brochure.pdf',
    // Naive UTC, as the backend sends it.
    started_at: new Date(Date.now() - minutesAgo * 60_000).toISOString().replace('Z', ''),
    finished_at: null,
    status: 'processing',
    aggregate: { total: 1, uploading: 0, processing: 1, linked: 0, unlinked: 0, failed: 0 },
    files: [],
    import_job_id: null,
    needs_action: false,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <UploadManagerProvider>{children}</UploadManagerProvider>
    </QueryClientProvider>
  );
}

async function callsAfter(sessions: UploadActivitySession[]): Promise<number> {
  vi.mocked(fetchUploadActivity).mockResolvedValue({ sessions });
  const { result } = renderHook(() => useUploadActivity(), { wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(16_000);
  });
  return vi.mocked(fetchUploadActivity).mock.calls.length;
}

describe('useUploadActivity polling cap', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchUploadActivity).mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('stops polling when the only processing upload is older than 30 minutes', async () => {
    expect(await callsAfter([processing(7 * 24 * 60)])).toBe(1);
  });

  it('keeps polling every 5 s for a fresh processing upload', async () => {
    expect(await callsAfter([processing(2)])).toBeGreaterThanOrEqual(3);
  });

  it('keeps polling an import job past the cap (it reports its own progress)', async () => {
    expect(await callsAfter([processing(90, 'import_job')])).toBeGreaterThanOrEqual(3);
  });
});
