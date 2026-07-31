import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/myDownloadsService', () => ({
  fetchDownloadUrl: vi.fn(),
}));

import { toast } from 'sonner';
import { fetchDownloadUrl, type MyDownload } from '@/services/myDownloadsService';
import { DownloadRow } from './DownloadRow';

const mockFetchUrl = fetchDownloadUrl as unknown as ReturnType<typeof vi.fn>;

function row(overrides: Partial<MyDownload> = {}): MyDownload {
  return {
    id: 'd1',
    kind: 'complaint_pdf',
    status: 'ready',
    filename: 'complaint-CMP26-0009.pdf',
    created_at: '2026-06-12T04:14:00Z',
    ...overrides,
  };
}

describe('DownloadRow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', vi.fn());
  });

  it('renders filename and Ready status', () => {
    render(<DownloadRow row={row()} />);
    expect(screen.getByText('complaint-CMP26-0009.pdf')).toBeInTheDocument();
    expect(screen.getByText(/Ready/i)).toBeInTheDocument();
  });

  it('ready row is clickable and downloads via resolved URL', async () => {
    mockFetchUrl.mockResolvedValue({ url: 'https://cdn/x.pdf' });
    render(<DownloadRow row={row()} />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(mockFetchUrl).toHaveBeenCalledWith('d1'));
    expect(window.open).toHaveBeenCalledWith(
      'https://cdn/x.pdf',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('toasts on download failure', async () => {
    mockFetchUrl.mockRejectedValue(new Error('Download not ready'));
    render(<DownloadRow row={row()} />);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Download not ready'));
    expect(window.open).not.toHaveBeenCalled();
  });

  it('non-ready row is inert (no button role, no download)', () => {
    render(<DownloadRow row={row({ status: 'processing' })} />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText(/Preparing/i)).toBeInTheDocument();
  });

  it('failed row shows error and is inert', () => {
    render(<DownloadRow row={row({ status: 'failed', error: 'boom' })} />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('labels a promotions_pdf download "Promotions PDF"', () => {
    // No filename → the kind label is the visible title AND the subtext.
    render(<DownloadRow row={row({ kind: 'promotions_pdf', filename: null })} />);
    expect(screen.getAllByText('Promotions PDF').length).toBeGreaterThan(0);
  });
});

describe('DownloadRow timestamp', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a naive-UTC created_at in Malaysia time (UTC+8)', () => {
    // The API serializes created_at as naive UTC - no trailing Z - and only the
    // string path of formatDateTimeInMalaysia appends it. Wrapping the value in
    // new Date() first makes the browser read it as local time, printing the UTC
    // digits 8 hours early (03:18 instead of 11:18).
    render(<DownloadRow row={row({ created_at: '2026-07-31T03:18:00' })} />);

    expect(screen.getByText(/31\/07\/2026, 11:18 am/)).toBeInTheDocument();
  });

  it('still handles an explicitly UTC-marked created_at', () => {
    render(<DownloadRow row={row({ created_at: '2026-07-31T03:18:00Z' })} />);

    expect(screen.getByText(/31\/07\/2026, 11:18 am/)).toBeInTheDocument();
  });

  it('renders no timestamp when created_at is absent', () => {
    render(<DownloadRow row={row({ created_at: undefined })} />);
    expect(screen.queryByText(/2026/)).toBeNull();
  });
});
