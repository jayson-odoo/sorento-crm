/** PRICETAG-TEMPLATE-PER-PRODUCT R5 / AC-16: the request form's live preview. */
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

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { TagPreviewResponse } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { PriceTagLivePreview, previewLines, previewPayload } from './PriceTagLivePreview';

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

const line = (patch: Partial<DraftLine>): DraftLine => ({ ...emptyDraftLine(), ...patch });

describe('previewLines', () => {
  it('sends only lines that name a product or a set, with the pick', () => {
    const sent = previewLines([
      line({ key: 'a', product_id: 'p1', tag_template_id: 't1' }),
      line({ key: 'b' }),
      line({ key: 'c', line_type: 'product_set', product_set_id: 's1', tag_template_id: 't9' }),
    ]);
    expect(sent.map((l) => [l.key, l.tag_template_id])).toEqual([
      ['a', 't1'],
      ['c', null],
    ]);
  });
});

describe('previewPayload', () => {
  it('draws one tag per line, keyed by the line key', () => {
    const sent = previewLines([line({ key: 'a', product_id: 'p1' }), line({ key: 'b', product_id: 'p2' })]);
    const payload = previewPayload(sent, response(['a', 'b']));
    const placed = payload?.doc?.sheets.flatMap((s) => s.tags) ?? [];
    expect(placed.map((t) => t.request_tag_id).sort()).toEqual(['a', 'b']);
    expect(Object.keys(payload?.resolvedData ?? {}).sort()).toEqual(['a', 'b']);
  });

  it('is null when no line got a template', () => {
    const sent = previewLines([line({ key: 'a', product_id: 'p1' })]);
    expect(previewPayload(sent, { ...response([]), templates: {} })).toBeNull();
  });
});

describe('PriceTagLivePreview', () => {
  it('renders nothing before the first item', () => {
    const lookup = vi.fn();
    const { container } = render(
      <PriceTagLivePreview lines={[line({ key: 'a' })]} priceMode="list" lookupTagPreview={lookup} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(lookup).not.toHaveBeenCalled();
  });

  it('asks once the first item is on a line and draws the answer', async () => {
    const lookup = vi.fn(async () => response(['a']));
    render(
      <PriceTagLivePreview lines={[line({ key: 'a', product_id: 'p1' })]} priceMode="selling" lookupTagPreview={lookup} />,
    );
    await waitFor(() => expect(screen.getByTestId('viewer')).toHaveTextContent('Preview:drawn'));
    expect(lookup).toHaveBeenCalledTimes(1);
    const [mode, sent] = lookup.mock.calls[0] as unknown as [string, { key: string }[]];
    expect(mode).toBe('selling');
    expect(sent.map((l) => l.key)).toEqual(['a']);
  });

  it('says so when the preview cannot be drawn', async () => {
    const lookup = vi.fn(async () => {
      throw new Error('boom');
    });
    render(<PriceTagLivePreview lines={[line({ key: 'a', product_id: 'p1' })]} priceMode="list" lookupTagPreview={lookup} />);
    await waitFor(() => expect(screen.getByTestId('viewer')).toHaveTextContent('Preview unavailable'));
  });
});
