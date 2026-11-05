/**
 * E1 from the PRICETAG-COMBO-FORMAT card: the SRTBF11416 combo description as the owner formats
 * it by hand in the editor. Bold codes and MIRROR / SHELF, grey part names and dimensions.
 *
 * The card prints only the first two paragraphs; the other ten follow the same pattern
 * (6 bold code / label lines, 6 grey dimension lines = 12 paragraphs). Shared by the parser,
 * line-breaking, canvas, print and parity tests so they all read the one description.
 */

const GREY = '#6b7280';
const grey = (text: string) => `<span style="color: ${GREY}">${text}</span>`;

const PAIRS: Array<[string, string, string]> = [
  ['SRTBF11416', '(CABINET)', 'L400xW345xH390mm'],
  ['SRTWB248', '(BASIN)', 'L600xW460xH170mm'],
  ['MIRROR', '(LED)', 'L600xH800mm'],
  ['SHELF', '(GLASS)', 'L600xW120mm'],
  ['SRTWT5837', '(TAP)', 'H150mm'],
  ['SRTW2600', '(WASTE)', 'D32mm'],
];

export const E1_GREY = GREY;
export const E1_BOLD_WORDS = PAIRS.map(([word]) => word);
export const E1_DIMENSIONS = PAIRS.map(([, , dimension]) => dimension);

export const E1_HTML = PAIRS.map(
  ([word, name, dimension]) =>
    `<p><strong>${word}</strong> ${grey(name)}</p><p>${grey(dimension)}</p>`,
).join('');

/** What every plain-text reader gets. */
export const E1_PLAIN = PAIRS.flatMap(([word, name, dimension]) => [
  `${word} ${name}`,
  dimension,
]).join('\n');

/** A description that uses every toolbar item once (AC-18). */
export const EVERY_ITEM_HTML =
  '<h1>Title</h1>' +
  '<p><strong>b</strong><em>i</em><u>u</u><s>s</s><code>c</code>' +
  `${grey('g')}<mark style="background-color: #fde68a">h</mark></p>` +
  '<ul><li>x</li></ul><ol><li>y</li></ol>' +
  '<blockquote><p>q</p></blockquote>' +
  '<p style="text-align: center">m</p>' +
  '<p><a>l</a></p>';

import type { TagLayer, TagSheetDoc, TextLayerProps } from './tag-template-types';

/** A text layer whose own text is `text` (no binding), in a box big enough for E1 at 10 pt. */
export function richTextLayer(
  text: string,
  over: Partial<TagLayer> = {},
  props: Partial<TextLayerProps> = {},
): TagLayer {
  return {
    id: 'desc',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 200,
    height_mm: 120,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text,
      fontFamily: 'DM Sans',
      fontSize: 10,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      ...props,
    },
    ...over,
  } as TagLayer;
}

export function tagSheetDocWith(layer: TagLayer): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 't1',
            template_id: 'tpl-1',
            request_tag_id: null,
            x_mm: 0,
            y_mm: 0,
            width_mm: 200,
            height_mm: 120,
            layers: [layer],
          },
        ],
      },
    ],
  } as unknown as TagSheetDoc;
}
