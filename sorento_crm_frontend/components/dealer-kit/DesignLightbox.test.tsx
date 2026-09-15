/**
 * The tag sheet lightbox (r9 S1/D2, AC-S1-5).
 *
 * What a salesperson does here is look closely at one tag, so the zoom has to
 * behave the way every image viewer they already use behaves (C1):
 * Ctrl/Cmd + wheel zooms AROUND THE CURSOR, a plain wheel scrolls the page,
 * and a drag pans once the sheet is bigger than the window.
 *
 * The cursor-anchored part is the bit that is easy to get wrong and hard to
 * notice: zooming that ignores the cursor walks the sheet towards its top-left
 * corner, so the tag the reader was studying slides off screen. It is asserted
 * here as scroll arithmetic rather than pixels, because jsdom lays nothing out
 * - the anchor maths is the behaviour, and it runs identically either way.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent } from '@testing-library/react';

import DesignLightbox from './DesignLightbox';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

class StubResizeObserver {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe() {
    this.callback(
      [{ contentRect: { width: 800, height: 600 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as Record<string, unknown>).ResizeObserver =
  StubResizeObserver;

vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return {
    ...actual,
    ensureFontsLoaded: vi.fn(async () => {}),
    ensureSeedFontsLoaded: vi.fn(async () => {}),
  };
});

function payload(sheets = 1): TagSheetDesignPayload {
  return {
    page_id: 'page-1',
    version: 1,
    source: 'version',
    doc: {
      kind: 'tag_sheet',
      imposition: { page_width_mm: 210, page_height_mm: 297 },
      sheets: Array.from({ length: sheets }, (_, index) => ({
        id: `sheet-${index + 1}`,
        tags: [],
      })),
    } as unknown as TagSheetDesignPayload['doc'],
    resolvedData: {},
    assets: {},
    images: {},
    fonts: [],
  };
}

function open(sheets = 1) {
  const result = render(
    <DesignLightbox
      open
      onOpenChange={vi.fn()}
      title="PT-202609-0001"
      payload={payload(sheets)}
    />,
  );
  const viewport = screen.getByTestId('design-lightbox-viewport');
  // jsdom reports 0 for every layout box, and the pan / anchor maths reads
  // these. Given real numbers, the arithmetic under test runs for real.
  viewport.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 }) as DOMRect;
  Object.defineProperty(viewport, 'clientWidth', { value: 800, configurable: true });
  Object.defineProperty(viewport, 'clientHeight', { value: 600, configurable: true });
  // Radix's scroll lock (`react-remove-scroll`) cancels every wheel event that
  // did not land on something it can prove is scrollable, and jsdom reports a
  // zero-sized, `overflow: visible` box for the Tailwind-classed container - so
  // without this the lock eats the wheel and the assertion below tests the
  // lock, not the lightbox.
  viewport.style.overflow = 'auto';
  Object.defineProperty(viewport, 'scrollHeight', { value: 4000, configurable: true });
  Object.defineProperty(viewport, 'scrollWidth', { value: 4000, configurable: true });
  return { ...result, viewport };
}

function zoomLabel(): string {
  return screen.getByLabelText('Zoom level').textContent?.trim() ?? '';
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('accessibility (live finding, Radix "Missing Description")', () => {
  it('the dialog carries a real aria-describedby, not a dangling one', () => {
    open();

    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    const describedBy = dialog?.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).not.toBeNull();
  });

  it('opening logs no Radix Description warning', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    open();

    const messages = errorSpy.mock.calls.flat().join(' ');
    expect(messages).not.toMatch(/description/i);
    errorSpy.mockRestore();
  });
});

describe('zoom (AC-S1-5)', () => {
  it('opens at Fit', () => {
    open();

    expect(zoomLabel()).toContain('Fit');
  });

  it('ctrl + wheel zooms the sheet and swallows the browser page zoom', () => {
    const { viewport } = open();
    const before = zoomLabel();

    const event = new WheelEvent('wheel', {
      deltaY: -120,
      ctrlKey: true,
      clientX: 400,
      clientY: 300,
      bubbles: true,
      cancelable: true,
    });
    // `dispatchEvent` on a NATIVE listener, so React's state update is not
    // batched by the test renderer unless it is wrapped.
    act(() => {
      viewport.dispatchEvent(event);
    });

    expect(zoomLabel()).not.toBe(before);
    expect(zoomLabel()).toMatch(/%$/);
    expect(event.defaultPrevented).toBe(true);
  });

  it('a plain wheel leaves the zoom alone and lets the container scroll', () => {
    const { viewport } = open();
    const before = zoomLabel();

    const event = new WheelEvent('wheel', {
      deltaY: -120,
      clientX: 400,
      clientY: 300,
      bubbles: true,
      cancelable: true,
    });
    act(() => {
      viewport.dispatchEvent(event);
    });

    // Only the zoom is asserted: `defaultPrevented` belongs to Radix's scroll
    // lock in jsdom, not to this component, so reading it here would test the
    // lock. What matters is that a plain wheel is not a zoom.
    expect(zoomLabel()).toBe(before);
  });

  it('keeps the point under the cursor under the cursor', () => {
    const { viewport } = open();
    viewport.scrollLeft = 100;
    viewport.scrollTop = 50;

    act(() => {
      viewport.dispatchEvent(
        new WheelEvent('wheel', {
          deltaY: -120,
          ctrlKey: true,
          clientX: 400,
          clientY: 300,
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    // Zooming in must scroll TOWARDS the cursor's content point, not stay put
    // at the sheet's top-left corner.
    expect(viewport.scrollLeft).toBeGreaterThan(100);
    expect(viewport.scrollTop).toBeGreaterThan(50);
  });

  it('answers + - and 0', () => {
    open();
    const dialog = screen.getByRole('dialog');

    fireEvent.keyDown(dialog, { key: '+' });
    const zoomedIn = zoomLabel();
    expect(zoomedIn).not.toContain('Fit');

    fireEvent.keyDown(dialog, { key: '-' });
    expect(zoomLabel()).not.toBe(zoomedIn);

    fireEvent.keyDown(dialog, { key: '0' });
    expect(zoomLabel()).toContain('Fit');
  });

  it('offers Fit and the preset steps in the % menu', async () => {
    open();

    // Opened from the keyboard: Radix's dropdown opens on pointerdown, and the
    // dialog's scroll lock sets `pointer-events: none` on the body in jsdom.
    fireEvent.keyDown(screen.getByLabelText('Zoom level'), { key: 'Enter' });

    const items = await screen.findAllByRole('menuitem');
    const labels = items.map((item) => item.textContent?.trim());
    expect(labels).toEqual(
      expect.arrayContaining(['Fit', '25%', '50%', '100%', '200%']),
    );
  });
});

describe('pan (AC-S1-5)', () => {
  it('a drag scrolls the viewport once the sheet is bigger than it', () => {
    const { viewport } = open();
    const dialog = screen.getByRole('dialog');
    // 400% of an A4 page is far larger than an 800x600 viewport.
    fireEvent.keyDown(dialog, { key: '+' });
    fireEvent.keyDown(dialog, { key: '+' });
    fireEvent.keyDown(dialog, { key: '+' });
    fireEvent.keyDown(dialog, { key: '+' });
    viewport.scrollLeft = 200;
    viewport.scrollTop = 200;

    fireEvent.pointerDown(viewport, { button: 0, clientX: 400, clientY: 300 });
    fireEvent.pointerMove(viewport, { clientX: 340, clientY: 260 });
    fireEvent.pointerUp(viewport, { clientX: 340, clientY: 260 });

    expect(viewport.scrollLeft).toBe(260);
    expect(viewport.scrollTop).toBe(240);
  });
});

describe('sheet paging (AC-S1-4 counter)', () => {
  it('shows n / N and walks it with the arrow keys', () => {
    open(3);
    const dialog = screen.getByRole('dialog');

    expect(screen.getByText('1 / 3')).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'ArrowRight' });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'ArrowLeft' });
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });
});
