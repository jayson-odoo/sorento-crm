/**
 * The header every full-screen preview shares (r9 S1/D2, AC-S1-4).
 *
 * Two surfaces drawing their own header is how a Download button ends up in a
 * different place on each of them, so the bar is one component and BOTH
 * consumers are asserted here: the attachment viewer (an editable percentage,
 * because any zoom value is meaningful on a photo) and the tag sheet lightbox
 * (a preset menu, because `Fit` has no number to type).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { Dialog, DialogContent } from '@/components/ui/dialog';
import {
  PREVIEW_ZOOM_MAX,
  PREVIEW_ZOOM_MIN,
  PreviewModalChrome,
} from './PreviewModalChrome';

function renderChrome(props: React.ComponentProps<typeof PreviewModalChrome>) {
  return render(
    <Dialog open onOpenChange={vi.fn()}>
      <DialogContent>
        <PreviewModalChrome {...props} />
      </DialogContent>
    </Dialog>,
  );
}

describe('the shared chrome (AC-S1-4)', () => {
  it('shows the title and the position counter', () => {
    renderChrome({ title: 'PT-202609-0001', counter: '2 / 5' });

    expect(screen.getByText('PT-202609-0001')).toBeInTheDocument();
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('renders whatever actions the caller gives it, right of the zoom', () => {
    renderChrome({
      title: 'invoice.pdf',
      actions: <button type="button">Download</button>,
    });

    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument();
  });

  it('has no zoom cluster at all on a surface that cannot zoom', () => {
    renderChrome({ title: 'clip.mp4', counter: '1 / 1' });

    expect(screen.queryByLabelText('Zoom in')).toBeNull();
    expect(screen.queryByLabelText('Zoom out')).toBeNull();
  });
});

describe('the attachment viewer half: an editable percentage', () => {
  it('commits a typed percentage on Enter, clamped to the bounds', () => {
    const onSetZoom = vi.fn();
    renderChrome({
      title: 'photo.jpg',
      zoom: { value: 1, onZoomBy: vi.fn(), onSetZoom },
    });

    const input = screen.getByLabelText('Zoom percentage');
    expect(input).toHaveValue('100');

    fireEvent.change(input, { target: { value: '250' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onSetZoom).toHaveBeenCalledWith(2.5);
  });

  it('clamps a percentage past the maximum rather than accepting it', () => {
    const onSetZoom = vi.fn();
    renderChrome({
      title: 'photo.jpg',
      zoom: { value: 1, onZoomBy: vi.fn(), onSetZoom },
    });

    const input = screen.getByLabelText('Zoom percentage');
    fireEvent.change(input, { target: { value: '900' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onSetZoom).toHaveBeenCalledWith(PREVIEW_ZOOM_MAX);
  });

  it('the buttons multiply the current scale and stop at the bounds', () => {
    const onZoomBy = vi.fn();
    const { rerender } = renderChrome({
      title: 'photo.jpg',
      zoom: { value: 1, onZoomBy, onSetZoom: vi.fn() },
    });

    fireEvent.click(screen.getByLabelText('Zoom in'));
    fireEvent.click(screen.getByLabelText('Zoom out'));

    expect(onZoomBy).toHaveBeenNthCalledWith(1, 1.25);
    expect(onZoomBy).toHaveBeenNthCalledWith(2, 0.8);

    rerender(
      <Dialog open onOpenChange={vi.fn()}>
        <DialogContent>
          <PreviewModalChrome
            title="photo.jpg"
            zoom={{
              value: PREVIEW_ZOOM_MIN,
              onZoomBy,
              onSetZoom: vi.fn(),
            }}
          />
        </DialogContent>
      </Dialog>,
    );
    expect(screen.getByLabelText('Zoom out')).toBeDisabled();
  });
});

describe('the tag sheet half: a preset menu', () => {
  it('shows the caller label instead of a percentage and lists the presets', async () => {
    const onSelect = vi.fn();
    renderChrome({
      title: 'PT-202609-0001',
      counter: '1 / 2',
      zoom: {
        value: 0.42,
        onZoomBy: vi.fn(),
        onSetZoom: vi.fn(),
        valueLabel: 'Fit',
        presets: [
          { label: 'Fit', onSelect },
          { label: '100%', onSelect: vi.fn() },
        ],
      },
    });

    const trigger = screen.getByLabelText('Zoom level');
    expect(trigger).toHaveTextContent('Fit');
    expect(screen.queryByLabelText('Zoom percentage')).toBeNull();

    fireEvent.keyDown(trigger, { key: 'Enter' });

    const items = await screen.findAllByRole('menuitem');
    expect(items.map((item) => item.textContent?.trim())).toEqual(['Fit', '100%']);
  });
});
