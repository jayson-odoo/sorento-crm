import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/myDownloadsService', () => ({
  fetchDownloadUrl: vi.fn(),
  downloadFilePath: (id: string) => `/api/v1/downloads/${id}/file`,
}));

// The preview modal is the REAL one - the claim is that this row hands it a usable URL - but its
// carousel wrapper reaches for IntersectionObserver/matchMedia/ResizeObserver, none of which
// jsdom has. Stubbed the same way AttachmentPreviewModal's own specs stub it, so the slide
// rendering under test still runs.
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
}));

import { toast } from 'sonner';
import { fetchDownloadUrl, type MyDownload } from '@/services/myDownloadsService';
import { DownloadRow } from './DownloadRow';

const mockFetchUrl = fetchDownloadUrl as unknown as ReturnType<typeof vi.fn>;

/**
 * The row body, which is the click-to-download surface. Queried by its title rather than by
 * role alone because a ready row also carries explicit Preview and Download controls beside it,
 * so "the only button" stopped being an unambiguous description of it.
 */
const rowBody = () => screen.getByTitle('Click to download');

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
    fireEvent.click(rowBody());
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
    fireEvent.click(rowBody());
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

  it('names the two quotation export kinds', () => {
    // A row whose kind the map does not know falls back to the raw key, which reads as a bug to
    // whoever opens the drawer. Both new kinds have to be in it.
    render(<DownloadRow row={row({ kind: 'quotation_pdf', filename: null })} />);
    expect(screen.getAllByText('Quotation PDF').length).toBeGreaterThan(0);
    render(<DownloadRow row={row({ kind: 'quotation_xlsx', filename: null })} />);
    expect(screen.getAllByText('Quotation Excel').length).toBeGreaterThan(0);
  });

  describe('preview', () => {
    it('opens the shared previewer on the resolved URL, alongside the download', async () => {
      // Preview is an ADDITION: the same row still downloads. What it resolves is both URLs the
      // previewer needs - the signed one an <iframe>/<img> can load itself, and the
      // same-origin /file path it reads spreadsheet bytes and saves through (a presigned URL is
      // cross-origin and sends no CORS headers, so fetching it fails).
      mockFetchUrl.mockResolvedValue({
        url: 'https://cdn/quotation.pdf',
        filename: 'quotation-SRT-Q-2026-0141-R1.pdf',
      });
      render(<DownloadRow row={row({ kind: 'quotation_pdf' })} />);

      fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));

      await waitFor(() => expect(mockFetchUrl).toHaveBeenCalledWith('d1'));
      // The previewer is open on the file, named after it, and did NOT open a tab.
      const dialog = await screen.findByRole('dialog');
      expect(
        within(dialog).getByText('quotation-SRT-Q-2026-0141-R1.pdf'),
      ).toBeInTheDocument();
      expect(dialog.querySelector('iframe')).toHaveAttribute(
        'src',
        'https://cdn/quotation.pdf',
      );
      expect(window.open).not.toHaveBeenCalled();
    });

    it('toasts rather than opening an empty previewer when the URL cannot be resolved', async () => {
      mockFetchUrl.mockRejectedValue(new Error('Download is not ready (status: processing)'));
      render(<DownloadRow row={row()} />);

      fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));

      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith('Download is not ready (status: processing)'),
      );
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('offers no preview on a row that is not ready', () => {
      // There is nothing to preview yet, and a control that can only resolve to a 409 is worse
      // than no control.
      render(<DownloadRow row={row({ status: 'processing' })} />);
      expect(screen.queryByRole('button', { name: /^Preview/ })).toBeNull();

      render(<DownloadRow row={row({ status: 'failed', error: 'boom' })} />);
      expect(screen.queryByRole('button', { name: /^Preview/ })).toBeNull();
    });

    it('keeps an explicit Download control beside Preview', async () => {
      // The row body is still click-to-download, but a discoverable button matters: somebody
      // who sees Preview will look for its pair rather than guess that the row is clickable.
      mockFetchUrl.mockResolvedValue({ url: 'https://cdn/x.pdf' });
      render(<DownloadRow row={row()} />);

      fireEvent.click(screen.getByRole('button', { name: /^Download/ }));

      await waitFor(() => expect(window.open).toHaveBeenCalledWith(
        'https://cdn/x.pdf',
        '_blank',
        'noopener,noreferrer',
      ));
      expect(screen.queryByRole('dialog')).toBeNull();
    });
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
