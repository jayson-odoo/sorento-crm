/**
 * Keyboard nudge step sizes (S2, PLAN D2, AC-S2-1/2/3).
 *
 * `TagCanvasEditor.tsx` moved the arrow-key nudge from Figma's own
 * 1mm/0.1mm to `NUDGE_MM = { base: 0.25, shift: 1, alt: 0.1 }` - too coarse
 * on a 60mm tag otherwise. This pins the WIRING: which modifier maps to
 * which delta, that a locked layer refuses to move at all, and that a
 * group moves once with every child rather than each child nudging
 * separately.
 *
 * Konva does not run in jsdom; `KonvaTagLayer` is stood in for by a
 * clickable div (the same idiom `TagCanvasEditor.clip.test.tsx` and
 * `TagCanvasEditor.polygon.test.tsx` use) since nudging itself is a pure
 * keyboard path that never touches the Konva Transformer. `InspectorPanel`
 * is left UNMOCKED so AC-S2-1's "Inspector X/Y reflect the exact value" and
 * AC-S2-2's step size are asserted against the real control.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    onSelect,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
  }) => <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, false)} />,
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

function shapeLayer(id: string, overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 10,
    y_mm: 10,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
    ...overrides,
  };
}

function groupLayer(id: string, children: string[], overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    ...shapeLayer(id, overrides),
    type: 'group',
    props: { kind: 'group', children },
  };
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers };
}

function selectLayer(id: string) {
  fireEvent.click(screen.getByTestId(`layer-${id}`));
}

function byId(layers: TagLayer[], id: string): TagLayer {
  const found = layers.find((l) => l.id === id);
  if (!found) throw new Error(`no layer ${id}`);
  return found;
}

describe('TagCanvasEditor keyboard nudge (S2, AC-S2-1)', () => {
  it('plain Arrow moves the selection 0.25mm', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(byId(latest, 'l1').x_mm).toBeCloseTo(10.25);
  });

  it('Shift+Arrow moves the selection 1mm', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowRight', shiftKey: true });

    expect(byId(latest, 'l1').x_mm).toBeCloseTo(11);
  });

  it('Alt/Option+Arrow moves the selection 0.1mm', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowRight', altKey: true });

    expect(byId(latest, 'l1').x_mm).toBeCloseTo(10.1);
  });

  it('ArrowUp/Down move Y by the same step sizes', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1'))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(byId(latest, 'l1').y_mm).toBeCloseTo(10.25);

    fireEvent.keyDown(window, { key: 'ArrowUp', shiftKey: true });
    expect(byId(latest, 'l1').y_mm).toBeCloseTo(9.25);
  });

  it('the Inspector X/Y reflect the exact nudged value', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(screen.getByLabelText('X (mm)')).toHaveValue(10.25);

    fireEvent.keyDown(window, { key: 'ArrowRight', shiftKey: true });
    expect(screen.getByLabelText('X (mm)')).toHaveValue(11.25);

    fireEvent.keyDown(window, { key: 'ArrowRight', altKey: true });
    expect(screen.getByLabelText('X (mm)')).toHaveValue(11.35);
  });
});

describe('TagCanvasEditor Inspector step sizes (S2, AC-S2-2)', () => {
  it('X/Y/W/H spinners step 0.25mm; Rotation stays at 1', () => {
    render(<TagCanvasEditor doc={docWith(shapeLayer('l1'))} onChange={vi.fn()} />);
    selectLayer('l1');

    expect(screen.getByLabelText('X (mm)')).toHaveAttribute('step', '0.25');
    expect(screen.getByLabelText('Y (mm)')).toHaveAttribute('step', '0.25');
    expect(screen.getByLabelText('W (mm)')).toHaveAttribute('step', '0.25');
    expect(screen.getByLabelText('H (mm)')).toHaveAttribute('step', '0.25');
    expect(screen.getByLabelText('Rotation')).toHaveAttribute('step', '1');
  });
});

describe('TagCanvasEditor nudge and locking/grouping (S2, AC-S2-3)', () => {
  it('a locked layer does not move', () => {
    let latest: TagLayer[] = [];
    render(
      <TagCanvasEditor
        doc={docWith(shapeLayer('l1', { locked: true }))}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('l1');

    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(byId(latest, 'l1').x_mm).toBe(10);
  });

  it('a group moves once with its children - each child by the same single delta', () => {
    let latest: TagLayer[] = [];
    const child = shapeLayer('child', { x_mm: 12, y_mm: 12, width_mm: 6, height_mm: 6 });
    const group = groupLayer('grp', ['child'], { x_mm: 10, y_mm: 10, width_mm: 20, height_mm: 20 });
    render(
      <TagCanvasEditor
        doc={docWith(child, group)}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          latest = layers;
        }}
      />,
    );
    selectLayer('grp');

    fireEvent.keyDown(window, { key: 'ArrowRight' });

    expect(byId(latest, 'grp').x_mm).toBeCloseTo(10.25);
    expect(byId(latest, 'child').x_mm).toBeCloseTo(12.25);
  });
});
