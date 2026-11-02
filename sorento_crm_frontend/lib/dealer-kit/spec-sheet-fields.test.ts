/**
 * PS-SPEC-SHEET: the shared tag-template pieces a project spec sheet page reads through.
 *
 * Every price tag must read exactly as before: a layer with no `show_when` prints, a line
 * without `strict_parts` still falls back to the parent, and the spec sheet tokens never
 * resolve on a price tag row.
 */
import { describe, expect, it } from 'vitest';

import { renderMergeFields } from './merge-fields';
import { layerShownFor, slotImageAttachmentId, slotImagesOf, resolveSlotText } from './product-block';
import {
  defaultImageProps,
  defaultTextProps,
  familyLabel,
  isSpecSheetFamily,
  TAG_TEMPLATE_FAMILIES,
  type LineTagData,
  type TagBindingData,
  type TagLayer,
} from './tag-template-types';

function layer(over: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 0,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultTextProps(),
    ...over,
  };
}

const DOC = {
  project_title: 'Proposed 3 blocks of 30 storey apartments',
  ref: 'QS/2026/7',
  your_ref: 'QS/2026/7',
  quotation_no: 'SRT/Q/2026/0141 (R1)',
  prepared_by: 'Sales A',
  prepared_by_phone: '012-000 0000',
  date: '02 NOV 2026',
};

function specLine(over: Partial<LineTagData> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 'set:1',
      line_id: 'line-1',
      tag_label: '2',
      open_groups: [],
      parts: [
        {
          code: 'SRTAV0010',
          name: 'Angle valve',
          dimensions: '',
          brand: 'SORENTO',
          images: [{ attachment_id: 'av-photo', url: 'https://x/av', is_primary: true }],
          drawing: { attachment_id: 'av-drawing', url: 'https://x/avd', is_primary: true },
        },
      ],
      code: 'SRTWC0001-RL',
      name: 'Wall hung WC',
      dimensions: '540 x 360 x 350 mm',
      spec_lines: '',
      specs: [{ key: 'is_rimless', label: 'Rimless', value: 'Yes', unit: null }],
      set_members: '',
      images: [{ attachment_id: 'wc-photo', url: 'https://x/wc', is_primary: true }],
      list_price: null,
      sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      brand: 'SORENTO',
      drawing: { attachment_id: 'wc-drawing', url: 'https://x/wcd', is_primary: true },
      area: 'UNIT & PODIUM',
      comment: 'Soft close',
      marker: '**',
      doc: DOC,
      strict_parts: true,
      ...over,
    },
  };
}

function priceTagLine(): TagBindingData {
  const data = specLine();
  if (data.kind !== 'line') throw new Error('line');
  // A price tag row carries none of the spec sheet fields.
  const line: Partial<LineTagData> = { ...data.line };
  for (const field of ['doc', 'area', 'comment', 'marker', 'strict_parts', 'brand', 'drawing'] as const) {
    delete line[field];
  }
  return { kind: 'line', line: line as LineTagData };
}

describe('spec sheet merge fields', () => {
  it('print the document and page fields on a spec sheet row', () => {
    const text =
      '{{doc.project_title}}|{{doc.ref}}|{{doc.your_ref}}|{{doc.quotation_no}}|{{doc.prepared_by}} {{doc.prepared_by_phone}}|{{doc.date}}|{{line.area}}|{{line.comment}}|{{line.marker}}|{{product.brand}} {{product.code}}';
    expect(renderMergeFields(text, specLine(), 'print')).toBe(
      `${DOC.project_title}|QS/2026/7|QS/2026/7|SRT/Q/2026/0141 (R1)|Sales A 012-000 0000|02 NOV 2026|UNIT & PODIUM|Soft close|**|SORENTO SRTWC0001-RL`,
    );
  });

  it('print nothing on a price tag and show the token in the editor', () => {
    const text = '{{doc.ref}}{{line.area}}{{product.brand}}';
    expect(renderMergeFields(text, priceTagLine(), 'print')).toBe('');
    expect(renderMergeFields(text, priceTagLine(), 'editor')).toBe(text);
  });

  it('read a part brand through the layer subject', () => {
    const accessory = layer({ props: { ...defaultTextProps(), subjectPart: 0 } as TagLayer['props'] });
    expect(renderMergeFields('{{product.brand}} {{product.code}}', specLine(), 'print', accessory)).toBe(
      'SORENTO SRTAV0010',
    );
  });
});

describe('strict parts', () => {
  it('a layer pointed at a missing accessory prints blank on a spec sheet page', () => {
    const second = layer({
      slot_binding: 'code',
      props: { ...defaultTextProps(), subjectPart: 1 } as TagLayer['props'],
    });
    expect(resolveSlotText(second, specLine())).toBe('');
  });

  it('still falls back to the parent on a price tag (unchanged)', () => {
    const second = layer({
      slot_binding: 'code',
      props: { ...defaultTextProps(), subjectPart: 1 } as TagLayer['props'],
    });
    expect(resolveSlotText(second, priceTagLine())).toBe('SRTWC0001-RL');
  });
});

describe('drawing slot', () => {
  const image = (subjectPart?: number) =>
    layer({
      type: 'image',
      slot_binding: 'drawing',
      props: { ...defaultImageProps(), ...(subjectPart != null ? { subjectPart } : {}) } as TagLayer['props'],
    });

  it('draws the main item drawing, never its photo', () => {
    const images = slotImagesOf(image(), specLine());
    expect(slotImageAttachmentId(image(), images)).toBe('wc-drawing');
  });

  it('draws an accessory drawing through its subject, and nothing when there is none', () => {
    const images = slotImagesOf(image(0), specLine());
    expect(slotImageAttachmentId(image(0), images)).toBe('av-drawing');
    expect(slotImagesOf(image(), specLine({ drawing: null }))).toEqual([]);
  });

  it('leaves the product photo slot alone', () => {
    const photo = layer({ type: 'image', slot_binding: 'product_image', props: defaultImageProps() });
    expect(slotImageAttachmentId(photo, slotImagesOf(photo, specLine()))).toBe('wc-photo');
  });
});

describe('show_when', () => {
  it('a layer with no condition always prints (every price tag)', () => {
    expect(layerShownFor(layer(), specLine())).toBe(true);
    expect(layerShownFor(layer(), null)).toBe(true);
  });

  it('an accessory row prints only when the page has that accessory', () => {
    expect(layerShownFor(layer({ show_when: { part: 0 } }), specLine())).toBe(true);
    expect(layerShownFor(layer({ show_when: { part: 1 } }), specLine())).toBe(false);
    expect(layerShownFor(layer({ show_when: { part: 0 } }), specLine({ parts: [] }))).toBe(false);
  });

  it('a badge prints only when its spec reads Yes', () => {
    expect(layerShownFor(layer({ show_when: { spec: 'is_rimless' } }), specLine())).toBe(true);
    expect(layerShownFor(layer({ show_when: { spec: 'is_accessible' } }), specLine())).toBe(false);
    expect(
      layerShownFor(
        layer({ show_when: { spec: 'is_rimless' } }),
        specLine({ specs: [{ key: 'is_rimless', label: 'Rimless', value: 'No', unit: null }] }),
      ),
    ).toBe(false);
  });
});

describe('families', () => {
  it('spec sheet families are labelled and never price tag families', () => {
    expect(familyLabel('spec_cover')).toBe('Spec sheet cover');
    expect(familyLabel('spec_page')).toBe('Spec sheet page');
    expect(isSpecSheetFamily('spec_page')).toBe(true);
    expect(isSpecSheetFamily('wc')).toBe(false);
    expect(TAG_TEMPLATE_FAMILIES.some((f) => isSpecSheetFamily(f.value))).toBe(false);
  });
});
