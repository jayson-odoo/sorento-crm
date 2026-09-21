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
  hasSubjectAwareToken,
  mergeFieldCatalog,
  renderMergeFields,
  soleMergeField,
} from './merge-fields';
import { layerText } from './product-block';
import type {
  LineTagData,
  ProductSetTagData,
  ProductTagData,
  TagBindingData,
  TagLayer,
  TagPartData,
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
      barcode: null,
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
    tag_id: 'tag-1',
    line_id: 'line-1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
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
    barcode: null,
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

  it('AC-A3: prices render the bare figure - grouped, no RM prefix, matching the text-slot rule (AC-A1/A2)', () => {
    const data = product();

    expect(renderMergeFields('{{product.list_price}}', data, 'print')).toBe('1,599');
    expect(renderMergeFields('{{product.sell_price}}', data, 'print')).toBe('599');
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

  it('draws nothing for a name that only repeats the code (S2, AC-S2-2)', () => {
    const data = product({ name: 'CBF3612' });
    expect(renderMergeFields('[{{product.name}}]', data, 'print')).toBe('[]');
  });
});

describe('renderMergeFields - spec paths', () => {
  // AC-S15-1 (PLAN-price-tag-ai-extract-resolver.md D20): the unit is the
  // designer's to type - `specText` answers the bare value now, never
  // "value unit" - so a composed string like `L{{spec.dim_length}}XW...mm`
  // does not print a doubled unit.
  it('renders a spec value alone, with no unit appended (AC-S15-1)', () => {
    expect(renderMergeFields('{{spec.diameter}}', product(), 'print')).toBe('407');
  });

  it('composes several bare spec values inside one literal string (AC-S15-1)', () => {
    const data = product({
      specs: [
        { key: 'dim_length', label: 'Length', value: '860', unit: 'mm' },
        { key: 'dim_width', label: 'Width', value: '480', unit: 'mm' },
        { key: 'dim_height', label: 'Height', value: '250', unit: 'mm' },
      ],
    });
    expect(
      renderMergeFields(
        'L{{spec.dim_length}}XW{{spec.dim_width}}XH{{spec.dim_height}}mm',
        data,
        'print',
      ),
    ).toBe('L860XW480XH250mm');
  });

  it('{{product.dimensions}} still renders the composed slot string unchanged (AC-S15-1)', () => {
    expect(renderMergeFields('{{product.dimensions}}', product(), 'print')).toBe(
      '800 x 500 x 220 mm',
    );
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
// AC-S18-1/S18-2 (PLAN-price-tag-ai-extract-resolver.md D23): the parts on a
// tag, as two Line-group merge fields.
// ---------------------------------------------------------------------------

describe('renderMergeFields - line.parts / line.parts_names paths (S18)', () => {
  it('AC-S18-1: {{line.parts}} joins the resolved parts\' codes with ", "', () => {
    const data = line({
      parts: [
        { product_id: 'p-mirror', code: 'SRTMR502-BL', name: 'ZZT Mirror', dimensions: '' },
      ],
    });
    expect(renderMergeFields('{{line.parts}}', data, 'print')).toBe('SRTMR502-BL');
  });

  it('AC-S18-1: two parts join with ", " for both codes and names', () => {
    const data = line({
      parts: [
        { product_id: 'p1', code: 'SRTKT71SS-BL', name: 'ZZT Kitchen Tap', dimensions: '' },
        { product_id: 'p2', code: 'SRTMR502-BL', name: 'ZZT Mirror', dimensions: '' },
      ],
    });
    expect(renderMergeFields('{{line.parts}}', data, 'print')).toBe(
      'SRTKT71SS-BL, SRTMR502-BL',
    );
    expect(renderMergeFields('{{line.parts_names}}', data, 'print')).toBe(
      'ZZT Kitchen Tap, ZZT Mirror',
    );
  });

  it('AC-S18-2: on a line with no parts, both resolve to an empty string', () => {
    expect(renderMergeFields('[{{line.parts}}]', line(), 'print')).toBe('[]');
    expect(renderMergeFields('[{{line.parts_names}}]', line(), 'print')).toBe('[]');
  });

  it('AC-S18-2: on a product binding, both resolve to null - the token\'s unanswered form', () => {
    expect(renderMergeFields('[{{line.parts}}]', product(), 'print')).toBe('[]');
    expect(renderMergeFields('[{{line.parts_names}}]', product(), 'print')).toBe('[]');
    // Unanswered on a BOUND (non-null) binding still draws nothing, even in
    // editor mode - only a fully absent binding falls back to the raw token
    // (mirrors {{line.quantity}} on a product binding, above).
    expect(renderMergeFields('{{line.parts}}', product(), 'editor')).toBe('');
  });
});

// ---------------------------------------------------------------------------
// {{product.currency}} (AC-A5 to AC-A9): the SUBJECT's own currency, never a
// slot binding - `hasSubjectAwareToken` already treats every `product.*` path
// as subject-aware, so D7's part-subject picker applies here with no change.
// ---------------------------------------------------------------------------

describe('renderMergeFields - product.currency (AC-A5 to AC-A9)', () => {
  it('AC-A5: renders the bound product\'s own currency', () => {
    expect(
      renderMergeFields('{{product.currency}}', product({ currency: 'MYR' }), 'print'),
    ).toBe('MYR');
    expect(
      renderMergeFields('{{product.currency}}', product({ currency: 'SGD' }), 'print'),
    ).toBe('SGD');
  });

  it('AC-A6: on a line-bound tag renders the LINE\'s own currency', () => {
    expect(
      renderMergeFields('{{product.currency}}', line({ currency: 'SGD' }), 'print'),
    ).toBe('SGD');
  });

  it('AC-A6: on a set renders the SET\'s own currency', () => {
    expect(
      renderMergeFields('{{product.currency}}', set({ currency: 'SGD' }), 'print'),
    ).toBe('SGD');
  });

  it('AC-A6: a layer with a part subject (subjectPart: n) renders that PART\'s currency, not the parent\'s (D7)', () => {
    const part: TagPartData = {
      product_id: 'part-1',
      code: 'PART-1',
      name: 'Part One',
      dimensions: '',
      currency: 'SGD',
    };
    const data = line({ currency: 'MYR', parts: [part] });
    const layer = { props: { kind: 'text' as const, subjectPart: 0 } };

    expect(renderMergeFields('{{product.currency}}', data, 'print', layer)).toBe('SGD');
  });

  it('AC-A7: a payload with no currency field (an older pinned row) renders MYR, never empty or the raw token', () => {
    const data = product({ currency: undefined });
    expect(renderMergeFields('{{product.currency}}', data, 'print')).toBe('MYR');
    expect(renderMergeFields('{{product.currency}}', data, 'editor')).toBe('MYR');
  });

  it('AC-A9: hasSubjectAwareToken is true for {{product.currency}}, so the subject picker shows', () => {
    expect(hasSubjectAwareToken('{{product.currency}}')).toBe(true);
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

describe('soleMergeField', () => {
  it('answers the token when the whole (trimmed) text is exactly one token', () => {
    expect(soleMergeField('{{product.code}}')).toBe('{{product.code}}');
    expect(soleMergeField('  {{product.code}}  ')).toBe('{{product.code}}');
    expect(soleMergeField('{{ product.code }}')).toBe('{{ product.code }}');
  });

  it('is null for mixed text, plain text, and no text', () => {
    expect(soleMergeField('Code {{product.code}}')).toBeNull();
    expect(soleMergeField('{{product.code}} - {{spec.material}}')).toBeNull();
    expect(soleMergeField('Plain words')).toBeNull();
    expect(soleMergeField('')).toBeNull();
    expect(soleMergeField(null)).toBeNull();
    expect(soleMergeField(undefined)).toBeNull();
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

  it('AC-S18-1: lists "Parts (codes)" and "Parts (names)" in the Line group', () => {
    const lineFields = catalog.filter((field) => field.group === 'Line');
    const codes = lineFields.find((field) => field.path === 'line.parts');
    const names = lineFields.find((field) => field.path === 'line.parts_names');
    expect(codes).toMatchObject({ label: 'Parts (codes)', token: '{{line.parts}}' });
    expect(names).toMatchObject({ label: 'Parts (names)', token: '{{line.parts_names}}' });
  });

  it('AC-A8: lists product.currency labelled Currency in the Product group, right after Sell price', () => {
    const productFields = catalog.filter((field) => field.group === 'Product');
    const sellIndex = productFields.findIndex((field) => field.path === 'product.sell_price');
    const currencyIndex = productFields.findIndex((field) => field.path === 'product.currency');

    expect(sellIndex).toBeGreaterThanOrEqual(0);
    expect(currencyIndex).toBe(sellIndex + 1);
    expect(productFields[currencyIndex]).toMatchObject({
      label: 'Currency',
      token: '{{product.currency}}',
      group: 'Product',
    });
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
              request_tag_id: 'tag-1',
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
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'tag-1': resolved }} />,
    );

    // AC-A3: the price token is bare since this feature - no RM prefix.
    expect(onCanvas).toBe('CBF3612 in stainless steel at 599');
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
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'tag-1': resolved }} />,
    );

    expect(onCanvas).toBe('Model CBF3612');
    expect(screen.getByText('Model CBF3612')).toBeTruthy();
  });

  it('a plain slot-bound layer still prints its bound value, untouched', () => {
    const layer: TagLayer = { ...textLayer('placeholder'), slot_binding: 'name' };
    const resolved: ResolvedLineData = lineData();

    render(
      <TagSheetRenderer doc={printDoc([layer])} resolvedData={{ 'tag-1': resolved }} />,
    );

    expect(screen.getByText('Kitchen Sink')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// AC-S4-5/S4-6/S4-7 (PLAN-price-tag-r10.md S4): `{{product.price_tag_
// description}}` - a subject-aware token like every other `product.*` field
// (subjectPart/Parent resolution is generic across PATH_SLOTS, already
// covered for every other product field; this pins the token's own entry).
// ---------------------------------------------------------------------------

describe('renderMergeFields - product.price_tag_description (AC-S4-5/S4-6)', () => {
  it('renders the line text verbatim, including line breaks', () => {
    const data = product({
      price_tag_description: 'Made in Malaysia\nStainless steel',
    } as Partial<ProductTagData>);

    expect(renderMergeFields('{{product.price_tag_description}}', data, 'print')).toBe(
      'Made in Malaysia\nStainless steel',
    );
  });

  it('AC-S4-6: an empty description renders an empty string, never spec_lines or description', () => {
    const data = product({ price_tag_description: null } as Partial<ProductTagData>);

    expect(renderMergeFields('[{{product.price_tag_description}}]', data, 'print')).toBe('[]');
  });
});

// ---------------------------------------------------------------------------
// AC-S4-13 (owner amendment 21 Sep, S11, amends AC-S4-5): the stored
// `price_tag_description` is a per-product TEMPLATE now, not plain text -
// `resolvePath` renders it ONE MORE TIME against the same subject's own
// data before it reaches the tag. Written test-FIRST: today `resolvePath`
// still returns the raw stored text unexpanded (a plain `PATH_SLOTS` read),
// so every test below but the last is red on that raw, unexpanded text.
// ---------------------------------------------------------------------------

describe('renderMergeFields - product.price_tag_description is a template (AC-S4-13, S11)', () => {
  it('a stored template resolves its own tokens against the SAME subject', () => {
    const data = product({
      name: 'Basin Tap',
      price_tag_description: '{{product.name}} in {{spec.material}}',
      specs: [{ key: 'material', label: 'Material', value: 'Stainless Steel', unit: null }],
    } as Partial<ProductTagData>);

    expect(renderMergeFields('{{product.price_tag_description}}', data, 'print')).toBe(
      'Basin Tap in Stainless Steel',
    );
  });

  it("with subjectPart: n the PART's own stored template renders against the PART's own data, not the parent's", () => {
    const part: TagPartData = {
      product_id: 'part-2',
      code: 'PART-2',
      name: 'Part Two',
      dimensions: '',
      specs: [{ key: 'finish', label: 'Finish', value: 'Matte black', unit: null }],
      price_tag_description: '{{product.code}} - {{spec.finish}}',
    };
    const data = line({
      price_tag_description: '{{product.name}} - parent template',
      parts: [
        { product_id: 'part-1', code: 'PART-1', name: 'Part One', dimensions: '' },
        part,
      ],
    });
    const layer = { props: { kind: 'text' as const, subjectPart: 1 } };

    expect(renderMergeFields('{{product.price_tag_description}}', data, 'print', layer)).toBe(
      'PART-2 - Matte black',
    );
  });

  it('a SPEC VALUE that itself contains the literal text {{product.name}} is never re-expanded - one pass only', () => {
    const data = product({
      name: 'Basin Tap',
      price_tag_description: '{{spec.material}}',
      specs: [
        { key: 'material', label: 'Material', value: 'Contains {{product.name}} literally', unit: null },
      ],
    } as Partial<ProductTagData>);

    expect(renderMergeFields('{{product.price_tag_description}}', data, 'print')).toBe(
      'Contains {{product.name}} literally',
    );
  });

  it('a template naming a token the data cannot answer renders that token empty, the rest of the sentence intact', () => {
    const data = product({
      price_tag_description: '[{{spec.nonexistent}} tap]',
      specs: [],
    } as Partial<ProductTagData>);

    expect(renderMergeFields('{{product.price_tag_description}}', data, 'print')).toBe('[ tap]');
  });

  it('an empty stored template still renders empty (Q5, unchanged)', () => {
    const data = product({ price_tag_description: '' } as Partial<ProductTagData>);

    expect(renderMergeFields('[{{product.price_tag_description}}]', data, 'print')).toBe('[]');
  });
});

describe('mergeFieldCatalog - Price tag description (AC-S4-7)', () => {
  it('lists Price tag description in group Product, directly after Spec lines', () => {
    const catalog = mergeFieldCatalog([]);
    const productFields = catalog.filter((field) => field.group === 'Product');
    const labels = productFields.map((field) => field.label);

    expect(labels).toContain('Price tag description');
    const specIndex = labels.indexOf('Spec lines');
    const descriptionIndex = labels.indexOf('Price tag description');
    expect(specIndex).toBeGreaterThanOrEqual(0);
    expect(descriptionIndex).toBe(specIndex + 1);
  });
});

// ---------------------------------------------------------------------------
// AC-S3-5 (PLAN-price-tag-r10.md S3): the FE is a pure pass-through for a
// spec value - S3's title-casing happens server-side (`_spec_display_value`),
// so a payload row that already carries "Stainless Steel" must render
// exactly that, unchanged.
// ---------------------------------------------------------------------------

describe('renderMergeFields - spec.material pass-through (AC-S3-5)', () => {
  it('renders a backend-formatted value unchanged, no client-side re-casing', () => {
    const data = product({
      specs: [{ key: 'material', label: 'Material', value: 'Stainless Steel', unit: null }],
    });

    expect(renderMergeFields('{{spec.material}}', data, 'print')).toBe('Stainless Steel');
  });
});
