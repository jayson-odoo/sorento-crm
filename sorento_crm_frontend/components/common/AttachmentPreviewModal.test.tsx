import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
    expect(screen.getByRole('button', { name: /download/i })).toBeTruthy();
  });

  it('lets the user type a zoom percentage', () => {
    render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[img]} />);
    const input = screen.getByLabelText('Zoom percentage') as HTMLInputElement;
    expect(input.value).toBe('100');
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

  // fetchBytes override (new optional prop) - token-authenticated surfaces
  // (e.g. the contact portal) have no NextAuth JWT session, so apiFetch would
  // 401 there. Existing (protected) callers omit the prop and must keep using
  // apiFetch exactly as before (covered above).
  describe('fetchBytes override', () => {
    it('uses the custom fetchBytes for the Excel slide instead of apiFetch', async () => {
      vi.doMock('xlsx', () => ({
        read: () => ({ SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } }),
        utils: {
          sheet_to_json: () => [
            ['Name', 'Qty'],
            ['Widget', '5'],
          ],
        },
      }));
      const customFetchBytes = vi.fn().mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      });
      const xlsx: AttachmentPreviewItem = {
        id: 'e',
        name: 'list.xlsx',
        url: 'https://cdn.example.com/list.xlsx',
        downloadUrl: '/portal/attachments/e/download',
      };
      render(
        <AttachmentPreviewModal
          open
          onOpenChange={() => {}}
          items={[xlsx]}
          fetchBytes={customFetchBytes}
        />,
      );
      await waitFor(() => expect(customFetchBytes).toHaveBeenCalledWith(xlsx));
      await waitFor(() => expect(screen.getByText('Widget')).toBeTruthy());
      expect(apiFetchMock).not.toHaveBeenCalled();
    });

    it('uses the custom fetchBytes for the Download button instead of apiFetch', async () => {
      const customFetchBytes = vi.fn().mockResolvedValue({
        ok: true,
        blob: async () => new Blob(['x']),
      });
      render(
        <AttachmentPreviewModal
          open
          onOpenChange={() => {}}
          items={[img]}
          fetchBytes={customFetchBytes}
        />,
      );
      const createObjectURL = vi.fn().mockReturnValue('blob:mock');
      const revokeObjectURL = vi.fn();
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = createObjectURL;
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeObjectURL;

      screen.getByRole('button', { name: /download/i }).click();

      await waitFor(() => expect(customFetchBytes).toHaveBeenCalledWith(img));
      expect(apiFetchMock).not.toHaveBeenCalled();
    });
  });

  // AC-N6 (PLAN-scm-loading-plan-lines-feedback-12sep.md): a supplier sheet like the
  // Container Status workbook is 60+ rows deep; Ms Tee needs to find one row by typing,
  // the same move the loading plan's own Lines table search box gives her (AC-N3).
  describe('search in sheet (AC-N6)', () => {
    const sheetXlsx: AttachmentPreviewItem = {
      id: 'f',
      name: 'catalogue.xlsx',
      url: 'https://cdn.example.com/catalogue.xlsx',
      downloadUrl: '/api/v1/resource-management/attachments/f/download',
    };

    function mockSheet() {
      apiFetchMock.mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      });
      vi.doMock('xlsx', () => ({
        read: () => ({ SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } }),
        utils: {
          sheet_to_json: () => [
            ['SRTWC286-SH-150', 'S', '150'],
            ['RPACC', 'R', '1'],
            ['CWCY605', 'C', '2'],
          ],
        },
      }));
    }

    it('shows a "Search in sheet" box once the sheet has loaded', async () => {
      mockSheet();
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[sheetXlsx]} />);
      await waitFor(() => expect(screen.getByText('RPACC')).toBeTruthy());

      expect(screen.getByPlaceholderText('Search in sheet')).toBeTruthy();
      // No filter typed yet: the plain preview, no "N of M rows" count.
      expect(screen.queryByText(/of 3 rows/)).toBeNull();
    });

    it('shows no search box for a PDF slide', () => {
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[pdf]} />);
      expect(screen.queryByPlaceholderText('Search in sheet')).toBeNull();
    });

    it('filters to rows matching the typed text, case-insensitively, and counts the matches', async () => {
      mockSheet();
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[sheetXlsx]} />);
      await waitFor(() => expect(screen.getByText('RPACC')).toBeTruthy());

      fireEvent.change(screen.getByPlaceholderText('Search in sheet'), {
        target: { value: 'rpacc' },
      });

      expect(screen.getByText('RPACC')).toBeTruthy();
      expect(screen.queryByText('SRTWC286-SH-150')).toBeNull();
      expect(screen.queryByText('CWCY605')).toBeNull();
      expect(screen.getByText('1 of 3 rows')).toBeTruthy();
    });

    it('shows "No cell matches" for a query nothing matches, and clearing restores every row', async () => {
      mockSheet();
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[sheetXlsx]} />);
      await waitFor(() => expect(screen.getByText('RPACC')).toBeTruthy());
      const input = screen.getByPlaceholderText('Search in sheet');

      fireEvent.change(input, { target: { value: 'zzz' } });
      expect(screen.getByText('No cell matches')).toBeTruthy();

      fireEvent.change(input, { target: { value: '' } });
      expect(screen.getByText('SRTWC286-SH-150')).toBeTruthy();
      expect(screen.getByText('RPACC')).toBeTruthy();
      expect(screen.getByText('CWCY605')).toBeTruthy();
    });

    // Reviewer round: assert on the ELEMENT, not its classes - the coder is changing the
    // highlight's classes to `bg-amber-300 px-0.5 text-zinc-900`, and a class assertion here
    // would pin the wrong thing and break on the very next styling pass.
    it('wraps the matched text in a <mark> element', async () => {
      mockSheet();
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[sheetXlsx]} />);
      await waitFor(() => expect(screen.getByText('RPACC')).toBeTruthy());

      fireEvent.change(screen.getByPlaceholderText('Search in sheet'), {
        target: { value: 'rpacc' },
      });

      const highlighted = document.querySelector('mark');
      expect(highlighted).not.toBeNull();
      expect(highlighted?.textContent).toBe('RPACC');
    });

    it('searches every loaded row, not only the 200 displayed', async () => {
      apiFetchMock.mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      });
      // 205 physical rows, "NEEDLE" only on row 203 (index 202) - past the 200-row display
      // slice, so a search over `rows` instead of `allRows` would find nothing.
      const rows205 = Array.from({ length: 205 }, (_, i) => [i === 202 ? 'NEEDLE' : `row-${i}`]);
      vi.doMock('xlsx', () => ({
        read: () => ({ SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } }),
        utils: { sheet_to_json: () => rows205 },
      }));
      const bigXlsx: AttachmentPreviewItem = {
        id: 'g',
        name: 'big.xlsx',
        url: 'https://cdn.example.com/big.xlsx',
        downloadUrl: '/api/v1/resource-management/attachments/g/download',
      };
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[bigXlsx]} />);
      await waitFor(() => expect(screen.getByText('row-0')).toBeTruthy());

      fireEvent.change(screen.getByPlaceholderText('Search in sheet'), {
        target: { value: 'needle' },
      });

      expect(screen.getByText('1 of 205 rows')).toBeTruthy();
      expect(document.querySelectorAll('tbody tr').length).toBe(1);
      expect(screen.getByText('NEEDLE')).toBeTruthy();
    });

    it('caps more than 200 matches at 200 rows, and the footnote says matches', async () => {
      apiFetchMock.mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      });
      const rows250 = Array.from({ length: 250 }, (_, i) => [`COMMON-${i}`]);
      vi.doMock('xlsx', () => ({
        read: () => ({ SheetNames: ['Sheet1'], Sheets: { Sheet1: {} } }),
        utils: { sheet_to_json: () => rows250 },
      }));
      const manyXlsx: AttachmentPreviewItem = {
        id: 'h',
        name: 'many.xlsx',
        url: 'https://cdn.example.com/many.xlsx',
        downloadUrl: '/api/v1/resource-management/attachments/h/download',
      };
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[manyXlsx]} />);
      await waitFor(() => expect(screen.getByText('COMMON-0')).toBeTruthy());

      fireEvent.change(screen.getByPlaceholderText('Search in sheet'), {
        target: { value: 'common' },
      });

      expect(screen.getByText('250 of 250 rows')).toBeTruthy();
      expect(document.querySelectorAll('tbody tr').length).toBe(200);
      expect(
        screen.getByText('Showing first 200 matches. Download for the full sheet.'),
      ).toBeTruthy();
    });

    it('keeps the query across a sheet switch, and re-applies it to the new sheet', async () => {
      apiFetchMock.mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      });
      vi.doMock('xlsx', () => ({
        read: () => ({
          SheetNames: ['Sheet1', 'Sheet2'],
          Sheets: { Sheet1: { tag: 'one' }, Sheet2: { tag: 'two' } },
        }),
        utils: {
          sheet_to_json: (ws: { tag: string }) =>
            ws.tag === 'two' ? [['ONLY-ON-TWO']] : [['ONLY-ON-ONE']],
        },
      }));
      const twoSheetXlsx: AttachmentPreviewItem = {
        id: 'i',
        name: 'two-sheets.xlsx',
        url: 'https://cdn.example.com/two-sheets.xlsx',
        downloadUrl: '/api/v1/resource-management/attachments/i/download',
      };
      render(<AttachmentPreviewModal open onOpenChange={() => {}} items={[twoSheetXlsx]} />);
      await waitFor(() => expect(screen.getByText('ONLY-ON-ONE')).toBeTruthy());

      fireEvent.change(screen.getByPlaceholderText('Search in sheet'), {
        target: { value: 'only-on-two' },
      });
      // Sheet1 names nothing matching the typed term.
      expect(screen.getByText('No cell matches')).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: 'Sheet2' }));

      // The query survived the switch and is re-applied against Sheet2's own rows.
      expect(await screen.findByText('ONLY-ON-TWO')).toBeTruthy();
      expect((screen.getByPlaceholderText('Search in sheet') as HTMLInputElement).value).toBe(
        'only-on-two',
      );
    });
  });
});
