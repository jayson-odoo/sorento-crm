/**
 * `designPayloadFromResponse` (r9 S1/D1, combos slice).
 *
 * Live defect, PT-202609-0015 (owner, 15 Sep): the History View lightbox
 * showed "Price TBC" instead of the pinned RM 1,260. The version's data was
 * right - `resolve_version_line_data` answers rows keyed by `tag_id`, and
 * `TagSheetRenderer` reads `resolvedData[tag.request_tag_id]` - but this
 * builder still keyed the map by `line.line_id`, so every reader through it
 * (the live design card, the portal preview AND the version lightbox) looked
 * up a key that was never there. The live surfaces happened to look right
 * only because a second, differently-keyed map fed them elsewhere; the
 * version view has no such second path.
 *
 * One line can carry more than one placed tag since the combos slice
 * (`request_tag_id` on `PlacedTag`, `tag_id` on the resolved row), so keying
 * by `line_id` was always wrong once a line had two tags - this just never
 * showed up until a fixture (or a real request) gave the two ids different
 * values.
 */
import { describe, it, expect } from 'vitest';

import {
  designPayloadFromResponse,
  type TagSheetDesignResponse,
} from './design-payload';
import type { LineTagData } from './tag-template-types';

function line(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    tag_id: 'tag-1',
    line_id: 'line-1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
    code: 'ZZT-SINK-1',
    name: 'ZZT Kitchen Sink',
    dimensions: '',
    spec_lines: '',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1260,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

function response(lines: LineTagData[]): TagSheetDesignResponse {
  return {
    page_id: 'page-1',
    version: 1,
    source: 'version',
    doc: null,
    lines,
  };
}

describe('designPayloadFromResponse keys resolvedData by the TAG (owner live finding, PT-202609-0015)', () => {
  it('a row with tag_id T and line_id L is found at T, not at L', () => {
    const row = line({ tag_id: 'tag-1', line_id: 'line-1', list_price: 1260 });

    const payload = designPayloadFromResponse(response([row]));

    expect(payload.resolvedData['tag-1']).toBe(row);
    expect(payload.resolvedData['line-1']).toBeUndefined();
  });

  it('two tags of one line are both present, each at its own tag id', () => {
    const first = line({ tag_id: 'tag-1', line_id: 'line-1', list_price: 1260 });
    const second = line({ tag_id: 'tag-2', line_id: 'line-1', list_price: 1260 });

    const payload = designPayloadFromResponse(response([first, second]));

    expect(payload.resolvedData['tag-1']).toBe(first);
    expect(payload.resolvedData['tag-2']).toBe(second);
    // Keying by line_id would have let the second tag silently overwrite the
    // first under one shared key - both must survive, distinctly.
    expect(Object.keys(payload.resolvedData)).toHaveLength(2);
  });

  it('a row with no tag_id at all falls back to line_id (a pre-combos backend)', () => {
    const row = { ...line({ line_id: 'line-1' }) } as Partial<LineTagData>;
    delete row.tag_id;

    const payload = designPayloadFromResponse(
      response([row as LineTagData]),
    );

    expect(payload.resolvedData['line-1']).toBe(row);
  });
});
