import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/services/uploadActivityService', () => ({
  fetchUploadActivity: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { fetchUploadActivity } from '@/services/uploadActivityService';
import { clearDismissed } from './dismissedSessions';
import { UploadActivityDrawer } from './UploadActivityDrawer';
import { UploadActivityIcon } from './UploadActivityIcon';
import { UploadManagerProvider } from './UploadManagerContext';
import type { UploadActivitySession } from './types';

/** The 19 Aug 2026 production row, verbatim. */
const RQ_ERROR =
  'Moved to FailedJobRegistry, due to AbandonedJobError, at 2026-08-19 03:28:40.362670+00:00';

const FAILED_IMPORT: UploadActivitySession = {
  session_id: 'job-0086',
  session_type: 'import_job',
  title: 'SPO-202608-0086.xlsx',
  started_at: new Date(Date.now() - 3_600_000).toISOString(),
  finished_at: new Date().toISOString(),
  status: 'failed',
  aggregate: { total: 0, uploading: 0, processing: 0, linked: 0, unlinked: 0, failed: 0 },
  files: [],
  import_job_id: 'job-0086',
  needs_action: true,
  job_type: 'spo_import',
  total_rows: 0,
  job_error: RQ_ERROR,
};

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UploadManagerProvider>
        <UploadActivityIcon />
        <UploadActivityDrawer />
      </UploadManagerProvider>
    </QueryClientProvider>,
  );
}

describe('upload activity badge dismissal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    clearDismissed();
    vi.mocked(fetchUploadActivity).mockResolvedValue({ sessions: [FAILED_IMPORT] });
  });

  it('badges a failed import, and clears it once the drawer has been opened', async () => {
    renderShell();

    const icon = await screen.findByRole('button', { name: /upload/i });
    // needs_action === true, so the badge nags.
    await waitFor(() => expect(screen.getByText('1')).toBeTruthy());

    fireEvent.click(icon);

    // Opening is the dismissal — the row stays in the drawer, the badge does not.
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
    expect(screen.getByText('SPO-202608-0086.xlsx')).toBeTruthy();
  });

  it('keeps the dismissal after a remount, the way a page reload would', async () => {
    const first = renderShell();
    const icon = await screen.findByRole('button', { name: /upload/i });
    await waitFor(() => expect(screen.getByText('1')).toBeTruthy());
    fireEvent.click(icon);
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
    first.unmount();

    renderShell();
    await screen.findByRole('button', { name: /upload activity/i });
    // The badge must not come back on the next page load.
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
  });

  it('shows the whole RQ failure string rather than cutting it mid-timestamp', async () => {
    renderShell();
    fireEvent.click(await screen.findByRole('button', { name: /upload/i }));
    const summary = await screen.findByText(RQ_ERROR);
    // `truncate` clips to one line and loses the reason; the row wraps instead
    // and carries the full text on hover.
    expect(summary.className).not.toContain('truncate');
    expect(summary.className).toContain('break-words');
    expect(summary.getAttribute('title')).toBe(RQ_ERROR);
  });
});
