/**
 * Portal attachment preview, end to end through the REAL shared modal
 * (UAC-portal-submission-revisions I1 / I2 / I3 / I5).
 *
 * Deliberately does NOT stub AttachmentPreviewModal - the point of these is
 * that the portal's own `fetchBytes` reaches the modal's Download and Excel
 * paths, that nothing leaves through `apiFetch` (no NextAuth session here),
 * and that an unpreviewable type still lands on the shared fallback card.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { AttachmentDropzone } from './AttachmentDropzone';
import { writePortalToken, clearPortalToken, type PortalAttachment } from '../lib/portal-client';

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return { ...original, uploadAttachment: vi.fn(), deleteAttachment: vi.fn() };
});

// embla-carousel needs layout APIs jsdom lacks; stub the wrapper so slide
// rendering (the logic under test) runs without a real carousel engine.
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
}));

function attachment(over: Partial<PortalAttachment> = {}): PortalAttachment {
  return {
    link_id: 'link-1',
    attachment_id: 'att-1',
    filename: 'quote.pdf',
    size: 4096,
    url: 'https://cdn.example.com/quote.pdf',
    content_type: 'application/pdf',
    uploader_kind: 'contact',
    can_unlink: true,
    ...over,
  };
}

beforeEach(() => {
  apiFetchMock.mockReset();
  clearPortalToken();
  writePortalToken('tok-123');
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

describe('portal attachment preview', () => {
  it('previews a PDF in place - no new tab, no anchor to a protected route', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[attachment()]}
        onChange={vi.fn()}
      />,
    );
    // The row itself never links out - clicking it opens the modal (I1).
    expect(document.body.querySelector('a[target="_blank"]')).toBeNull();
    fireEvent.click(screen.getByLabelText('Preview quote.pdf'));

    const frame = document.body.querySelector('iframe');
    expect(frame?.getAttribute('src')).toBe('https://cdn.example.com/quote.pdf');
  });

  it('renders the shared fallback card for an unpreviewable type', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[attachment({ filename: 'archive.zip', url: 'https://cdn.example.com/archive.zip' })]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('Preview archive.zip'));

    expect(screen.getByText(/no inline preview/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download to view/i })).toBeInTheDocument();
  });

  it('downloads bytes through the portal token route, never apiFetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['x']),
    });
    vi.stubGlobal('fetch', fetchMock);
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi
      .fn()
      .mockReturnValue('blob:mock');
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();

    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[attachment()]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('Preview quote.pdf'));
    fireEvent.click(screen.getByRole('button', { name: /^download$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    // Keyed on attachment_id (I2a), carrying the portal token (I2).
    expect(url).toMatch(/\/api\/v1\/public\/portal\/attachments\/att-1\/download$/);
    expect(new Headers(init.headers).get('X-Portal-Token')).toBe('tok-123');
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('previews a file staged before upload in place too', () => {
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi
      .fn()
      .mockReturnValue('blob:pending-1');
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    const pending = new File(['bytes'], 'snap.png', { type: 'image/png' });

    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId={null}
        attachments={[]}
        onChange={vi.fn()}
        pendingFiles={[pending]}
        onPendingFilesChange={vi.fn()}
      />,
    );
    // The thumbnail is a button, not an anchor - the old markup opened the
    // blob in a new tab.
    expect(document.body.querySelector('a[target="_blank"]')).toBeNull();
    fireEvent.click(screen.getByLabelText('Preview snap.png'));

    const full = screen.getAllByAltText('snap.png').find((el) => el.closest('[role="dialog"]'));
    expect(full).toBeTruthy();
    expect(full?.getAttribute('src')).toBe('blob:pending-1');
  });
});
