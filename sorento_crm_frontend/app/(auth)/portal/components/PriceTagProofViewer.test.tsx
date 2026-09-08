/**
 * Zoom control (D11, AC-S4-2, AC-S4-5): Fit plus six discrete presets,
 * defaulting to Fit. `TagSheetRenderer` is mocked to a thin spy - the pixel
 * math of the real renderer is out of scope here, only what scale this
 * component hands it.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const rendererSpy = vi.fn();
vi.mock(
  '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer',
  () => ({
    __esModule: true,
    default: (props: Record<string, unknown>) => {
      rendererSpy(props);
      return <div data-testid="tag-sheet-renderer" />;
    },
  }),
);

import PriceTagProofViewer from './PriceTagProofViewer';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

function doc(): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: {
      preset: 'auto',
      page_width_mm: 210,
      page_height_mm: 297,
      bleed_mm: 3,
      gap_mm: 2,
    },
    sheets: [{ id: 'sheet-1', tags: [] }],
  };
}

/** Radix's DropdownMenuTrigger opens on a real pointerdown/pointerup/click
 *  sequence - a bare fireEvent.click leaves aria-expanded="false" in jsdom. */
async function openZoomMenu() {
  const trigger = await screen.findByRole('button', { name: 'Zoom level' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
  return trigger;
}

beforeEach(() => {
  rendererSpy.mockClear();
});

describe('PriceTagProofViewer - zoom', () => {
  it('defaults to Fit', () => {
    render(<PriceTagProofViewer doc={doc()} resolvedData={{}} />);

    expect(screen.getByRole('button', { name: 'Zoom level' }).textContent).toContain('Fit');
  });

  it('offers Fit, 25, 50, 75, 100, 150 and 200 percent, in that order', async () => {
    render(<PriceTagProofViewer doc={doc()} resolvedData={{}} />);

    await openZoomMenu();
    const items = screen.getAllByRole('menuitem').map((el) => el.textContent);

    expect(items).toEqual(['Fit', '25%', '50%', '75%', '100%', '150%', '200%']);
  });

  it('selecting 200% updates the trigger label and hands the renderer previewScale=2', async () => {
    render(<PriceTagProofViewer doc={doc()} resolvedData={{}} />);

    await openZoomMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '200%' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zoom level' }).textContent).toContain('200%'),
    );
    expect(rendererSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ preview: true, previewScale: 2 }),
    );
  });

  it('selecting a level and then Fit returns the trigger label to Fit', async () => {
    render(<PriceTagProofViewer doc={doc()} resolvedData={{}} />);

    await openZoomMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '50%' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zoom level' }).textContent).toContain('50%'),
    );

    await openZoomMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Fit' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zoom level' }).textContent).toContain('Fit'),
    );
  });

  it('renders neither the zoom control nor the renderer when there are no sheets', () => {
    render(
      <PriceTagProofViewer
        doc={{ ...doc(), sheets: [] }}
        resolvedData={{}}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Zoom level' })).toBeNull();
    expect(screen.getByText('No tag sheets designed yet.')).toBeTruthy();
  });

  it('renders nothing (no crash) when doc is null', () => {
    render(<PriceTagProofViewer doc={null} resolvedData={{}} />);

    expect(screen.getByText('No tag sheets designed yet.')).toBeTruthy();
  });
});
