/**
 * Crew browser pass (5 Nov): the request preview (staff Design section, portal live preview and
 * self-approval all draw through DesignViewer) warns above the sheet which tags lose feature
 * icons because their box is too narrow.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import DesignViewer from './DesignViewer';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

// jsdom has no ResizeObserver, and the card measures its container to fit.
class StubResizeObserver {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe() {
    this.callback(
      [{ contentRect: { width: 640, height: 480 } } as ResizeObserverEntry],
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

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

function payload(width_mm: number): TagSheetDesignPayload {
  return {
    page_id: 'page-1',
    version: 1,
    source: 'version',
    doc: {
      kind: 'tag_sheet',
      imposition: { page_width_mm: 210, page_height_mm: 297 },
      sheets: [
        {
          id: 'sheet-1',
          tags: [
            {
              id: 'placed-1',
              template_id: 'tpl',
              request_tag_id: 'tag-2a',
              x_mm: 0,
              y_mm: 0,
              width_mm: 90,
              height_mm: 60,
              layers: [
                {
                  id: 'fi',
                  type: 'feature_icons',
                  x_mm: 0,
                  y_mm: 0,
                  width_mm,
                  height_mm: 10,
                  rotation_deg: 0,
                  z_index: 1,
                  locked: false,
                  visible: true,
                  slot_binding: null,
                  text_override: null,
                  props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left' },
                },
              ],
            },
          ],
        },
      ],
    },
    resolvedData: {
      'tag-2a': { tag_label: '2a', specs: [spec('water_supply', 'Mixer', 'mixer')] },
    },
    assets: { cold: 'https://cdn/cold.png', hot: 'https://cdn/hot.png' },
    images: {},
    fonts: [],
    featureIcons: [
      { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['mixer'] },
      { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
    ],
  } as unknown as TagSheetDesignPayload;
}

describe('DesignViewer feature icon warning', () => {
  it('names the tag that loses an icon', () => {
    render(<DesignViewer docNumber="PT-1" payload={payload(10)} />);
    expect(screen.getByText('Tag 2a: 1 feature icon does not fit its box')).toBeInTheDocument();
  });

  it('says nothing when the icons fit', () => {
    render(<DesignViewer docNumber="PT-1" payload={payload(40)} />);
    expect(screen.queryByText(/does not fit its box/)).toBeNull();
  });
});
