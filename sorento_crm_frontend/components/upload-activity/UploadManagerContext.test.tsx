import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { UploadManagerProvider, useUploadManager } from './UploadManagerContext';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <UploadManagerProvider>{children}</UploadManagerProvider>
    </QueryClientProvider>
  );
}

function makeFile(name = 'a.jpg'): File {
  return new File(['x'], name, { type: 'image/jpeg' });
}

describe('UploadManagerContext', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it('pushes an optimistic session, opens the drawer, and reconciles each POST', async () => {
    // Deferred promises let the assertion observe the initial `uploading`
    // state before the uploader resolves to `processing`.
    type Resolver = (v: { attachment_id: string }) => void;
    const resolvers: Resolver[] = [];
    const uploader = vi
      .fn<(f: File) => Promise<{ attachment_id: string }>>()
      .mockImplementation(() => new Promise<{ attachment_id: string }>((r) => resolvers.push(r)));

    const { result } = renderHook(() => useUploadManager(), { wrapper });

    let sessionId = '';
    act(() => {
      sessionId = result.current.startSession({
        files: [makeFile('a.jpg'), makeFile('b.jpg')],
        sessionType: 'multi',
        uploader,
      });
    });
    expect(sessionId).toBeTruthy();
    expect(result.current.state.isDrawerOpen).toBe(true);
    expect(result.current.state.sessions[sessionId].files).toHaveLength(2);
    expect(result.current.state.sessions[sessionId].files[0].status).toBe('uploading');

    // Resolve both POSTs.
    await act(async () => {
      resolvers[0]({ attachment_id: 'att-1' });
      resolvers[1]({ attachment_id: 'att-2' });
    });

    await waitFor(() => {
      const files = result.current.state.sessions[sessionId].files;
      expect(files.every((f) => f.status === 'processing')).toBe(true);
    });
    const files = result.current.state.sessions[sessionId].files;
    expect(files[0].attachment_id).toBe('att-1');
    expect(files[1].attachment_id).toBe('att-2');
    expect(uploader).toHaveBeenCalledTimes(2);
  });

  it('marks a file post_failed when the uploader rejects + retry replays the cached blob', async () => {
    const uploader = vi
      .fn<(f: File) => Promise<{ attachment_id: string }>>()
      .mockRejectedValueOnce(new Error('file too large'))
      .mockResolvedValueOnce({ attachment_id: 'att-99' });

    const { result } = renderHook(() => useUploadManager(), { wrapper });

    let sessionId = '';
    await act(async () => {
      sessionId = result.current.startSession({
        files: [makeFile('big.zip')],
        sessionType: 'single',
        uploader,
      });
    });

    await waitFor(() => {
      const f = result.current.state.sessions[sessionId].files[0];
      expect(f.status).toBe('post_failed');
      expect(f.error_code).toBe('POST_FAILED');
      expect(f.error_message).toBe('file too large');
    });

    // Retry uses the cached blob; uploader called again with the same File.
    await act(async () => {
      const f = result.current.state.sessions[sessionId].files[0];
      await result.current.retryFile(sessionId, f.client_id);
    });
    await waitFor(() => {
      const f = result.current.state.sessions[sessionId].files[0];
      expect(f.status).toBe('processing');
      expect(f.attachment_id).toBe('att-99');
    });
    expect(uploader).toHaveBeenCalledTimes(2);
  });

  it('keys an import_job session on the job id so the BE row replaces it', async () => {
    // The backend keys its own import_job session on `str(job.job_id)`, and the
    // drawer merges optimistic + backend rows by session_id. A random id here
    // shows the same import TWICE until a refresh drops the optimistic half.
    const { result } = renderHook(() => useUploadManager(), { wrapper });

    let sessionId = '';
    await act(async () => {
      sessionId = result.current.startSession({
        files: [makeFile('container-status-2026.xlsx')],
        sessionType: 'import_job',
        importJobId: 'job-abc-123',
        jobType: 'container_status',
        uploader: async () => ({ attachment_id: 'job-abc-123' }),
      });
    });

    expect(sessionId).toBe('job-abc-123');
    expect(result.current.state.sessions['job-abc-123']).toBeTruthy();
  });

  it('still keys an attachment batch on the upload batch id', () => {
    // uploadBatchId wins: that is what the backend groups attachment rows on.
    const { result } = renderHook(() => useUploadManager(), { wrapper });

    let sessionId = '';
    act(() => {
      sessionId = result.current.startSession({
        files: [makeFile('a.jpg')],
        sessionType: 'multi',
        uploadBatchId: 'batch-1',
        importJobId: 'job-should-lose',
        uploader: async () => ({ attachment_id: 'att-1' }),
      });
    });

    expect(sessionId).toBe('batch-1');
  });

  it('setDrawerOpen toggles drawer state', () => {
    const { result } = renderHook(() => useUploadManager(), { wrapper });
    expect(result.current.state.isDrawerOpen).toBe(false);
    act(() => result.current.setDrawerOpen(true));
    expect(result.current.state.isDrawerOpen).toBe(true);
    act(() => result.current.setDrawerOpen(false));
    expect(result.current.state.isDrawerOpen).toBe(false);
  });
});
