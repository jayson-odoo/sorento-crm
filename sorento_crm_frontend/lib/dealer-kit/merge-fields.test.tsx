/**
 * Merge fields in a tag's text (D55-D57, AC-M.24).
 *
 * Written before the resolver. The rules worth pinning here are the ones that
 * put a wrong figure in front of a customer if they drift: a price token has to
 * print the same `RM #,##0` the badge prints, an unknown token has to vanish
 * rather than print itself onto a tag, and the canvas and the PDF have to agree
 * about every one of them - which is why the last test renders one layer
 * through both surfaces and compares the words.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import {
  hasMergeField,
  mergeFieldCatalog,
  renderMergeFields,
} from './merge-fields';
import { layerText } from './product-block';
import type {
  LineTagData,
  ProductSetTagData,
  ProductTagData,
  TagBindingData,
  TagLayer,
  TagSheetDoc,
} from './tag-template-types';
import { defaultTextProps } from './tag-template-types';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function product(overrides: Partial<ProductTagData> = {}): TagBindingData {
  return {
    kind: 'product',
    product: {
      id: 'p1',
      code: 'CBF3612',
      name: 'Kitchen Sink',
      dimensions: '800 x 500 x 220 mm',
      spec_lines: ['Stainless steel', 'Overflow included'],
      specs: [
        { key: 'material', label: 'Material', value: 'stainless steel', unit: null },
        { key: 'diameter', label: 'Diameter', value: '407', unit: 'mm' },
      ],
      images: [],
      list_price: 1599,
      offer_price: 599,
      promotion_id: null,
      ...overrides,
    },
  };
}

function set(overrides: Partial<ProductSetTagData> = {}): TagBindingData {
  return {
    kind: 'set',
    set: {
      id: 's1',
      set_code: 'BFS-100',
      name: 'Bathroom Furniture Set',
      members: [
        {
          product_id: 'p1',
          code: 'CB-1',
          name: 'Cabinet',
          dimensions: '600 x 450 mm',
          quantity: 1,
        },
        {
          product_id: 'p2',
          code: 'MR-1',
          name: 'Mirror',
          dimensions: '600 x 800 mm',
          quantity: 1,
        },
      ],
      list_price: 2400,
      offer_price: null,
      promotion_id: null,
      ...overrides,
    },
  };
}

function lineData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    line_id: 'line-1',
    code: 'CBF3612',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel\nOverflow included',
    specs: [
      { key: 'material', label: 'Material', value: 'stainless steel', unit: null },
    ],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: 599,
    show_promo_price: true,
    included_accessories: 'Waste and trap',
    quantity: 3,
    ...overrides,
  };
}

function line(overrides: Partial<LineTagData> = {}): TagBindingData {
  return { kind: 'line', line: lineData(overrides) };
}

function textLayer(content: string): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 80,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: content },
  };
}

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

describe('renderMergeFields - product paths', () => {
  it('draws every product field a token can name', () => {
    const data = product();

    expect(renderMergeFields('{{product.code}}', data, 'print')).toBe('CBF3612');
    expect(renderMergeFields('{{product.name}}', data, 'print')).toBe('Kitchen Sink');
    expect(renderMergeFields('{{product.dimensions}}', data, 'print')).toBe(
      '800 x 500 x 220 mm',
    );
    expect(renderMergeFields('{{product.spec_lines}}', data, 'print')).toBe(
      'Stainless steel\nOverflow included',
    );
  });

  it('prices carry the same RM formatting the badge prints', () => {
    const data = product();

    expect(renderMergeFields('{{product.list_price}}', data, 'print')).toBe('RM 1,599');
    expect(renderMergeFields('{{product.sell_price}}', data, 'print')).toBe('RM 599');
  });

  it('resolves several tokens inside one sentence, keeping the words around them', () => {
    expect(
      renderMergeFields(
        '{{product.code}} - {{product.dimensions}} in {{spec.material}}',
        product(),
        'print',
      ),
    ).toBe('CBF3612 - 800 x 500 x 220 mm in stainless steel');
  });

  it('tolerates whitespace inside the braces', () => {
    expect(renderMergeFields('{{ product.code }}', product(), 'print')).toBe('CBF3612');
  });
});

describe('renderMergeFields - spec paths', () => {
  it('renders a spec value with its unit when the registry has one', () => {
    expect(renderMergeFields('{{spec.diameter}}', product(), 'print')).toBe('407 mm');
  });

  it('renders a spec value with no unit as the value alone', () => {
    expect(renderMergeFields('{{spec.material}}', product(), 'print')).toBe(
      'stainless steel',
    );
  });

  it('a spec the product does not carry renders empty', () => {
    expect(renderMergeFields('[{{spec.finish}}]', product(), 'print')).toBe('[]');
  });

  it('a set has no specs of its own', () => {
    expect(renderMergeFields('[{{spec.material}}]', set(), 'print')).toBe('[]');
  });
});

describe('renderMergeFields - set and line paths', () => {
  it('draws the set code, name and member text', () => {
    const data = set();

    expect(renderMergeFields('{{set.code}}', data, 'print')).toBe('BFS-100');
    expect(renderMergeFields('{{set.name}}', data, 'print')).toBe(
      'Bathroom Furniture Set',
    );
    expect(renderMergeFields('{{set.members}}', data, 'print')).toContain('CB-1');
    expect(renderMergeFields('{{set.members}}', data, 'print')).toContain('MR-1');
  });

  it('a product block has no members, so the token is empty', () => {
    expect(renderMergeFields('[{{set.members}}]', product(), 'print')).toBe('[]');
  });

  it('quantity resolves only against a request line', () => {
    expect(renderMergeFields('{{line.quantity}}', line(), 'print')).toBe('3');
    expect(renderMergeFields('[{{line.quantity}}]', product(), 'print')).toBe('[]');
  });

  it('a line answers the product paths, because the tag is about that line', () => {
    const data = line();

    expect(renderMergeFields('{{product.code}}', data, 'print')).toBe('CBF3612');
    expect(renderMergeFields('{{product.included_accessories}}', data, 'print')).toBe(
      'Waste and trap',
    );
    expect(renderMergeFields('{{spec.material}}', data, 'print')).toBe(
      'stainless steel',
    );
  });

  it("a line with the promo switched off prints no sell price, as the badge does", () => {
    expect(
      renderMergeFields('[{{product.sell_price}}]', line({ show_promo_price: false }), 'print'),
    ).toBe('[]');
  });
});

// ---------------------------------------------------------------------------
// Unknown tokens and the two modes
// ---------------------------------------------------------------------------

describe('renderMergeFields - what is left when nothing resolves', () => {
  it('an unknown path renders empty in print', () => {
    expect(renderMergeFields('[{{product.colour}}]', product(), 'print')).toBe('[]');
    expect(renderMergeFields('[{{nonsense}}]', product(), 'print')).toBe('[]');
  });

  it('text with no token comes back untouched', () => {
    expect(renderMergeFields('Plain words', product(), 'print')).toBe('Plain words');
    expect(renderMergeFields('Plain words', null, 'editor')).toBe('Plain words');
  });

  it('the editor draws the token itself while nothing is previewed', () => {
    expect(renderMergeFields('{{spec.material}}', null, 'editor')).toBe(
      '{{spec.material}}',
    );
  });

  it('print draws nothing where the editor drew the token', () => {
    expect(renderMergeFields('[{{spec.material}}]', null, 'print')).toBe('[]');
  });

  it('once data arrives the editor shows the value, not the token', () => {
    expect(renderMergeFields('{{spec.material}}', product(), 'editor')).toBe(
      'stainless steel',
    );
  });
});

describe('hasMergeField', () => {
  it('answers for a token anywhere in the text', () => {
    expect(hasMergeField('Made of {{spec.material}}')).toBe(true);
    expect(hasMergeField('{{ product.code }}')).toBe(true);
  });

  it('is false for plain text, empty text and nothing at all', () => {
    expect(hasMergeField('Made of steel')).toBe(false);
    expect(hasMergeField('')).toBe(false);
    expect(hasMergeField(null)).toBe(false);
    expect(hasMergeField('{ not a token }')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// The catalogue the Insert field dialog lists
// ---------------------------------------------------------------------------

describe('mergeFieldCatalog', () => {
  const catalog = mergeFieldCatalog([
    { key: 'material', label: 'Material', unit: null },
    { key: 'diameter', label: 'Diameter', unit: 'mm' },
  ]);

  it('offers the fixed groups plus one entry per registry key', () => {
    const groups = new Set(catalog.map((field) => field.group));
    expect(groups).toEqual(new Set(['Product', 'Specs', 'Set', 'Line']));

    const specs = catalog.filter((field) => field.group === 'Specs');
    expect(specs.map((field) => field.token)).toEqual([
      '{{spec.material}}',
      '{{spec.diameter}}',
    ]);
    // The unit rides in the label, so the designer can see what will print.
    expect(specs[1].label).toBe('Diameter (mm)');
  });

  it('every token it offers is one this resolver answers', () => {
    const data = product();
    for (const field of catalog) {
      expect(renderMergeFields(field.token, data, 'print')).not.toBe(field.token);
    }
  });

  it('has no spec group entries when the registry is empty', () => {
    expect(mergeFieldCatalog([]).some((field) => field.group === 'Specs')).toBe(false);
  });

  it('names each field for a person, never as a raw path', () => {
    const code = catalog.find((field) => field.path === 'product.code');
    expect(code?.label).toBe('Code');
    expect(code?.token).toBe('{{product.code}}');
  });
});

// ---------------------------------------------------------------------------
// Parity: the canvas and the PDF resolve the same words
// ---------------------------------------------------------------------------

describe('the print page and the canvas resolve a token identically', () => {
  const CONTENT = '{{product.code}} in {{spec.material}} at {{product.sell_price}}';

  function printDoc(layers: TagLayer[]): TagSheetDoc {
    return {
      kind: 'tag_sheet',
      imposition: {
        preset: 'a4_3up',
        page_width_mm: 210,
        page_height_mm: 297,
        bleed_mm: 0,
        gap_mm: 2,
      },
      sheets: [
        {
          id: 's1',
          tags: [
            {
              id: 't1',
              template_id: 'tpl-1',
              request_line_id: 'line-1',
              x_mm: 0,
              y_mm: 0,
              width_mm: 95,
              height_mm: 130,
              layers,
            },
          ],
        },
      ],
    };
  }

  it('renders the same text through layerText and through the print DOM', () => {
    const layer = textLayer(CONTENT);
    const resolved: ResolvedLineData = lineData();

    const onCanvas = layerText(layer, { kind: 'line', line: lineData() }, 'print');

    render(
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'line-1': resolved }} />,
    );

    expect(onCanvas).toBe('CBF3612 in stainless steel at RM 599');
    expect(screen.getByText(onCanvas)).toBeTruthy();
  });

  it('a slot-bound layer typed over with a token resolves on both surfaces', () => {
    const layer: TagLayer = {
      ...textLayer('placeholder'),
      slot_binding: 'name',
      text_override: 'Model {{product.code}}',
    };
    const resolved: ResolvedLineData = lineData();

    const onCanvas = layerText(layer, { kind: 'line', line: lineData() }, 'print');

    render(
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'line-1': resolved }} />,
    );

    expect(onCanvas).toBe('Model CBF3612');
    expect(screen.getByText('Model CBF3612')).toBeTruthy();
  });

  it('a plain slot-bound layer still prints its bound value, untouched', () => {
    const layer: TagLayer = { ...textLayer('placeholder'), slot_binding: 'name' };
    const resolved: ResolvedLineData = lineData();

    render(
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'line-1': resolved }} />,
    );

    expect(screen.getByText('Kitchen Sink')).toBeTruthy();
  });
});
