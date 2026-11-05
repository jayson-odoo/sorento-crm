/**
 * O2: the request form's whole-request preview is a popup the Preview button opens, not an
 * always-on card. With `popup` the component still asks and reports readiness (Approve needs it),
 * but draws nothing until the popup is open.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: () => <div data-testid="viewer" />,
}));
vi.mock('@/components/dealer-kit/DesignLightbox', () => ({
  __esModule: true,
  default: ({ title, payload }: { title: string; payload: unknown }) => (
    <div data-testid="lightbox">
      {title}:{payload ? 'drawn' : 'empty'}
    </div>
  ),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { TagPreviewResponse } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { PriceTagLivePreview } from './PriceTagLivePreview';

const template = {
  id: 'tpl', name: 'A', family: 'art_basin',
  doc: { layers: [], width_mm: 80, height_mm: 50 }, print_size: { width_mm: 80, height_mm: 50 },
};
const response = (keys: string[], withTemplates = true) =>
  ({
    lines: keys.map((key) => ({ line_id: key, tag_id: key, code: `C-${key}`, name: key, images: [] })),
    templates: withTemplates ? Object.fromEntries(keys.map((key) => [key, template])) : {},
    assets: {}, images: {}, fonts: [],
  }) as unknown as TagPreviewResponse;
const line = { ...emptyDraftLine(), key: 'a', code: 'C-a', product_id: 'p1' } as DraftLine;

function draw(popup: { open: boolean; onClose: () => void }, lookup = vi.fn(async () => response(['a']))) {
  const onReadyChange = vi.fn();
  render(
    <PriceTagLivePreview
      lines={[line]}
      priceMode="list"
      lookupTagPreview={lookup}
      docNumber="PT-1"
      onReadyChange={onReadyChange}
      popup={popup}
    />,
  );
  return { onReadyChange, lookup };
}

describe('PriceTagLivePreview popup mode', () => {
  it('draws no card while closed, but still reports readiness', async () => {
    const { onReadyChange } = draw({ open: false, onClose: vi.fn() });
    await waitFor(() =>
      expect(onReadyChange).toHaveBeenLastCalledWith({ missing: [], drawn: true, failed: false }),
    );
    expect(screen.queryByTestId('viewer')).toBeNull();
    expect(screen.queryByTestId('lightbox')).toBeNull();
  });

  it('reports a missing template without drawing', async () => {
    const { onReadyChange } = draw({ open: false, onClose: vi.fn() }, vi.fn(async () => response(['a'], false)));
    await waitFor(() => expect(onReadyChange).toHaveBeenLastCalledWith(expect.objectContaining({ missing: ['C-a'] })));
    expect(screen.queryByTestId('viewer')).toBeNull();
  });

  it('opens the same sheet in the lightbox when asked', async () => {
    draw({ open: true, onClose: vi.fn() });
    await waitFor(() => expect(screen.getByTestId('lightbox')).toHaveTextContent('PT-1:drawn'));
    expect(screen.queryByTestId('viewer')).toBeNull();
  });
});
