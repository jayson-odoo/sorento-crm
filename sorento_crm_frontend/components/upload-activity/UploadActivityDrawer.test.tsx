import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/services/uploadActivityService', () => ({
  fetchUploadActivity: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { fetchUploadActivity } from '@/services/uploadActivityService';
import { UploadActivityDrawer } from './UploadActivityDrawer';
import { UploadManagerProvider, useUploadManager } from './UploadManagerContext';
import type { UploadActivitySession } from './types';

function renderDrawer(initialOpen = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Inner() {
    const { setDrawerOpen } = useUploadManager();
    React.useEffect(() => {
      if (initialOpen) setDrawerOpen(true);
    }, [setDrawerOpen]);
    return <UploadActivityDrawer />;
  }
  return render(
    <QueryClientProvider client={qc}>
      <UploadManagerProvider>
        <Inner />
      </UploadManagerProvider>
    </QueryClientProvider>,
  );
}

const SESSION_LINKED: UploadActivitySession = {
  session_id: 's-linked',
  session_type: 'single',
  title: 'receipt.pdf',
  started_at: new Date(Date.now() - 60_000).toISOString(),
  finished_at: new Date().toISOString(),
  status: 'linked',
  aggregate: { total: 1, uploading: 0, processing: 0, linked: 1, unlinked: 0, failed: 0 },
  files: [
    {
      client_id: 'a-linked',
      attachment_id: 'a-linked',
      filename: 'receipt.pdf',
      status: 'linked',
      summary: '',
      linked: [
        { entity_type: 'product', entity_id: 'p1', display_name: 'CBMC5570', matched_by: 'token' },
      ],
      unlinked_reasons: [],
      error_code: null,
      error_message: null,
      integration_log_id: 'log-1',
      last_updated_at: new Date().toISOString(),
    },
  ],
  import_job_id: null,
  needs_action: false,
};

describe('UploadActivityDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the empty state when the BE returns no sessions', async () => {
    (fetchUploadActivity as any).mockResolvedValue({ sessions: [] });
    renderDrawer(true);
    await waitFor(() => {
      expect(screen.getByText(/No uploads yet/i)).toBeTruthy();
    });
  });

  it('renders a single linked session with its file summary', async () => {
    (fetchUploadActivity as any).mockResolvedValue({ sessions: [SESSION_LINKED] });
    renderDrawer(true);
    await waitFor(() => {
      expect(screen.getByText('receipt.pdf')).toBeTruthy();
    });
    // Status badge for the session header.
    expect(screen.getAllByText(/Linked/i).length).toBeGreaterThan(0);
  });
});
