import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/myDownloadsService', () => ({
  ENTITY_DOWNLOADS_QUERY_KEY: ['entity-downloads'],
  fetchDownloadsForEntity: vi.fn(),
  fetchDownloadUrl: vi.fn(),
  downloadFilePath: (id: string) => `/api/v1/downloads/${id}/file`,
}));

// The rows inside the modal render the shared preview modal, whose carousel wrapper needs
// browser layout APIs jsdom lacks. Stubbed so this file stays about the chip and its modal.
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
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

  it('serves a quotation revision with no complaint-shaped copy anywhere', async () => {
    // The component was written for complaints and hard-coded "this complaint" into its tooltip
    // and its empty state. Reused on a quotation that reads as somebody else's screen, so the
    // copy is now driven by the label it was given.
    mockFetchEntity.mockResolvedValue({ downloads: [] });
    renderBtn({
      entityType: 'quotation_issue',
      entityId: 'i9',
      label: 'SRT/Q/2026/0141 (R2)',
      count: undefined,
    });

    await waitFor(() =>
      expect(mockFetchEntity).toHaveBeenCalledWith('quotation_issue', 'i9', 100),
    );
    expect(
      screen.getByTitle('View downloads for SRT/Q/2026/0141 (R2)'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /0/ }));
    expect(await screen.findByText(/Downloads · SRT\/Q\/2026\/0141 \(R2\)/)).toBeInTheDocument();
    expect(screen.getByText(/No downloads yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/complaint/i)).toBeNull();
  });

  it('lists a queued quotation export while it is still preparing', async () => {
    // The chip is the collection point, so it has to show the row from the moment the export is
    // queued - not only once the worker has finished. A chip that stayed at 0 for ten seconds
    // reads as "the button did nothing", which is the bug the whole async change was made for.
    mockFetchEntity.mockResolvedValue({
      downloads: [
        {
          id: 'd9',
          kind: 'quotation_pdf',
          status: 'pending',
          filename: 'quotation-SRT-Q-2026-0141-R2.pdf',
          created_at: '2026-08-05T02:00:00Z',
        },
      ],
    });
    renderBtn({ entityType: 'quotation_issue', entityId: 'i9', count: undefined });

    await waitFor(() => expect(screen.getByRole('button', { name: /1/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /1/ }));

    expect(await screen.findByText('quotation-SRT-Q-2026-0141-R2.pdf')).toBeInTheDocument();
    expect(screen.getByText(/Queued/i)).toBeInTheDocument();
    // Nothing to open yet, so neither control is offered.
    expect(screen.queryByRole('button', { name: /^Preview/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Download/ })).toBeNull();
  });
});
