/**
 * PRICETAG-COMBO-FORMAT AC-19: merge fields resolve on text RUNS. A spec value `<b>x</b>` inside
 * `<p>{{spec.width}}</p>` prints as the literal text `<b>x</b>`, never as bold "x".
 *
 * Written test-FIRST. Today `layerText` substitutes into the string, so a rich string would then be
 * parsed with the spec value's markup live. The assertion is on what the print page draws, so it
 * does not depend on which function the implementation parses in.
 *
 * KILL: substitute before parsing -> red (a <b> element / bold run appears).
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { richTextLayer, tagSheetDocWith } from './rich-text.e1.fixture';

function resolved(): ResolvedLineData {
  return {
    tag_id: 'tag-1',
    tag_label: '1a',
    line_id: 'line-1',
    code: 'ZZT1',
    name: 'Host',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: null,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    parts: [],
    specs: [{ key: 'width', label: 'Width', value: '<b>x</b>', unit: null }],
  } as unknown as ResolvedLineData;
}

describe('merge fields on text runs (AC-19)', () => {
  it('AC-19: a spec value holding markup prints as literal text, in no bold element', () => {
    const layer = richTextLayer('', { text_override: '<p>{{spec.width}}</p>' });
    const doc = tagSheetDocWith(layer);
    (doc.sheets[0].tags[0] as { request_tag_id: string | null }).request_tag_id = 'tag-1';
    const { container } = render(
      <TagSheetRenderer doc={doc} resolvedData={{ 'tag-1': resolved() }} />,
    );

    expect(screen.getByText('<b>x</b>')).toBeInTheDocument();
    expect(container.querySelector('b, strong')).toBeNull();
    const run = screen.getByText('<b>x</b>');
    expect(['', 'normal', '400']).toContain(run.style.fontWeight);
  });
});
