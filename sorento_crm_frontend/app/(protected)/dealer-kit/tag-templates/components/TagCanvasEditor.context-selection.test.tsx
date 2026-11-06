/**
 * DESIGNER-RICH-TEXT owner bug (6 Nov): multi-select two text boxes, right-click one to Group.
 * The right-click replaced the selection with the frame (a full-tag shape drawn ON TOP, transparent
 * inside, so a left click reaches the text but the right-click hit test landed on the frame), and
 * Group stayed disabled.
 *
 * Rule: right-click on ANY layer that is already part of the selection keeps the whole selection
 * and the menu acts on it; on an unselected layer it selects just that one (the layer Konva
 * actually hit, when it reports one); on empty canvas it keeps the selection. On macOS the menu
 * writes shortcuts with the command symbol, and Cmd+G groups.
 *
 * Written test-FIRST. Stand-ins as in `TagCanvasEditor.context-menu.test.tsx`; the layer stand-in
 * reports an additive select on click (the additive rule itself is `canvas-input.test.ts`).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps, defaultTextProps } from '@/lib/dealer-kit/tag-template-types';
import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';

/** What Konva's own hit test reports for a point: set per test, null = nothing. */
let konvaHit: string | null = null;

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: ({
      children,
      ref,
    }: {
      children?: React.ReactNode;
      ref?: React.Ref<unknown>;
    }) => {
      const instance = {
        getContent: () => document.createElement('div'),
        getIntersection: () =>
          konvaHit ? { id: () => konvaHit as string, getParent: () => null } : null,
      };
      if (typeof ref === 'function') ref(instance);
      else if (ref && 'current' in (ref as { current: unknown })) {
        (ref as { current: unknown }).current = instance;
      }
      return <div data-konva="stage">{children}</div>;
    },
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
  }) => <div data-testid={`layer-${layer.id}`} onClick={() => onSelect?.(layer.id, true)} />,
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

function text(id: string, x: number, z: number): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: x,
    y_mm: 5,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: z,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: id },
  } as TagLayer;
}

/** The whole tag, drawn on top of everything (an outline frame). */
function frame(): TagLayer {
  return {
    id: 'frame',
    type: 'shape',
    x_mm: 0,
    y_mm: 0,
    width_mm: 80,
    height_mm: 60,
    rotation_deg: 0,
    z_index: 9,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

function doc(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 80, height_mm: 60, layers };
}

const px = (mm: number) => mm * CANVAS_PX_PER_MM;
const INSIDE_A = { clientX: px(10), clientY: px(10) };
const INSIDE_C = { clientX: px(70), clientY: px(40) };
const EMPTY = { clientX: 500, clientY: 500 };

function rightClick(container: HTMLElement, point: { clientX: number; clientY: number }) {
  const host = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(host, point);
}

function groupItem() {
  return screen.getByRole('menuitem', { name: /^Group/ });
}

const isDisabled = (el: HTMLElement) =>
  el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('data-disabled');

function setPlatform(value: string) {
  Object.defineProperty(window.navigator, 'platform', { value, configurable: true });
}

afterEach(() => {
  konvaHit = null;
  setPlatform('');
});

describe('right-click keeps a multi-selection (owner bug, 6 Nov)', () => {
  it('right-click on a selected text box under the frame keeps both selected: Group is enabled', () => {
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2), frame())} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));

    rightClick(container, INSIDE_A);

    expect(isDisabled(groupItem())).toBe(false);
  });

  it('Konva reports the text it hit: still kept', () => {
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2), frame())} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));
    konvaHit = 'a';

    rightClick(container, INSIDE_A);

    expect(isDisabled(groupItem())).toBe(false);
  });

  it('right-click on an UNSELECTED layer selects just it: Group is disabled', () => {
    const c = { ...text('c', 60, 3), y_mm: 35 };
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2), c)} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));

    rightClick(container, INSIDE_C);

    expect(isDisabled(groupItem())).toBe(true);
  });

  it('an unselected text under the frame: the layer Konva hit is selected, not the frame', () => {
    const onLayersChange = vi.fn();
    const { container } = render(
      <TagCanvasEditor
        doc={doc(text('a', 5, 1), text('b', 40, 2), frame())}
        onChange={vi.fn()}
        onLayersChange={onLayersChange}
      />,
    );
    konvaHit = 'a';
    rightClick(container, INSIDE_A);
    // The frame and the text share one menu, so read the selection off what Bring to Front moves.
    fireEvent.click(screen.getByRole('menuitem', { name: /Bring to Front/ }));
    const last = onLayersChange.mock.calls.at(-1)![0] as TagLayer[];
    const z = (id: string) => last.find((l) => l.id === id)!.z_index;
    expect(z('a')).toBeGreaterThan(z('frame'));
  });

  it('right-click on empty canvas keeps the selection', () => {
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2))} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));

    rightClick(container, EMPTY);
    rightClick(container, INSIDE_A);

    expect(isDisabled(groupItem())).toBe(false);
  });

  it('Cmd+G groups a multi-selection on macOS', () => {
    setPlatform('MacIntel');
    const onLayersChange = vi.fn();
    render(
      <TagCanvasEditor
        doc={doc(text('a', 5, 1), text('b', 40, 2))}
        onChange={vi.fn()}
        onLayersChange={onLayersChange}
      />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));

    fireEvent.keyDown(window, { key: 'g', metaKey: true });

    const last = onLayersChange.mock.calls.at(-1)![0] as TagLayer[];
    const group = last.find((l) => l.props.kind === 'group');
    expect(group).toBeDefined();
    expect(group!.props.kind === 'group' && [...group!.props.children].sort()).toEqual(['a', 'b']);
  });
});

describe('menu shortcut labels', () => {
  it('macOS shows the command symbol', () => {
    setPlatform('MacIntel');
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2))} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));
    rightClick(container, INSIDE_A);

    expect(groupItem()).toHaveTextContent('⌘G');
    expect(screen.getByRole('menuitem', { name: /^Copy/ })).toHaveTextContent('⌘C');
    expect(screen.queryByText(/Ctrl\+/)).toBeNull();
  });

  it('elsewhere shows Ctrl+', () => {
    setPlatform('Win32');
    const { container } = render(
      <TagCanvasEditor doc={doc(text('a', 5, 1), text('b', 40, 2))} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.click(screen.getByTestId('layer-b'));
    rightClick(container, INSIDE_A);

    expect(groupItem()).toHaveTextContent('Ctrl+G');
  });
});
