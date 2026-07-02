import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from './AttachmentPreviewModal';

// apiFetch is only used by the Excel branch (same-origin byte fetch).
const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

// embla-carousel needs layout APIs jsdom lacks; stub the wrapper so slide
// rendering (the logic under test) runs without a real carousel engine.
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
}));

const img: AttachmentPreviewItem = {
  id: 'a',
  name: 'photo.jpg',
  url: 'https://cdn.example.com/photo.jpg',
  downloadUrl: '/api/v1/resource-management/attachments/a/download',
};
const video: AttachmentPreviewItem = {
  id: 'b',
  name: 'clip.mp4',
  url: 'https://cdn.example.com/clip.mp4',
  downloadUrl: '/api/v1/resource-management/attachments/b/download',
};
const pdf: AttachmentPreviewItem = {
  id: 'c',
  name: 'doc.pdf',
  url: 'https://cdn.example.com/doc.pdf',
};
const other: AttachmentPreviewItem = {
  id: 'd',
  name: 'archive.zip',
  url: 'https://cdn.example.com/archive.zip',
  downloadUrl: '/api/v1/resource-management/attachments/d/download',
};

// embla-carousel touches matchMedia + ResizeObserver, absent in jsdom.
beforeEach(() => {
  apiFetchMock.mockReset();
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

describe('AttachmentPreviewModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <AttachmentPreviewModal open={false} onOpenChange={() => {}} items={[img]} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('photo.jpg')).toBeNull();
  });

  it('renders nothing with no items', () => {
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[]} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders an image via the cacheable CDN url + shows counter and download', () => {
    render(
      <AttachmentPreviewModal
        open
        onOpenChange={() => {}}
        items={[img, video]}
        startIndex={0}
      />,
    );
    const el = screen.getByAltText('photo.jpg') as HTMLImageElement;
    expect(el.tagName).toBe('IMG');
    expect(el.getAttribute('src')).toBe('https://cdn.example.com/photo.jpg');
    expect(el.getAttribute('loading')).toBe('lazy');
    expect(screen.getByText('1 / 2')).toBeTruthy();
    const dl = screen.getByRole('link', { name: /download/i }) as HTMLAnchorElement;
    expect(dl.getAttribute('href')).toBe(img.downloadUrl);
  });

  it('mounts a <video> for the active video slide', () => {
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[video]} />);
    const v = document.body.querySelector('video');
    expect(v).not.toBeNull();
    expect(v?.getAttribute('src')).toBe('https://cdn.example.com/clip.mp4');
  });

  it('mounts an <iframe> for the active pdf slide', () => {
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[pdf]} />);
    const frame = document.body.querySelector('iframe');
    expect(frame?.getAttribute('src')).toBe('https://cdn.example.com/doc.pdf');
  });

  it('shows a download fallback for unpreviewable types', () => {
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[other]} />);
    expect(screen.getByText(/no inline preview/i)).toBeTruthy();
  });

  it('fetches Excel bytes same-origin and renders a sheet table', async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    });
    // Stub the dynamically-imported xlsx module.
    vi.doMock('xlsx', () => ({
      read: () => ({ SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } }),
      utils: {
        sheet_to_json: () => [
          ['Name', 'Qty'],
          ['Widget', '5'],
        ],
      },
    }));
    const xlsx: AttachmentPreviewItem = {
      id: 'e',
      name: 'list.xlsx',
      url: 'https://cdn.example.com/list.xlsx',
      downloadUrl: '/api/v1/resource-management/attachments/e/download',
    };
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[xlsx]} />);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith(xlsx.downloadUrl));
    await waitFor(() => expect(screen.getByText('Widget')).toBeTruthy());
    expect(screen.getByText('Qty')).toBeTruthy();
  });
});
