/**
 * PRICETAG-LPSP S6, AC-20: the preview speaks each line's price type and can draw one line alone.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). `previewLines` sends no `price_type` and the
 * component has no per-line mode.
 *
 * Contract: `previewLines(lines)` carries each line's `price_type`; `<PriceTagLivePreview lineKey="b" />`
 * asks the server for that one line only and draws it (the eye icon's lightbox).
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: ({ title, payload, emptyMessage }: { title: string; payload: unknown; emptyMessage: string }) => (
    <div data-testid="viewer">
      {title}:{payload ? 'drawn' : emptyMessage}
    </div>
  ),
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
import { PriceTagLivePreview, previewLines } from './PriceTagLivePreview';

const template = {
  id: 'tpl',
  name: 'Basin A5',
  family: 'art_basin',
  doc: { layers: [], width_mm: 80, height_mm: 50 },
  print_size: { width_mm: 80, height_mm: 50 },
};

function response(keys: string[]): TagPreviewResponse {
  return {
    lines: keys.map((key) => ({ line_id: key, tag_id: key, code: `C-${key}`, name: key, images: [] })),
    templates: Object.fromEntries(keys.map((key) => [key, template])),
    assets: {},
    images: {},
    fonts: [],
  } as unknown as TagPreviewResponse;
}

const line = (patch: Record<string, unknown>): DraftLine =>
  ({ ...emptyDraftLine(), ...patch }) as DraftLine;

describe('previewLines price_type (AC-20)', () => {
  it('sends each line its own type', () => {
    const sent = previewLines([
      line({ key: 'a', product_id: 'p1', price_type: 'list' }),
      line({ key: 'b', product_id: 'p2', price_type: 'selling', manual_sell_price: 599 }),
    ]) as unknown as Array<Record<string, unknown>>;
    expect(sent.map((l) => [l.key, l.price_type])).toEqual([
      ['a', 'list'],
      ['b', 'selling'],
    ]);
  });

  it('does not send a typed price on an LP line', () => {
    const sent = previewLines([
      line({ key: 'a', product_id: 'p1', price_type: 'list', manual_sell_price: 599 }),
    ]) as unknown as Array<Record<string, unknown>>;
    expect(sent[0].manual_sell_price == null).toBe(true);
  });
});

describe('PriceTagLivePreview one line (AC-20)', () => {
  it('asks for that line only and draws it', async () => {
    const lookup = vi.fn(async () => response(['b']));
    render(
      <PriceTagLivePreview
        lines={[
          line({ key: 'a', product_id: 'p1', price_type: 'list' }),
          line({ key: 'b', code: 'C-b', product_id: 'p2', price_type: 'selling' }),
        ]}
        priceMode="list"
        lookupTagPreview={lookup}
        {...({ lineKey: 'b' } as object)}
      />,
    );
    // The lightbox straight away (no card), headed by the line's code and its type.
    await waitFor(() => expect(screen.getByTestId('lightbox')).toHaveTextContent(':drawn'));
    expect(screen.getByTestId('lightbox')).toHaveTextContent('C-b - SP');
    expect(screen.queryByTestId('viewer')).toBeNull();
    expect(lookup).toHaveBeenCalledTimes(1);
    const [, sent] = lookup.mock.calls[0] as unknown as [string, Array<Record<string, unknown>>];
    expect(sent.map((l) => l.key)).toEqual(['b']);
    expect(sent[0].price_type).toBe('selling');
  });

  it('renders nothing for a key that is not on the form', () => {
    const lookup = vi.fn(async () => response([]));
    const { container } = render(
      <PriceTagLivePreview
        lines={[line({ key: 'a', product_id: 'p1' })]}
        priceMode="list"
        lookupTagPreview={lookup}
        {...({ lineKey: 'gone' } as object)}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(lookup).not.toHaveBeenCalled();
  });
});
