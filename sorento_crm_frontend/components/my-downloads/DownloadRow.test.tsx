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
});
