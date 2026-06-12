import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/myDownloadsService', () => ({
  fetchDownloadsForEntity: vi.fn(),
  fetchDownloadUrl: vi.fn(),
}));

import {
  fetchDownloadsForEntity,
  fetchDownloadUrl,
  type MyDownload,
} from '@/services/myDownloadsService';
import { EntityDownloadsButton } from './EntityDownloadsButton';

const mockFetchEntity = fetchDownloadsForEntity as unknown as ReturnType<typeof vi.fn>;
const mockFetchUrl = fetchDownloadUrl as unknown as ReturnType<typeof vi.fn>;

function renderBtn(props: Partial<React.ComponentProps<typeof EntityDownloadsButton>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EntityDownloadsButton entityType="complaint" entityId="c1" label="CMP26-0009" {...props} />
    </QueryClientProvider>,
  );
}

const readyRow: MyDownload = {
  id: 'd1',
  kind: 'complaint_pdf',
  status: 'ready',
  filename: 'complaint-CMP26-0009.pdf',
  created_at: '2026-06-12T04:14:00Z',
};

describe('EntityDownloadsButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', vi.fn());
  });

  it('shows the provided count without fetching on mount', () => {
    renderBtn({ count: 4 });
    expect(screen.getByRole('button', { name: /4/ })).toBeInTheDocument();
    expect(mockFetchEntity).not.toHaveBeenCalled();
  });

  it('opens the modal and lists this entity downloads, click-to-download', async () => {
    mockFetchEntity.mockResolvedValue({ downloads: [readyRow] });
    mockFetchUrl.mockResolvedValue({ url: 'https://cdn/x.pdf' });
    renderBtn({ count: 1 });

    fireEvent.click(screen.getByRole('button', { name: /1/ }));

    // modal title includes the label
    await waitFor(() => expect(screen.getByText(/Downloads · CMP26-0009/)).toBeInTheDocument());
    await waitFor(() => expect(mockFetchEntity).toHaveBeenCalledWith('complaint', 'c1', 100));

    const fileRow = await screen.findByText('complaint-CMP26-0009.pdf');
    fireEvent.click(fileRow);
    await waitFor(() => expect(mockFetchUrl).toHaveBeenCalledWith('d1'));
    expect(window.open).toHaveBeenCalled();
  });

  it('shows empty state when no downloads', async () => {
    mockFetchEntity.mockResolvedValue({ downloads: [] });
    renderBtn({ count: 0 });
    fireEvent.click(screen.getByRole('button', { name: /0/ }));
    await waitFor(() => expect(screen.getByText(/No downloads yet/i)).toBeInTheDocument());
  });

  it('derives the count from the feed when no count prop is given', async () => {
    mockFetchEntity.mockResolvedValue({ downloads: [readyRow, { ...readyRow, id: 'd2' }] });
    renderBtn({ count: undefined });
    // fetched on mount; chip reflects feed length
    await waitFor(() => expect(screen.getByRole('button', { name: /2/ })).toBeInTheDocument());
  });
});
