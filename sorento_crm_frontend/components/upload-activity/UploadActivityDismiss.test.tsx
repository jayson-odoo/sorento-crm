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

/** The real production shape that pinned the badge: an attachment with no
 *  integration_log row at all, so the feed calls it "processing" for ever. */
const STUCK_PROCESSING: UploadActivitySession = {
  session_id: 'att-flyer-1',
  session_type: 'single',
  title: 'flyer_sample page 1 banner.jpg',
  started_at: new Date(Date.now() - 7 * 86_400_000).toISOString(),
  finished_at: null,
  status: 'processing',
  aggregate: { total: 1, uploading: 0, processing: 1, linked: 0, unlinked: 0, failed: 0 },
  files: [
    {
      client_id: 'att-flyer-1',
      attachment_id: 'att-flyer-1',
      filename: 'flyer_sample page 1 banner.jpg',
      status: 'processing',
      summary: '',
      linked: [],
      unlinked_reasons: [],
      error_code: null,
      error_message: null,
      integration_log_id: null,
      last_updated_at: new Date(Date.now() - 7 * 86_400_000).toISOString(),
    },
  ],
  import_job_id: null,
  needs_action: false,
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

describe('dismissing a session stuck on Processing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    clearDismissed();
    vi.mocked(fetchUploadActivity).mockResolvedValue({ sessions: [STUCK_PROCESSING] });
  });

  it('keeps badging on drawer open — auto-marking must not silence in-flight', async () => {
    renderShell();
    const icon = await screen.findByRole('button', { name: /upload/i });
    await waitFor(() => expect(screen.getByText('1')).toBeTruthy());
    fireEvent.click(icon);
    // Opening is NOT enough: this session is not needs_action, and a live upload
    // that later fails must still be able to raise the badge.
    await waitFor(() => expect(screen.getByText('flyer_sample page 1 banner.jpg')).toBeTruthy());
    expect(screen.getByText('1')).toBeTruthy();
  });

  it('clears on "Dismiss all", which is the only way out for this state', async () => {
    renderShell();
    fireEvent.click(await screen.findByRole('button', { name: /upload/i }));
    fireEvent.click(await screen.findByRole('button', { name: /dismiss all/i }));
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
    // The row itself stays listed — dismissing un-nags, it does not hide.
    expect(screen.getByText('flyer_sample page 1 banner.jpg')).toBeTruthy();
  });

  it('badges again if the dismissed session changes state', async () => {
    const first = renderShell();
    fireEvent.click(await screen.findByRole('button', { name: /upload/i }));
    fireEvent.click(await screen.findByRole('button', { name: /dismiss all/i }));
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
    first.unmount();

    // n8n finally answers, with an error. The stored key was written against
    // `processing`, so it no longer matches and the badge is entitled to nag.
    vi.mocked(fetchUploadActivity).mockResolvedValue({
      sessions: [{ ...STUCK_PROCESSING, status: 'failed', needs_action: true }],
    });
    renderShell();
    await waitFor(() => expect(screen.getByText('1')).toBeTruthy());
  });
});
