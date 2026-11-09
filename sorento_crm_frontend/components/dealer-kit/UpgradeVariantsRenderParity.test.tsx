/**
 * PRICETAG-UPGRADE-VARIANTS FE test 7 (AC-U9): the canvas (`KonvaTagLayer` fed `layerDisplay`) and
 * the print page (`TagSheetRenderer`) draw the SAME number of feature icons, the same size and the
 * same spacing, for (a) a `feature_icons` card element of an Upgrades box and (b) a feature icons
 * layer on "All variants". Plus: the layout function feeding both gives one set of element rects.
 *
 * Written test-FIRST. The card has no picture element so every image drawn is a feature icon.
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));
vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => undefined),
}));
vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-x={String(props.x ?? 0)}
          data-y={String(props.y ?? 0)}
          data-w={String(props.width ?? '')}
          data-h={String(props.height ?? '')}
          data-text={String(props.text ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
  };
});

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import { cardElementsFor } from '@/lib/dealer-kit/accessory-card';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import {
  FAMILY_VARIANTS,
  familyLine,
  icon,
  sinkLine,
  SUS_ICON,
  TRAP_ICONS,
} from '@/lib/dealer-kit/test-support/upgrade-variants-fixtures';
import {
  defaultAccessoriesProps,
  type TagBindingData,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';

class StubImage {
  width = 100;
  height = 100;
  onload: (() => void) | null = null;
  set src(_v: string) {
    Promise.resolve().then(() => this.onload?.());
  }
}
beforeEach(() => vi.stubGlobal('Image', StubImage));
afterEach(() => cleanup());

const SCALE = 4;
const SUS2 = icon('nano', 'Nano', 'finish', ['nano']);
const UPGRADE_ICONS = [SUS_ICON, SUS2];
const URLS: Record<string, string> = Object.fromEntries(
  [...TRAP_ICONS, ...UPGRADE_ICONS].map((i) => [i.id, `https://cdn/${i.id}.png`]),
);

const CARD = {
  width_mm: 71,
  height_mm: 21.5,
  elements: [
    { id: 'code', kind: 'text', field: 'code', x_mm: 17, y_mm: 1, width_mm: 50, height_mm: 4, fontSize: 9 },
    { id: 'fi', kind: 'feature_icons', x_mm: 17, y_mm: 6, width_mm: 50, height_mm: 6, iconSize_mm: 4.6, gap_mm: 0.8, align: 'left' },
  ],
};

const upgradesBox = (): TagLayer =>
  ({
    id: 'up', type: 'accessories', x_mm: 3, y_mm: 4, width_mm: 75, height_mm: 40, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), list: 'upgrades', card: CARD, headerText: 'UPGRADE' },
  }) as unknown as TagLayer;

const variantsLayer = (): TagLayer =>
  ({
    id: 'fv', type: 'feature_icons', x_mm: 3, y_mm: 4, width_mm: 60, height_mm: 8, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 6, gap_mm: 1, align: 'left', subjectSlot: { kind: 'variants' } },
  }) as unknown as TagLayer;

function sheet(layer: TagLayer): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [{ id: 's1', tags: [{ id: 't-t1', template_id: 'tpl', request_tag_id: 't1', x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] }] }],
  } as TagSheetDoc;
}

const rowOf = (data: TagBindingData) => (data.kind === 'line' ? data.line : null) as unknown as ResolvedLineData;

function printIcons(layer: TagLayer, data: TagBindingData, icons = TRAP_ICONS) {
  const { container } = render(
    <TagSheetRenderer doc={sheet(layer)} resolvedData={{ t1: rowOf(data) }} assets={URLS} featureIcons={icons} />,
  );
  return [...container.querySelectorAll<HTMLImageElement>('img')].map((img) => ({
    left: parseFloat(img.style.left),
    size: parseFloat(img.style.width),
  }));
}

async function canvasIcons(layer: TagLayer, data: TagBindingData, icons = TRAP_ICONS) {
  const display = layerDisplay(layer, data, URLS, icons);
  const { container } = render(<KonvaTagLayer layer={layer} scale={SCALE} display={display} />);
  await act(async () => {
    await Promise.resolve();
  });
  return [...container.querySelectorAll<HTMLElement>('[data-konva="image"]')].map((node) => {
    // Absolute x: the node's own offset plus every ancestor's, up to the root.
    let x = 0;
    for (let cur: HTMLElement | null = node; cur && cur !== container; cur = cur.parentElement) {
      x += Number(cur.getAttribute('data-x') ?? 0);
    }
    return { left: x / SCALE, size: Number(node.getAttribute('data-w')) / SCALE };
  });
}

const spacing = (list: { left: number }[]) => list.slice(1).map((c, i) => c.left - list[i].left);

describe('the Upgrades card icons', () => {
  const data = () => {
    const d = sinkLine();
    // The upgrade's two matching icons (SUS 304 and nano) come from its own specs.
    const upgrade = (d as never as { line: { slots: { upgrades: { specs: unknown[] }[] } } }).line.slots.upgrades[0];
    upgrade.specs = [
      { key: 'steel_grade', label: 'steel_grade', value: 'SUS 304', unit: null, raw: '304' },
      { key: 'finish', label: 'finish', value: 'Nano', unit: null, raw: 'nano' },
    ];
    return d;
  };

  it('both renderers draw the same icons, size and spacing', async () => {
    const layer = upgradesBox();
    const print = printIcons(layer, data(), UPGRADE_ICONS);
    const canvas = await canvasIcons(layer, data(), UPGRADE_ICONS);
    expect(print).toHaveLength(2);
    expect(canvas).toHaveLength(print.length);
    expect(canvas.map((c) => c.size)).toEqual(print.map((p) => p.size));
    spacing(canvas).forEach((gap, i) => expect(gap).toBeCloseTo(spacing(print)[i], 5));
  });

  it('an upgrade with no matching icon draws none on either surface (dropped, closes up)', async () => {
    const bare = sinkLine();
    expect(printIcons(upgradesBox(), bare, TRAP_ICONS)).toHaveLength(0);
    expect(await canvasIcons(upgradesBox(), bare, TRAP_ICONS)).toHaveLength(0);
  });

  it('the one layout function (cardElementsFor) hands both renderers the same element rects', () => {
    const item = { kind: 'upgrade', id: 'u', code: 'SRTKT71SS', name: 'x', spec: null, image: null,
      specs: [{ key: 'steel_grade', label: 's', value: '304', unit: null, raw: '304' }] } as never;
    const a = cardElementsFor(item, CARD as never, UPGRADE_ICONS);
    const b = cardElementsFor(item, JSON.parse(JSON.stringify(CARD)), UPGRADE_ICONS);
    const rects = (list: typeof a) => list.map(({ id, x_mm, y_mm, width_mm, height_mm }) => ({ id, x_mm, y_mm, width_mm, height_mm }));
    expect(rects(a)).toEqual(rects(b));
    expect(a.map((e) => e.id)).toEqual(['code', 'fi']);
  });
});

describe('the "All variants" layer', () => {
  it('both renderers draw the same icons, size and spacing', async () => {
    const layer = variantsLayer();
    const data = familyLine(FAMILY_VARIANTS);
    const print = printIcons(layer, data);
    const canvas = await canvasIcons(layer, data);
    expect(print).toHaveLength(5);
    expect(canvas).toHaveLength(5);
    expect(canvas.map((c) => c.size)).toEqual(print.map((p) => p.size));
    spacing(canvas).forEach((gap, i) => expect(gap).toBeCloseTo(spacing(print)[i], 5));
  });

  it('a leaf line draws only its own icon on both', async () => {
    const leaf = familyLine([]);
    expect(printIcons(variantsLayer(), leaf)).toHaveLength(1);
    expect(await canvasIcons(variantsLayer(), leaf)).toHaveLength(1);
  });
});
