/**
 * M2-02 - in the attachment lightbox, ArrowRight/ArrowLeft change the slide
 * on the same frame (no animation); drag and dot navigation still play
 * Embla's own scroll (carousel.tsx, duration 20).
 *
 * Embla's `scrollNext`/`scrollPrev` take an optional `jump` boolean that
 * skips the scroll animation entirely - the arrow-key handler in
 * `AttachmentPreviewModal` passes `true`, everything else (drag, the
 * next/previous buttons) calls the carousel's own `scrollNext`/`scrollPrev`
 * with no argument, which is a separate code path this test does not touch.
 */
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import AttachmentPreviewModal, { type AttachmentPreviewItem } from './AttachmentPreviewModal';

const fakeApi = vi.hoisted(() => ({
  selectedScrollSnap: vi.fn(() => 0),
  on: vi.fn(),
  off: vi.fn(),
  scrollNext: vi.fn(),
  scrollPrev: vi.fn(),
}));

// Stub the wrapper so the modal gets a fake embla api (via setApi) whose
// scrollNext/scrollPrev calls can be asserted on, without a real embla
// engine (jsdom lacks the layout APIs it needs).
vi.mock('@/components/ui/carousel', () => ({
  Carousel: ({
    children,
    setApi,
  }: {
    children: ReactNode;
    setApi?: (api: unknown) => void;
  }) => {
    useEffect(() => {
      setApi?.(fakeApi);
    }, [setApi]);
    return <div>{children}</div>;
  },
  CarouselContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CarouselNext: () => <button type="button">next</button>,
  CarouselPrevious: () => <button type="button">prev</button>,
}));

const img: AttachmentPreviewItem = {
  id: 'a',
  name: 'photo.jpg',
  url: 'https://cdn.example.com/photo.jpg',
};
const video: AttachmentPreviewItem = {
  id: 'b',
  name: 'clip.mp4',
  url: 'https://cdn.example.com/clip.mp4',
};

beforeEach(() => {
  fakeApi.scrollNext.mockClear();
  fakeApi.scrollPrev.mockClear();
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

describe('AttachmentPreviewModal arrow-key navigation (M2-02)', () => {
  it('ArrowRight jumps to the next slide (no animation)', () => {
    render(
      <AttachmentPreviewModal open onOpenChange={() => {}} items={[img, video]} />,
    );

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowRight' });

    expect(fakeApi.scrollNext).toHaveBeenCalledWith(true);
    expect(fakeApi.scrollPrev).not.toHaveBeenCalled();
  });

  it('ArrowLeft jumps to the previous slide (no animation)', () => {
    render(
      <AttachmentPreviewModal open onOpenChange={() => {}} items={[img, video]} />,
    );

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowLeft' });

    expect(fakeApi.scrollPrev).toHaveBeenCalledWith(true);
    expect(fakeApi.scrollNext).not.toHaveBeenCalled();
  });
});
